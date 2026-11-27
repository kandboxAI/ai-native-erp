"""员工 MCP 专属查询；本人范围不受管理员的全部数据范围放宽。"""
from sqlmodel import select
from app.framework.db.models import utc_now
from .employee_mcp_models import (
    EmployeeUser, EmployeeExpenseRequest, EmployeeExpenseFile, EmployeeExpenseInvoice,
    SoftwareClaim, SoftwareClaimItem, SoftwareClaimFile,
)
from .models import SampleEmployee, SampleReimbursement
from app.modules.organization.models import SysOrg
from app.auth.scope_filters import scoped_conditions


async def current_binding(session, user_id, *, lock=False):
    now = utc_now()
    query = select(EmployeeUser).where(EmployeeUser.user_id == user_id, EmployeeUser.deleted_at.is_(None),
                                      EmployeeUser.valid_from <= now, EmployeeUser.valid_to.is_(None))
    if lock:
        query = query.with_for_update()
    rows = list((await session.exec(query)).all())
    return rows


async def active_employee(session, employee_id):
    return (await session.exec(select(SampleEmployee).where(SampleEmployee.id == employee_id, SampleEmployee.deleted_at.is_(None)))).first()


async def visible_bindings(session, user):
    statement = (select(EmployeeUser, SampleEmployee.full_name).join(SampleEmployee, SampleEmployee.id == EmployeeUser.employee_id)
                 .where(*scoped_conditions(SampleEmployee, user, "sample_app:access"),
                        EmployeeUser.org_id == SampleEmployee.org_id, EmployeeUser.deleted_at.is_(None),
                        EmployeeUser.valid_from <= utc_now(), EmployeeUser.valid_to.is_(None))
                 .order_by(SampleEmployee.full_name))
    return list((await session.exec(statement)).all())


async def own_org_name(session, org_id):
    """仅由已核对本人绑定的 Service 使用；跨模块契约只读组织名称及启用/软删除。"""
    return (await session.exec(select(SysOrg.org_name).where(SysOrg.id == org_id, SysOrg.is_active.is_(True), SysOrg.deleted_at.is_(None)))).first()


async def active_org_names(session):
    """启用组织的名称，供发票抬头匹配费用企业。"""
    return list((await session.exec(select(SysOrg.id, SysOrg.org_name).where(
        SysOrg.is_active.is_(True), SysOrg.deleted_at.is_(None)))).all())


async def request_by_key(session, user_id, key):
    return (await session.exec(select(EmployeeExpenseRequest).where(EmployeeExpenseRequest.user_id == user_id,
                              EmployeeExpenseRequest.request_key == key, EmployeeExpenseRequest.deleted_at.is_(None)))).first()


async def own_request(session, user_id, request_id):
    return (await session.exec(select(EmployeeExpenseRequest).where(EmployeeExpenseRequest.id == request_id,
                              EmployeeExpenseRequest.user_id == user_id, EmployeeExpenseRequest.deleted_at.is_(None)).with_for_update())).first()


async def request_files(session, request_id):
    return list((await session.exec(select(EmployeeExpenseFile).where(EmployeeExpenseFile.request_id == request_id,
                                   EmployeeExpenseFile.deleted_at.is_(None)).order_by(EmployeeExpenseFile.id))).all())


async def invoice_manifest(session, request_id):
    statement = select(EmployeeExpenseInvoice).where(EmployeeExpenseInvoice.request_id == request_id,
        EmployeeExpenseInvoice.deleted_at.is_(None)).order_by(EmployeeExpenseInvoice.id).with_for_update()
    return list((await session.exec(statement)).all())


async def next_request(session, previous_request_id):
    return (await session.exec(select(EmployeeExpenseRequest).where(
        EmployeeExpenseRequest.previous_request_id == previous_request_id,
        EmployeeExpenseRequest.deleted_at.is_(None)))).first()


async def own_recent_requests(session, user_id, employee_id, org_id):
    """仅列出本人仍可继续的未提交申请；正式报销另按员工归属读取。"""
    del org_id
    statement = (select(EmployeeExpenseRequest)
        .where(EmployeeExpenseRequest.user_id == user_id, EmployeeExpenseRequest.employee_id == employee_id,
               EmployeeExpenseRequest.reimbursement_id.is_(None),
               EmployeeExpenseRequest.status_code.in_(["preparing", "ready", "approved"]),
               EmployeeExpenseRequest.expires_at > utc_now(),
               EmployeeExpenseRequest.deleted_at.is_(None))
        .order_by(EmployeeExpenseRequest.occurred_on.desc(), EmployeeExpenseRequest.id.desc()).limit(50))
    return list((await session.exec(statement)).all())


async def own_reimbursements(session, employee_id):
    """本人正式报销（含管理员代录），不以创建人或名册企业限制费用归属。"""
    statement = (select(SampleReimbursement).where(
        SampleReimbursement.employee_id == employee_id, SampleReimbursement.deleted_at.is_(None))
        .order_by(SampleReimbursement.occurred_on.desc(), SampleReimbursement.id.desc()).limit(50))
    return list((await session.exec(statement)).all())


async def own_reimbursement(session, employee_id, reimbursement_id):
    return (await session.exec(select(SampleReimbursement).where(
        SampleReimbursement.id == reimbursement_id, SampleReimbursement.employee_id == employee_id,
        SampleReimbursement.deleted_at.is_(None)))).first()


async def own_result(session, request, user):
    return (await session.exec(select(SampleReimbursement).where(SampleReimbursement.id == request.reimbursement_id,
                              SampleReimbursement.employee_id == request.employee_id, SampleReimbursement.org_id == request.org_id,
                              SampleReimbursement.deleted_at.is_(None)))).first()


async def insert(session, row):
    session.add(row)
    await session.flush()
    return row


async def software_claim_by_key(session, user_id, key):
    return (await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.user_id == user_id, SoftwareClaim.request_key == key,
        SoftwareClaim.deleted_at.is_(None)))).first()


async def own_software_claim(session, user_id, claim_id):
    return (await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.id == claim_id, SoftwareClaim.user_id == user_id,
        SoftwareClaim.deleted_at.is_(None)).with_for_update())).first()


async def own_software_claims(session, user_id, employee_id):
    """本人软件报销：含待核对与已确认；不含已失效版本。"""
    return list((await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.user_id == user_id, SoftwareClaim.employee_id == employee_id,
        SoftwareClaim.status_code.in_(["preparing", "ready", "approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None))
        .order_by(SoftwareClaim.period_month.desc(), SoftwareClaim.created_at.desc()).limit(50))).all())


async def active_software_claim(session, employee_id, period_month):
    return (await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.employee_id == employee_id, SoftwareClaim.period_month == period_month,
        SoftwareClaim.status_code.in_(["preparing", "ready", "approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None)).with_for_update())).first()


async def software_claim_items(session, claim_id):
    return list((await session.exec(select(SoftwareClaimItem).where(
        SoftwareClaimItem.claim_id == claim_id, SoftwareClaimItem.deleted_at.is_(None)
    ).order_by(SoftwareClaimItem.sort_no, SoftwareClaimItem.id))).all())


async def software_claim_files(session, claim_id):
    return list((await session.exec(select(SoftwareClaimFile).where(
        SoftwareClaimFile.claim_id == claim_id, SoftwareClaimFile.deleted_at.is_(None)
    ).order_by(SoftwareClaimFile.id).with_for_update())).all())


async def software_claims_for_org_month(session, org_id, period_month):
    """管理端查看：当前有效的软件报销（不含已失效的旧版本）。"""
    return list((await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.org_id == org_id, SoftwareClaim.period_month == period_month,
        SoftwareClaim.status_code.in_(["preparing", "ready", "approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None)).order_by(SoftwareClaim.created_at))).all())


async def page_software_claims_for_orgs(session, org_ids, period_month, *, page: int, page_size: int):
    """管理端：多组织 + 工资月分页。"""
    from sqlalchemy import func
    if not org_ids:
        return 0, []
    conditions = [
        SoftwareClaim.org_id.in_(org_ids),
        SoftwareClaim.period_month == period_month,
        SoftwareClaim.status_code.in_(["preparing", "ready", "approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None),
    ]
    total = (await session.exec(select(func.count()).select_from(SoftwareClaim).where(*conditions))).one()
    rows = list((await session.exec(
        select(SoftwareClaim).where(*conditions)
        .order_by(SoftwareClaim.created_at.desc(), SoftwareClaim.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    return int(total or 0), rows


async def page_own_software_claims(session, user_id, employee_id, *, page: int, page_size: int):
    """员工端：本人软件报销分页。"""
    from sqlalchemy import func
    conditions = [
        SoftwareClaim.user_id == user_id,
        SoftwareClaim.employee_id == employee_id,
        SoftwareClaim.status_code.in_(["preparing", "ready", "approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None),
    ]
    total = (await session.exec(select(func.count()).select_from(SoftwareClaim).where(*conditions))).one()
    rows = list((await session.exec(
        select(SoftwareClaim).where(*conditions)
        .order_by(SoftwareClaim.period_month.desc(), SoftwareClaim.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    return int(total or 0), rows


async def page_own_reimbursements(session, employee_id, *, page: int, page_size: int):
    """员工端：本人正式费用报销分页。"""
    from sqlalchemy import func
    conditions = [SampleReimbursement.employee_id == employee_id, SampleReimbursement.deleted_at.is_(None)]
    total = (await session.exec(select(func.count()).select_from(SampleReimbursement).where(*conditions))).one()
    rows = list((await session.exec(
        select(SampleReimbursement).where(*conditions)
        .order_by(SampleReimbursement.occurred_on.desc(), SampleReimbursement.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    return int(total or 0), rows


async def software_claims_for_period(session, org_id, period_month):
    return list((await session.exec(select(SoftwareClaim).where(
        SoftwareClaim.org_id == org_id, SoftwareClaim.period_month == period_month,
        SoftwareClaim.status_code.in_(["approved", "applied"]),
        SoftwareClaim.deleted_at.is_(None)))).all())
