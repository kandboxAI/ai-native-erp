"""查询本人的偏好/角色，以及当前租户统一配置的角色模板。"""
from sqlalchemy import select
from app.framework.db.models import utc_now

from app.modules.role.models import SysRole
from app.modules.user_role.models import SysUserRole
from .context_models import AiPromptTemplate, AiUserPreference, AiUserTemplatePreference


async def template_preferences(session, user):
    return (await session.execute(select(AiUserTemplatePreference).where(
        AiUserTemplatePreference.user_id == user.user_id,
    ))).scalars().all()


async def save_template_preference(session, user, template_id, is_active):
    row = (await session.execute(select(AiUserTemplatePreference).where(
        AiUserTemplatePreference.user_id == user.user_id,
        AiUserTemplatePreference.template_id == template_id,
    ))).scalar_one_or_none()
    if row is None:
        row = AiUserTemplatePreference(user_id=user.user_id, org_id=user.org_id,
                                       template_id=template_id, created_by=user.user_id)
    row.is_active = is_active
    row.updated_by = user.user_id
    row.updated_at = utc_now()
    session.add(row)
    await session.flush()
    return row


async def preference(session, user):
    return (await session.execute(select(AiUserPreference).where(AiUserPreference.user_id == user.user_id))).scalar_one_or_none()


async def save_preference(session, user, instructions):
    row = await preference(session, user)
    if row is None:
        row = AiUserPreference(user_id=user.user_id, org_id=user.org_id, created_by=user.user_id)
    row.instructions = instructions
    row.updated_by = user.user_id
    row.updated_at = utc_now()
    session.add(row)
    await session.flush()
    return row


async def templates(session):
    # 租户由会话 search_path 隔离；模板在租户内共享，不按用户主组织过滤。
    return (await session.execute(select(AiPromptTemplate).where(
        AiPromptTemplate.role_id.is_not(None),
        AiPromptTemplate.position_id.is_(None), AiPromptTemplate.context_key.is_(None),
    ).order_by(AiPromptTemplate.created_at, AiPromptTemplate.id))).scalars().all()


async def role_ids(session, user):
    return set((await session.execute(select(SysRole.id).join(
        SysUserRole, SysUserRole.role_id == SysRole.id,
    ).where(SysUserRole.user_id == user.user_id, SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)))).scalars().all())


async def target_options(session, user):
    # 只发布启用的租户共享角色标识和名称，供已授权管理员选择。
    roles = (await session.execute(select(SysRole.id, SysRole.role_name).where(
        SysRole.deleted_at.is_(None), SysRole.is_active.is_(True),
    ).order_by(SysRole.role_name))).all()
    return {"roles": [{"id": str(row[0]), "name": row[1]} for row in roles]}


async def save_template(session, user, payload, template_id=None):
    row = None
    if template_id is not None:
        row = (await session.execute(select(AiPromptTemplate).where(
            AiPromptTemplate.id == template_id,
        ))).scalar_one_or_none()
        if row is None:
            return None
    if row is None:
        row = AiPromptTemplate(org_id=user.org_id, created_by=user.user_id, **payload.model_dump())
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    # 历史字段保留在数据库中；角色模板保存时清空其他匹配条件。
    row.position_id = None
    row.context_key = None
    row.updated_by = user.user_id
    row.updated_at = utc_now()
    session.add(row)
    await session.flush()
    return row


async def seed_tenant(session, schema):
    """维护脚本只允许处理已登记且启用的租户。"""
    from app.auth.models import AuthTenant

    return (await session.execute(select(AuthTenant).where(
        AuthTenant.schema_name == schema, AuthTenant.is_active.is_(True),
    ))).scalar_one_or_none()


async def seed_org_and_actor(session, org_no=None):
    """读取种子目标组织和审计动作人；不创建组织、账号或授权。"""
    from app.modules.organization.models import SysOrg
    from app.modules.user_profile.models import SysUser

    query = select(SysOrg).where(SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True))
    query = query.where(SysOrg.org_no == org_no) if org_no else query.where(SysOrg.parent_id.is_(None))
    organizations = (await session.execute(query)).scalars().all()
    if len(organizations) != 1:
        raise ValueError("目标组织不存在或根组织不唯一，请通过 --org-no 指定已启用组织")
    # 内置管理员仅作为本地维护的审计动作人，不用于网络接口的权限旁路。
    actor = (await session.execute(select(SysUser, SysRole.id).join(
        SysUserRole, SysUserRole.user_id == SysUser.id,
    ).join(SysRole, SysRole.id == SysUserRole.role_id).where(
        SysRole.is_builtin.is_(True), SysRole.deleted_at.is_(None), SysRole.is_active.is_(True),
        SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
    ).order_by(SysUser.created_at, SysUser.id).limit(1))).first()
    if actor is None:
        raise ValueError("租户缺少可用的内置管理员，无法记录模板导入动作人")
    return organizations[0], actor[0], actor[1]
