from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.modules.rbac_repository_utils import normalize_uuid, row_to_dict, utc_now
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission

from .models import SysPermission
from .schemas import PermissionDetailItem, PermissionItem, PermissionListQuery, PermissionRoleItem


def _role_count():
    return (
        select(func.count())
        .select_from(SysRolePermission)
        .join(SysRole, SysRole.id == SysRolePermission.role_id)
        .where(SysRolePermission.permission_id == SysPermission.id, SysRole.deleted_at.is_(None))
        .correlate(SysPermission)
        .scalar_subquery()
    )


class PermissionRepository:
    @staticmethod
    def _conditions(params: PermissionListQuery) -> list[Any]:
        conditions: list[Any] = [SysPermission.deleted_at.is_(None)]
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            conditions.append(
                or_(
                    SysPermission.permission_key.ilike(keyword),
                    SysPermission.permission_name.ilike(keyword),
                    SysPermission.module_code.ilike(keyword),
                )
            )
        if params.permission_key:
            conditions.append(SysPermission.permission_key.ilike(f"%{params.permission_key.strip()}%"))
        if params.permission_name:
            conditions.append(SysPermission.permission_name.ilike(f"%{params.permission_name.strip()}%"))
        if params.module_code:
            conditions.append(SysPermission.module_code == params.module_code.strip())
        if params.is_active is not None:
            conditions.append(SysPermission.is_active.is_(params.is_active))
        return conditions

    async def list(self, session: AsyncSession, params: PermissionListQuery, blocked_module_codes: set[str] | None = None) -> dict[str, Any]:
        conditions = self._conditions(params)
        if blocked_module_codes:
            conditions.append(SysPermission.module_code.not_in(blocked_module_codes))
        total = int((await session.execute(select(func.count()).select_from(SysPermission).where(*conditions))).scalar_one() or 0)
        role_count = _role_count().label("role_count")
        sort_map = {
            "updated_at": SysPermission.updated_at,
            "created_at": SysPermission.created_at,
            "permission_key": SysPermission.permission_key,
            "module_code": SysPermission.module_code,
            "role_count": role_count,
        }
        order = sort_map[params.sort_by]
        order = order.asc() if params.sort_order == "asc" else order.desc()
        statement = (
            select(SysPermission, role_count)
            .where(*conditions)
            .order_by(order, SysPermission.permission_key)
            .limit(params.page_size)
            .offset((params.page - 1) * params.page_size)
        )
        items = []
        for entity, count in (await session.execute(statement)).all():
            item = PermissionItem.model_validate(entity)
            item.role_count = int(count or 0)
            items.append(item.model_dump(mode="json"))
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def get(self, session: AsyncSession, item_id: str) -> SysPermission | None:
        entity = await session.get(SysPermission, normalize_uuid(item_id))
        return entity if entity is not None and entity.deleted_at is None else None

    async def detail(self, session: AsyncSession, item_id: str) -> PermissionDetailItem | None:
        entity = await self.get(session, item_id)
        if entity is None:
            return None
        rows = (
            await session.execute(
                select(SysRole.id, SysRole.role_no, SysRole.role_name)
                .join(SysRolePermission, SysRolePermission.role_id == SysRole.id)
                .where(SysRolePermission.permission_id == entity.id, SysRole.deleted_at.is_(None))
                .order_by(SysRole.role_no)
            )
        ).all()
        item = PermissionDetailItem.model_validate(entity)
        item.roles = [PermissionRoleItem(**row_to_dict(row)) for row in rows]
        item.role_count = len(item.roles)
        return item

    async def update(self, session: AsyncSession, entity: SysPermission, payload: dict[str, Any], current_user: AuthenticatedUser) -> None:
        for column in ("permission_name", "is_active"):
            if column in payload and payload[column] is not None:
                setattr(entity, column, payload[column])
        entity.updated_by = current_user.user_id
        entity.updated_at = utc_now()
        session.add(entity)
        await session.commit()


repository = PermissionRepository()
