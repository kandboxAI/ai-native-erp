"""询价业务动作；文件、身份和权限复用底座公开能力。"""

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.framework.files.storage import get_storage
from app.modules.file.service import register_file_access, register_file_scene, service as files
from .artifacts import artifact_path, ocr_artifact_names
from .config import settings
from .drafts import analysis_plan, apply_draft
from .models import CncPart, CncDrawingFile, CncQuote, CncAnalysisJob
from .material_ai import select_material
from .observability import event, error_metadata
from .pricing import calculate_quote, IncompleteQuote
from .process_catalog import process_catalog
from .repository import repository as repo, LIST, MANAGE, ANALYZE, APPROVE, RULES
from .rules import apply_rules, apply_stock_rule, preserve_sources, same_value, model_dimensions
from .schemas import Specs, Operation
from .weight import estimate_weight
from ..process_matching import matching_catalog, analysis_matches,canonical_operations, validate_rule_bindings, archive_category

SCENE = "mes_cnc_drawing"
register_file_scene(
    SCENE,
    kinds={"document", "other"},
    max_bytes=20 * 1024 * 1024,
    max_count=2,
    extra_content_types={"application/step": "step"},
)


def check_version(part, version):
    if part.version_no != version:
        raise AppException("数据已更新，请重新加载后修改", 409)


def specs_data(part):
    return Specs.model_validate({key: getattr(part, key) for key in Specs.model_fields}).model_dump(
        mode="json"
    )


def operation_data(row):
    return Operation.model_validate(
        {
            key: (str(getattr(row, key,None)) if getattr(row, key,None) else None)
            if key in {"id", "source_job_id"}
            else getattr(row, key,None)
            for key in Operation.model_fields
        }
    ).model_dump(mode="json")


def quote_data(quote):
    return {
        "id": str(quote.id),
        "version_no": quote.version_no,
        "result": quote.result_snapshot,
        "approved_by": str(quote.approved_by) if quote.approved_by else None,
        "approved_name_snapshot": quote.approved_name_snapshot,
        "approved_at": quote.approved_at,
        "created_at": quote.created_at,
    }


def artifact_names(analysis):
    names = ocr_artifact_names(analysis)
    for document in analysis.get("documents", []):
        for page in document["pages"]:
            names.add(page["image"])
            names.update(view["image"] for view in page.get("detail_views", []))
    if analysis.get("geometry"):
        names.add(analysis["geometry"]["mesh"])
    return names


class CncService:
    async def process_options(self,identifier,user):
        async with get_session_context() as session:
            part=await repo.part(session,identifier,user,LIST)
            return [dict(row) for row in await matching_catalog(session,part.org_id,user,LIST)]

    async def part_data(self, session, part, *, detail=True):
        job = await repo.jobs(session, part.id)
        data = {
            "id": str(part.id),
            "org_id": str(part.org_id),
            "name": part.name,
            "quantity": part.quantity,
            "version_no": part.version_no,
            "created_at": part.created_at,
            "deleted_at": part.deleted_at,
            "job": {
                "id": str(job.id),
                "status_code": job.status_code,
                "stage": job.stage,
                "error": job.error,
                "updated_at": job.updated_at,
            }
            if job
            else None,
        }
        if detail:
            operations = [operation_data(row) for row in await repo.operations(session, part.id)]
            bindings = await repo.files(session, part.id)
            originals = {row.id: row for row in await files.list_for_business(session, SCENE, [part.id])}
            history = await repo.quotes(session, part.id)
            current = history[0] if history and history[0].version_no == part.version_no else None
            data.update(
                specs=specs_data(part),
                operations=operations,
                analysis=part.analysis,
                model_dimensions=model_dimensions(part.analysis),
                weight_estimate=estimate_weight(Specs.model_validate(specs_data(part)), part.quantity, part.analysis.get("geometry")),
                files=[
                    {
                        "id": str(row.id),
                        "name": originals[row.attachment_id].original_file_name,
                        "kind": row.kind_code,
                        "size": originals[row.attachment_id].file_size,
                        "sha256": row.sha256,
                    }
                    for row in bindings
                    if row.attachment_id in originals
                ],
                quote=quote_data(current) if current else None,
                quote_history=[quote_data(row) for row in history],
            )
        return data

    async def listing(self, user, deleted=False, search="", page=1, page_size=200):
        async with get_session_context() as session:
            return [
                await self.part_data(session, row, detail=False)
                for row in await repo.parts(session, user, deleted, search, page, page_size)
            ]

    async def detail(self, identifier, user, *, status_only=False):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user)
            return await self.part_data(session, part, detail=not status_only)

    async def create(self, uploads, name, quantity, user):
        org_id = resolve_write_org_id(user, None, MANAGE)
        if not 1 <= quantity <= 1000000 or not 1 <= len(uploads) <= 2:
            raise AppException("数量须为正整数；上传一份 PDF 和/或一份 STEP", 422)
        prepared, kinds = [], set()
        for upload in uploads:
            filename = Path(upload.filename or "").name[:200]
            extension = Path(filename).suffix.lower()
            kind = "pdf" if extension == ".pdf" else "step" if extension in {".step", ".stp"} else None
            if kind is None or kind in kinds:
                raise AppException("仅支持一份 PDF 和一份 STEP/STP", 422)
            content = await upload.read(20 * 1024 * 1024 + 1)
            if not content or len(content) > 20 * 1024 * 1024:
                raise AppException("单份文件不能为空，且不得超过 20 MB", 422)
            if (kind == "pdf" and not content.startswith(b"%PDF-")) or (
                kind == "step" and b"ISO-10303-21" not in content[:256]
            ):
                raise AppException("文件内容与扩展名不符", 422)
            kinds.add(kind)
            prepared.append((filename, kind, content))
        tickets = []
        try:
            for filename, kind, content in prepared:
                tickets.append(
                    await files.upload_bytes(
                        scene_code=SCENE,
                        file_name=filename,
                        content_type="application/pdf" if kind == "pdf" else "application/step",
                        content=content,
                        user=user,
                    )
                )
            async with get_session_context() as session:
                part = CncPart(
                    org_id=org_id,
                    name=(name.strip() or Path(prepared[0][0]).stem)[:200],
                    quantity=quantity,
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
                repo.add(session, part)
                await session.flush()
                await files.bind(
                    session,
                    [UUID(ticket["id"]) for ticket in tickets],
                    user=user,
                    org_id=org_id,
                    scene_code=SCENE,
                    business_type_code=SCENE,
                    business_id=part.id,
                )
                for ticket, (_, kind, content) in zip(tickets, prepared, strict=True):
                    repo.add(
                        session,
                        CncDrawingFile(
                            part_id=part.id,
                            org_id=org_id,
                            attachment_id=UUID(ticket["id"]),
                            kind_code=kind,
                            sha256=hashlib.sha256(content).hexdigest(),
                            created_by=user.user_id,
                            updated_by=user.user_id,
                        ),
                    )
                await session.flush()
                data = await self.part_data(session, part)
                await session.commit()
                return data
        except Exception:
            for ticket in tickets:
                await files.discard(UUID(ticket["id"]), user)
            raise

    async def edit(self, identifier, body, user):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, MANAGE, lock=True)
            check_version(part, body.version_no)
            old = specs_data(part)
            edited = body.specs.model_dump(mode="json")
            if edited["material"] != old["material"] and edited.get("material_rule_no") == old.get(
                "material_rule_no"
            ):
                edited["material_rule_no"] = None
                for key in ("density", "material_price"):
                    if key in old.get("parameter_sources", {}) and same_value(edited.get(key), old.get(key)):
                        edited[key] = None
                if edited["material_price"] is None:
                    edited["material_price_unit_code"] = "kg"
            specs = preserve_sources(
                old, edited, basis_fields=("material", "material_rule_no", "material_price_unit_code")
            )
            previous = {str(row.id): operation_data(row) for row in await repo.operations(session, part.id)}
            operations = [
                preserve_sources(
                    previous.get(item.id, {}),
                    item.model_dump(mode="json"),
                    basis_fields=(
                        "name",
                        "process_id",
                        "machine",
                        "process_type_code",
                        "pricing_mode_code",
                        "quote_rule_no",
                    ),
                )
                for item in body.operations
            ]
            operations=canonical_operations(operations,await matching_catalog(session,part.org_id,user,MANAGE,lock=True),strict=True)
            part.name, part.quantity = body.name.strip(), body.quantity
            if not part.name:
                raise AppException("零件名称不能为空", 422)
            await repo.save_inputs(session, part, specs, operations, user)
            part.version_no += 1
            await session.commit()
            return await self.part_data(session, part)

    async def delete_or_restore(self, identifier, user, *, version=None, restore=False):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, MANAGE, lock=True, deleted=restore)
            if restore:
                if part.deleted_at is None:
                    raise AppException("零件已经恢复", 409)
                part.deleted_at = part.deleted_by = None
                part.is_requirements_confirmed = False
            else:
                check_version(part, version)
                if await repo.active(session, part.id):
                    raise AppException("解析任务结束后才能删除零件", 409)
                part.deleted_at, part.deleted_by = utc_now(), user.user_id
            part.version_no += 1
            part.updated_by = user.user_id
            await session.commit()
            return await self.part_data(session, part, detail=False)

    async def rules(self, user, body=None, org_id=None):
        async with get_session_context() as session:
            row, config = await repo.rules(
                session, user, RULES if body else LIST, lock=body is not None, org_id=org_id
            )
            catalogue = await matching_catalog(session, row.org_id, user, RULES if body else LIST, lock=body is not None)
            if body:
                check_version(row, body.version_no)
                validate_rule_bindings(body.config, catalogue)
                archives = {str(p["id"]): p for p in catalogue}
                for group in (body.config.processes, body.config.external_processes):
                    for rule in group:
                        rule.name = archives[str(rule.process_id)]["process_name"]
                for rule in body.config.processes:
                    rule.process_type_code = archive_category(rule.name)
                await repo.save_rules(session, row, body.config, user)
                row.version_no += 1
                config = body.config
            await session.commit()
            return {
                "version_no": row.version_no,
                "config": config.model_dump(mode="json"),
                "process_catalog": process_catalog(),
                "manufacturing_processes": [dict(id=str(p["id"]), process_no=p["process_no"],
                    process_name=p["process_name"], processing_type_code=p["processing_type_code"],
                    process_type_code=archive_category(p["process_name"])) for p in catalogue],
            }

    async def fill_rules(self, identifier, body, user, *, adopt=False):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, MANAGE, lock=True)
            check_version(part, body.version_no)
            record, config = await repo.rules(session, user, MANAGE, org_id=part.org_id)
            operations = [operation_data(row) for row in await repo.operations(session, part.id)]
            specs = specs_data(part)
            if adopt:
                if await repo.active(session, part.id):
                    raise AppException("请等待解析完成后再采用工艺", 409)
                ai = part.analysis.get("ai", {})
                if (
                    ai.get("planning_status") not in ("completed", "partial")
                    or not ai.get("operations")
                    or ai.get("estimate_quantity") != part.quantity
                ):
                    raise AppException("尚无可用工艺建议或数量已变化，请重新解析", 422)
                if any(not item.get("process_id") for item in ai["operations"]):
                    raise AppException("旧工艺建议未从正式工艺档案选择，请重新分析后采用",422)
                specs, operations, draft = apply_draft(
                    specs, [], part.analysis, part.analysis["artifact_job"], part.quantity
                )
            else:
                check_version(record, body.rules_version_no)
            catalogue=await matching_catalog(session,part.org_id,user,MANAGE,lock=True)
            operations=canonical_operations(operations,catalogue,strict=True,require_selected=adopt)
            if not adopt and body.is_stock_only:
                specs, summary = apply_stock_rule(specs, part.analysis, record.version_no)
                summary.update(unmatched_operations=[], material_match={"status": "not_requested"})
            else:
                validate_rule_bindings(config, catalogue)
                specs, operations, summary = apply_rules(
                    specs, operations, part.analysis, config, record.version_no
                )
            if adopt or summary["filled"]:
                specs["is_requirements_confirmed"] = False
                await repo.save_inputs(session, part, specs, operations, user)
                part.version_no += 1
            if adopt:
                matches = analysis_matches(operations, catalogue)
                part.analysis = {**part.analysis, "draft": draft, "rules": summary, "process_archive_matches": matches}
                try:
                    await session.flush()
                    quote = await self.make_quote(session, part, user)
                    pricing = {
                        "status": "completed",
                        "quote_id": str(quote.id),
                        "version_no": part.version_no,
                    }
                except IncompleteQuote as error:
                    pricing = {
                        "status": "incomplete",
                        "missing": error.missing,
                        "version_no": part.version_no,
                    }
                part.analysis = {**part.analysis, "pricing": pricing}
            await session.commit()
            data = await self.part_data(session, part)
            return data if adopt else {"part": data, "summary": summary}

    async def select_material(self, identifier, body, user):
        if not body.cloud_allowed:
            raise AppException("请确认允许发送本零件牌号、状态、毛坯尺寸及当前组织材料规则用于 AI 选材", 422)
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, ANALYZE)
            await repo.part(session, identifier, user, MANAGE)
            check_version(part, body.version_no)
            if await repo.active(session, part.id):
                raise AppException("请等待解析完成后再进行 AI 选材", 409)
            if part.material_rule_no:
                raise AppException("当前已手动指定材料规则，请先清除手选绑定再进行 AI 选材", 422)
            record, rules = await repo.rules(session, user, ANALYZE, org_id=part.org_id)
            rule_version = record.version_no
            analysis = dict(part.analysis)
            specs, stock_summary = apply_stock_rule(specs_data(part), analysis, rule_version)
            await session.commit()
        # 模型调用不占用数据库事务；返回后沿用输入版本校验，避免覆盖期间修改的参数。
        try:
            selection = await asyncio.to_thread(select_material, specs, rules, rule_version)
        except (ValueError, KeyError, httpx.HTTPError) as error:
            event("ai.material_failed", level="ERROR", **error_metadata(error))
            raise AppException("AI 选材未完成，请检查模型配置后重试，或手动选择材料规则", 502) from error
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, ANALYZE, lock=True)
            await repo.part(session, identifier, user, MANAGE)
            check_version(part, body.version_no)
            if await repo.active(session, part.id):
                raise AppException("已有解析任务开始，请等待完成后再选材", 409)
            record, rules = await repo.rules(session, user, ANALYZE, org_id=part.org_id)
            if record.version_no != rule_version:
                raise AppException("材料规则已更新，请重新 AI 选材", 409)
            analysis = {**part.analysis, "material_selection": selection}
            # 单独选材不补工序费率，也不改变已有工艺。
            specs, _, summary = apply_rules(specs, [], analysis, rules, rule_version)
            summary["filled"] = stock_summary["filled"] + summary["filled"]
            summary["skipped"] = stock_summary["skipped"] + summary["skipped"]
            operations = [operation_data(row) for row in await repo.operations(session, part.id)]
            if summary["filled"]:
                specs["is_requirements_confirmed"] = False
                await repo.save_inputs(session, part, specs, operations, user)
            part.analysis = {**analysis, "material_rule_result": summary}
            part.version_no += 1
            part.updated_by = user.user_id
            await session.commit()
            return {"part": await self.part_data(session, part), "selection": selection, "summary": summary}

    async def make_quote(self, session, part, user):
        specs = Specs.model_validate(specs_data(part))
        operations = [
            Operation.model_validate(operation_data(row)) for row in await repo.operations(session, part.id)
        ]
        missing = [f"{op.name}：请从现有正式工艺档案选择" for op in operations if not op.process_id]
        if missing:
            raise IncompleteQuote(missing)
        catalogue = await matching_catalog(session, part.org_id, user, MANAGE, lock=True)
        canonical_operations([op.model_dump(mode="json") for op in operations], catalogue, require_selected=True)
        geometry = part.analysis.get("geometry") or {}
        result = calculate_quote(
            specs,
            operations,
            part.quantity,
            net_volume_mm3=geometry.get("volume_mm3"),
            surface_area_mm2=geometry.get("area_mm2"),
        )
        result["weight_estimate"] = estimate_weight(specs, part.quantity, geometry)
        uncovered = list(part.analysis.get("ai", {}).get("uncovered_requirements", []))
        if uncovered:
            result.update(
                is_reference=True,
                uncovered_requirements=uncovered,
                warnings=[f"{item}；该要求未自动计入，请报价人员核对并调整。" for item in uncovered],
            )
        if geometry and specs.stock_length * specs.stock_width * specs.stock_height < geometry["volume_mm3"]:
            raise IncompleteQuote(["毛坯体积小于 CAD 净体积，请核实毛坯尺寸"])
        originals = {row.id: row for row in await files.list_for_business(session, SCENE, [part.id])}
        bindings = await repo.files(session, part.id)
        row = CncQuote(
            part_id=part.id,
            org_id=part.org_id,
            version_no=part.version_no,
            inputs_snapshot={
                "name": part.name,
                "specs": specs_data(part),
                "operations": [item.model_dump(mode="json") for item in operations],
                "analysis_job": part.analysis.get("artifact_job"),
                "uncovered_requirements": uncovered,
                "model_dimensions": model_dimensions(part.analysis),
                "files": [
                    {"name": originals[item.attachment_id].original_file_name, "sha256": item.sha256}
                    for item in bindings
                    if item.attachment_id in originals
                ],
            },
            result_snapshot=result,
            unit_price=result["unit_price"],
            total_price=result["total_price"],
            created_by=user.user_id,
            updated_by=user.user_id,
        )
        repo.add(session, row)
        return row

    async def evaluate(self, identifier, user):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, MANAGE, lock=True)
            quote = await self.make_quote(session, part, user)
            await session.commit()
            return quote_data(quote)

    async def approve(self, identifier, user):
        async with get_session_context() as session:
            quote = await repo.quote(session, identifier)
            # 所有写动作统一先锁零件，避免与核价及异步解析形成反向锁序。
            part = await repo.part(session, quote.part_id, user, APPROVE, lock=True)
            history = await repo.quotes(session, part.id)
            if not history or history[0].id != quote.id or quote.version_no != part.version_no:
                raise AppException("报价已过期，请重新核算", 409)
            if await repo.active(session, part.id):
                raise AppException("解析结束并复核后才能审核报价", 409)
            if not part.is_requirements_confirmed:
                raise AppException("请先确认制造要求、工艺和核价参数，再保存并核算", 422)
            if quote.approved_by:
                raise AppException("该报价已经审核", 409)
            quote.approved_by, quote.approved_at, quote.updated_by = user.user_id, utc_now(), user.user_id
            quote.approved_name_snapshot = user.display_name or str(user.user_id)
            await session.commit()
            return quote_data(quote)

    async def queue(self, identifier, body, user):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user, ANALYZE, lock=True)
            if await repo.active(session, part.id):
                raise AppException("该零件已有解析任务", 409)
            bindings = await repo.files(session, part.id)
            try:
                plan = analysis_plan({item.kind_code for item in bindings}, body, settings())
            except ValueError as error:
                raise AppException(str(error), 422) from error
            job = CncAnalysisJob(
                part_id=part.id,
                org_id=part.org_id,
                auth_user_id=user.auth_user_id,
                is_use_ai=plan["use_ai"],
                is_use_ocr=plan["use_ocr"],
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            repo.add(session, job)
            await session.commit()
            return {"job_id": str(job.id)}

    async def reconcile(self, identifier, user):
        async with get_session_context() as session:
            job = await repo.job(session, identifier)
            if job is None:
                raise AppException("任务不存在", 404)
            await repo.part(session, job.part_id, user, ANALYZE, lock=True)
            job = await repo.job(session, identifier, lock=True)
            if job.status_code == "running" and job.lease_expires_at and job.lease_expires_at < utc_now():
                job.status_code, job.stage = "failed", "解析已中断，可重试"
                job.error, job.updated_at = "处理进程中断；已有结果保留", utc_now()
                await session.commit()
            if job.status_code in {"queued", "running"}:
                raise AppException("任务仍在等待或处理中，请稍后查看", 409)
            return {"status_code": job.status_code}

    async def ocr_export(self, identifier, user):
        from .artifacts import ocr_zip

        async with get_session_context() as session:
            part = await repo.part(session, identifier, user)
            if not ocr_artifact_names(part.analysis):
                raise AppException("尚未生成文档解析产物", 404)
            output = settings().storage / str(part.id) / str(UUID(part.analysis["artifact_job"]))
            return ocr_zip(part.analysis, output)

    async def file_content(self, identifier, user):
        # 文件 ID 本身不是权限凭证；先定位父零件，再通过 L1 读取已绑定原件。
        async with get_session_context() as session:
            from .file_repository import drawing_file

            binding = await drawing_file(session, identifier)
            part = await repo.part(session, binding.part_id, user)
            originals = await files.list_for_business(session, SCENE, [part.id])
            original = next((row for row in originals if row.id == binding.attachment_id), None)
            if original is None:
                raise AppException("图纸原件不存在", 404)
            content = await get_storage(original.storage_backend).read(
                original.storage_key, max_bytes=20 * 1024 * 1024
            )
            if hashlib.sha256(content).hexdigest() != binding.sha256:
                raise AppException("原件内容已变化，请重新上传", 409)
            return content, original.content_type, original.original_file_name

    async def artifact(self, identifier, filename, user):
        async with get_session_context() as session:
            part = await repo.part(session, identifier, user)
            if filename not in artifact_names(part.analysis):
                raise AppException("解析产物不存在", 404)
            output = settings().storage / str(part.id) / str(UUID(part.analysis["artifact_job"]))
            path = artifact_path(output, filename)
            if not path.is_file():
                raise AppException("解析产物已不可用", 404)
            return path

    async def export_context(self, identifier, user):
        async with get_session_context() as session:
            quote = await repo.quote(session, identifier)
            await repo.part(session, quote.part_id, user)
            return SimpleNamespace(
                id=str(quote.id),
                version_no=quote.version_no,
                inputs=quote.inputs_snapshot,
                result=quote.result_snapshot,
                approved_by=quote.approved_name_snapshot if quote.approved_by else None,
            )

    async def file_access(self, session, user, identifier):
        if LIST not in user.permissions:
            return False
        try:
            await repo.part(session, identifier, user)
        except AppException:
            return False
        return True


service = CncService()
register_file_access(SCENE, service.file_access)
