"""快盒删除查询：授权范围、关联检查及软删除持久化。"""
from sqlmodel import SQLModel, select
from app.auth.scope_filters import scoped_conditions
from .models import SamplePayroll


async def owned_row(session, model, user, identity, selected_org=None):
    query = select(model).where(model.id == identity, *scoped_conditions(model, user, "sample_app:access"))
    if selected_org is not None:
        query = query.where(model.org_id == selected_org)
    return (await session.exec(query.with_for_update())).first()


async def has_references(session, model, identity, *, exclude_tables=()):
    # 仅查询本插件已注册的实体关系，不跨模块写入、级联删除或暴露关联内容。
    target = f"{model.__tablename__}.id"
    for table in SQLModel.metadata.tables.values():
        if not table.name.startswith("sample_app_") or table.name in exclude_tables:
            continue
        for fk in table.foreign_keys:
            if fk.target_fullname != target:
                continue
            query = select(table.c.id).where(fk.parent == identity)
            if "deleted_at" in table.c:
                query = query.where(table.c.deleted_at.is_(None))
            if (await session.exec(query.limit(1))).first() is not None:
                return True
    return False


async def has_payroll_since(session, org_id, period):
    query = select(SamplePayroll.id).where(SamplePayroll.org_id == org_id,
        SamplePayroll.deleted_at.is_(None), SamplePayroll.period_month >= period).limit(1)
    return (await session.exec(query)).first() is not None


def mark_deleted(session, row, user_id, now):
    row.deleted_at, row.deleted_by = now, user_id
    row.updated_at, row.updated_by = now, user_id
    session.add(row)


async def other_versions(session, model, row):
    query = select(model).where(model.org_id == row.org_id, model.employee_id == row.employee_id,
        model.id != row.id, model.deleted_at.is_(None)).with_for_update()
    return list((await session.exec(query)).all())


def restore_version_end(session, row, end, user_id, now):
    row.valid_to, row.updated_by, row.updated_at = end, user_id, now
    session.add(row)
