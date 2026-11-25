"""业务单据的人员显示契约；联系方式只允许读取当前登录人本人。"""
from app.auth.scope_filters import ensure_org_access

from .repository import repository


async def _business_assignee(session, account, department_name, current_user, org_id, required_permissions, require_department):
    from app.auth.repository import repository as authorization
    from app.auth.schemas import AuthenticatedUser
    from app.core.exceptions import AppException
    from app.framework.deployment import blocked_plugin_module_codes
    if require_department and not department_name:
        return None
    enabled = current_user.enabled_plugin_keys
    grants = await authorization.get_grants(session, account.id, blocked_plugin_module_codes(enabled))
    grants = await authorization.extend_grants(session, account, grants, enabled)
    memberships = await authorization.get_user_orgs(session, account.id)
    candidate = AuthenticatedUser(auth_user_id=account.auth_user_id, tenant_id=current_user.tenant_id,
        tenant_no=current_user.tenant_no, tenant_schema=current_user.tenant_schema, user_id=account.id,
        org_id=account.org_id, org_ids=[row.org_id for row in memberships], org_access_mode_code=account.org_access_mode_code,
        department_id=account.department_id, permissions=grants.permissions, permission_scopes=grants.permission_scopes)
    for key in required_permissions:
        if key in candidate.permissions:
            try:
                ensure_org_access(candidate, org_id, key)
            except AppException:
                continue
            return {"id": account.id, "name": account.display_name, "department_id": account.department_id,
                    "department_name": department_name}
    return None


async def business_assignee_options(session, current_user, org_id, permission, *, required_permissions, keyword="", require_department=False):
    """授权业务组织内可办理指定动作的账号；按真实有效授权校验，不按角色名判断。"""
    from app.core.exceptions import AppException
    if permission not in current_user.permissions:
        raise AppException("无权选择业务人员", 403)
    ensure_org_access(current_user, org_id, permission)
    result = []
    for account, department in await repository.business_assignees(session, tenant_id=current_user.tenant_id, keyword=keyword):
        item = await _business_assignee(session, account, department, current_user, org_id, required_permissions, require_department)
        if item:
            result.append(item)
        if len(result) == 50:
            break
    return result


async def business_assignee_reference(session, current_user, org_id, permission, user_id, *, required_permissions, require_department=False):
    """提交时重新校验指定账号、当前成员资格、部门、有效权限及业务组织范围。"""
    from app.core.exceptions import AppException
    if permission not in current_user.permissions:
        raise AppException("无权引用业务人员", 403)
    ensure_org_access(current_user, org_id, permission)
    rows = await repository.business_assignees(session, tenant_id=current_user.tenant_id, user_id=user_id, limit=1)
    item = await _business_assignee(session, *rows[0], current_user, org_id, required_permissions, require_department) if rows else None
    if item is None:
        raise AppException("所选账号已停用、部门无效或无权办理该组织业务，请重新选择", 409)
    return item


async def current_contact(session, current_user):
    """供业务表单默认带出本人姓名、电话，不接收客户端人员 ID。"""
    row = await repository.current_contact(session, current_user.user_id, current_user.auth_user_id)
    return dict(row) if row else {"contact_name": "", "contact_phone": ""}


async def business_account_choices(session, current_user, org_id, permission, *, keyword="", user_ids=None):
    """按调用方动作范围读取组织内有效账号；指定 ID 时加锁重新校验，仅发布姓名和部门。

    引用参与人员无需对方具有办理业务的权限；账号、租户成员及组织必须有效。
    self 按账号本身匹配，related 无提供器时拒绝，均复用用户范围契约。
    """
    from app.core.exceptions import AppException
    from .service import scope_condition
    if permission not in current_user.permissions:
        raise AppException("无权选择业务账号", 403)
    ensure_org_access(current_user, org_id, permission)
    if user_ids is not None and not user_ids:
        return []
    rows = await repository.business_assignees(
        session, tenant_id=current_user.tenant_id, org_id=org_id,
        condition=scope_condition(current_user, permission), keyword=keyword,
        user_ids=user_ids, for_update=user_ids is not None,
        limit=len(user_ids) if user_ids is not None else 51,
    )
    return [{"user_id": account.id, "display_name": account.display_name,
             "department_name": department} for account, department in rows]


async def list_assignee_options(session, user, org_id, permission: str, keyword: str = "", limit: int = 50):
    """调用方先验证业务权限/单据范围；此处再次验证可访问组织。"""
    ensure_org_access(user, org_id, permission)
    return [dict(row) for row in await repository.assignee_options(session, org_id, keyword, min(max(limit, 1), 50))]


async def user_display_names(session, user_ids):
    """只为已通过范围校验的业务单据补齐人员显示名，不作为人员搜索接口。"""
    return await repository.display_names(session, user_ids)


def user_name_matching_ids(keyword: str):
    """按显示名匹配的 ID 查询契约；不能直接作为人员列表返回，业务方须叠加自身权限范围。"""
    return repository.name_matching_ids(keyword)
