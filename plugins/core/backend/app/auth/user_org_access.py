from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, or_

from app.auth.data_scope import ORG_ACCESS_ALL
from app.modules.user_profile.models import SysUser, SysUserOrg


def user_can_access_org_condition(org_id: UUID):
    """SQL 条件：租户内用户可以访问指定组织（组织访问方式为全部，或在用户可访问组织中）。"""
    return or_(
        SysUser.org_access_mode_code == ORG_ACCESS_ALL,
        exists()
        .where(SysUserOrg.user_id == SysUser.id, SysUserOrg.org_id == org_id)
        .correlate(SysUser),
    )
