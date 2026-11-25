"""仓库向指定下级组织开放申领；不更改用户的组织授权。"""
from uuid import UUID

from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from .requisition_scope_repository import SCOPE_PERMISSION, repository


class RequisitionScopeService:
    @staticmethod
    def _require_permission(user):
        if SCOPE_PERMISSION not in user.permissions:
            raise AppException("无权配置仓库申领范围", status_code=403)

    async def _detail(self, session, warehouse):
        options = await repository.organization_options(session, warehouse.org_id)
        grants = await repository.current_grants(session, warehouse.id)
        selected = {row.recipient_org_id for row in grants}
        available = {row["id"] for row in options}
        names = await repository.organization_names(session, selected | {warehouse.org_id})
        return {
            "warehouse_id": str(warehouse.id), "warehouse_name": warehouse.warehouse_name,
            "owner_org_id": str(warehouse.org_id), "owner_org_name": names.get(warehouse.org_id, ""),
            "expected_updated_at": warehouse.updated_at.isoformat(),
            "recipient_org_ids": [str(key) for key in sorted(selected, key=str)],
            "organizations": [{"id": str(row["id"]), "org_name": row["org_name"],
                               "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
                               "is_available": True} for row in options] + [
                {"id": str(key), "org_name": names.get(key, "已失效组织"), "parent_id": None, "is_available": False}
                for key in sorted(selected - available, key=str)
            ],
        }

    async def detail(self, warehouse_id: UUID, user):
        self._require_permission(user)
        async with get_session_context() as session:
            warehouse = await repository.managed_warehouse(session, warehouse_id, user)
            if warehouse is None:
                raise AppException("仓库不存在或无权配置申领范围", status_code=404)
            return await self._detail(session, warehouse)

    async def save(self, warehouse_id: UUID, payload, user):
        self._require_permission(user)
        async with get_session_context() as session:
            warehouse = await repository.managed_warehouse(session, warehouse_id, user, lock=True)
            if warehouse is None:
                raise AppException("仓库不存在或无权配置申领范围", status_code=404)
            if not warehouse.is_active:
                raise AppException("已停用仓库不能开放申领", status_code=409)
            if warehouse.updated_at != payload.expected_updated_at:
                raise AppException("仓库或申领范围已被修改，请重新加载后保存", status_code=409)
            options = await repository.organization_options(session, warehouse.org_id)
            wanted = set(payload.recipient_org_ids)
            if not wanted.issubset({row["id"] for row in options}):
                raise AppException("只能选择该仓库所属组织下有效的组织；请移除停用、删除或已移出的组织", status_code=422)
            current = await repository.current_grants(session, warehouse.id)
            if wanted != {row.recipient_org_id for row in current}:
                await repository.replace(session, warehouse, current, wanted, user)
            await session.commit()
            return await self._detail(session, warehouse)


service = RequisitionScopeService()
