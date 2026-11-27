"""软件报销：AI 摘录微信/支付宝/invoice，本人确认后写入当月工资单软件报销。"""
import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.file.service import service as files

from . import employee_mcp_repository as employee_repo
from . import employee_mcp_service as employee_mcp
from . import payroll_calc as calc
from . import repository
from .employee_mcp_manifest import manifest_hash
from .employee_mcp_models import SoftwareClaim, SoftwareClaimFile, SoftwareClaimItem
from .software_claim_files import BUSINESS_TYPE, SCENE
from .software_claim_period import allowed_period_months, billing_problem, resolved_billing_month

ACTIVE_STATUSES = {"preparing", "ready", "approved", "applied"}


def period_start(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def money(value) -> Decimal:
    return calc.money(value)


def invoice_data(row) -> dict:
    return {key: getattr(row, key) for key in ("file_name", "content_type", "file_size", "content_md5")}


def _date_text(value) -> str | None:
    return value.isoformat() if value is not None else None


def _item_view(item):
    if isinstance(item, dict):
        return {
            "occurred_on": _date_text(item["occurred_on"]),
            "billing_month": item["billing_month"],
            "amount": str(item["amount"]),
            "merchant_name": item["merchant_name"],
            "source_code": item["source_code"],
            "note": item.get("note"),
        }
    return {
        "occurred_on": _date_text(item.occurred_on),
        "billing_month": item.billing_month,
        "amount": str(item.amount),
        "merchant_name": item.merchant_name,
        "source_code": item.source_code,
        "note": item.note,
    }


def summary(row: SoftwareClaim, items=(), attachments=()):
    return {
        "request_id": str(row.id),
        "claim_id": str(row.id),
        "period_month": row.period_month.strftime("%Y-%m"),
        "status": row.status_code,
        "claimed_amount": str(row.claimed_amount),
        "applied_amount": str(row.applied_amount),
        "expires_at": row.expires_at.isoformat(),
        "approved": row.approved_at is not None,
        "payslip_id": str(row.payslip_id) if row.payslip_id else None,
        "items": [_item_view(item) for item in items],
        "attachments": list(attachments),
    }


async def can_read_own_claim(session, user, claim_id) -> bool:
    try:
        person = await employee_mcp.identity(session, user)
    except AppException:
        return False
    row = await employee_repo.own_software_claim(session, user.user_id, claim_id)
    return row is not None and row.employee_id == person.id


async def claim_in_session(session, user, claim_id, *, allow_inactive=False):
    person = await employee_mcp.identity(session, user)
    row = await employee_repo.own_software_claim(session, user.user_id, claim_id)
    if row is None:
        raise AppException("本人软件报销申请不存在", status_code=404)
    if row.employee_id != person.id:
        raise AppException("人员关联已经变化，请重新准备软件报销", status_code=409)
    if not allow_inactive and row.status_code == "superseded":
        raise AppException("本次申请已失效，请重新准备", status_code=409)
    if not allow_inactive and row.status_code not in {"applied"} and row.expires_at <= utc_now():
        raise AppException("软件报销申请已过期，请重新准备", status_code=410)
    return row, person


def _item_key(occurred_on, billing_month, amount, merchant_name, source_code, note) -> tuple:
    """幂等比较用的可排序键：扣款日期可能为空，统一转为文本。"""
    return (_date_text(occurred_on) or "", billing_month, str(amount), merchant_name, source_code, note or "")


def validate_items(items, billing_months) -> tuple[Decimal, list[dict]]:
    """billing_months 与 items 一一对应，为 resolved_billing_month 的结果；已由 billing_problem 确认全部等于申报月。"""
    total = Decimal("0")
    rows = []
    for index, (item, billing_month) in enumerate(zip(items, billing_months)):
        amount = money(item.amount)
        if amount <= 0:
            raise AppException("明细金额必须大于 0", status_code=422)
        total += amount
        rows.append({
            "occurred_on": item.occurred_on,
            "billing_month": billing_month,
            "amount": amount,
            "merchant_name": item.merchant_name.strip(),
            "source_code": item.source_code,
            "note": item.note.strip() if item.note else None,
            "sort_no": index,
        })
    if not rows:
        raise AppException("请至少提供一条消费明细", status_code=422)
    return money(total), rows


async def prepare(user, body):
    employee_mcp.authorize(user)
    if not body.items:
        return {"status": "needs_input", "missing_fields": ["items"],
                "question": "请从微信/支付宝扣款记录或 invoice 摘录至少一条消费明细。"}
    today = local_now().date()
    if body.period_month not in allowed_period_months(today):
        raise AppException(f"申报工资月只能是上月、本月或下月（今天为 {today:%Y-%m}）", status_code=422)
    billing_months = [resolved_billing_month(item.occurred_on, item.billing_month) for item in body.items]
    problem = billing_problem(body.period_month, billing_months, today)
    if problem is not None:
        return problem
    period = period_start(body.period_month)
    claimed, item_rows = validate_items(body.items, billing_months)
    applied = claimed
    descriptions = [item.model_dump() for item in body.files]
    if descriptions and len({item["content_md5"] for item in descriptions}) != len(descriptions):
        raise AppException("同一份凭证不能重复提交", status_code=422)
    fingerprint = manifest_hash(descriptions) if descriptions else None
    if body.evidence_manifest_hash and fingerprint != body.evidence_manifest_hash:
        raise AppException("凭证清单与声明的摘要不一致，请重新准备", status_code=422)
    if not descriptions:
        return {"status": "needs_input", "missing_fields": ["files"],
                "question": "请提供至少一份微信/支付宝扣款截图或 invoice 原件。"}
    try:
        async with get_session_context() as session:
            person = await employee_mcp.identity(session, user)
            existing = await employee_repo.software_claim_by_key(session, user.user_id, body.request_key)
            if existing is not None:
                declared = await employee_repo.software_claim_items(session, existing.id)
                files_declared = await employee_repo.software_claim_files(session, existing.id)
                same = (
                    existing.employee_id == person.id
                    and existing.org_id == person.org_id
                    and existing.period_month == period
                    and existing.claimed_amount == claimed
                    and existing.evidence_manifest_hash == fingerprint
                    and sorted(_item_key(item.occurred_on, item.billing_month, item.amount, item.merchant_name, item.source_code, item.note) for item in declared)
                    == sorted(_item_key(row["occurred_on"], row["billing_month"], row["amount"], row["merchant_name"], row["source_code"], row["note"]) for row in item_rows)
                    and sorted(tuple(invoice_data(item).values()) for item in files_declared)
                    == sorted(tuple(item.values()) for item in descriptions)
                )
                if not same:
                    raise AppException("幂等标识已用于另一份内容，请使用新的标识", status_code=409)
                if existing.expires_at <= utc_now() and existing.status_code not in {"applied"}:
                    raise AppException("申请已过期，请使用新的幂等标识", status_code=410)
                return {"status": existing.status_code, **summary(existing, declared)}
            current = await employee_repo.active_software_claim(session, person.id, period)
            if current is not None and current.status_code == "applied":
                payroll = await repository.get_payroll(session, person.org_id, period)
                if payroll and payroll.status_code == "closed":
                    raise AppException("该月工资已封账，不能再改软件报销", status_code=409)
                current.status_code = "superseded"
                current.updated_at, current.updated_by = utc_now(), user.user_id
                session.add(current)
            elif current is not None:
                current.status_code = "superseded"
                current.updated_at, current.updated_by = utc_now(), user.user_id
                session.add(current)
            row = await employee_repo.insert(session, SoftwareClaim(
                org_id=person.org_id, user_id=user.user_id, employee_id=person.id,
                request_key=body.request_key, period_month=period, status_code="preparing",
                claimed_amount=claimed, applied_amount=applied, evidence_manifest_hash=fingerprint,
                expires_at=utc_now() + timedelta(hours=24),
                created_by=user.user_id, updated_by=user.user_id,
            ))
            for item in item_rows:
                await employee_repo.insert(session, SoftwareClaimItem(
                    org_id=person.org_id, claim_id=row.id, created_by=user.user_id, updated_by=user.user_id, **item,
                ))
            for item in descriptions:
                await employee_repo.insert(session, SoftwareClaimFile(
                    org_id=person.org_id, claim_id=row.id, created_by=user.user_id, updated_by=user.user_id, **item,
                ))
            await session.commit()
            return {"status": row.status_code, **summary(row, item_rows)}
    except IntegrityError:
        raise AppException("同一申请正在准备，请使用相同标识重试", status_code=409) from None


async def upload_tickets(user, claim_id, descriptions):
    async with get_session_context() as session:
        row, _person = await claim_in_session(session, user, claim_id)
        if row.status_code != "preparing":
            raise AppException("申请已进入核对或已写入工资，不能再改凭证", status_code=409)
        declared = await employee_repo.software_claim_files(session, row.id)
        by_digest = {item.content_md5: item for item in declared}
        if len({item.content_md5 for item in descriptions}) != len(descriptions):
            raise AppException("不能重复申请同一份凭证的上传票据", status_code=422)
        for item in descriptions:
            expected = by_digest.get(item.content_md5)
            if expected is None or invoice_data(expected) != item.model_dump():
                raise AppException("只能上传准备时已声明的凭证", status_code=409)
        completed = {item.file_id for item in declared if item.file_id}
        if any(by_digest[item.content_md5].file_id in completed for item in descriptions):
            raise AppException("凭证已经完成上传，请刷新后继续", status_code=409)
        tickets = []
        for item in descriptions:
            ticket = await files.create_upload_ticket(scene_code=SCENE, user=user, **item.model_dump())
            expected = by_digest[item.content_md5]
            expected.file_id, expected.updated_at, expected.updated_by = UUID(str(ticket["id"])), utc_now(), user.user_id
            session.add(expected)
            tickets.append(ticket)
        await session.commit()
        return tickets


async def _all_evidence_ready(session, user, row, declared) -> bool:
    ids = [item.file_id for item in declared if item.file_id]
    if len(ids) != len(declared):
        return False
    try:
        actual = await files.pending_items(session, ids, user=user, scene_code=SCENE, include_integrity=True)
    except AppException:
        return False
    return manifest_hash(actual) == row.evidence_manifest_hash


async def complete_upload(user, claim_id, file_id):
    async with get_session_context() as session:
        row, _person = await claim_in_session(session, user, claim_id)
        declared = await employee_repo.software_claim_files(session, row.id)
        expected = next((item for item in declared if item.file_id == file_id), None)
        if expected is not None and row.status_code in {"ready", "approved", "applied"}:
            return {"file_id": str(file_id), "attached": True, "reused": True, "status": row.status_code}
        if row.status_code != "preparing":
            raise AppException("申请已进入核对或已写入工资，不能再改凭证", status_code=409)
        if expected is None:
            raise AppException("此文件不是本次预定凭证的有效上传票据", status_code=409)
        await files.complete_upload(file_id, user)
        uploaded = await files.pending_items(session, [file_id], user=user, scene_code=SCENE, include_integrity=True)
        if not uploaded or any(uploaded[0].get(key) != value for key, value in invoice_data(expected).items()):
            raise AppException("上传凭证与预定清单不一致，请重新准备", status_code=409)
        if await _all_evidence_ready(session, user, row, declared):
            row.status_code = "ready"
            row.updated_at, row.updated_by = utc_now(), user.user_id
            session.add(row)
        await session.commit()
        return {"file_id": str(file_id), "attached": True, "status": row.status_code}


async def recent_claims(user, *, page: int = 1, page_size: int = 20):
    """员工门户：本人软件报销分页。"""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    async with get_session_context() as session:
        person = await employee_mcp.identity(session, user)
        total, rows = await employee_repo.page_own_software_claims(
            session, user.user_id, person.id, page=page, page_size=page_size)
        items = [{
            "claim_id": str(row.id),
            "period_month": row.period_month.strftime("%Y-%m"),
            "status": row.status_code,
            "claimed_amount": str(row.claimed_amount),
            "applied_amount": str(row.applied_amount),
            "approved": row.approved_at is not None,
        } for row in rows]
        return {
            "employee_name": person.full_name,
            "org_name": await employee_repo.own_org_name(session, person.org_id),
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }


async def detail(user, claim_id):
    async with get_session_context() as session:
        row, person = await claim_in_session(session, user, claim_id, allow_inactive=True)
        items = await employee_repo.software_claim_items(session, row.id)
        declared = await employee_repo.software_claim_files(session, row.id)
        ids = [item.file_id for item in declared if item.file_id]
        attachments = []
        if ids:
            if row.status_code in {"approved", "applied"}:
                bound = await files.list_for_business(session, BUSINESS_TYPE, [row.id], scene_code=SCENE)
                attachments = [{"id": str(item.id), "file_name": item.original_file_name,
                                "file_size": item.file_size, "content_type": item.content_type} for item in bound]
            else:
                pending = await files.pending_items(session, ids, user=user, scene_code=SCENE, include_integrity=True)
                attachments = [{"id": item["id"], "file_name": item["file_name"], "file_size": item["file_size"],
                                "content_type": item["content_type"], "content_md5": item["content_md5"]} for item in pending]
        return {**summary(row, items, attachments), "employee_name": person.full_name,
                "org_name": await employee_repo.own_org_name(session, row.org_id)}


async def _apply_to_payslip(session, user, row: SoftwareClaim):
    payroll = await repository.get_payroll(session, row.org_id, row.period_month)
    if payroll is None:
        return None
    if payroll.status_code == "closed":
        raise AppException("该月工资已封账，不能写入软件报销", status_code=409)
    slips = await repository.list_payslips(session, payroll.id)
    slip = next((item for item in slips if item.employee_id == row.employee_id), None)
    if slip is None:
        return None
    slip.software_amount = row.applied_amount
    gross = calc.gross_pay(
        base_amount=slip.base_amount, performance_amount=slip.performance_amount, bonus_amount=slip.bonus_amount,
        overtime_amount=slip.overtime_amount, software_amount=slip.software_amount, travel_amount=slip.travel_amount,
        other_amount=slip.other_amount, adjust_amount=slip.adjust_amount,
    )
    slip.gross_amount = gross
    slip.net_amount = calc.net_pay(
        gross=gross, tax=slip.tax_amount, pension_employee=slip.pension_employee_amount,
        unemployment_employee=slip.unemployment_employee_amount, medical_employee=slip.medical_employee_amount,
        housing_employee=slip.housing_employee_amount, other_deduction=slip.other_deduction_amount,
    )
    slip.employer_cost_amount = calc.employer_cost(
        gross=gross, pension_employer=slip.pension_employer_amount, unemployment_employer=slip.unemployment_employer_amount,
        injury_employer=slip.injury_employer_amount, medical_employer=slip.medical_employer_amount,
        housing_employer=slip.housing_employer_amount,
    )
    slip.updated_by, slip.updated_at = user.user_id, utc_now()
    session.add(slip)
    return slip


async def approve(user, claim_id):
    """本人确认；若当月工资草稿已有本人工资单则立即写入软件报销，否则待核算时带入。"""
    async with get_session_context() as session:
        row, _person = await claim_in_session(session, user, claim_id)
        if row.status_code in {"approved", "applied"}:
            items = await employee_repo.software_claim_items(session, row.id)
            return summary(row, items)
        if row.status_code != "ready":
            raise AppException("请先传齐全部凭证后再确认", status_code=409)
        declared = await employee_repo.software_claim_files(session, row.id)
        ids = [item.file_id for item in declared if item.file_id]
        if len(ids) != len(declared):
            raise AppException("凭证尚未全部上传", status_code=409)
        actual = await files.pending_items(session, ids, user=user, scene_code=SCENE, include_integrity=True)
        if manifest_hash(actual) != row.evidence_manifest_hash:
            raise AppException("实际凭证与准备时声明的清单不同，请重新准备", status_code=409)
        # 本人确认时即绑定凭证；工资核算由管理员执行，不能代员工 bind 待绑定文件。
        await files.bind(session, ids, user=user, org_id=row.org_id, scene_code=SCENE,
                         business_type_code=BUSINESS_TYPE, business_id=row.id)
        slip = await _apply_to_payslip(session, user, row)
        now = utc_now()
        row.approved_at = now
        row.updated_at, row.updated_by = now, user.user_id
        if slip is not None:
            row.status_code = "applied"
            row.payslip_id = slip.id
        else:
            row.status_code = "approved"
        session.add(row)
        await session.commit()
        items = await employee_repo.software_claim_items(session, row.id)
        return summary(row, items)


def _admin_row(row, person, items, declared, bound):
    return {
        "id": str(row.id),
        "employee_id": str(row.employee_id),
        "employee_no": person.get("employee_no", ""),
        "full_name": person.get("full_name", ""),
        "org_id": str(row.org_id),
        "period_month": row.period_month.strftime("%Y-%m"),
        "status_code": row.status_code,
        "claimed_amount": float(row.claimed_amount),
        "applied_amount": float(row.applied_amount),
        "item_count": len(items),
        "items": [_item_view(item) for item in items],
        "declared_file_count": len(declared),
        "attachments": bound.get(row.id, []),
        "approved": row.approved_at is not None,
        "payslip_id": str(row.payslip_id) if row.payslip_id else None,
    }


async def admin_list(org_id: UUID, period_month: str) -> list[dict]:
    """管理端按组织、工资月查看软件报销（兼容旧调用；新列表走 admin_page）。"""
    result = await admin_page([org_id], period_month, page=1, page_size=100,
                              org_map={org_id: {"id": org_id, "org_name": ""}})
    return result["items"]


async def admin_page(org_ids: list[UUID], period_month: str, *, page: int, page_size: int, org_map: dict | None = None) -> dict:
    """管理端软件报销分页。"""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(period_month or "")):
        raise AppException("工资月份格式应为 YYYY-MM", status_code=422)
    period = period_start(period_month)
    org_map = org_map or {}
    async with get_session_context() as session:
        total, rows = await employee_repo.page_software_claims_for_orgs(
            session, org_ids, period, page=page, page_size=page_size)
        if not rows:
            return {"items": [], "total": total, "page": page, "page_size": page_size}
        names = await repository.names_by_employee(session, [row.employee_id for row in rows])
        bound = await files.items_for_business(session, BUSINESS_TYPE, [row.id for row in rows], scene_code=SCENE)
        items = []
        for row in rows:
            detail_items = await employee_repo.software_claim_items(session, row.id)
            declared = await employee_repo.software_claim_files(session, row.id)
            person = names.get(row.employee_id, {})
            payload = _admin_row(row, person, detail_items, declared, bound)
            org = org_map.get(row.org_id) or org_map.get(str(row.org_id))
            if org:
                payload = {**payload, "org_id": str(org["id"]), "org_name": org.get("org_name", "")}
            items.append(payload)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


async def applied_amounts_for_period(session, org_id: UUID, period: date) -> dict[UUID, Decimal]:
    """工资核算读取已确认/已写入的软件报销金额。"""
    rows = await employee_repo.software_claims_for_period(session, org_id, period)
    return {row.employee_id: row.applied_amount for row in rows if row.status_code in {"approved", "applied"}}


async def mark_applied_after_payroll(session, org_id: UUID, period: date, payslips: dict[UUID, UUID], user_id):
    rows = await employee_repo.software_claims_for_period(session, org_id, period)
    for row in rows:
        if row.status_code not in {"approved", "applied"} or row.employee_id not in payslips:
            continue
        row.status_code = "applied"
        row.payslip_id = payslips[row.employee_id]
        row.updated_at, row.updated_by = utc_now(), user_id
        session.add(row)
