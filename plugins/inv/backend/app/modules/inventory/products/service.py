from __future__ import annotations
from app.auth.schemas import AuthenticatedUser
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from ..item_policy import (
    CANTEEN_WAREHOUSE_SCOPE,
    candidate_item_ids,
    restricted_item_ids,
)
from .repository import category_repository, item_repository
from .schemas import ItemOption, ItemOptionQuery
from .warehouse_repository import repository as warehouse_links
from app.core.exceptions import AppException
from app.auth.scope_filters import resolve_effective_data_scope
from ..stock_order.repository import repository as stock_locks
from uuid import UUID


class ItemCategoryService(CrudService):
    async def options(self) -> list[dict]:
        async with get_session_context() as session:
            return await category_repository.options(session)


class ItemService(CrudService):
    async def warehouse_options(self, user, action):
        permission = f"inventory_product:{action}"
        if permission not in user.permissions:
            raise AppException("无权查看物料适用仓库选项", 403)
        async with get_session_context() as session:
            return [{"id": str(row.id), "warehouse_name": row.warehouse_name, "org_name": org,
                "label": f"{org} / {row.warehouse_name}"} for row, org in await warehouse_links.warehouses(session, user, permission)]

    async def _enrich(self, session, items, user, action="list"):
        ids = [UUID(str(item["id"])) for item in items]
        links = await warehouse_links.references(session, ids, user, f"inventory_product:{action}")
        editable = await warehouse_links.editable_base_ids(session, ids, user)
        for item in items:
            references = links.get(UUID(str(item["id"])), [])
            item["warehouse_ids"] = [row["id"] for row in references]
            item["warehouses"] = references
            item["can_edit_base_fields"] = UUID(str(item["id"])) in editable
        return items

    async def list(self, params, current_user):
        async with get_session_context() as session:
            await self.validate_filter(session, params, current_user)
            result = await item_repository.list(session, params, current_user)
            result["items"] = await self._enrich(session, result["items"], current_user)
            return result

    async def validate_filter(self, session, params, current_user):
        await warehouse_links.require_scope_ready(session, current_user, "inventory_product:list")
        warehouse_id = getattr(params, "applicable_warehouse_id", None)
        if warehouse_id is not None:
            await warehouse_links.require_ready(session)
            visible = await warehouse_links.warehouses(session, current_user, "inventory_product:list")
            if warehouse_id not in {row.id for row, _ in visible}:
                raise AppException("无权按该适用仓库查询物料", 403)

    async def export_rows(self, params, current_user, *, limit):
        async with get_session_context() as session:
            await self.validate_filter(session, params, current_user)
            return await item_repository.export_rows(session, params, current_user, limit=limit)

    async def detail(self, item_id, current_user):
        async with get_session_context() as session:
            await warehouse_links.require_scope_ready(session, current_user, "inventory_product:detail")
            result = await item_repository.detail(session, item_id, current_user)
            if result is None:
                return None
            return type(result).model_validate((await self._enrich(session, [result.model_dump()], current_user, "detail"))[0])

    async def create(self, payload, current_user):
        data = dict(payload)
        warehouse_ids = data.pop("warehouse_ids", None)
        if not warehouse_ids and resolve_effective_data_scope(current_user, "inventory_product:create") == "related":
            raise AppException("请选择本人管理的适用仓库后新增物料", 422)
        if warehouse_ids is None:
            return await super().create(data, current_user)
        if "inventory_product:create" not in current_user.permissions:
            raise AppException("无权新增物料", 403)
        async with get_session_context() as session, session.begin():
            await warehouse_links.require_ready(session)
            await warehouse_links.lock_targets(session, warehouse_ids, current_user, "inventory_product:create")
            item = await item_repository.create_in_session(session, data, current_user)
            await stock_locks.lock_items(session, [item.id])
            await warehouse_links.replace(session, item.id, warehouse_ids, current_user, "inventory_product:create")
            result = await item_repository.serialize_item(session, item)
            return type(result).model_validate((await self._enrich(session, [result.model_dump()], current_user, "create"))[0])

    async def update(
        self,
        item_id: str,
        payload: dict,
        current_user: AuthenticatedUser,
    ):
        data = dict(payload)
        warehouse_ids = data.pop("warehouse_ids", None)
        async with get_session_context() as session, session.begin():
            if warehouse_ids is not None:
                if "inventory_product:update" not in current_user.permissions:
                    raise AppException("无权配置物料适用仓库", 403)
                if not data.get("expected_updated_at"):
                    raise AppException("修改适用仓库必须提供物料版本时间，请刷新后重试", 409)
                await warehouse_links.require_ready(session)
                await warehouse_links.lock_targets(session, warehouse_ids, current_user, "inventory_product:update")
                await stock_locks.lock_items(session, [UUID(str(item_id))])
            result = await item_repository.update_in_session(session, item_id, data, current_user)
            if result is None:
                return None
            item, changed = result
            if warehouse_ids is not None:
                await warehouse_links.replace(session, item.id, warehouse_ids, current_user, "inventory_product:update")
                from app.framework.db.models import utc_now
                item.updated_at, item.updated_by = utc_now(), current_user.user_id
                session.add(item)
                changed = True
            if changed:
                await session.flush()
            serialized = await item_repository.serialize_item(session, item)
            return type(serialized).model_validate((await self._enrich(session, [serialized.model_dump()], current_user, "update"))[0])

    async def options(self, query: ItemOptionQuery, current_user=None) -> list[ItemOption]:
        async with get_session_context() as session:
            if query.inbound_warehouse_id is not None:
                if current_user is None:
                    raise AppException("入库候选物料必须校验当前账号", 403)
                permission = f"inventory_inbound:{query.inbound_action}"
                if permission not in current_user.permissions:
                    raise AppException("无权查询入库候选物料", 403)
                await warehouse_links.require_ready(session)
                rows = await warehouse_links.warehouses(session, current_user, permission)
                if query.inbound_warehouse_id not in {row.id for row, _ in rows}:
                    raise AppException("目标仓库不存在、已停用或不在当前账号范围内", 403)
            excluded = await restricted_item_ids(session, query.usage_scope_code)
            candidates = await candidate_item_ids(session, query.usage_scope_code)
            return await item_repository.options(
                session,
                query,
                excluded_item_ids=excluded,
                candidate_item_ids=candidates,
                warehouse_related_only=(
                    query.usage_scope_code == CANTEEN_WAREHOUSE_SCOPE
                ),
            )


category_service = ItemCategoryService(repository=category_repository, session_getter=get_session_context)
item_service = ItemService(repository=item_repository, session_getter=get_session_context)
