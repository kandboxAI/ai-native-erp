"""解析链路日志：按任务关联，响应只记录排障字段，不记录图纸及模型正文。"""

import json
import logging
import os
import re
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .config import ROOT, settings

logger = logging.getLogger("cnc.events")
context: ContextVar[dict] = ContextVar("analysis_log_context", default={})


def safe_text(value: object, limit: int = 600) -> str:
    text = str(value)
    config = settings()
    for secret in (config.ai_api_key, config.paddleocr_access_token):
        if key := secret.get_secret_value():
            text = text.replace(key, "[REDACTED]")
    text = re.sub(r"https?://[^\s<>\"']+", "[URL]", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"data:[^\s]+", "[DATA]", text)
    return text[:limit]


def safe_id(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[\w.:-]{1,160}", value) else None


def scrub_fields(value):
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.lower() in {"authorization", "api_key", "access_token", "password"}
            else scrub_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub_fields(item) for item in value]
    return value


def configure_logging(role: str) -> None:
    if logger.handlers:
        return
    directory = ROOT / "storage" / "mes-cnc" / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    # 每个进程一个滚动文件，避免 Windows 多 Worker 争用同一个日志文件。
    handler = RotatingFileHandler(
        directory / f"{role}-{os.getpid()}.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(message)s")
    console = logging.StreamHandler()
    for target in (handler, console):
        target.setFormatter(formatter)
        logger.addHandler(target)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # httpx 的默认 INFO 包含完整 URL；资源下载可能带有签名，统一使用下方的安全摘要。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@contextmanager
def job_trace(job_id: str):
    token = context.set({"job_id": job_id})
    try:
        yield
    finally:
        context.reset(token)


def bind_job(part_id: str, output: Path) -> None:
    context.set({**context.get(), "part_id": part_id, "event_path": output / "events.jsonl"})


def event(name: str, *, level: str = "INFO", **fields) -> None:
    if not logger.handlers:
        configure_logging("process")
    trace = context.get()
    record = {
        "time": datetime.now(UTC).isoformat(),
        "level": level,
        "pid": os.getpid(),
        "event": name,
        **{key: value for key, value in trace.items() if key != "event_path"},
        **fields,
    }
    line = json.dumps(scrub_fields(record), ensure_ascii=False, default=lambda value: safe_text(value))
    logger.log(getattr(logging, level), line)
    if path := trace.get("event_path"):
        # 云请求日志与本地解析产物保存在同一任务目录，旧任务不因再次解析而丢失。
        try:
            with path.open("a", encoding="utf-8") as target:
                target.write(line + "\n")
        except OSError as error:
            logger.error(json.dumps({"event": "log.write_failed", "error_type": type(error).__name__}))


def response_metadata(response: httpx.Response) -> dict:
    result = {"http_status": response.status_code}
    for header in ("x-request-id", "x-trace-id", "request-id"):
        if identifier := safe_id(response.headers.get(header)):
            result["remote_request_id"] = identifier
            break
    try:
        payload = response.json()
    except (ValueError, httpx.ResponseNotRead):
        result["content_type"] = response.headers.get("content-type", "")[:100]
        return result
    if not isinstance(payload, dict):
        return result
    if isinstance(payload.get("code"), (str, int)):
        result["business_code"] = safe_text(payload["code"], 80)
    if trace_id := safe_id(payload.get("traceId")):
        result["trace_id"] = trace_id
    if response.is_error or payload.get("code", 0) != 0 or payload.get("error"):
        detail = payload.get("error")
        detail = detail if isinstance(detail, dict) else payload
        for source, target in (
            ("msg", "remote_message"),
            ("message", "remote_message"),
            ("type", "remote_type"),
        ):
            if isinstance(detail.get(source), str):
                result[target] = safe_text(detail[source])
        if isinstance(detail.get("code"), (str, int)):
            result["remote_code"] = safe_text(detail["code"], 80)
    return result


def error_metadata(error: Exception) -> dict:
    if isinstance(error, ValidationError):
        # Pydantic 默认异常字符串含输入数据，日志和页面均不抄录模型原文。
        message = "结构校验失败：" + "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
            for item in error.errors(include_input=False, include_url=False)[:10]
        )
    else:
        message = safe_text(error)
    result = {"error_type": type(error).__name__, "error_message": message}
    if isinstance(error, httpx.HTTPStatusError):
        result.update(response_metadata(error.response))
    result["stack"] = [
        {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
        for frame in traceback.extract_tb(error.__traceback__)[-10:]
    ]
    return result


def cloud_request(
    client: httpx.Client, method: str, url: str, *, stage: str, fields: dict | None = None, **kwargs
) -> httpx.Response:
    fields = fields or {}
    endpoint = urlsplit(url)
    started = time.monotonic()
    event(
        "cloud.request",
        stage=stage,
        method=method,
        host=endpoint.hostname,
        request_timeout=safe_text(kwargs.get("timeout", client.timeout)),
        **fields,
    )
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        event(
            "cloud.request_failed",
            level="ERROR",
            stage=stage,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            **fields,
            **error_metadata(error),
        )
        raise
    metadata = response_metadata(response)
    failed = response.is_error or metadata.get("business_code", "0") != "0"
    event(
        "cloud.response",
        level="WARNING" if failed else "INFO",
        stage=stage,
        elapsed_ms=round((time.monotonic() - started) * 1000),
        response_bytes=len(response.content),
        **fields,
        **metadata,
    )
    return response
