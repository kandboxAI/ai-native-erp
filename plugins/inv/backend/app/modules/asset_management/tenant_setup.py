"""资产管理默认角色授权；只补缺失授权，不覆盖学校配置。"""

from sqlmodel import select

from app.modules.menu.models import SysMenu
from app.modules.miniapp_menu.models import SysMiniappMenu
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_menu.models import SysRoleMenu
from app.modules.role_miniapp_menu.models import SysRoleMiniappMenu
from app.modules.role_permission.models import SysRolePermission


DEFAULTS = {
    "asset_register:confirm": {"logistics"},
    "asset_register:void": {"logistics"},
    "asset_handover:list": {"logistics"},
    "asset_handover:create": {"logistics"},
    "asset_handover:manage": {"logistics"},
    "asset_handover:receive": {"logistics"},
    "asset_handover:mine": {"teacher", "homeroom_teacher"},
}


async def setup_tenant(session, ctx) -> None:
    del ctx
    permissions = (
        await session.exec(
            select(SysPermission).where(
                SysPermission.permission_key.in_(DEFAULTS),
                SysPermission.deleted_at.is_(None),
            )
        )
    ).all()
    roles = (
        await session.exec(
            select(SysRole).where(SysRole.deleted_at.is_(None), SysRole.is_active.is_(True))
        )
    ).all()
    existing = set(
        (await session.exec(select(SysRolePermission.role_id, SysRolePermission.permission_id))).all()
    )
    for permission in permissions:
        for role in roles:
            key = (role.id, permission.id)
            if role.role_no in DEFAULTS[permission.permission_key] and key not in existing:
                session.add(SysRolePermission(role_id=role.id, permission_id=permission.id))
                existing.add(key)

    receipt_roles = [role for role in roles if role.role_no in {"teacher", "homeroom_teacher"}]
    receipt_menu = (
        await session.exec(
            select(SysMenu).where(
                SysMenu.menu_key == "EduMyAssetHandovers",
                SysMenu.deleted_at.is_(None),
            )
        )
    ).first()
    if receipt_menu is not None:
        menus = {row.id: row for row in (await session.exec(select(SysMenu))).all()}
        menu_ids = {receipt_menu.id}
        parent_id = receipt_menu.parent_id
        while parent_id is not None and parent_id not in menu_ids:
            menu_ids.add(parent_id)
            parent_id = menus.get(parent_id).parent_id if menus.get(parent_id) else None
        existing_role_menus = set(
            (await session.exec(select(SysRoleMenu.role_id, SysRoleMenu.menu_id))).all()
        )
        for role in receipt_roles:
            for menu_id in menu_ids:
                key = (role.id, menu_id)
                if key not in existing_role_menus:
                    session.add(SysRoleMenu(role_id=role.id, menu_id=menu_id))
                    existing_role_menus.add(key)

    miniapp_menu = (
        await session.exec(
            select(SysMiniappMenu).where(
                SysMiniappMenu.portal_code == "teacher",
                SysMiniappMenu.menu_key == "asset_handover_mine",
                SysMiniappMenu.deleted_at.is_(None),
            )
        )
    ).first()
    if miniapp_menu is not None:
        existing_miniapp_menus = set(
            (
                await session.exec(
                    select(
                        SysRoleMiniappMenu.role_id,
                        SysRoleMiniappMenu.miniapp_menu_id,
                    )
                )
            ).all()
        )
        for role in receipt_roles:
            key = (role.id, miniapp_menu.id)
            if key not in existing_miniapp_menus:
                session.add(
                    SysRoleMiniappMenu(
                        role_id=role.id,
                        miniapp_menu_id=miniapp_menu.id,
                    )
                )
                existing_miniapp_menus.add(key)
    await session.flush()
