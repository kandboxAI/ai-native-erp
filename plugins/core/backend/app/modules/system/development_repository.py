"""开发同步的底座初始化检查；不创建组织、账号或授权关系。"""
from sqlalchemy import select

from app.modules.organization.models import SysOrg
from app.modules.role.models import SysRole
from app.modules.user_profile.models import SysUser
from app.modules.user_role.models import SysUserRole


async def has_initialized_admin(session) -> bool:
    root = await session.scalar(select(SysOrg.id).where(
        SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
    ).limit(1))
    if root is None:
        return False
    admin = await session.scalar(select(SysUser.id).join(SysUserRole, SysUserRole.user_id == SysUser.id).join(
        SysRole, SysRole.id == SysUserRole.role_id,
    ).where(
        SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
        SysRole.is_builtin.is_(True), SysRole.data_scope_code == "all",
        SysRole.deleted_at.is_(None), SysRole.is_active.is_(True),
    ).limit(1))
    return admin is not None
