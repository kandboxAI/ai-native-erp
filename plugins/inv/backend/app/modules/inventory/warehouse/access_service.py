"""仓库管理账号授权；功能权限和原有组织边界仍独立生效。"""
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from .access_repository import AUTHORIZE, repository


class WarehouseAccessService:
    def _require(self, user):
        if AUTHORIZE not in user.permissions:
            raise AppException("无权配置仓库管理账号", status_code=403)

    async def _detail(self, session, warehouse, user):
        options = await repository.user_options(session, warehouse, user)
        grants = await repository.current(session, warehouse.id)
        selected = {row.user_id for row in grants}
        available = {row["id"] for row in options}
        return {"warehouse_id": str(warehouse.id), "warehouse_name": warehouse.warehouse_name,
            "expected_updated_at": warehouse.updated_at.isoformat(),
            "user_ids": [str(key) for key in sorted(selected, key=str)],
            "users": [{"id": str(row["id"]), "display_name": row["display_name"], "is_available": True,
                "is_recommended": row.get("is_recommended", False)} for row in options] + [
                {"id": str(key), "display_name": "已失效或超出范围的账号", "is_available": False}
                for key in sorted(selected - available, key=str)]}

    async def detail(self, warehouse_id, user):
        self._require(user)
        async with get_session_context() as session:
            warehouse = await repository.managed(session, warehouse_id, user)
            if warehouse is None:
                raise AppException("仓库不存在或无权授权", status_code=404)
            return await self._detail(session, warehouse, user)

    async def save(self, warehouse_id, payload, user):
        self._require(user)
        async with get_session_context() as session:
            warehouse = await repository.managed(session, warehouse_id, user, lock=True)
            if warehouse is None:
                raise AppException("仓库不存在或无权授权", status_code=404)
            if not warehouse.is_active or warehouse.updated_at != payload.expected_updated_at:
                raise AppException("仓库已停用或配置已变化，请重新加载后核对", status_code=409)
            wanted = set(payload.user_ids)
            available = {row["id"] for row in await repository.user_options(session, warehouse, user)}
            if not wanted.issubset(available):
                raise AppException("请选择有效且在授权组织范围内的账号，移除已失效的账号", status_code=422)
            current = await repository.current(session, warehouse.id)
            if wanted != {row.user_id for row in current}:
                await repository.replace(session, warehouse, current, wanted, user)
            await session.commit()
            return await self._detail(session, warehouse, user)


service = WarehouseAccessService()
