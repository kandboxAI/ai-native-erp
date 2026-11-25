"""按文件选择解析链路，填入可编辑初稿；人工计价参数始终保留。"""

import re

from pydantic import ValidationError

from .schemas import AnalysisRequest, Operation, Specs


def analysis_plan(kinds: set[str], request: AnalysisRequest, config) -> dict:
    if request.mode == "local":
        return {"use_ai": False, "use_ocr": False}
    if not request.cloud_allowed:
        raise ValueError("自动解析会调用已配置的云服务，请确认允许发送本次图纸或模型几何摘要")
    if not config.ai_api_key.get_secret_value():
        raise ValueError("请先配置 DeepSeek API Key；自动解析需要生成制造要求与工艺初稿")
    has_pdf = "pdf" in kinds
    if has_pdf and not config.paddleocr_access_token.get_secret_value():
        raise ValueError("PDF 自动解析需要配置 PaddleOCR Access Token")
    return {"use_ai": True, "use_ocr": has_pdf}


def apply_draft(
    specs: dict,
    operations: list[dict],
    analysis: dict,
    job_id: str,
    quantity: int = 1,
) -> tuple[dict, list, dict]:
    updated = Specs.model_validate(specs).model_dump(mode="json")
    summary = {
        "filled_fields": [],
        "review_fields": [],
        "added_operations": 0,
        "preserved_operations": len(operations),
    }
    facts = analysis.get("ai", {}).get("facts", [])
    for key in ("material", "treatment", "hardness", "tolerance", "notes"):
        if str(updated.get(key, "")).strip():
            continue
        fact_key = "requirement" if key == "notes" else key
        values = list(dict.fromkeys(fact["value"].strip() for fact in facts if fact["key"] == fact_key))
        if not values:
            continue
        value = "；".join(values)
        if key in ("treatment", "hardness") and re.search(r"N\s*/\s*A", value, re.IGNORECASE):
            source_text = "\n".join(
                page.get("ocr_text", "") + "\n" + page.get("text", "")
                for doc in analysis.get("documents", [])
                for page in doc["pages"]
            )
            if not re.search(r"N\s*/\s*A", source_text, re.IGNORECASE):
                # 防止模型把空白栏改写成 N/A；缺少文字佐证时保留建议，交由人工复核。
                summary["review_fields"].append(key)
                continue
        # 超长内容留在识别依据，不截断制造要求后强行填入。
        try:
            candidate = Specs.model_validate({**updated, key: value})
        except ValidationError:
            continue
        updated = candidate.model_dump(mode="json")
        summary["filled_fields"].append(key)
    # 有现有工序时保持原表，避免重解析覆盖人工改动、费率或重复追加。
    if not operations and analysis.get("ai", {}).get("planning_status") in (None, "completed", "partial"):
        if any(not item.get("process_id") for item in analysis.get("ai", {}).get("operations", [])):
            raise ValueError("AI 工序未绑定正式工艺，请重新分析后采用")
        operations = [
            Operation(
                name=item["name"],
                process_id=item.get("process_id"),
                process_no_snapshot=item.get("process_no_snapshot"),
                machine=item.get("machine", ""),
                process_type_code=item.get("process_type_code"),
                quote_rule_no=item.get("quote_rule_no"),
                pricing_mode_code=item.get("pricing_mode_code", "hourly"),
                unit_hours=item.get("unit_hours"),
                note=item.get("note", ""),
                estimate_basis=item.get("estimate_basis", ""),
                assumptions=item.get("assumptions", []),
                estimate_quantity=quantity if item.get("unit_hours") is not None else None,
                origin_code="ai",
                source_job_id=job_id,
                evidence_refs=item.get("evidence_refs", []),
                parameter_sources={
                    key: {
                        "kind": "ai_estimate",
                        "rule_name": "模型工时预估（待确认）",
                        "job_id": job_id,
                        "quantity": quantity,
                        "value": str(item[key]),
                    }
                    for key in ("unit_hours",)
                    if item.get(key) is not None
                },
            ).model_dump(mode="json")
            for item in analysis.get("ai", {}).get("operations", [])
        ]
        summary["added_operations"] = len(operations)
    updated["is_requirements_confirmed"] = False
    return updated, operations, summary
