"""业务待办同步使用的底座读取契约，不读取业务表。"""
from sqlalchemy import Uuid, false, inspect, literal
from sqlmodel import select

from app.auth.models import AuthMembership, AuthTenant, AuthUser
from app.framework.db.tenant import get_tenant_schema
from app.modules.user_profile.models import SysUser
from .models import SysTodo, SysTodoAssignee


def empty_sources():
    return select(literal(None, type_=Uuid)).where(false())


async def tables_available(session, *tables):
    key = ("todo_source_tables", get_tenant_schema())
    if key not in session.info:
        def names(sync):
            connection = sync.connection()
            schema = get_tenant_schema() if connection.dialect.name == "postgresql" else None
            return set(inspect(connection).get_table_names(schema=schema))
        session.info[key] = await session.run_sync(names)
    return set(tables) <= session.info[key]


async def login_accounts(session, user_ids=None):
    """仅当前租户的有效登录成员；投影限于构造权限上下文所需字段。"""
    stmt = select(SysUser, AuthTenant).join(AuthUser, AuthUser.id == SysUser.auth_user_id).join(
        AuthMembership, AuthMembership.auth_user_id == AuthUser.id,
    ).join(AuthTenant, AuthTenant.id == AuthMembership.tenant_id).where(
        AuthTenant.schema_name == get_tenant_schema(), AuthTenant.is_active.is_(True),
        AuthMembership.is_active.is_(True), AuthUser.is_active.is_(True),
        SysUser.is_active.is_(True), SysUser.deleted_at.is_(None),
    )
    if user_ids is not None:
        stmt = stmt.where(SysUser.id.in_(user_ids))
    return (await session.exec(stmt)).all()


async def pending_source(session, type_key, source_id):
    rows = (await session.exec(select(SysTodo, SysTodoAssignee).outerjoin(
        SysTodoAssignee, SysTodoAssignee.todo_id == SysTodo.id,
    ).where(SysTodo.todo_type_key == type_key, SysTodo.source_id == source_id,
            SysTodo.status_code == "pending"))).all()
    result = {}
    for todo, assignee in rows:
        _, assignees = result.setdefault(todo.id, (todo, {}))
        if assignee is not None:
            assignees[assignee.user_id] = assignee
    return list(result.values())


def pending_source_ids(type_keys):
    return select(SysTodo.source_id).where(SysTodo.todo_type_key.in_(type_keys), SysTodo.status_code == "pending")
