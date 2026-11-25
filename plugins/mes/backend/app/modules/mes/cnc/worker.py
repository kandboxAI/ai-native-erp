"""由 MES 租户定时任务领取持久化解析任务，不额外引入独立数据库或 RQ。"""

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import httpx

from app.auth.plugin_repository import repository as tenants
from app.auth.service import build_authenticated_user
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.db.tenant import require_tenant_schema, use_tenant_schema
from app.framework.tenant_plugins import is_plugin_enabled_for_schema
from app.framework.files.storage import get_storage
from app.modules.file.service import service as files
from .ai import extract_requirements
from .config import ROOT, settings
from .drafts import apply_draft
from .material_ai import select_material
from .material_matching import material_basis
from .observability import event, job_trace, bind_job, error_metadata
from .ocr import cloud_ocr
from .pricing import IncompleteQuote
from .repository import repository as repo, LIST, MANAGE, ANALYZE
from .rules import apply_rules, apply_stock_rule
from .service import service, specs_data, operation_data, SCENE
from ..process_matching import matching_catalog, analysis_matches,canonical_operations


async def current_actor(job, schema):
    async with get_session_context() as session:
        tenant = await tenants.get_tenant_by_schema(session, schema)
    if tenant is None or not tenant.is_active:
        raise AppException("租户已停用", 403)
    user = await build_authenticated_user({"sub": str(job.auth_user_id), "tenant_id": str(tenant.id)})
    if "mes" not in user.enabled_plugin_keys or any(
        key not in user.permissions for key in (LIST, MANAGE, ANALYZE)
    ):
        raise AppException("申请人已失去解析权限", 403)
    return user


def parse_local(manifest_path, output):
    with (output / "parser.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [sys.executable, "-m", "app.modules.mes.cnc.analysis", str(manifest_path)],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=settings().analysis_timeout_seconds,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    return json.loads((output / "result.json").read_text(encoding="utf-8"))


async def mark(identifier, stage, status="running", error=None):
    async with get_session_context() as session:
        job = await repo.job(session, identifier, lock=True)
        if job and job.status_code == "running":
            job.stage, job.status_code, job.error, job.updated_at = stage, status, error, utc_now()
            await session.commit()


async def run_pending():
    schema = require_tenant_schema()
    if not await is_plugin_enabled_for_schema(schema, "mes"):
        return
    async with get_session_context() as session:
        # 已启用的旧版 MES 租户可能尚未升级，沿用其他 MES 任务的就绪检查。
        if not await repo.is_ready(session):
            return
        job = await repo.claim(session)
        if job is None:
            await session.commit()
            return
        config = settings()
        job.status_code, job.stage = "running", "核对权限与原件"
        job.lease_expires_at = utc_now() + timedelta(
            seconds=config.analysis_timeout_seconds
            + config.paddleocr_poll_timeout
            + config.ai_total_timeout
            + 90
            + 300
        )
        job.updated_at = utc_now()
        await session.commit()
    output = config.storage / str(job.part_id) / str(job.id)
    output.mkdir(parents=True, exist_ok=True)
    with job_trace(str(job.id)):
        bind_job(str(job.part_id), output)
        try:
            user = await current_actor(job, schema)
            with use_tenant_schema(schema):
                async with get_session_context() as session:
                    part = await repo.part(session, job.part_id, user, ANALYZE)
                    input_version, quantity, input_specs = part.version_no, part.quantity, specs_data(part)
                    record, rules = await repo.rules(session, user, ANALYZE, org_id=part.org_id)
                    catalogue=await matching_catalog(session,part.org_id,user,ANALYZE) if job.is_use_ai else []
                    if job.is_use_ai:
                        from ..process_matching import validate_rule_bindings
                        validate_rule_bindings(rules, catalogue)
                    originals = {
                        row.id: row for row in await files.list_for_business(session, SCENE, [part.id])
                    }
                    bindings = await repo.files(session, part.id)
                    manifest = {"output": str(output), "files": []}
                    for binding in bindings:
                        original = originals.get(binding.attachment_id)
                        if original is None:
                            raise AppException("图纸原件不可用", 422)
                        content = await get_storage(original.storage_backend).read(
                            original.storage_key, max_bytes=20 * 1024 * 1024
                        )
                        import hashlib

                        if hashlib.sha256(content).hexdigest() != binding.sha256:
                            raise AppException("图纸原件已变化", 409)
                        path = output / (
                            str(binding.id) + (".pdf" if binding.kind_code == "pdf" else ".step")
                        )
                        path.write_bytes(content)
                        manifest["files"].append(
                            {
                                "id": str(binding.id),
                                "name": original.original_file_name,
                                "kind": binding.kind_code,
                                "path": str(path),
                                "size": len(content),
                                "sha256": binding.sha256,
                            }
                        )
                    await session.commit()
                manifest_path = output / "manifest.json"
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                await mark(job.id, "解析图纸与模型几何")
                result = await asyncio.to_thread(parse_local, manifest_path, output)
                result["artifact_job"] = str(job.id)
                if len({Path(item["name"]).stem.lower() for item in manifest["files"]}) > 1:
                    result["warnings"].append("PDF 与 STEP 文件主名不同，请核实零件及修订是否一致。")
                if job.is_use_ocr:
                    await mark(job.id, "解析完整文档、版面与 Markdown")
                    try:
                        result["ocr"] = await asyncio.to_thread(cloud_ocr, result, output, manifest["files"])
                        result["ocr"]["status"] = "completed"
                        result["warnings"].extend(result["ocr"].get("warnings", []))
                    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
                        event("ocr.failed", level="ERROR", **error_metadata(error))
                        ocr = result.setdefault("ocr", {})
                        ocr.update(
                            status="partial" if ocr.get("processed_pages") else "failed",
                            error="文档解析未完成，请核对后重试",
                        )
                if job.is_use_ai:
                    await mark(job.id, "提取制造要求并估算整件工艺")
                    process_rules = [
                        {**item.model_dump(mode="json"), "pricing_mode_code": mode}
                        for mode, group in (
                            ("hourly", rules.processes),
                            ("external", rules.external_processes),
                        )
                        for item in group
                        if item.is_active
                    ]
                    try:
                        # 仅发送已确认的本次图纸、几何和工厂工序定义，不发送人工备注、用户资料或其他业务记录。
                        safe_specs = {
                            key: value
                            for key, value in input_specs.items()
                            if key in {"material", "stock_length", "stock_width", "stock_height"}
                        }
                        result["ai"] = await asyncio.to_thread(
                            extract_requirements,
                            result,
                            output,
                            quantity=quantity,
                            process_rules=process_rules,
                            manufacturing_processes=[dict(row) for row in catalogue],
                            specs=safe_specs,
                        )
                        result["warnings"].extend(result["ai"].get("warnings", []))
                    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
                        event("ai.failed", level="ERROR", **error_metadata(error))
                        result["ai"] = {"status": "failed", "error": "工艺分析未完成，请核对后重试"}
                if job.is_use_ai and rules.is_auto_apply and not input_specs.get("material_rule_no"):
                    candidate, _, _ = apply_draft(input_specs, [], result, str(job.id), quantity)
                    candidate, _ = apply_stock_rule(candidate, result, record.version_no)
                    if candidate.get("density") is None or candidate.get("material_price") is None:
                        await mark(job.id, "AI 选择材料参考规则")
                        try:
                            result["material_selection"] = await asyncio.to_thread(
                                select_material, candidate, rules, record.version_no
                            )
                        except (ValueError, KeyError, httpx.HTTPError) as error:
                            event("ai.material_failed", level="ERROR", **error_metadata(error))
                            result["material_selection"] = {
                                "status": "failed", "basis": material_basis(candidate),
                                "rules_version_no": record.version_no,
                                "reason": "AI 选材未完成，请检查模型配置后重试或人工选择",
                            }
                            result["warnings"].append("AI 选材未完成，可在材料与计价条件中重试或人工选择。")
                # 云调用完成后再次校验实时权限，撤权不能依靠排队时的身份继续写回。
                user = await current_actor(job, schema)
                async with get_session_context() as session:
                    part = await repo.part(session, job.part_id, user, ANALYZE, lock=True)
                    current = await repo.job(session, job.id, lock=True)
                    if current.status_code != "running":
                        return
                    specs = specs_data(part)
                    operations = [operation_data(row) for row in await repo.operations(session, part.id)]
                    if job.is_use_ai:
                        catalogue = await matching_catalog(session, part.org_id, user, ANALYZE,lock=True)
                    if job.is_use_ai and result.get("ai", {}).get("operations"):
                        matches = analysis_matches(result["ai"]["operations"], catalogue)
                        result["process_archive_matches"] = matches
                        if matches["pending_count"]:
                            raise AppException("本次工艺未全部选择有效正式档案，请重新分析后核价",422)
                    if part.version_no != input_version:
                        result["warnings"].append(
                            "解析期间核价输入已修改；本次建议未自动填表，请复核后采用。"
                        )
                    else:
                        if job.is_use_ai:
                            specs, operations, result["draft"] = apply_draft(
                                specs, operations, result, str(job.id), quantity
                            )
                            operations=canonical_operations(operations,catalogue,strict=True)
                        record, rules = await repo.rules(session, user, ANALYZE, org_id=part.org_id)
                        if job.is_use_ai:
                            validate_rule_bindings(rules, catalogue)
                        if rules.is_auto_apply:
                            specs, operations, result["rules"] = apply_rules(
                                specs, operations, result, rules, record.version_no
                            )
                        else:
                            # 毛坯是固定几何规则，不受材料/工序参数自动补齐开关影响。
                            specs, result["stock_rule"] = apply_stock_rule(specs, result, record.version_no)
                        await repo.save_inputs(session, part, specs, operations, user)
                    # 核价前会 flush；先复制，避免之后追加 pricing 时原地修改已刷新的 JSON，导致缺项提示未保存。
                    part.analysis, part.is_requirements_confirmed = dict(result), False
                    part.version_no += 1
                    part.updated_by = user.user_id
                    if (
                        part.version_no == input_version + 1
                        and result.get("ai", {}).get("planning_status") in ("completed", "partial")
                    ):
                        try:
                            await session.flush()
                            quote = await service.make_quote(session, part, user)
                            result["pricing"] = {
                                "status": "completed",
                                "quote_id": str(quote.id),
                                "version_no": part.version_no,
                            }
                        except IncompleteQuote as error:
                            result["pricing"] = {
                                "status": "incomplete",
                                "missing": error.missing,
                                "version_no": part.version_no,
                            }
                    elif job.is_use_ai:
                        result["pricing"] = {
                            "status": "incomplete",
                            "version_no": part.version_no,
                            "missing": ["本次工艺与估时尚未完整采用，请复核识别结果后再核价"],
                        }
                    part.analysis = dict(result)
                    if job.is_use_ai and result.get("ai", {}).get("planning_status") not in ("completed", "partial"):
                        current.status_code = "failed"
                        current.stage = "工艺规划未完成，请重新分析"
                        current.error = "未生成全部选用正式工艺的路线，请检查工艺档案及报价规则后重新分析"
                    elif result.get("ai", {}).get("planning_status") == "partial":
                        current.status_code, current.stage = "completed", "解析完成，已保留可用工序，部分加工要求待补充"
                        current.error = None
                    else:
                        current.status_code, current.stage = "completed", "解析完成，请复核图纸与工艺"
                    current.updated_at = utc_now()
                    await session.commit()
                (output / "analysis.json").write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as error:
            event("analysis.failed", level="ERROR", **error_metadata(error))
            await mark(
                job.id,
                "解析中断，可重新解析",
                "failed",
                "本次解析未完成；已有结果保留，请检查配置及任务日志后重试",
            )
