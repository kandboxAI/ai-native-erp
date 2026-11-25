"""Excel 导入：物料分类、物料档案、库存盘点。

- 先预校验（validate）再正式导入（import），整批在同一事务内提交或回滚。
- 库存盘点导入不直接改数量：按仓库生成“盘点调整”库存单据（方向 adjust）并确认，由统一记账服务按实盘数与账面数的差额记流水。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import accessible_org_ids, has_all_organization_access
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context

from ..constants import DIRECTION_ADJUST
from ..item_policy import GENERAL_WAREHOUSE_SCOPE, restricted_item_ids
from ..stock_order.repository import type_repository
from ..stock_order.schemas import OrderCreate, OrderLineWrite
from ..stock_order.service import service as order_service
from ..products.repository import ASSET_DEFAULT_DICTS, item_repository, normalize_asset_defaults
from . import excel
from .repository import item_selection_label, repository
from .schemas import (
    ImportResult,
    ImportSummary,
    InventoryImportIssue,
    InventoryImportOptions,
    ItemTemplateChoices,
    StockTemplateChoices,
)


def _result(errors: list[InventoryImportIssue], summary: ImportSummary, warnings: list[InventoryImportIssue] | None = None) -> ImportResult:
    return ImportResult(valid=not errors, summary=summary, errors=errors, warnings=warnings or [])


def _org_filter(current_user: AuthenticatedUser) -> list | None:
    try:
        if has_all_organization_access(current_user, "inventory_item:import"):
            return None
    except AppException:
        pass
    return accessible_org_ids(current_user) or None


class InventoryImportService:
    # ───────── 模板 ─────────
    async def category_template(self) -> bytes:
        return excel.build_category_template()

    async def item_template(self) -> bytes:
        async with get_session_context() as session:
            choices = ItemTemplateChoices(
                categories=list((await repository.categories(session)).keys()),
                suppliers=list((await repository.suppliers(session)).keys()),
                units=[name for _code, name in await repository.dict_items(session, "md_unit")],
                asset_types=[name for _, name in await item_repository.asset_dictionary_items(session, "asset_type")],
            )
        return excel.build_item_template(choices)

    async def item_export(self, query, user: AuthenticatedUser) -> bytes:
        async with get_session_context() as session:
            from ..products.service import item_service
            await item_service.validate_filter(session, query, user)
            rows = await item_repository.template_export_rows(
                session, query, user, limit=excel.MAX_ITEM_ROWS + 1,
            )
            if len(rows) > excel.MAX_ITEM_ROWS:
                raise AppException("导出超过10000条，请缩小筛选范围")
            asset_types = dict(await item_repository.asset_dictionary_items(session, "asset_type"))
            units = dict(await repository.dict_items(session, "md_unit"))
            categories = await repository.categories(session)
            all_suppliers = await repository.suppliers(session, include_inactive=True)
            category_ids = {category.id for category in categories.values()}
            supplier_ids = set(all_suppliers.values())
            choices = ItemTemplateChoices(
                categories=list(categories.keys()),
                suppliers=list((await repository.suppliers(session)).keys()),
                units=list(units.values()),
                asset_types=list(asset_types.values()),
            )
            for row in rows:
                for field, names in (("default_asset_type_code", asset_types),):
                    row[field] = names.get(row.get(field), row.get(field))
                row["unit_name"] = units.get(row["unit_code"], row["unit_code"])
                row["sub_unit_name"] = units.get(row.get("sub_unit_code"), row.get("sub_unit_code"))
                row["supplier_name"] = row.get("default_supplier_name")
                # 保留已有引用（包括停用供应商），以支持原样导出再回导。
                if row.get("category_id") and row["category_id"] not in category_ids:
                    raise AppException("物料引用了已删除分类，请先修正后再导出")
                if row.get("default_supplier_id") and row["default_supplier_id"] not in supplier_ids:
                    raise AppException("物料引用了已删除供应商，请先修正后再导出")
                if row.get("supplier_name"):
                    choices.suppliers.append(row["supplier_name"])
            return excel.build_item_export(choices, rows)

    async def stock_template(self, current_user: AuthenticatedUser) -> bytes:
        async with get_session_context() as session:
            items = await repository.items(session, active_only=True)
            blocked = await restricted_item_ids(
                session,
                GENERAL_WAREHOUSE_SCOPE,
                {item.id for item in items},
            )
            choices = StockTemplateChoices(
                warehouses=list((await repository.warehouses(session, _org_filter(current_user), user=current_user)).keys()),
                items=[item_selection_label(item) for item in await repository.items(session, active_only=True)],
            )
        return excel.build_stock_template(choices)

    # ───────── 物料分类 ─────────
    async def _categories(self, session: AsyncSession, content: bytes, filename: str, options: InventoryImportOptions, user, *, write: bool) -> ImportResult:
        rows, errors = excel.parse_category_workbook(content, filename)
        existing = await repository.categories(session)
        seen: set[str] = set()
        result = _result(errors, ImportSummary(rows=len(rows)))
        for row in rows:
            if row.category_name in seen:
                errors.append(InventoryImportIssue(sheet=excel.SHEET_CATEGORY, row=row.row_no, field="分类名称", message="文件内分类名称重复"))
            seen.add(row.category_name)
            if row.category_name in existing and not options.allow_update_existing:
                errors.append(InventoryImportIssue(sheet=excel.SHEET_CATEGORY, row=row.row_no, field="分类名称", message="分类已存在；如需更新请开启“允许更新已有数据”"))
        result = _result(errors, ImportSummary(rows=len(rows), categories=len(seen)))
        if write and result.valid:
            for row in rows:
                created = await repository.upsert_category(
                    session, existing.get(row.category_name), {"category_name": row.category_name, "description": row.description}, user.user_id
                )
                result.created += int(created)
                result.updated += int(not created)
        return result

    # ───────── 物料档案 ─────────
    async def _items(self, session: AsyncSession, content: bytes, filename: str, options: InventoryImportOptions, user, *, write: bool) -> ImportResult:
        rows, errors = excel.parse_item_workbook(content, filename)
        asset_dictionaries = {}
        for field, (code, _) in ASSET_DEFAULT_DICTS.items():
            if any(getattr(row, field) is not None for row in rows):
                asset_dictionaries[code] = await item_repository.asset_dictionary_items(session, code)
        if write:
            await repository.lock_item_import(session, user.tenant_schema)
        categories = await repository.categories(session)
        suppliers = await repository.suppliers(session)
        all_suppliers = await repository.suppliers(session, include_inactive=True)
        units = {name: code for code, name in await repository.dict_items(session, "md_unit")}
        units.update({code: code for code in list(units.values())})
        matches = await repository.matching_items(
            session, {row.item_name for row in rows}, {row.item_no for row in rows if row.item_no}, lock=write,
        )
        by_number = {item.item_no: item for item in matches}
        by_name = {}
        for item in matches:
            by_name.setdefault((item.item_name, item.specification or ""), []).append(item)
        allowed_ids = await repository.importable_item_ids(session, user, {item.id for item in matches})
        seen: set[tuple[str, str]] = set()
        seen_numbers, seen_ids = set(), set()
        prepared: list[tuple[Any, dict[str, Any]]] = []
        sheet = excel.SHEET_ITEM
        for row in rows:
            key = (row.item_name, row.specification or "")
            same_names = by_name.get(key, [])
            entity = by_number.get(row.item_no) if row.item_no else (same_names[0] if len(same_names) == 1 else None)
            if not row.item_no and len(same_names) > 1:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料编号", message="同名同规格存在多条记录，请填写物料编号"))
            if any(item.id != getattr(entity, "id", None) for item in same_names):
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料名称", message="名称与规格已被其他编号的物料使用"))
            if row.item_no:
                if row.item_no in seen_numbers:
                    errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料编号", message="文件内物料编号重复"))
                seen_numbers.add(row.item_no)
            if entity is not None:
                if entity.id in seen_ids:
                    errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料编号", message="文件中多行指向同一物料"))
                seen_ids.add(entity.id)
                if entity.id not in allowed_ids:
                    errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料编号", message="已有物料不在当前导入权限的数据范围内"))
            if key in seen:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料名称", message="文件内物料名称 + 规格重复"))
            seen.add(key)
            category = categories.get(row.category_name)
            if row.category_name and category is None:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料分类", message="物料分类不存在"))
            if row.unit_name not in units and not (entity and row.unit_name == entity.unit_code):
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="单位", message="单位不在计量单位字典中"))
            if row.sub_unit_name and row.sub_unit_name not in units and not (entity and row.sub_unit_name == entity.sub_unit_code):
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="辅助单位", message="辅助单位不在计量单位字典中"))
            supplier_id = all_suppliers.get(row.supplier_name)
            unchanged_supplier = entity is not None and entity.default_supplier_id == supplier_id
            if row.supplier_name and (supplier_id is None or (row.supplier_name not in suppliers and not unchanged_supplier)):
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="默认供应商", message="供应商不存在或已停用"))
            if entity is not None and not options.allow_update_existing:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料名称", message="物料已存在；如需更新请开启“允许更新已有数据”"))
            asset_defaults = {field: getattr(row, field) for field in ("is_asset_managed", *ASSET_DEFAULT_DICTS, "default_asset_management_mode_code") if field in row.model_fields_set}
            try:
                normalize_asset_defaults(asset_defaults, entity, asset_dictionaries)
            except AppException as exc:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, message=exc.message))
            prepared.append(
                (
                    entity,
                    {
                        **asset_defaults,
                        "item_name": row.item_name,
                        "specification": row.specification,
                        "category_id": category.id if category else None,
                        "unit_code": units.get(row.unit_name, row.unit_name),
                        "sub_unit_code": units.get(row.sub_unit_name, row.sub_unit_name) if row.sub_unit_name else None,
                        "unit_price": row.unit_price,
                        "default_supplier_id": supplier_id if row.supplier_name else None,
                        "is_active": row.is_active,
                        "remark": row.remark,
                        **({"item_no": row.item_no} if row.item_no else {}),
                        **({"is_lot_controlled": row.is_lot_controlled} if "is_lot_controlled" in row.model_fields_set else {}),
                        **({"shelf_life_days": row.shelf_life_days} if "shelf_life_days" in row.model_fields_set else {}),
                    },
                )
            )
        result = _result(errors, ImportSummary(rows=len(rows), items=len(seen)))
        if not errors:
            result.created = sum(entity is None for entity, _ in prepared)
            result.updated = len(prepared) - result.created
        if write and result.valid:
            for entity, data in prepared:
                await repository.upsert_item(session, entity, data, user.user_id)
        return result

    # ───────── 库存盘点 ─────────
    async def _stock(self, session: AsyncSession, content: bytes, filename: str, options: InventoryImportOptions, user, *, write: bool) -> ImportResult:
        rows, errors = excel.parse_stock_workbook(content, filename)
        warehouses = await repository.warehouses(session, _org_filter(user), user=user)
        items = {item_selection_label(item): item for item in await repository.items(session, active_only=True)}
        blocked = await restricted_item_ids(
            session,
            GENERAL_WAREHOUSE_SCOPE,
            {item.id for item in items.values()},
        )
        sheet = excel.SHEET_STOCK
        grouped: dict[Any, list[OrderLineWrite]] = {}
        warehouse_by_id: dict[Any, Any] = {}
        seen: set[tuple[str, str, str]] = set()
        unchanged = 0
        for row in rows:
            warehouse = warehouses.get(row.warehouse_label)
            if warehouse is None:
                # 旧模板仅带组织/仓库名称；只在名称能唯一定位时兼容，避免同名新仓库串账。
                matches = [value for key, value in warehouses.items() if key.rsplit("（", 1)[0] == row.warehouse_label]
                warehouse = matches[0] if len(matches) == 1 else None
            item = items.get(row.item_selection)
            if warehouse is None:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="仓库", message="仓库不存在或无权访问"))
            if item is None:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料", message="物料不存在或已停用"))
            if warehouse is None or item is None:
                continue
            key = (str(warehouse.id), str(item.id), row.lot_no or "")
            if key in seen:
                errors.append(InventoryImportIssue(sheet=sheet, row=row.row_no, field="物料", message="同一仓库、物料、批次重复"))
                continue
            seen.add(key)
            book = await repository.book_quantity(session, item_id=item.id, warehouse_id=warehouse.id, lot_no=row.lot_no)
            if book != 0 and not options.allow_update_existing:
                errors.append(
                    InventoryImportIssue(sheet=sheet, row=row.row_no, field="实盘数量", message=f"已有库存 {book.normalize():f}；调整已有库存请开启“允许更新已有数据”")
                )
                continue
            if book == Decimal(row.counted_quantity):
                unchanged += 1
                continue
            warehouse_by_id[warehouse.id] = warehouse
            grouped.setdefault(warehouse.id, []).append(
                OrderLineWrite(
                    item_id=item.id,
                    lot_no=row.lot_no,
                    production_date=row.production_date,
                    expiry_date=row.expiry_date,
                    to_warehouse_id=warehouse.id,
                    counted_quantity=row.counted_quantity,
                    remark=row.remark,
                )
            )
        result = _result(errors, ImportSummary(rows=len(rows), items=len({key[1] for key in seen}), warehouses=len(grouped)))
        result.unchanged = unchanged
        if write and result.valid and grouped:
            adjust_types = await type_repository.options(session, form=None, direction_code=DIRECTION_ADJUST, include_inactive=False)
            if not adjust_types:
                raise AppException("未配置盘点调整单据类型", status_code=400)
            for warehouse_id, lines in grouped.items():
                warehouse = warehouse_by_id[warehouse_id]
                order = await order_service._create_in_session(
                    session,
                    OrderCreate(
                        order_type_id=adjust_types[0].id,
                        org_id=warehouse.org_id,
                        to_warehouse_id=warehouse.id,
                        reason=f"库存盘点导入：{filename}",
                        lines=lines,
                        confirm=True,
                    ),
                    user,
                )
                result.stock_order_ids.append(str(order.id))
                result.updated += len(lines)
        return result

    async def run(self, kind: str, content: bytes, filename: str, options: InventoryImportOptions, user: AuthenticatedUser, *, write: bool) -> ImportResult:
        handler = {"category": self._categories, "item": self._items, "stock": self._stock}[kind]
        async with get_session_context() as session:
            try:
                result = await handler(session, content, filename, options, user, write=write)
                if write and result.valid:
                    await session.commit()
                else:
                    await session.rollback()
            except IntegrityError as exc:
                await session.rollback()
                raise AppException("数据发生并发变更，本批次已回滚，请重新预校验", status_code=409) from exc
            except Exception:
                await session.rollback()
                raise
        return result


service = InventoryImportService()
