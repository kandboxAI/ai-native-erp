"""PaddleOCR-VL 云文档解析：Markdown、版面、图片与原始响应一起保留。"""

import hashlib
import ipaddress
import json
import math
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from .config import settings
from .observability import cloud_request, error_metadata, event, safe_id, safe_text

RESOURCE_LIMIT = 20 * 1024 * 1024
DOCUMENT_RESOURCE_LIMIT = 128 * 1024 * 1024
# 首次提交失败后，最多重试三次，总退避时间为 56 秒。
SUBMIT_RETRY_DELAYS = (8, 16, 32)


class PaddleAPIError(ValueError):
    def __init__(self, response: httpx.Response, payload: dict):
        self.code = payload.get("code")
        self.status_code = response.status_code
        trace = payload.get("traceId")
        self.trace_id = safe_id(trace)
        # 只呈现已知业务含义和安全标识，不将任意响应体、Token 或资源 URL 写入提示。
        reason = "PaddleOCR 任务提交队列已满，请稍后重试" if self.code == 10010 else "PaddleOCR 请求被拒绝"
        detail = f"HTTP {self.status_code}，code {self.code if isinstance(self.code, int) else '未知'}"
        if self.trace_id:
            detail += f"，traceId {self.trace_id}"
        super().__init__(f"{reason}（{detail}）")


def api_data(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise ValueError("PaddleOCR 云服务返回的内容不是 JSON") from None
    if isinstance(payload, dict) and payload.get("code", 0) != 0:
        raise PaddleAPIError(response, payload)
    response.raise_for_status()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ValueError("PaddleOCR 云服务返回业务错误或缺少 data")
    return payload["data"]


def submit_document(
    client: httpx.Client,
    jobs_url: str,
    headers: dict,
    source: dict,
    model: str,
    deadline: float,
    progress: Callable[[str], None] | None,
) -> dict:
    # 仅重试服务端明确拒收的队列满；网络超时可能已创建远端任务，不能盲目重复提交。
    options = {"useDocOrientationClassify": False, "useDocUnwarping": False, "useChartRecognition": False}
    for attempt in range(len(SUBMIT_RETRY_DELAYS) + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("PaddleOCR 总处理时间已超过配置")
        try:
            with Path(source["path"]).open("rb") as pdf:
                return api_data(
                    cloud_request(
                        client,
                        "POST",
                        jobs_url,
                        stage="ocr.submit",
                        fields={
                            "file_id": source.get("id"),
                            "model": model,
                            "attempt": attempt + 1,
                            "upload_bytes": Path(source["path"]).stat().st_size,
                            "options": options,
                        },
                        headers=headers,
                        timeout=min(45, remaining),
                        data={
                            "model": model,
                            "optionalPayload": json.dumps(options),
                        },
                        files={"file": (source["name"], pdf, "application/pdf")},
                    )
                )
        except PaddleAPIError as error:
            if error.code != 10010:
                raise
            if attempt == len(SUBMIT_RETRY_DELAYS):
                event("ocr.submit_exhausted", level="ERROR", attempts=attempt + 1, **error_metadata(error))
                raise ValueError(f"{error}；已提交 {attempt + 1} 次，请稍后重新解析。") from error
            delay = SUBMIT_RETRY_DELAYS[attempt]
            if time.monotonic() + delay >= deadline:
                raise ValueError(f"{error}；已达到总等待时限，请稍后重新解析。") from error
            if progress:
                progress(
                    f"PaddleOCR 云端队列已满，{delay} 秒后重试（{attempt + 1}/{len(SUBMIT_RETRY_DELAYS)}）"
                )
            event(
                "ocr.submit_retry", level="WARNING", attempt=attempt + 1, delay_seconds=delay, code=error.code
            )
            time.sleep(delay)
    raise AssertionError("未处理的提交状态")


def validate_resource_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("OCR 资源必须来自 HTTPS 下载地址")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("OCR 资源地址不能指向本地服务")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("OCR 资源地址不能指向私有网络")


def download_resource(client: httpx.Client, url: str, deadline: float, limit: int) -> bytes:
    validate_resource_url(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("PaddleOCR 总处理时间已超过配置")
    content = bytearray()
    started = time.monotonic()
    event("ocr.resource_download", host=urlparse(url).hostname, limit_bytes=limit)
    # 不携带 Token 下载结果资源，也不自动跟随到未知重定向目标。
    try:
        with client.stream("GET", url, timeout=min(45, remaining)) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("OCR 资源下载返回了重定向，请检查云服务配置")
            for chunk in response.iter_bytes():
                if time.monotonic() >= deadline:
                    raise ValueError("PaddleOCR 资源下载超时")
                content.extend(chunk)
                if len(content) > limit:
                    raise ValueError("OCR 返回资源超过大小限制")
    except (httpx.HTTPError, ValueError) as error:
        event("ocr.resource_failed", level="ERROR", **error_metadata(error))
        raise
    event("ocr.resource_saved", bytes=len(content), elapsed_ms=round((time.monotonic() - started) * 1000))
    return bytes(content)


def normalize_bbox(raw: list, width: float, height: float) -> list[float] | None:
    if len(raw) == 4 and all(isinstance(value, (int, float)) for value in raw):
        x0, y0, x1, y1 = raw
    elif len(raw) >= 3 and all(isinstance(point, list) and len(point) == 2 for point in raw):
        x0, y0 = min(point[0] for point in raw), min(point[1] for point in raw)
        x1, y1 = max(point[0] for point in raw), max(point[1] for point in raw)
    else:
        return None
    bbox = [x0 / width, y0 / height, x1 / width, y1 / height]
    if not all(math.isfinite(value) for value in bbox):
        return None
    if not (0 <= bbox[0] < bbox[2] <= 1.01 and 0 <= bbox[1] < bbox[3] <= 1.01):
        return None
    return [min(1, value) for value in bbox]


def normalize_layout(pruned: dict, prefix: str, dimensions: dict | None = None) -> tuple[list, list]:
    dimensions = dimensions or {}
    width = pruned.get("width") or dimensions.get("width")
    height = pruned.get("height") or dimensions.get("height")
    valid_size = all(
        isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in (width, height)
    )
    blocks, warnings = [], []
    for index, block in enumerate(pruned.get("parsing_res_list", [])):
        raw_bbox = block.get("block_bbox")
        bbox = normalize_bbox(raw_bbox, width, height) if valid_size and isinstance(raw_bbox, list) else None
        blocks.append(
            {
                "id": f"{prefix}-b{index}",
                "label": block.get("block_label", "unknown"),
                "text": str(block.get("block_content", "")),
                "order": block.get("block_order", index),
                "bbox": bbox,
                "raw_bbox": raw_bbox,
                "source": "PaddleOCR-VL 版面区域",
            }
        )
        if bbox is None:
            warnings.append(f"版面块 {index + 1} 缺少可靠的坐标或画布尺寸，已保留内容但不生成定位框。")
    return blocks, warnings


def persist_layout_page(
    item: dict,
    page: dict,
    output: Path,
    prefix: str,
    client: httpx.Client,
    deadline: float,
    budget: list[int],
    dimensions: dict | None = None,
) -> list[str]:
    markdown = item.get("markdown")
    pruned = item.get("prunedResult")
    if (
        not isinstance(markdown, dict)
        or not isinstance(markdown.get("text"), str)
        or not isinstance(pruned, dict)
    ):
        raise ValueError("文档解析结果缺少 markdown.text 或 prunedResult")
    blocks, warnings = normalize_layout(pruned, prefix, dimensions)
    page["ocr_blocks"] = blocks
    page["ocr_markdown_original"] = markdown["text"]
    page["ocr_text"] = "\n".join(block["text"] for block in blocks)
    page["ocr_result_file"] = f"{prefix}-layout.json"
    (output / page["ocr_result_file"]).write_text(json.dumps(pruned, ensure_ascii=False), encoding="utf-8")
    local_markdown = markdown["text"]
    assets = []
    resources = [("markdown", key, url) for key, url in (markdown.get("images") or {}).items()]
    resources += [("output", key, url) for key, url in (item.get("outputImages") or {}).items()]
    for index, (role, key, url) in enumerate(resources):
        if index >= 100:
            warnings.append("当前页图片超过 100 张，其余图片未下载。")
            break
        asset = {"key": key, "role": role}
        try:
            remaining = DOCUMENT_RESOURCE_LIMIT - budget[0]
            if remaining <= 0:
                raise ValueError("当前文档关联图片超过总大小限制")
            content = download_resource(client, url, deadline, min(RESOURCE_LIMIT, remaining))
            budget[0] += len(content)
            with Image.open(BytesIO(content)) as image:
                extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}.get(image.format)
                if not extension:
                    raise ValueError("OCR 资源不是支持的图片格式")
                image.verify()
            # 不使用远端 key 作为路径，避免 ../、绝对路径和同名图片覆盖。
            digest = hashlib.sha256(content).hexdigest()[:12]
            filename = f"{prefix}-{role}-{index}-{digest}.{extension}"
            (output / filename).write_bytes(content)
            asset["asset"] = filename
            if role == "markdown":
                local_markdown = local_markdown.replace(key, filename)
        except (httpx.HTTPError, ValueError, OSError) as error:
            asset["error"] = "图片下载失败或格式不受支持"
            warnings.append(f"关联图片 {index + 1} 未保存：{type(error).__name__}。")
            event(
                "ocr.asset_failed", level="WARNING", page=page["number"], role=role, **error_metadata(error)
            )
        assets.append(asset)
    page["ocr_assets"] = assets
    page["ocr_markdown"] = local_markdown
    page["ocr_markdown_file"] = f"{prefix}.md"
    (output / page["ocr_markdown_file"]).write_text(local_markdown, encoding="utf-8")
    event(
        "ocr.page_saved",
        page=page["number"],
        blocks=len(blocks),
        assets=len(assets),
        markdown_chars=len(local_markdown),
        missing_boxes=sum(block["bbox"] is None for block in blocks),
        warning_count=len(warnings),
    )
    return warnings


def cloud_ocr(
    analysis: dict,
    output: Path,
    source_files: list[dict],
    progress: Callable[[str], None] | None = None,
) -> dict:
    config = settings()
    headers = {"Authorization": "Bearer " + config.paddleocr_access_token.get_secret_value()}
    jobs_url = config.paddleocr_base_url.rstrip("/") + "/api/v2/ocr/jobs"
    deadline = time.monotonic() + config.paddleocr_poll_timeout
    sources = {record["id"]: record for record in source_files}
    documents = analysis["documents"]
    if not documents:
        raise ValueError("云文档解析需要 PDF 文件")
    summary = {
        "model": config.paddleocr_model,
        "job_ids": [],
        "raw_files": [],
        "processed_pages": 0,
        "warnings": [],
    }
    budget = [0]
    # 先记录摘要，即便后续某页失败，已生成的 Markdown 和原始结果仍可查看与下载。
    analysis["ocr"] = summary
    event(
        "ocr.started",
        model=config.paddleocr_model,
        documents=len(documents),
        timeout_seconds=config.paddleocr_poll_timeout,
    )
    with httpx.Client(timeout=httpx.Timeout(45, connect=10)) as client:
        for document in documents:
            source = sources[document["file_id"]]
            data = submit_document(
                client, jobs_url, headers, source, config.paddleocr_model, deadline, progress
            )
            job_id = str(data["jobId"])
            summary["job_ids"].append(job_id)
            event("ocr.accepted", remote_job_id=job_id, file_id=document["file_id"])
            if progress:
                progress("PaddleOCR 已接收文档，等待云端解析")
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("PaddleOCR 总等待时间已超过配置")
                status = api_data(
                    cloud_request(
                        client,
                        "GET",
                        f"{jobs_url}/{job_id}",
                        stage="ocr.poll",
                        fields={"remote_job_id": job_id},
                        headers=headers,
                        timeout=min(45, remaining),
                    )
                )
                progress_info = status.get("extractProgress") or {}
                event(
                    "ocr.poll",
                    remote_job_id=job_id,
                    state=safe_id(status.get("state")),
                    total_pages=progress_info.get("totalPages"),
                    extracted_pages=progress_info.get("extractedPages"),
                )
                if status["state"] == "failed":
                    event(
                        "ocr.remote_failed",
                        level="ERROR",
                        remote_job_id=job_id,
                        remote_message=safe_text(status.get("errorMsg", "未知原因")),
                    )
                    raise ValueError("PaddleOCR 远端任务失败，请检查服务控制台")
                if status["state"] == "done":
                    break
                if status["state"] not in ("running", "pending"):
                    raise ValueError("PaddleOCR 返回未知任务状态")
                time.sleep(min(2, max(0, deadline - time.monotonic())))
            raw = download_resource(client, status["resultUrl"]["jsonUrl"], deadline, RESOURCE_LIMIT)
            raw_name = f"ocr-{document['file_id']}-raw.jsonl"
            (output / raw_name).write_bytes(raw)
            summary["raw_files"].append(raw_name)
            lines = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
            results, metadata = [], []
            for line in lines:
                result = line["result"]
                if not isinstance(result.get("layoutParsingResults"), list):
                    raise ValueError("服务未返回 layoutParsingResults，请使用 PaddleOCR-VL 文档解析模型")
                results.extend(result["layoutParsingResults"])
                metadata.extend(result.get("dataInfo", {}).get("pages", []))
            if len(results) != len(document["pages"]):
                raise ValueError("云端与原始 PDF 页数不一致，停止绑定，避免证据错页")
            for index, (item, page) in enumerate(zip(results, document["pages"], strict=True)):
                prefix = f"ocr-{document['file_id']}-p{page['number']}"
                warnings = persist_layout_page(
                    item,
                    page,
                    output,
                    prefix,
                    client,
                    deadline,
                    budget,
                    metadata[index] if index < len(metadata) else None,
                )
                summary["warnings"].extend(f"第 {page['number']} 页：{warning}" for warning in warnings)
                summary["processed_pages"] += 1
    return summary
