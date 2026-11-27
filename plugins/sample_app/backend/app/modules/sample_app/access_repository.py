"""插件组织访问查询；复用底座权限范围，不改写登录身份。"""
from sqlmodel import select
from app.auth.scope_filters import scoped_conditions
from app.modules.organization.models import SysOrg
from .import_models import FinanceImportRow

async def organizations(session, user, selected=None, permission="sample_app:access"):
    query = select(SysOrg.id, SysOrg.org_name).where(*scoped_conditions(SysOrg, user, permission), SysOrg.is_active.is_(True))
    if selected is not None:
        query = query.where(SysOrg.id == selected)
    return [{"id": identity, "org_name": name} for identity, name in (await session.exec(query.order_by(SysOrg.org_name))).all()]

async def record_org(session, user, model, identity, selected=None):
    query = select(model.org_id).where(model.id == identity, *scoped_conditions(model, user, "sample_app:access"))
    if selected is not None:
        query = query.where(model.org_id == selected)
    return (await session.exec(query)).first()

async def history(session, user, selected=None):
    query = select(FinanceImportRow).where(*scoped_conditions(FinanceImportRow, user, "sample_app:history"), *scoped_conditions(FinanceImportRow, user, "sample_app:access"))
    if selected is not None:
        query = query.where(FinanceImportRow.org_id == selected)
    return list((await session.exec(query.order_by(FinanceImportRow.org_id, FinanceImportRow.sheet_name, FinanceImportRow.row_no))).all())
