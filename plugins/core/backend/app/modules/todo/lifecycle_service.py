"""业务拥有来源行锁和事务，底座提供账号解析及单来源待办生命周期。"""
from app.auth.data_scope import ORG_ACCESS_ALL, normalize_org_access_mode
from app.auth.plugin_repository import repository as plugins
from app.auth.repository import repository as auth
from app.auth.schemas import AuthenticatedUser
from app.framework.db.ids import uuid7
from app.framework.deployment import blocked_plugin_module_codes, effective_plugin_keys
from . import lifecycle_repository as repository
from . import service as todos

tables_available = repository.tables_available
pending_source_ids = repository.pending_source_ids
empty_sources = repository.empty_sources


async def recipient_contexts(session, user_ids=None):
    # 缓存只存在于本次业务事务/扫描会话，下一轮重新计算有效权限。
    key = ("todo_recipient_contexts", None if user_ids is None else frozenset(user_ids))
    if key not in session.info:
        result = {}
        enabled_by_tenant = {}
        for account, tenant in await repository.login_accounts(session, user_ids):
            if tenant.id not in enabled_by_tenant:
                enabled_by_tenant[tenant.id] = effective_plugin_keys(await plugins.active_keys(session, tenant.id))
            enabled = enabled_by_tenant[tenant.id]
            grants = await auth.get_grants(session, account.id, blocked_plugin_module_codes(enabled))
            grants = await auth.extend_grants(session, account, grants, enabled)
            organizations = await auth.get_user_orgs(session, account.id)
            primary = next((row for row in organizations if row.is_primary), organizations[0] if organizations else None)
            mode = normalize_org_access_mode(account.org_access_mode_code)
            result[account.id] = AuthenticatedUser(
                auth_user_id=account.auth_user_id, tenant_id=tenant.id,
                tenant_no=tenant.tenant_no, tenant_schema=tenant.schema_name,
                user_id=account.id, org_id=primary.org_id if primary else account.org_id,
                org_ids=[] if mode == ORG_ACCESS_ALL else [row.org_id for row in organizations],
                org_access_mode_code=mode,
                department_id=account.department_id, permissions=grants.permissions,
                permission_scopes=grants.permission_scopes, data_scope_code=grants.data_scope_code,
                enabled_plugin_keys=list(enabled),
            )
        session.info[key] = result
    return session.info[key]


async def sync_source(session, *, type_key, row, active, user_ids, title, summary,
                      completion_status="completed", actor_id=None, arrived_at=None):
    """调用者须先锁住来源行；后台和业务操作按同一锁序串行，不重复开轮次。"""
    pending = await repository.pending_source(session, type_key, row.id)
    if not active:
        for todo, _ in pending:
            await todos.finish(session, todo, status_code=completion_status, user_id=actor_id)
        return
    values = dict(title=title[:256], summary=summary, priority_code="important", due_at=None)
    if pending:
        todo, assignees = pending[0]
        await todos.refresh_pending(session, todo, assignees, set(user_ids), **values)
        for duplicate, _ in pending[1:]:
            await todos.finish(session, duplicate, status_code="cancelled", user_id=actor_id)
    elif user_ids:
        await todos.publish(
            session, todo_type_key=type_key, source_id=row.id, org_id=row.org_id,
            dedup_key=f"{type_key}:{row.id}:{uuid7()}", user_ids=set(user_ids),
            arrived_at=arrived_at or row.updated_at or row.created_at,
            created_by=actor_id, updated_by=actor_id, **values,
        )
