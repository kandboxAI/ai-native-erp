"""离线导入的持久化和受权限约束的来源台账查询。只写快盒拥有的数据。"""
from uuid import UUID
from sqlalchemy import text
from sqlmodel import select

from app.auth.scope_filters import alive_condition, table_scope_condition
from app.modules.organization.models import SysOrg
from .import_models import FinanceImportRow
from .models import SampleEmployee, SampleProject, SampleContract, SampleReceipt


async def organization_options(session, user):
    # 跨模块只读契约：仅组织id/name/编号，使用调用者的sample_app权限范围。
    condition = table_scope_condition(SysOrg, user, "sample_app:access")
    query = select(SysOrg).where(alive_condition(SysOrg), SysOrg.is_active.is_(True))
    if condition is not None:
        query = query.where(condition)
    return [{"id": str(row.id), "org_name": row.org_name} for row in (await session.exec(query.order_by(SysOrg.org_name))).all()]


async def source_rows(session, user, org_id: UUID):
    condition = table_scope_condition(FinanceImportRow, user, "sample_app:history")
    query = select(FinanceImportRow).where(FinanceImportRow.org_id == org_id, alive_condition(FinanceImportRow))
    if condition is not None:
        query = query.where(condition)
    return list((await session.exec(query.order_by(FinanceImportRow.sheet_name, FinanceImportRow.row_no).limit(500))).all())


async def lock_import(session, schema: str, org_id: UUID):
    await session.execute(text("select pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"sample_app_import:{schema}:{org_id}"})
    # 只校验目标组织存在，不更改底座组织数据。
    org = await session.get(SysOrg, org_id)
    if org is None or org.deleted_at is not None or not org.is_active:
        raise ValueError("目标组织不存在或已停用")


async def imported_rows(session, org_id: UUID):
    return list((await session.exec(select(FinanceImportRow).where(FinanceImportRow.org_id == org_id, alive_condition(FinanceImportRow)))).all())


async def business_is_empty(session, org_id: UUID):
    for model in (SampleEmployee, SampleProject, SampleContract, SampleReceipt):
        if (await session.exec(select(model.id).where(model.org_id == org_id, alive_condition(model)).limit(1))).first():
            return False
    return True


async def insert(session, model, org_id: UUID, **values):
    row = model(org_id=org_id, **values)
    session.add(row)
    await session.flush()
    return row
