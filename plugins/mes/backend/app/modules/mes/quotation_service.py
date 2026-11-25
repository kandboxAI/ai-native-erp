"""销售询价动作；数据库查询只在 Repository，原件和核价复用所属模块。"""
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from app.auth.scope_filters import resolve_write_org_id, ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.file.service import service as files, register_file_scene, register_file_access
from .quotation_models import MesQuotation, MesQuotationLine, MesQuotationCnc, MesQuotationEvent
from .quotation_repository import repository as repo
from .quotation_schemas import Weight
from .quotation_exchange_rates import exchange_rates, reference_note
from .sales_order_repository import repository as orders
from .cnc.repository import repository as cnc_repo, LIST, MANAGE, ANALYZE
from .cnc.models import CncPart, CncDrawingFile, CncAnalysisJob
from .cnc.service import SCENE as CNC_SCENE
from .cnc.config import settings as cnc_settings
from .cnc.drafts import analysis_plan
from .cnc.schemas import AnalysisRequest

SCENE = "mes_quotation_drawing"
NET_WEIGHT = TypeAdapter(Weight)
register_file_scene(SCENE, kinds={"document", "other"}, max_bytes=20*1024*1024, max_count=2, extra_content_types={"application/step": "step"})


def require(user, permission):
    if permission not in user.permissions:
        raise AppException("缺少询价操作权限", 403)


def version(quote, value):
    if quote.version_no != value:
        raise AppException("询价已由其他人员修改，请重新加载，保留本地修改后核对", 409)


def source_hash(line, bindings, *, legacy=False):
    # 保留摘要中的原重量位置，使此前未填重量的核价链接仍可直接使用。
    weight = str(Decimal(line.weight_kg).normalize()) if legacy and line.weight_kg is not None else None
    values = [line.drawing_no, line.drawing_revision, str(Decimal(line.quantity).normalize()), line.unit_name,
        line.customer_material, line.surface_treatment, weight,
        sorted(str(row.attachment_id) for row in bindings)]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def matches_source(link, line, bindings):
    # 保留旧来源单中含业务重量的核价链接，采用成功时更新为不依赖重量的摘要。
    return link.source_hash == source_hash(line, bindings) or link.source_hash == source_hash(line, bindings, legacy=True)


def snapshot_net_weight(snapshot):
    estimate = snapshot.result_snapshot.get("weight_estimate") or {}
    if estimate.get("method_key") != "cad_volume":
        return None
    try:
        return NET_WEIGHT.validate_python(estimate.get("net_weight_kg"))
    except ValidationError:
        return None


def check_status(quote, allowed):
    if quote.status_code not in allowed:
        raise AppException("当前询价状态不允许此操作", 409)


def check_requirements(lines):
    if not lines:
        raise AppException("请至少录入一项货品", 422)
    for index, line in enumerate(lines, 1):
        missing = [label for field, label in (("drawing_no", "图号"), ("description", "描述"),
                   ("customer_material", "客户材料")) if not getattr(line, field, "").strip()]
        if missing:
            raise AppException(f"{line.drawing_no or f'第 {index} 项货品'}：请填写{'、'.join(missing)}", 422)


def check_engineering(lines):
    lines = tuple(lines)
    if not lines:
        raise AppException("请至少录入一项货品", 422)
    for line in lines:
        missing = []
        if not line.quoted_material.strip():
            missing.append("报价采用材料")
        if line.unit_price is None:
            missing.append("单价")
        if missing:
            raise AppException(f"{line.drawing_no}：请填写{'、'.join(missing)}", 422)


class QuotationService:
    async def check_tier_prices(self, session, lines):
        for line in lines:
            if any(tier.unit_price is None for tier in await repo.tiers(session, line.id)):
                raise AppException(f"{line.drawing_no}：请完成所有数量档的报价", 422)

    async def historical_prices(self, user, drawing_no, customer_id=None, page=1, size=20):
        require(user, "mes:quotation:list")
        require(user, "mes:quotation:price")
        async with get_session_context() as session:
            rows, total = await repo.historical_prices(session, user, drawing_no, customer_id, page, size)
            items = []
            for quote, line in rows:
                items.append(dict(quotation_id=str(quote.id), quotation_line_id=str(line.id),
                    quote_no=quote.quote_no, revision=quote.revision, quoted_at=quote.updated_at,
                    customer_id=str(quote.customer_id), customer_name_snapshot=quote.customer_name_snapshot,
                    currency=quote.currency, drawing_no=line.drawing_no, drawing_revision=line.drawing_revision,
                    customer_material=line.customer_material, quoted_material=line.quoted_material,
                    quantity=str(line.quantity), unit_name=line.unit_name, unit_price=str(line.unit_price),
                    weight_kg=str(line.weight_kg) if line.weight_kg is not None else None,
                    lead_days=line.lead_days, quantity_tiers=[dict(id=str(t.id), quantity=str(t.quantity),
                    unit_price=str(t.unit_price)) for t in await repo.tiers(session, line.id)]))
            return dict(items=items, total=total, page=page, page_size=size)

    async def exchange_rate(self, identifier, quote_currency, user):
        for permission in ("mes:quotation:list", "mes:quotation:price", LIST):
            require(user, permission)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price")
            base = quote.currency
        # 不在公开网络请求期间保持数据库会话及事务。
        return await exchange_rates.get(base, quote_currency)

    async def cnc_records(self, session, line, user):
        records = []
        bindings = await repo.files(session, line.id)
        for link in await repo.cnc_links(session, line.id):
            try:
                await cnc_repo.part(session, link.part_id, user, LIST)
            except AppException as error:
                if error.status_code == 404:
                    continue
                raise
            job = await cnc_repo.jobs(session, link.part_id)
            records.append(dict(id=str(link.id), part_id=str(link.part_id),
                status_code=job.status_code if job else "idle", stage=job.stage if job else "尚未解析",
                is_stale=not matches_source(link, line, bindings), created_at=link.created_at))
        return records

    async def cnc_progress(self, identifier, user):
        for permission in ("mes:quotation:list", "mes:quotation:price", LIST):
            require(user, permission)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price")
            return dict(lines=[dict(id=str(line.id), cnc_records=await self.cnc_records(session, line, user))
                for line in await repo.lines(session, quote)])

    def touch(self, session, quote, user, action, note=""):
        quote.version_no += 1
        quote.updated_by, quote.updated_at = user.user_id, utc_now()
        repo.add(session, quote)
        repo.add(session, MesQuotationEvent(org_id=quote.org_id, quotation_id=quote.id,
            action_key=action, version_no_snapshot=quote.version_no, note=note, created_by=user.user_id))

    async def data(self, session, quote, user, *, detail=True):
        result = quote.model_dump(mode="json", exclude={"flex_form", "deleted_at", "deleted_by"})
        if "mes:sales_order:list" in user.permissions:
            result["customer_order_count"] = await repo.customer_order_count(session, quote.id, user)
        if not detail:
            return result
        result["lines"] = []
        can_price = "mes:quotation:price" in user.permissions and await repo.visible(session, quote.id, user, "mes:quotation:price")
        references = await repo.historical_references(session, quote.id, user) if can_price else {}
        for line in await repo.lines(session, quote):
            value = line.model_dump(mode="json", exclude={"flex_form", "deleted_at", "deleted_by"})
            if line.id in references:
                reference = references[line.id]
                value["historical_reference"] = {key: (str(item) if key in {"quotation_line_id", "unit_price", "quantity", "weight_kg"} and item is not None else item)
                    for key, item in reference.items() if key not in {"line_id", "rank"}}
            if not can_price:
                value.pop("engineering_note", None)
            value["quantity_tiers"] = [dict(id=str(t.id), quantity=str(t.quantity),
                unit_price=str(t.unit_price) if t.unit_price is not None else None,
                **({"calculation_note": t.calculation_note} if can_price else {})) for t in await repo.tiers(session, line.id)]
            value["files"] = []
            for binding in await repo.files(session, line.id):
                # URL remains protected by L1's registered quotation access checker.
                item = await files.download_url(binding.attachment_id, user)
                value["files"].append(dict(attachment_id=str(binding.attachment_id), kind=binding.kind, name=item["name"], size=item["file_size"]))
            value["cnc_records"] = []
            if can_price and LIST in user.permissions:
                value["cnc_records"] = await self.cnc_records(session, line, user)
            result["lines"].append(value)
        result["events"] = [row.model_dump(mode="json", exclude={"flex_form"}) for row in await repo.history(session, quote)]
        return result

    async def page(self, user, keyword="", status="", page=1, size=50):
        async with get_session_context() as session:
            rows, total = await repo.page(session, user, keyword, status, page, size)
            return dict(items=[await self.data(session, row, user, detail=False) for row in rows], total=total, page=page, page_size=size)

    async def detail(self, identifier, user):
        async with get_session_context() as session:
            return await self.data(session, await repo.get(session, identifier, user, "mes:quotation:list"), user)

    async def customers(self, org_id, user):
        org_id = resolve_write_org_id(user, org_id, "mes:quotation:manage")
        async with get_session_context() as session:
            return dict(org_id=str(org_id), customers=[dict(id=str(row.id), name=f"{row.customer_no} · {row.customer_name}") for row in await repo.customers(session, org_id)])

    async def upload(self, upload, user):
        require(user, "mes:quotation:manage")
        name = Path((upload.filename or "").replace("\\", "/")).name
        suffix = Path(name).suffix.lower()
        kind = "pdf" if suffix == ".pdf" else "model" if suffix in {".stp", ".step"} else None
        content = await upload.read(20*1024*1024+1)
        if not kind or not content or len(content) > 20*1024*1024:
            raise AppException("只允许非空且不超过 20MB 的 PDF、STP、STEP 文件", 422)
        if (kind == "pdf" and not content.startswith(b"%PDF-")) or (kind == "model" and b"ISO-10303-21" not in content[:256]):
            raise AppException("图纸内容与扩展名不符", 422)
        ticket = await files.upload_bytes(scene_code=SCENE, file_name=name,
            content_type="application/pdf" if kind == "pdf" else "application/step", content=content, user=user)
        return dict(attachment_id=ticket["id"], name=name, size=len(content), kind=kind)

    async def save(self, identifier, body, user, *, submit=False):
        require(user, "mes:quotation:manage")
        check_requirements(body.lines)
        if submit:
            for line in body.lines:
                if not line.files:
                    raise AppException(f"{line.drawing_no}：请上传图纸或模型", 422)
        async with get_session_context() as session:
            if identifier:
                quote = await repo.get(session, identifier, user, "mes:quotation:manage", lock=True)
                version(quote, body.version_no)
                check_status(quote, {"draft"})
                if body.org_id and body.org_id != quote.org_id:
                    raise AppException("询价不能切换组织", 422)
            else:
                org_id = resolve_write_org_id(user, body.org_id, "mes:quotation:manage")
                customer = await repo.customer(session, body.customer_id, org_id)
                quote = MesQuotation(org_id=org_id, quote_no=f"BJ-{utc_now():%Y%m%d}-{str(uuid7()).replace('-', '')[-16:]}",
                    title=body.title, customer_id=customer.id, customer_name_snapshot=customer.customer_name,
                    currency=body.currency, owner_user_id=user.user_id, created_by=user.user_id, updated_by=user.user_id)
                repo.add(session, quote)
                await session.flush()
            customer = await repo.customer(session, body.customer_id, quote.org_id)
            pricing_context_changed = quote.currency != body.currency or quote.customer_id != customer.id
            quote.title, quote.customer_id, quote.customer_name_snapshot = body.title, customer.id, customer.customer_name
            quote.currency, quote.deadline, quote.note = body.currency, body.deadline, body.note
            current = {line.id: line for line in await repo.lines(session, quote)}
            # Temporarily move sequence values to avoid swaps violating the unique index.
            for line in current.values():
                line.sequence_no = -line.sequence_no
            await session.flush()
            retained = set()
            for index, value in enumerate(body.lines, 1):
                line = current.get(value.id) if value.id else None
                if value.id and line is None:
                    raise AppException("明细不属于本询价", 422)
                if line is None:
                    line = MesQuotationLine(org_id=quote.org_id, quotation_id=quote.id, sequence_no=index,
                        drawing_no=value.drawing_no, quantity=value.quantity, created_by=user.user_id, updated_by=user.user_id)
                    repo.add(session, line)
                    await session.flush()
                previous_bindings = await repo.files(session, line.id)
                previous_source = source_hash(line, previous_bindings)
                old_files = {row.attachment_id for row in previous_bindings}
                for item in value.files:
                    if item.attachment_id not in old_files:
                        attachment, _ = await files.read_pending_for_ingest(session, item.attachment_id, user=user, org_id=user.org_id, scene_code=SCENE)
                        expected = "pdf" if attachment.content_type == "application/pdf" else "model"
                        if expected != item.kind:
                            raise AppException("附件类型不匹配", 422)
                        await files.bind(session, [item.attachment_id], user=user, org_id=quote.org_id,
                            scene_code=SCENE, business_type_code=SCENE, business_id=line.id)
                for key in ("drawing_no", "drawing_revision", "description", "quantity", "unit_name", "customer_material", "surface_treatment", "note"):
                    setattr(line, key, getattr(value, key))
                line.sequence_no, line.updated_by, line.updated_at = index, user.user_id, utc_now()
                line.adopted_cnc_quote_id = None
                await repo.replace_files(session, line, value.files, user)
                if pricing_context_changed or previous_source != source_hash(line, value.files):
                    line.unit_price = None
                await repo.replace_tiers(session, line, value.quantity_tiers, user,
                    clear_prices=pricing_context_changed or previous_source != source_hash(line, value.files))
                retained.add(line.id)
            for line in current.values():
                if line.id not in retained:
                    line.deleted_at, line.deleted_by = utc_now(), user.user_id
            if submit:
                quote.status_code, quote.return_reason = "pending", ""
            self.touch(session, quote, user, "submit" if submit else "save")
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result

    async def engineering(self, identifier, body, user, *, submit=False):
        require(user, "mes:quotation:price")
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price", lock=True)
            version(quote, body.version_no)
            check_status(quote, {"pending", "pricing"})
            lines = {row.id: row for row in await repo.lines(session, quote)}
            if len({row.id for row in body.lines}) != len(body.lines) or set(lines) != {row.id for row in body.lines}:
                raise AppException("请提交本询价完整且不重复的工程明细", 422)
            for value in body.lines:
                line = lines[value.id]
                tiers = {t.id: t for t in await repo.tiers(session, line.id)}
                if len({t.id for t in value.quantity_tiers}) != len(value.quantity_tiers) or set(tiers) != {t.id for t in value.quantity_tiers}:
                    raise AppException(f"{line.drawing_no}：请提交完整且不重复的数量档", 422)
                for entry in value.quantity_tiers:
                    tier = tiers[entry.id]
                    tier.unit_price, tier.calculation_note = entry.unit_price, entry.calculation_note
                    tier.updated_at, tier.updated_by = utc_now(), user.user_id
                if (line.quoted_material, line.unit_price) != (value.quoted_material, value.unit_price):
                    line.adopted_cnc_quote_id = None
                for key in ("quoted_material", "weight_kg", "unit_price", "engineering_note"):
                    setattr(line, key, getattr(value, key))
                line.updated_at, line.updated_by = utc_now(), user.user_id
            if submit:
                check_engineering(lines.values())
                await self.check_tier_prices(session, lines.values())
                quote.return_reason = ""
            quote.status_code, quote.engineer_user_id = "review" if submit else "pricing", user.user_id
            self.touch(session, quote, user, "finish" if submit else "engineering")
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result

    async def check_quotation_reviewer(self, session, quote, user):
        if quote.engineer_user_id != user.user_id:
            return False
        if "mes:quotation:approve_self" not in user.permissions:
            raise AppException("工程报价不能由本人审核，请分配其他审核人员", 403)
        # 特殊自审授权也受自己的数据范围约束，不扩大普通审核的可见范围。
        await repo.get(session, quote.id, user, "mes:quotation:approve_self")
        return True

    async def approve(self, identifier, body, user):
        require(user, "mes:quotation:approve")
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:approve", lock=True)
            version(quote, body.version_no)
            check_status(quote, {"review"})
            is_self_review = await self.check_quotation_reviewer(session, quote, user)
            lines = {row.id: row for row in await repo.lines(session, quote)}
            if len({row.id for row in body.lines}) != len(body.lines) or set(lines) != {row.id for row in body.lines}:
                raise AppException("请确认本询价每项货品的最终交期，明细不得遗漏或重复", 422)
            check_engineering(lines.values())
            await self.check_tier_prices(session, lines.values())
            adjustments = []
            for value in body.lines:
                line = lines[value.id]
                if "unit_price" in value.model_fields_set:
                    if value.unit_price is None:
                        raise AppException(f"{line.drawing_no}：请填写有效的最终对客单价", 422)
                    if line.unit_price != value.unit_price:
                        adjustments.append((line, line, value.unit_price, f"主数量{line.quantity}{line.unit_name}"))
                if value.quantity_tiers is not None:
                    tiers = {t.id: t for t in await repo.tiers(session, line.id)}
                    if len({t.id for t in value.quantity_tiers}) != len(value.quantity_tiers) or set(tiers) != {t.id for t in value.quantity_tiers}:
                        raise AppException(f"{line.drawing_no}：请提交完整且不重复的数量档，不能新增或更换其他货品的档位", 422)
                    for supplied in value.quantity_tiers:
                        tier = tiers[supplied.id]
                        if tier.unit_price != supplied.unit_price:
                            adjustments.append((line, tier, supplied.unit_price, f"数量档{tier.quantity}{line.unit_name}"))
            if adjustments and not body.price_adjustment_reason:
                raise AppException("调整报价时请填写改价说明", 422)
            # 校验完整请求后再写入；原价按明细追加留在审计中，不修改工程核算依据。
            for line, target, final_price, label in adjustments:
                old_price = target.unit_price
                target.unit_price = final_price
                target.updated_by, target.updated_at = user.user_id, utc_now()
                repo.add(session, MesQuotationEvent(org_id=quote.org_id, quotation_id=quote.id,
                    action_key="approval_price", version_no_snapshot=quote.version_no + 1,
                    note=f"图号{line.drawing_no} / 版本{line.drawing_revision} / {label}：工程报价{old_price:.2f} {quote.currency} → 审核定价{final_price:.2f} {quote.currency}；原因：{body.price_adjustment_reason}",
                    created_by=user.user_id))
            for value in body.lines:
                line = lines[value.id]
                line.lead_days = value.lead_days
                line.updated_by, line.updated_at = user.user_id, utc_now()
            quote.status_code, quote.return_reason = "final_review", ""
            note = "；".join(filter(None, [body.note, "经授权审核本人提交的报价" if is_self_review else ""]))
            self.touch(session, quote, user, "approve", note)
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result

    async def delete_draft(self, identifier, version_no, user):
        require(user, "mes:quotation:manage")
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:manage", lock=True)
            version(quote, version_no)
            if quote.status_code != "draft":
                raise AppException("仅业务录入状态的询价可以删除", 409)
            quote.deleted_at, quote.deleted_by = utc_now(), user.user_id
            self.touch(session, quote, user, "delete")
            await session.commit()
            return {"id": str(quote.id)}

    async def revise(self, identifier, body, user):
        require(user, "mes:quotation:manage")
        async with get_session_context() as session:
            original = await repo.get(session, identifier, user, "mes:quotation:manage", lock=True)
            version(original, body.version_no)
            check_status(original, {"quoted"})
            if await repo.revisions_in_progress(session, original):
                raise AppException("该报价已有未完成修订", 409)
            quote = MesQuotation(org_id=original.org_id, quote_no=original.quote_no,
                revision=await repo.next_revision(session, original), title=original.title,
                customer_id=original.customer_id, customer_name_snapshot=original.customer_name_snapshot,
                currency=original.currency, deadline=original.deadline, note=original.note,
                owner_user_id=user.user_id, created_by=user.user_id, updated_by=user.user_id)
            repo.add(session, quote)
            await session.flush()
            for source in await repo.lines(session, original):
                values = source.model_dump(exclude={"id", "quotation_id", "created_at", "created_by", "updated_at", "updated_by", "deleted_at", "deleted_by", "adopted_cnc_quote_id", "lead_days"})
                line = MesQuotationLine(**values, quotation_id=quote.id, created_by=user.user_id, updated_by=user.user_id)
                repo.add(session, line)
                await session.flush()
                await repo.replace_files(session, line, await repo.files(session, source.id), user)
                await repo.replace_tiers(session, line, [t.quantity for t in await repo.tiers(session, source.id)], user)
                old_tiers = {t.quantity: t for t in await repo.tiers(session, source.id)}
                await session.flush()
                for tier in await repo.tiers(session, line.id):
                    tier.unit_price = old_tiers[tier.quantity].unit_price
                    tier.calculation_note = old_tiers[tier.quantity].calculation_note
            self.touch(session, quote, user, "revise", body.note)
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result

    async def command(self, identifier, action, body, user):
        permission = {
            "submit": "manage", "finish": "price", "return": "price",
            "approve": "approve", "reject": "approve",
            "final_approve": "approve", "final_reject": "approve", "void": "manage",
        }.get(action)
        if permission is None:
            raise AppException("不支持的询价动作", 422)
        permission = f"mes:quotation:{permission}"
        require(user, permission)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, permission, lock=True)
            version(quote, body.version_no)
            note = body.note
            if action == "submit":
                check_status(quote, {"draft"})
                lines = await repo.lines(session, quote)
                check_requirements(lines)
                for line in lines:
                    if not await repo.files(session, line.id):
                        raise AppException(f"{line.drawing_no}：请上传图纸或模型", 422)
                quote.status_code, quote.return_reason = "pending", ""
            elif action == "finish":
                check_status(quote, {"pending", "pricing"})
                lines = await repo.lines(session, quote)
                check_engineering(lines)
                await self.check_tier_prices(session, lines)
                quote.status_code, quote.engineer_user_id = "review", user.user_id
                quote.return_reason = ""
            elif action in {"return", "reject"}:
                check_status(quote, {"review"} if action == "reject" else {"pending", "pricing"})
                if not body.note:
                    raise AppException("请填写退回原因", 422)
                quote.status_code = "pricing" if action == "reject" else "draft"
                quote.return_reason = body.note
            elif action in {"final_approve", "final_reject"}:
                check_status(quote, {"final_review"})
                is_self_review = await self.check_quotation_reviewer(session, quote, user)
                if action == "final_approve":
                    lines = await repo.lines(session, quote)
                    check_engineering(lines)
                    await self.check_tier_prices(session, lines)
                    for line in lines:
                        if line.lead_days is None or not 1 <= line.lead_days <= 3650:
                            raise AppException(f"{line.drawing_no}：请退回初审补齐最终交期", 422)
                    quote.status_code, quote.return_reason = "quoted", ""
                else:
                    if not body.note:
                        raise AppException("请填写退回初审的原因", 422)
                    quote.status_code, quote.return_reason = "review", body.note
                note = "；".join(filter(None, [body.note, "经授权复审本人提交的报价" if is_self_review else ""]))
            elif action == "void":
                check_status(quote, {"pending", "pricing", "review", "final_review", "quoted"})
                if not note:
                    raise AppException("请填写作废原因", 422)
                # 订单创建也先锁定来源报价，避免检查后又生成订单。
                if await orders.has_quotation_reference(session, quote.id, quote.org_id):
                    raise AppException("本版报价已关联客户订单，不能作废", 409)
                quote.status_code, quote.return_reason = "voided", ""
            else:
                check_status(quote, {"review"})
                await self.check_quotation_reviewer(session, quote, user)
                raise AppException("请填写每项货品的最终交期后审核通过", 422)
            self.touch(session, quote, user, action, note)
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result

    async def prepare_cnc(self, identifier, line_id, body, user):
        for permission in ("mes:quotation:price", LIST, MANAGE, ANALYZE):
            require(user, permission)
        tickets = []
        try:
            async with get_session_context() as session:
                quote = await repo.get(session, identifier, user, "mes:quotation:price", lock=True)
                version(quote, body.version_no)
                check_status(quote, {"pending", "pricing"})
                ensure_org_access(user, quote.org_id, MANAGE)
                ensure_org_access(user, quote.org_id, ANALYZE)
                line = next((row for row in await repo.lines(session, quote) if row.id == line_id), None)
                if not line:
                    raise AppException("货品不属于本询价", 404)
                if line.quantity != int(line.quantity) or line.unit_name.lower() not in {"件", "pcs", "piece", "pieces"}:
                    raise AppException("加工核价目前仅支持整数件数；请人工报价或核对单位", 422)
                bindings = await repo.files(session, line.id)
                if not bindings:
                    raise AppException("请先添加图纸或模型", 422)
                digest = source_hash(line, bindings)
                links = await repo.cnc_links(session, line.id)
                if links and matches_source(links[0], line, bindings) and not body.is_retry:
                    await cnc_repo.part(session, links[0].part_id, user, LIST)
                    return dict(part_id=str(links[0].part_id), reused=True)
                try:
                    plan = analysis_plan({"pdf" if row.kind == "pdf" else "step" for row in bindings},
                        AnalysisRequest(cloud_allowed=body.cloud_allowed), cnc_settings())
                except ValueError as error:
                    raise AppException(str(error), 422) from error
                originals = []
                for binding in bindings:
                    original, content = await files.read_content(session, binding.attachment_id, user=user)
                    ticket = await files.upload_bytes(scene_code=CNC_SCENE, file_name=original.original_file_name,
                        content_type=original.content_type, content=content, user=user)
                    tickets.append(ticket)
                    originals.append((binding, content))
                part = CncPart(org_id=quote.org_id, name=line.drawing_no, quantity=int(line.quantity),
                    material=line.customer_material, treatment=line.surface_treatment, created_by=user.user_id, updated_by=user.user_id)
                cnc_repo.add(session, part)
                await session.flush()
                await files.bind(session, [UUID(ticket["id"]) for ticket in tickets], user=user, org_id=quote.org_id,
                    scene_code=CNC_SCENE, business_type_code=CNC_SCENE, business_id=part.id)
                for ticket, (binding, content) in zip(tickets, originals, strict=True):
                    cnc_repo.add(session, CncDrawingFile(org_id=quote.org_id, part_id=part.id, attachment_id=UUID(ticket["id"]),
                        kind_code="pdf" if binding.kind == "pdf" else "step", sha256=hashlib.sha256(content).hexdigest(), created_by=user.user_id, updated_by=user.user_id))
                cnc_repo.add(session, CncAnalysisJob(org_id=quote.org_id, part_id=part.id, auth_user_id=user.auth_user_id,
                    is_use_ai=plan["use_ai"], is_use_ocr=plan["use_ocr"], created_by=user.user_id, updated_by=user.user_id))
                repo.add(session, MesQuotationCnc(org_id=quote.org_id, line_id=line.id, part_id=part.id, source_hash=digest,
                    created_by=user.user_id, updated_by=user.user_id))
                await session.commit()
                return dict(part_id=str(part.id), reused=False)
        except Exception:
            for ticket in tickets:
                await files.discard(UUID(ticket["id"]), user)
            raise

    async def adoption_basis(self, session, quote, line, user, *, cnc_quote_id=None, lock=False):
        if line is None:
            raise AppException("货品不属于本询价", 404)
        links = await repo.cnc_links(session, line.id)
        bindings = await repo.files(session, line.id)
        if not links or not matches_source(links[0], line, bindings):
            raise AppException("核价来源已变化，请重新分析", 409)
        part = await cnc_repo.part(session, links[0].part_id, user, LIST, lock=lock)
        if part.quantity != line.quantity or (line.surface_treatment and part.treatment != line.surface_treatment):
            raise AppException("加工核价数量或表面处理已偏离询价要求，请核对后重新核价", 409)
        history = await cnc_repo.quotes(session, part.id)
        if not history:
            raise AppException("尚未完成工程核算", 409)
        if history[0].version_no != part.version_no:
            raise AppException("核价依据已更新，请重新核算后确认采用", 409)
        if cnc_quote_id is not None and history[0].id != cnc_quote_id:
            raise AppException("核价快照已变化，请重新确认", 409)
        if part.org_id != quote.org_id:
            raise AppException("核价零件不属于当前询价组织", 409)
        if await cnc_repo.active(session, part.id):
            raise AppException("核价任务仍在执行，请稍后重试", 409)
        job = await cnc_repo.jobs(session, part.id)
        if job is not None and job.status_code != "completed":
            raise AppException("核价任务尚未成功完成，请完成分析后再采用", 409)
        operations = history[0].inputs_snapshot.get("operations", [])
        if any(not row.get("process_id") for row in operations):
            raise AppException("核价工序未全部选择正式工艺，请重新分析并核算后再确认采用",422)
        if operations:
            from .process_matching import matching_catalog, canonical_operations
            catalogue = await matching_catalog(session, part.org_id, user, LIST, lock=lock)
            canonical_operations(operations, catalogue, require_selected=True)
        return part, history[0], links[0], source_hash(line, bindings)

    def apply_adoption(self, line, part, snapshot, link, digest, unit_price, user):
        line.quoted_material, line.unit_price = part.material, unit_price
        weight = snapshot_net_weight(snapshot)
        if weight is not None:
            line.weight_kg = weight
        if link.source_hash != digest:
            link.source_hash = digest
            link.updated_by, link.updated_at = user.user_id, utc_now()
        line.adopted_cnc_quote_id = snapshot.id
        line.updated_by, line.updated_at = user.user_id, utc_now()

    def cnc_price(self, snapshot):
        currency = snapshot.result_snapshot.get("currency", "CNY")
        try:
            price = Decimal(str(snapshot.unit_price))
        except (InvalidOperation, ValueError):
            raise AppException("核价金额无效，请重新核算", 422)
        if not price.is_finite() or price < 0 or currency not in {"CNY", "EUR", "USD"}:
            raise AppException("核价金额或币种无效，请重新核算", 422)
        return price, currency

    def suggested_price(self, quote, snapshot, exchange_rate):
        price, currency = self.cnc_price(snapshot)
        if currency != quote.currency:
            if exchange_rate is None:
                raise AppException(f"请填写汇率（1 {quote.currency} 折合多少 {currency}）后自动回填", 422)
            price /= exchange_rate
        price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if price > Decimal("100000000"):
            raise AppException("换算后的单价超过允许范围，请核对汇率或手动填写", 422)
        return price

    def adoption_note(self, note, quote, exchange_rate, automatic_count, source_currencies, reference=None):
        notes = [note] if note else []
        if automatic_count:
            notes.append(f"AI 核价自动回填 {automatic_count} 项")
            if exchange_rate is not None:
                notes.extend(f"汇率：1 {quote.currency} = {exchange_rate} {currency}"
                    for currency in sorted(source_currencies) if currency != quote.currency)
                provenance = reference_note(reference, quote.currency, source_currencies, exchange_rate) if source_currencies - {quote.currency} else ""
                if provenance:
                    notes.append(provenance)
        return "；".join(notes)

    async def adoption_preview(self, identifier, body, user):
        for permission in ("mes:quotation:list", "mes:quotation:price", LIST):
            require(user, permission)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price")
            version(quote, body.version_no)
            check_status(quote, {"pending", "pricing"})
            lines = {line.id: line for line in await repo.lines(session, quote)}
            results = []
            for identifier in body.line_ids:
                try:
                    part, snapshot, _, _ = await self.adoption_basis(session, quote, lines.get(identifier), user)
                    weight = snapshot_net_weight(snapshot)
                    raw_price, currency = self.cnc_price(snapshot)
                    suggested, price_message = None, ""
                    try:
                        suggested = str(self.suggested_price(quote, snapshot, body.exchange_rate))
                    except AppException as error:
                        price_message = error.message
                    results.append(dict(line_id=str(identifier), can_adopt=True, cnc_quote_id=str(snapshot.id),
                        quoted_material=part.material, net_weight_kg=str(weight) if weight is not None else None,
                        cnc_unit_price=str(raw_price), cnc_currency=currency,
                        suggested_unit_price=suggested, price_message=price_message, message="可采用"))
                except AppException as error:
                    results.append(dict(line_id=str(identifier), can_adopt=False, message=error.message))
            return dict(items=results)

    async def adopt_batch(self, identifier, body, user):
        for permission in ("mes:quotation:list", "mes:quotation:price", LIST):
            require(user, permission)
        if not body.is_confirmed:
            raise AppException("请确认已逐项核对核价依据和对客单价", 422)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price", lock=True)
            version(quote, body.version_no)
            check_status(quote, {"pending", "pricing"})
            lines = {line.id: line for line in await repo.lines(session, quote)}
            results = []
            automatic_count, source_currencies = 0, set()
            for value in body.lines:
                line = lines.get(value.line_id)
                try:
                    part, snapshot, link, digest = await self.adoption_basis(session, quote, line, user,
                        cnc_quote_id=value.cnc_quote_id, lock=True)
                    unit_price = self.suggested_price(quote, snapshot, body.exchange_rate)
                except AppException as error:
                    results.append(dict(line_id=str(value.line_id), is_success=False,
                        code=error.status_code, message=error.message))
                    continue
                self.apply_adoption(line, part, snapshot, link, digest, unit_price, user)
                automatic_count += 1
                source_currencies.add(self.cnc_price(snapshot)[1])
                results.append(dict(line_id=str(value.line_id), is_success=True, code=0, message="已采用核价"))
            count = sum(row["is_success"] for row in results)
            if count:
                quote.status_code, quote.engineer_user_id = "pricing", user.user_id
                self.touch(session, quote, user, "adopt", self.adoption_note(
                    body.note or f"批量采用 {count} 项核价", quote, body.exchange_rate, automatic_count,
                    source_currencies, body.exchange_rate_reference))
                await session.flush()
            result = dict(quotation=await self.data(session, quote, user), items=results)
            await session.commit()
            return result

    async def adopt(self, identifier, line_id, body, user):
        require(user, "mes:quotation:price")
        require(user, LIST)
        if not body.is_confirmed:
            raise AppException("请确认已复核核价依据及最终单价", 422)
        async with get_session_context() as session:
            quote = await repo.get(session, identifier, user, "mes:quotation:price", lock=True)
            version(quote, body.version_no)
            check_status(quote, {"pending", "pricing"})
            line = next((row for row in await repo.lines(session, quote) if row.id == line_id), None)
            part, snapshot, link, digest = await self.adoption_basis(session, quote, line, user,
                cnc_quote_id=body.cnc_quote_id, lock=True)
            unit_price = self.suggested_price(quote, snapshot, body.exchange_rate)
            self.apply_adoption(line, part, snapshot, link, digest, unit_price, user)
            quote.status_code, quote.engineer_user_id = "pricing", user.user_id
            self.touch(session, quote, user, "adopt", self.adoption_note(body.note, quote,
                body.exchange_rate, 1, {self.cnc_price(snapshot)[1]}, body.exchange_rate_reference))
            await session.flush()
            result = await self.data(session, quote, user)
            await session.commit()
            return result


service = QuotationService()


async def file_access(session, user, line_id):
    if "mes" not in getattr(user, "enabled_plugin_keys", []):
        return False
    if "mes:quotation:list" in user.permissions and await repo.file_access(session, user, line_id):
        return True
    if "mes:sales_order:list" in user.permissions:
        return await orders.file_access(session, line_id, user)
    return False


register_file_access(SCENE, file_access)
