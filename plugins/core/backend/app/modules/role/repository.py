from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.data_scope import DATA_SCOPE_ALL, normalize_data_scope
from app.auth.schemas import AuthenticatedUser
from app.modules.masterdata.models import MdPerson
from app.modules.menu.models import SysMenu
from app.modules.permission.models import SysPermission
from app.modules.rbac_repository_utils import normalize_uuid, utc_now
from app.modules.role_menu.models import SysRoleMenu
from app.modules.role_miniapp_menu.models import SysRoleMiniappMenu
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_profile.models import SysUser
from app.modules.user_role.models import SysUserRole

from .models import SysRole
from .permission_template import RoleTemplateRow
from .schemas import (
    RoleDetailItem,
    RoleListItem,
    RoleListQuery,
    RoleMenuItem,
    RolePermissionConfig,
    RolePermissionConfigItem,
    RolePermissionItem,
    RolePermissionTemplateImportResult,
    RoleUserItem,
)


def is_builtin_admin(role: SysRole) -> bool:
    """内置管理员：内置且数据范围为全部（开通租户时创建，被授予全部权限）。"""
    return bool(role.is_builtin) and role.data_scope_code == DATA_SCOPE_ALL


def _alive_user_count():
    return (
        select(func.count())
        .select_from(SysUserRole)
        .join(SysUser, SysUser.id == SysUserRole.user_id)
        .where(SysUserRole.role_id == SysRole.id, SysUser.deleted_at.is_(None))
        .correlate(SysRole)
        .scalar_subquery()
    )


def _permission_count():
    return (
        select(func.count())
        .select_from(SysRolePermission)
        .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
        .where(SysRolePermission.role_id == SysRole.id, SysPermission.deleted_at.is_(None))
        .correlate(SysRole)
        .scalar_subquery()
    )


def _menu_count():
    return (
        select(func.count())
        .select_from(SysRoleMenu)
        .join(SysMenu, SysMenu.id == SysRoleMenu.menu_id)
        .where(SysRoleMenu.role_id == SysRole.id, SysMenu.deleted_at.is_(None))
        .correlate(SysRole)
        .scalar_subquery()
    )


class RoleRepository:
    @staticmethod
    def _conditions(params: RoleListQuery) -> list[Any]:
        conditions: list[Any] = [SysRole.deleted_at.is_(None)]
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            conditions.append(
                or_(SysRole.role_no.ilike(keyword), SysRole.role_name.ilike(keyword), func.coalesce(SysRole.description, "").ilike(keyword))
            )
        if params.role_no:
            conditions.append(SysRole.role_no.ilike(f"%{params.role_no.strip()}%"))
        if params.role_name:
            conditions.append(SysRole.role_name.ilike(f"%{params.role_name.strip()}%"))
        if params.is_active is not None:
            conditions.append(SysRole.is_active.is_(params.is_active))
        return conditions

    async def list(self, session: AsyncSession, params: RoleListQuery) -> dict[str, Any]:
        conditions = self._conditions(params)
        total = int((await session.execute(select(func.count()).select_from(SysRole).where(*conditions))).scalar_one() or 0)
        user_count = _alive_user_count().label("user_count")
        permission_count = _permission_count().label("permission_count")
        menu_count = _menu_count().label("menu_count")
        sort_map = {
            "updated_at": SysRole.updated_at,
            "created_at": SysRole.created_at,
            "role_no": SysRole.role_no,
            "role_name": SysRole.role_name,
            "user_count": user_count,
            "permission_count": permission_count,
        }
        order = sort_map[params.sort_by]
        order = order.asc() if params.sort_order == "asc" else order.desc()
        statement = (
            select(SysRole, user_count, permission_count, menu_count)
            .where(*conditions)
            .order_by(SysRole.is_builtin.desc(), order, SysRole.id)
            .limit(params.page_size)
            .offset((params.page - 1) * params.page_size)
        )
        items = []
        for role, users, permissions, menus in (await session.execute(statement)).all():
            item = RoleListItem.model_validate(role)
            item.user_count, item.permission_count, item.menu_count = int(users or 0), int(permissions or 0), int(menus or 0)
            items.append(item.model_dump(mode="json"))
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def get(self, session: AsyncSession, item_id: str | UUID, *, for_update: bool = False) -> SysRole | None:
        statement = select(SysRole).where(SysRole.id == normalize_uuid(item_id), SysRole.deleted_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    async def detail(self, session: AsyncSession, item_id: str | UUID) -> RoleDetailItem | None:
        role = await self.get(session, item_id)
        if role is None:
            return None
        permission_rows = (
            await session.execute(
                select(
                    SysPermission.id,
                    SysPermission.permission_key,
                    SysPermission.permission_name,
                    SysPermission.module_code,
                    SysRolePermission.data_scope_code,
                )
                .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
                .where(SysRolePermission.role_id == role.id, SysPermission.deleted_at.is_(None))
                .order_by(SysPermission.module_code, SysPermission.permission_key)
            )
        ).all()
        menu_rows = (
            await session.execute(
                select(SysMenu.id, SysMenu.menu_key, SysMenu.menu_name, SysMenu.menu_type_code, SysMenu.path)
                .join(SysRoleMenu, SysRoleMenu.menu_id == SysMenu.id)
                .where(SysRoleMenu.role_id == role.id, SysMenu.deleted_at.is_(None))
                .order_by(SysMenu.sort_no.nulls_last(), SysMenu.menu_key)
            )
        ).all()
        user_rows = (
            await session.execute(
                select(SysUser.id, SysUser.display_name, MdPerson.full_name)
                .join(SysUserRole, SysUserRole.user_id == SysUser.id)
                .outerjoin(MdPerson, and_(MdPerson.user_id == SysUser.id, MdPerson.deleted_at.is_(None)))
                .where(SysUserRole.role_id == role.id, SysUser.deleted_at.is_(None))
                .order_by(SysUser.display_name)
            )
        ).all()
        miniapp_ids = (
            await session.execute(select(SysRoleMiniappMenu.miniapp_menu_id).where(SysRoleMiniappMenu.role_id == role.id))
        ).scalars().all()
        item = RoleDetailItem.model_validate(role)
        item.permissions = [
            RolePermissionItem(
                id=row.id,
                permission_key=row.permission_key,
                permission_name=row.permission_name,
                module_code=row.module_code,
                data_scope_code=normalize_data_scope(row.data_scope_code or role.data_scope_code),
                is_scope_overridden=row.data_scope_code is not None,
            )
            for row in permission_rows
        ]
        item.menus = [RoleMenuItem(**row._mapping) for row in menu_rows]
        item.users = [RoleUserItem(**row._mapping) for row in user_rows]
        item.miniapp_menu_ids = list(miniapp_ids)
        item.permission_count, item.menu_count, item.user_count = len(item.permissions), len(item.menus), len(item.users)
        return item

    async def permission_config(self, session: AsyncSession, item_id: str, blocked_module_codes: set[str] | None = None) -> RolePermissionConfig | None:
        role = await self.get(session, item_id)
        if role is None:
            return None
        statement = (
            select(
                SysPermission.id,
                SysPermission.permission_key,
                SysPermission.permission_name,
                SysPermission.module_code,
                SysRolePermission.id.label("binding_id"),
                SysRolePermission.data_scope_code,
            )
            .outerjoin(
                SysRolePermission,
                and_(SysRolePermission.permission_id == SysPermission.id, SysRolePermission.role_id == role.id),
            )
            .where(SysPermission.deleted_at.is_(None), SysPermission.is_active.is_(True))
            .order_by(SysPermission.module_code, SysPermission.permission_key)
        )
        if blocked_module_codes:
            statement = statement.where(SysPermission.module_code.not_in(blocked_module_codes))
        rows = (await session.execute(statement)).all()
        return RolePermissionConfig(
            role=RoleListItem.model_validate(role),
            permissions=[
                RolePermissionConfigItem(
                    id=row.id,
                    permission_key=row.permission_key,
                    permission_name=row.permission_name,
                    module_code=row.module_code,
                    selected=row.binding_id is not None,
                    data_scope_code=normalize_data_scope(row.data_scope_code or role.data_scope_code),
                )
                for row in rows
            ],
        )

    async def exists_by_no(self, session: AsyncSession, role_no: str, exclude_id: UUID | None = None) -> bool:
        conditions = [SysRole.role_no == role_no, SysRole.deleted_at.is_(None)]
        if exclude_id is not None:
            conditions.append(SysRole.id != exclude_id)
        return (await session.execute(select(SysRole.id).where(*conditions).limit(1))).scalar_one_or_none() is not None

    async def create(self, session: AsyncSession, payload: dict[str, Any], current_user: AuthenticatedUser) -> SysRole:
        role = SysRole(**payload, is_builtin=False, created_by=current_user.user_id, updated_by=current_user.user_id)
        session.add(role)
        await session.commit()
        return role

    async def update(self, session: AsyncSession, role: SysRole, payload: dict[str, Any], current_user: AuthenticatedUser) -> None:
        for column, value in payload.items():
            setattr(role, column, value)
        role.updated_by = current_user.user_id
        role.updated_at = utc_now()
        session.add(role)
        await session.commit()

    async def count_users(self, session: AsyncSession, role_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(SysUserRole)
            .join(SysUser, SysUser.id == SysUserRole.user_id)
            .where(SysUserRole.role_id == role_id, SysUser.deleted_at.is_(None))
        )
        return int((await session.execute(statement)).scalar_one() or 0)

    async def soft_delete(self, session: AsyncSession, role: SysRole, current_user: AuthenticatedUser) -> None:
        """软删除角色，并删除其权限、菜单、小程序菜单与（已删除用户的）用户角色关联。"""
        for model in (SysRolePermission, SysRoleMenu, SysRoleMiniappMenu, SysUserRole):
            await session.execute(delete(model).where(model.role_id == role.id))
        role.deleted_at = utc_now()
        role.deleted_by = current_user.user_id
        role.updated_by = current_user.user_id
        session.add(role)
        await session.commit()

    # ───────── 角色权限导入模板 ─────────
    async def permission_template_data(self, session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
        parent_menu = aliased(SysMenu)
        roles = [
            role
            for role in (await session.execute(select(SysRole).where(SysRole.deleted_at.is_(None)).order_by(SysRole.role_no))).scalars().all()
            if not is_builtin_admin(role)  # 内置管理员拥有全部权限，不进入模板
        ]
        role_ids = [role.id for role in roles]
        menu_map: dict[UUID, list[str]] = {}
        permission_map: dict[UUID, list[tuple[str, str]]] = {}
        if role_ids:
            for role_id, menu_key in (
                await session.execute(
                    select(SysRoleMenu.role_id, SysMenu.menu_key)
                    .join(SysMenu, SysMenu.id == SysRoleMenu.menu_id)
                    .where(SysRoleMenu.role_id.in_(role_ids), SysMenu.menu_type_code == "menu", SysMenu.deleted_at.is_(None))
                    .order_by(SysMenu.sort_no.nulls_last(), SysMenu.menu_key)
                )
            ).all():
                menu_map.setdefault(role_id, []).append(menu_key)
            for role_id, key, scope in (
                await session.execute(
                    select(
                        SysRolePermission.role_id,
                        SysPermission.permission_key,
                        func.coalesce(SysRolePermission.data_scope_code, SysRole.data_scope_code),
                    )
                    .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
                    .join(SysRole, SysRole.id == SysRolePermission.role_id)
                    .where(SysRolePermission.role_id.in_(role_ids), SysPermission.deleted_at.is_(None))
                    .order_by(SysPermission.module_code, SysPermission.permission_key)
                )
            ).all():
                permission_map.setdefault(role_id, []).append((key, scope))
        menus = (
            await session.execute(
                select(SysMenu.id, SysMenu.menu_key, SysMenu.menu_name, parent_menu.menu_name.label("parent_name"), SysMenu.path)
                .outerjoin(parent_menu, parent_menu.id == SysMenu.parent_id)
                .where(SysMenu.menu_type_code == "menu", SysMenu.deleted_at.is_(None))
                .order_by(parent_menu.sort_no.asc().nulls_first(), SysMenu.sort_no.nulls_last(), SysMenu.menu_key)
            )
        ).all()
        permissions = (
            await session.execute(
                select(SysPermission.id, SysPermission.permission_key, SysPermission.permission_name, SysPermission.module_code)
                .where(SysPermission.deleted_at.is_(None))
                .order_by(SysPermission.module_code, SysPermission.permission_key)
            )
        ).all()
        return {
            "roles": [
                {
                    "role_no": role.role_no,
                    "role_name": role.role_name,
                    "description": role.description,
                    "data_scope_code": role.data_scope_code,
                    "menu_keys": menu_map.get(role.id, []),
                    "permission_keys": [key for key, _ in permission_map.get(role.id, [])],
                    "permission_scopes": dict(permission_map.get(role.id, [])),
                }
                for role in roles
            ],
            "menus": [dict(row._mapping) for row in menus],
            "permissions": [dict(row._mapping) for row in permissions],
        }

    async def permission_template_import_reference(self, session: AsyncSession) -> dict[str, dict[str, Any]]:
        roles = (await session.execute(select(SysRole).where(SysRole.deleted_at.is_(None)))).scalars().all()
        menus = (
            await session.execute(
                select(SysMenu.id, SysMenu.menu_key).where(SysMenu.menu_type_code == "menu", SysMenu.deleted_at.is_(None))
            )
        ).all()
        permissions = (
            await session.execute(select(SysPermission.id, SysPermission.permission_key).where(SysPermission.deleted_at.is_(None)))
        ).all()
        return {
            "roles": {role.role_no: role for role in roles},
            "menus": {row.menu_key: row.id for row in menus},
            "permissions": {row.permission_key: row.id for row in permissions},
        }

    async def import_permission_template(
        self,
        session: AsyncSession,
        rows: list[RoleTemplateRow],
        current_user: AuthenticatedUser,
        visible_menu_ids: set[UUID],
        visible_permission_ids: set[UUID],
    ) -> RolePermissionTemplateImportResult:
        refs = await self.permission_template_import_reference(session)
        roles: dict[str, SysRole] = refs["roles"]
        result = RolePermissionTemplateImportResult(processed_count=len(rows))
        user_id = current_user.user_id
        try:
            for item in rows:
                role = roles.get(item.role_no)
                if role is None:
                    role = SysRole(
                        role_no=item.role_no,
                        role_name=item.role_name,
                        description=item.description,
                        data_scope_code=item.data_scope_code,
                        created_by=user_id,
                        updated_by=user_id,
                    )
                    session.add(role)
                    await session.flush()
                    roles[item.role_no] = role
                    result.created_count += 1
                else:
                    role.role_name = item.role_name
                    role.description = item.description
                    if not role.is_builtin:
                        role.data_scope_code = item.data_scope_code
                    role.updated_by = user_id
                    role.updated_at = utc_now()
                    session.add(role)
                    result.updated_count += 1

                menu_ids = [refs["menus"][key] for key in item.menu_keys]
                await session.execute(delete(SysRoleMenu).where(SysRoleMenu.role_id == role.id, SysRoleMenu.menu_id.in_(visible_menu_ids)))
                session.add_all(SysRoleMenu(role_id=role.id, menu_id=mid, created_by=user_id, updated_by=user_id) for mid in menu_ids)
                result.role_menu_total += len(menu_ids)

                await session.execute(delete(SysRolePermission).where(SysRolePermission.role_id == role.id, SysRolePermission.permission_id.in_(visible_permission_ids)))
                for key, scope in item.permission_scopes.items():
                    session.add(
                        SysRolePermission(
                            role_id=role.id,
                            permission_id=refs["permissions"][key],
                            data_scope_code=None if scope == role.data_scope_code else scope,
                            created_by=user_id,
                            updated_by=user_id,
                        )
                    )
                result.role_permission_total += len(item.permission_scopes)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return result


repository = RoleRepository()
