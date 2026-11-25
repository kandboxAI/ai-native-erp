"""物料分类与物料的数据访问。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.framework.crud.repository import CONCURRENCY_TOKEN_FIELD, SqlModelCrudRepository
from app.framework.db.ids import uuid7
from app.modules.supplier.models import MdSupplier
from app.modules.supplier.repository import supplier_names
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem

from ..models import InvItemWarehouseSetting, InvStockBalance, InvStockOrderLine, InvWarehouse, MdItem, MdItemCategory
from .schemas import ItemCategoryItem, ItemItem, ItemOption, ItemOptionQuery
from . import warehouse_repository as _warehouse_scopes  # 注册直接 Repository 调用所需的关联范围


def _uuid(value: Any) -> UUID | None:
    return None if value in (None, "") else UUID(str(value))


# ───────── 物料分类 ─────────
async def _normalize_category(session: AsyncSession, data: dict[str, Any], current_user: AuthenticatedUser, entity) -> dict[str, Any]:
    parent_id = data.get("parent_id")
    if parent_id is not None:
        if entity is not None and parent_id == entity.id:
            raise AppException("上级分类不能是自己", status_code=status.HTTP_400_BAD_REQUEST)
        exists = (
            await session.exec(select(MdItemCategory.id).where(MdItemCategory.id == parent_id, MdItemCategory.deleted_at.is_(None)))
        ).first()
        if exists is None:
            raise AppException("上级分类不存在", status_code=status.HTTP_400_BAD_REQUEST)
    return data


class ItemCategoryRepository(SqlModelCrudRepository):
    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        category_id = self._normalize_id(item_id)
        used_item = (
            await session.exec(select(MdItem.id).where(MdItem.category_id == category_id, MdItem.deleted_at.is_(None)).limit(1))
        ).first()
        child = (
            await session.exec(
                select(MdItemCategory.id).where(MdItemCategory.parent_id == category_id, MdItemCategory.deleted_at.is_(None)).limit(1)
            )
        ).first()
        if used_item is not None or child is not None:
            raise AppException("该分类下仍有物料或下级分类，不能删除", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)

    async def options(self, session: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await session.exec(
                select(MdItemCategory).where(MdItemCategory.deleted_at.is_(None)).order_by(MdItemCategory.category_name)
            )
        ).all()
        return [{"id": str(row.id), "category_name": row.category_name, "parent_id": str(row.parent_id) if row.parent_id else None} for row in rows]

    async def find_by_name(self, session: AsyncSession, name: str) -> MdItemCategory | None:
        return (
            await session.exec(
                select(MdItemCategory).where(MdItemCategory.category_name == name.strip(), MdItemCategory.deleted_at.is_(None))
            )
        ).first()


category_repository = ItemCategoryRepository(
    table_model=MdItemCategory,
    item_model=ItemCategoryItem,
    writable_columns=["category_name", "parent_id", "description"],
    searchable_columns=["category_name", "description"],
    filterable_columns=["parent_id"],
    create_payload_normalizer=_normalize_category,
    update_payload_normalizer=_normalize_category,
    scope_resource="inventory_product_category",
)


# ───────── 物料 ─────────
def new_item_no() -> str:
    return f"WL-{uuid7().hex[-10:].upper()}"


ASSET_DEFAULT_DICTS = {
    "default_asset_type_code": ("asset_type", "默认资产类型"),
}


def normalize_asset_defaults(data: dict, entity, dictionaries: dict) -> dict:
    """表单与 Excel 共用；旧值可原样保留，新引用必须来自启用字典。"""
    for field, (code, label) in ASSET_DEFAULT_DICTS.items():
        if field not in data or data[field] is None:
            continue
        value = data[field]
        choices = dictionaries.get(code, [])
        mapping = {name: key for key, name in choices}
        mapping.update({key: key for key, _ in choices})
        normalized = mapping.get(value)
        if normalized is None and entity is not None and value == getattr(entity, field, None):
            normalized = value
        if normalized is None:
            raise AppException(f"{label}不存在或已停用，请重新选择")
        data[field] = normalized
    if data.get("default_asset_management_mode_code") not in (None, "", "individual", "单件登记", "逐件编号"):
        raise AppException("新资产统一逐件编号，不再支持按数量登记，请删除旧模板的建议登记方式列或填写单件登记")
    managed = data.get("is_asset_managed", getattr(entity, "is_asset_managed", False))
    # 仓库关系或其他普通字段编辑不补写历史资产登记方式；仅建档/显式资产配置时规范化。
    if managed and (entity is None or "is_asset_managed" in data or "default_asset_management_mode_code" in data):
        data["default_asset_management_mode_code"] = "individual"
    elif "is_asset_managed" in data or "default_asset_management_mode_code" in data:
        data["default_asset_management_mode_code"] = None
    return data


async def _normalize_item(session: AsyncSession, data: dict[str, Any], current_user: AuthenticatedUser, entity) -> dict[str, Any]:
    dictionaries = {}
    for field, (code, _) in ASSET_DEFAULT_DICTS.items():
        if data.get(field) is not None:
            dictionaries[code] = await item_repository.asset_dictionary_items(session, code)
    normalize_asset_defaults(data, entity, dictionaries)
    if entity is None and not data.get("item_no"):
        data["item_no"] = new_item_no()
    if data.get("category_id") is not None:
        exists = (
            await session.exec(
                select(MdItemCategory.id).where(MdItemCategory.id == data["category_id"], MdItemCategory.deleted_at.is_(None))
            )
        ).first()
        if exists is None:
            raise AppException("物料分类不存在", status_code=status.HTTP_400_BAD_REQUEST)
    if data.get("default_supplier_id") is not None:
        exists = (
            await session.exec(
                select(MdSupplier.id).where(MdSupplier.id == data["default_supplier_id"], MdSupplier.deleted_at.is_(None))
            )
        ).first()
        if exists is None:
            raise AppException("默认供应商不存在", status_code=status.HTTP_400_BAD_REQUEST)
    name = data.get("item_name", entity.item_name if entity is not None else None)
    spec = data.get("specification", entity.specification if entity is not None else None)
    duplicate = select(MdItem.id).where(
        MdItem.deleted_at.is_(None),
        MdItem.item_name == name,
        func.coalesce(MdItem.specification, "") == (spec or ""),
    )
    if entity is not None:
        duplicate = duplicate.where(MdItem.id != entity.id)
    if (await session.exec(duplicate.limit(1))).first() is not None:
        raise AppException(f"已存在同名同规格的物料：{name} {spec or ''}".strip(), status_code=status.HTTP_409_CONFLICT)
    return data


class ItemRepository(SqlModelCrudRepository):
    async def create_in_session(self, session, payload, current_user):
        """公开业务建档复用相同校验和审计；由调用方提交完整事务。"""
        data = await self._run_payload_normalizer(self.create_payload_normalizer, session, payload, current_user, is_create=True)
        self._stamp_create(data, current_user)
        entity = self.table_model(**data)
        session.add(entity)
        await session.flush()
        return entity


    async def asset_dictionary_items(self, session: AsyncSession, code: str):
        return (await session.exec(
            select(SysDictItem.item_code, SysDictItem.item_name)
            .join(SysDict, SysDict.id == SysDictItem.dict_id)
            .where(SysDict.dict_code == code, SysDict.deleted_at.is_(None),
                   SysDict.is_active.is_(True), SysDictItem.deleted_at.is_(None),
                   SysDictItem.is_active.is_(True))
        )).all()

    async def warehouse_category_options(
        self, session: AsyncSession, current_user: AuthenticatedUser, *,
        permission_key: str, category_name: str, warehouse_no: str | None = None,
        item_ids: set[UUID] | None = None,
    ) -> list[ItemOption]:
        """严格交集：可访问仓库已有余额/未删除设置关系，且分类匹配的启用物料。

        不要求正库存；不通过上层候选提供器扩大仓库关系，也不读其他分类。
        分类及仓库标识由调用方传入，库存模块不包含行业分类规则。
        """
        if item_ids is not None and not item_ids:
            return []
        warehouse_ids = select(InvWarehouse.id).where(
            *scoped_conditions(InvWarehouse, current_user, permission_key),
            InvWarehouse.is_active.is_(True),
        )
        if warehouse_no is not None:
            warehouse_ids = warehouse_ids.where(InvWarehouse.warehouse_no == warehouse_no)
        has_balance = select(InvStockBalance.id).where(
            InvStockBalance.item_id == MdItem.id,
            InvStockBalance.warehouse_id.in_(warehouse_ids),
        ).exists()
        has_setting = select(InvItemWarehouseSetting.id).where(
            InvItemWarehouseSetting.item_id == MdItem.id,
            InvItemWarehouseSetting.warehouse_id.in_(warehouse_ids),
            InvItemWarehouseSetting.deleted_at.is_(None),
        ).exists()
        statement = select(MdItem).join(MdItemCategory, MdItem.category_id == MdItemCategory.id).where(
            *scoped_conditions(MdItem, current_user, permission_key),
            MdItem.is_active.is_(True),
            MdItemCategory.category_name == category_name,
            MdItemCategory.deleted_at.is_(None),
            or_(has_balance, has_setting),
        ).order_by(MdItem.item_name, MdItem.item_no)
        if item_ids is not None:
            statement = statement.where(MdItem.id.in_(item_ids))
        else:
            statement = statement.limit(5000)
        rows = (await session.exec(statement)).all()
        return [ItemOption(
            id=row.id, item_no=row.item_no, item_name=row.item_name,
            category_id=row.category_id, category_name=category_name,
            specification=row.specification, unit_code=row.unit_code,
            unit_price=row.unit_price, is_lot_controlled=row.is_lot_controlled,
            is_asset_managed=row.is_asset_managed, default_asset_type_code=row.default_asset_type_code,
            default_asset_management_mode_code="individual" if row.is_asset_managed else None,
        ) for row in rows]

    def _filter_conditions(self, params) -> list[Any]:
        conditions = super()._filter_conditions(params)
        applicable = getattr(params, "applicable_warehouse_id", None)
        if applicable is not None:
            from .warehouse_repository import repository as warehouse_links
            conditions.append(warehouse_links.applies(MdItem.id, applicable))
        warehouse_id = getattr(params, "warehouse_id", None)
        if warehouse_id is not None:
            has_balance = (
                select(InvStockBalance.id)
                .where(
                    InvStockBalance.item_id == MdItem.id,
                    InvStockBalance.warehouse_id == warehouse_id,
                )
                .exists()
            )
            has_setting = (
                select(InvItemWarehouseSetting.id)
                .where(
                    InvItemWarehouseSetting.item_id == MdItem.id,
                    InvItemWarehouseSetting.warehouse_id == warehouse_id,
                    InvItemWarehouseSetting.deleted_at.is_(None),
                )
                .exists()
            )
            conditions.append(or_(has_balance, has_setting))
        return conditions

    async def create(self, session: AsyncSession, payload: dict[str, Any], current_user: AuthenticatedUser):
        item = await super().create(session, payload, current_user)
        return ItemItem.model_validate((await self._name_maps(session, [item.model_dump(mode="json")]))[0])

    async def update_in_session(
        self,
        session: AsyncSession,
        item_id: str,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
    ):
        """事务内更新物料，供阈值变更与预警通知原子提交。"""
        from .warehouse_repository import repository as warehouse_links
        await warehouse_links.require_scope_ready(session, current_user, "inventory_product:update")
        entity = (
            await session.exec(
                self._scoped_detail_statement(item_id, current_user, for_update=True, action="update")
            )
        ).one_or_none()
        if entity is None:
            return None

        exact_version = payload.pop("expected_updated_at", None)
        if exact_version is not None:
            from app.framework.datetime_local import parse_datetime_input
            if parse_datetime_input(exact_version) != parse_datetime_input(entity.updated_at):
                raise AppException("物料或适用仓库已被他人修改，请刷新后重试", 409)
        expected_updated_at = payload.pop(CONCURRENCY_TOKEN_FIELD, None)
        data = await self._run_payload_normalizer(
            self.update_payload_normalizer,
            session,
            payload,
            current_user,
            entity=entity,
            is_create=False,
        )
        self._assert_not_stale(entity, expected_updated_at)
        await warehouse_links.require_basic_edit(session, entity, data, current_user)
        if data:
            self._stamp_update(data, current_user)
            for column_name, value in data.items():
                setattr(entity, column_name, value)
            session.add(entity)
            await session.flush()
        return entity, bool(data)

    async def serialize_item(self, session: AsyncSession, item: MdItem) -> ItemItem:
        return ItemItem.model_validate((await self._name_maps(session, [item.model_dump(mode="json")]))[0])

    async def update(self, session: AsyncSession, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        result = await self.update_in_session(session, item_id, payload, current_user)
        if result is None:
            return None
        item, changed = result
        if changed:
            await session.commit()
            await session.refresh(item)
        return await self.serialize_item(session, item)

    async def _name_maps(self, session: AsyncSession, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        category_ids = {_uuid(item.get("category_id")) for item in items} - {None}
        supplier_ids = {_uuid(item.get("default_supplier_id")) for item in items} - {None}
        categories: dict[UUID, str] = {}
        suppliers: dict[UUID, str] = {}
        if category_ids:
            rows = (await session.exec(select(MdItemCategory.id, MdItemCategory.category_name).where(MdItemCategory.id.in_(category_ids)))).all()
            categories = {row[0]: row[1] for row in rows}
        if supplier_ids:
            suppliers = await supplier_names(session, supplier_ids)
        for item in items:
            item["default_asset_management_mode_code"] = "individual" if item.get("is_asset_managed") else None
            item["category_name"] = categories.get(_uuid(item.get("category_id")))
            item["default_supplier_name"] = suppliers.get(_uuid(item.get("default_supplier_id")))
        return items

    async def list(self, session: AsyncSession, params, current_user: AuthenticatedUser) -> dict[str, Any]:
        result = await super().list(session, params, current_user)
        result["items"] = await self._name_maps(session, result["items"])
        return result

    async def detail(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser):
        item = await super().detail(session, item_id, current_user)
        if item is None:
            return None
        return ItemItem.model_validate((await self._name_maps(session, [item.model_dump(mode="json")]))[0])

    async def export_rows(self, session: AsyncSession, params, current_user: AuthenticatedUser, *, limit: int) -> list[dict[str, Any]]:
        return await self._name_maps(session, await super().export_rows(session, params, current_user, limit=limit))

    async def template_export_rows(self, session, params, current_user, *, limit):
        """与列表复用筛选（含仓库），同时应用查询及导出数据范围，不按分页截取。"""
        _, statement = self._filtered_list_statements(params, current_user, action="export")
        statement = self._apply_scope(statement, current_user, "list")
        rows = (await session.exec(statement.order_by(MdItem.updated_at.desc(), MdItem.id).limit(limit))).all()
        return await self._name_maps(session, [row.model_dump() for row in rows])

    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        target = self._normalize_id(item_id)
        from .warehouse_repository import repository as warehouse_links
        await warehouse_links.require_scope_ready(session, current_user, "inventory_product:delete")
        entity = (await session.exec(self._scoped_detail_statement(item_id, current_user, action="delete", for_update=True))).one_or_none()
        if entity is None:
            return False
        await warehouse_links.require_basic_edit(session, entity, {}, current_user, deleting=True)
        has_stock = (await session.exec(select(InvStockBalance.id).where(InvStockBalance.item_id == target).limit(1))).first()
        has_lines = (await session.exec(select(InvStockOrderLine.id).where(InvStockOrderLine.item_id == target).limit(1))).first()
        if has_stock is not None or has_lines is not None:
            raise AppException("物料已有库存或单据记录，不能删除，请改为停用", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)

    async def options(
        self,
        session: AsyncSession,
        query: ItemOptionQuery,
        *,
        excluded_item_ids: set[UUID] | None = None,
        candidate_item_ids: set[UUID] | None = None,
        warehouse_related_only: bool = False,
    ) -> list[ItemOption]:
        available = None
        statement = (
            select(MdItem, MdItemCategory.category_name)
            .join(MdItemCategory, MdItemCategory.id == MdItem.category_id, isouter=True)
            .where(MdItem.deleted_at.is_(None), MdItem.is_active.is_(True))
        )
        if excluded_item_ids:
            statement = statement.where(MdItem.id.not_in(excluded_item_ids))
        if query.inbound_warehouse_id is not None:
            from .warehouse_repository import repository as warehouse_links
            statement = statement.where(warehouse_links.applies(MdItem.id, query.inbound_warehouse_id))
        if query.is_asset_managed is not None:
            statement = statement.where(MdItem.is_asset_managed.is_(query.is_asset_managed))
        if warehouse_related_only:
            if query.warehouse_id is None:
                raise AppException(
                    "按仓库范围加载候选物料时必须指定仓库",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            related_conditions = [
                select(InvStockBalance.id)
                .where(
                    InvStockBalance.item_id == MdItem.id,
                    InvStockBalance.warehouse_id == query.warehouse_id,
                )
                .exists(),
                select(InvItemWarehouseSetting.id)
                .where(
                    InvItemWarehouseSetting.item_id == MdItem.id,
                    InvItemWarehouseSetting.warehouse_id == query.warehouse_id,
                    InvItemWarehouseSetting.deleted_at.is_(None),
                )
                .exists(),
            ]
            if candidate_item_ids:
                related_conditions.append(MdItem.id.in_(candidate_item_ids))
            statement = statement.where(or_(*related_conditions))
        if query.warehouse_id is not None or query.org_id is not None:
            balance_filter = [InvStockBalance.stock_status_code == query.stock_status_code]
            if query.warehouse_id is not None:
                balance_filter.append(InvStockBalance.warehouse_id == query.warehouse_id)
            if query.org_id is not None:
                balance_filter.append(InvStockBalance.org_id == query.org_id)
            available = (
                select(
                    InvStockBalance.item_id.label("item_id"),
                    func.sum(InvStockBalance.quantity - InvStockBalance.reserved_quantity).label("available_quantity"),
                )
                .where(*balance_filter)
                .group_by(InvStockBalance.item_id)
                .subquery()
            )
            statement = statement.add_columns(available.c.available_quantity).join(
                available, available.c.item_id == MdItem.id, isouter=not query.in_stock_only
            )
            if query.in_stock_only:
                statement = statement.where(available.c.available_quantity > 0)
        if query.item_id is not None:
            statement = statement.where(MdItem.id == query.item_id)
        if query.category_id is not None:
            statement = statement.where(MdItem.category_id == query.category_id)
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            statement = statement.where(or_(MdItem.item_name.ilike(pattern), MdItem.item_no.ilike(pattern), MdItem.specification.ilike(pattern)))
        rows = (await session.exec(statement.order_by(MdItem.item_name).limit(query.limit))).all()
        result: list[ItemOption] = []
        for row in rows:
            item, category_name = row[0], row[1]
            result.append(
                ItemOption(
                    id=item.id,
                    item_no=item.item_no,
                    item_name=item.item_name,
                    category_id=item.category_id,
                    category_name=category_name,
                    specification=item.specification,
                    unit_code=item.unit_code,
                    unit_price=item.unit_price,
                    is_lot_controlled=item.is_lot_controlled,
                    is_asset_managed=item.is_asset_managed, default_asset_type_code=item.default_asset_type_code,
                    default_asset_management_mode_code="individual" if item.is_asset_managed else None,
                    available_quantity=(row[2] or 0) if available is not None else None,
                )
            )
        return result

    async def find_by_name_spec(self, session: AsyncSession, name: str, spec: str | None) -> MdItem | None:
        return (
            await session.exec(
                select(MdItem).where(
                    MdItem.deleted_at.is_(None),
                    MdItem.item_name == name.strip(),
                    func.coalesce(MdItem.specification, "") == (spec or "").strip(),
                )
            )
        ).first()

    async def get_many(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, MdItem]:
        if not ids:
            return {}
        rows = (await session.exec(select(MdItem).where(MdItem.id.in_(ids), MdItem.deleted_at.is_(None)))).all()
        return {row.id: row for row in rows}


item_repository = ItemRepository(
    table_model=MdItem,
    item_model=ItemItem,
    writable_columns=[
        "item_no",
        "item_name",
        "category_id",
        "specification",
        "unit_code",
        "sub_unit_code",
        "unit_price",
        "default_supplier_id",
        "is_asset_managed",
        "default_asset_type_code",
        "default_asset_management_mode_code",
        "is_lot_controlled",
        "shelf_life_days",
        "is_active",
        "remark",
    ],
    searchable_columns=["item_no", "item_name", "specification", "remark"],
    filterable_columns=["category_id", "default_supplier_id", "is_active", "is_asset_managed"],
    create_payload_normalizer=_normalize_item,
    update_payload_normalizer=_normalize_item,
    scope_resource="inventory_product",
)


