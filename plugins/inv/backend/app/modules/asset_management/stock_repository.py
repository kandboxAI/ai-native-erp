"""资产库存数据访问。

跨模块只读契约：仅在已授权过账事务中按传入库存明细/流水取来源；
查询入口按资产权限和仓库所属组织取交集，只发布物料、单号、数量和位置。
不写库存表，不发布人员及采购价格；库存由其公开过账能力维护。
"""
from sqlalchemy import exists, func, or_
from sqlmodel import select

from app.auth.scope_filters import scoped_conditions
from app.modules.inventory.models import InvStockOrder, InvStockOrderLine, InvWarehouse, MdItem
from .models import AssetLocationItem, AssetRegister
from .stock_models import AssetStockBinding, AssetStockReceipt, AssetStockSelection, AssetStockRegistrationPlan


class StockAssetRepository:
    async def issued_personal_assets(self, session, order_id, request_id):
        return (await session.exec(select(AssetStockSelection, InvStockOrderLine.item_id)
            .join(InvStockOrderLine, InvStockOrderLine.id == AssetStockSelection.stock_order_line_id)
            .join(InvStockOrder, InvStockOrder.id == InvStockOrderLine.stock_order_id).where(
                InvStockOrder.id == order_id, InvStockOrder.source_doc_type_code == "inv_requisition",
                InvStockOrder.source_doc_id == request_id, AssetStockSelection.result_binding_id.is_not(None),
                AssetStockSelection.target_location_id.is_(None), AssetStockSelection.custodian_user_id.is_not(None),
            ).order_by(InvStockOrderLine.line_no, AssetStockSelection.id))).all()

    async def registration_plan(self, session, line_id):
        return (await session.exec(select(AssetStockRegistrationPlan).where(
            AssetStockRegistrationPlan.stock_order_line_id == line_id))).first()

    async def line_receipts(self, session, line_id):
        """已鉴权库存单据的只读登记进度契约；不发布资产责任人或价格。"""
        return (await session.exec(select(AssetStockReceipt).where(
            AssetStockReceipt.stock_order_line_id == line_id, AssetStockReceipt.is_reversed.is_(False)))).all()

    def visible_asset_condition(self, user, permission):
        """在计数及分页前与资产自身权限/软删除范围取交集。"""
        return or_(
            exists(select(AssetRegister.id).where(AssetRegister.id == AssetStockBinding.asset_register_id,
                AssetRegister.org_id == AssetStockBinding.org_id,
                AssetRegister.item_id == AssetStockReceipt.item_id,
                AssetRegister.registration_status_code == "confirmed",
                AssetRegister.status_code.in_(["in_use", "idle"]),
                *scoped_conditions(AssetRegister, user, permission))),
            exists(select(AssetLocationItem.id).where(AssetLocationItem.id == AssetStockBinding.location_item_id,
                AssetLocationItem.org_id == AssetStockBinding.org_id,
                AssetLocationItem.item_id == AssetStockReceipt.item_id,
                AssetLocationItem.registration_status_code == "confirmed",
                AssetLocationItem.status_code.in_(["in_use", "idle"]),
                *scoped_conditions(AssetLocationItem, user, permission))),
        )

    def add(self, session, *rows):
        session.add_all(rows)


    async def receipt_transaction(self, session, transaction_id):
        return (await session.exec(select(AssetStockReceipt).where(
            AssetStockReceipt.stock_transaction_id == transaction_id).with_for_update())).first()

    async def source_receipts(self, session, order_id):
        return (await session.exec(select(AssetStockReceipt).join(
            InvStockOrderLine, InvStockOrderLine.id == AssetStockReceipt.stock_order_line_id,
        ).where(InvStockOrderLine.stock_order_id == order_id).with_for_update(of=AssetStockReceipt))).all()

    async def order_has_movement(self, session, order_id):
        return (await session.exec(select(AssetStockSelection.id).join(
            InvStockOrderLine, InvStockOrderLine.id == AssetStockSelection.stock_order_line_id,
        ).where(InvStockOrderLine.stock_order_id == order_id,
                AssetStockSelection.result_binding_id.is_not(None)).limit(1))).first() is not None


    async def binding(self, session, binding_id, user, *, permission="asset_register:transfer", lock=True):
        statement = select(AssetStockBinding).where(
            AssetStockBinding.id == binding_id,
            *scoped_conditions(AssetStockBinding, user, permission),
        )
        return (await session.exec(statement.with_for_update().execution_options(populate_existing=True) if lock else statement)).first()

    async def binding_receipt(self, session, binding):
        return await session.get(AssetStockReceipt, binding.receipt_id)

    async def binding_warehouse(self, session, binding):
        """已鉴权实物的当前仓库引用核验，不发布仓库目录。"""
        return (await session.exec(select(InvWarehouse).where(
            InvWarehouse.id == binding.warehouse_id,
            InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
        ))).first()

    async def asset(self, session, binding, *, user=None, permission="asset_register:transfer"):
        model, key = (AssetRegister, binding.asset_register_id) if binding.asset_register_id else (AssetLocationItem, binding.location_item_id)
        conditions = scoped_conditions(model, user, permission) if user else [model.deleted_at.is_(None)]
        return (await session.exec(select(model).where(model.id == key, *conditions).with_for_update().execution_options(populate_existing=True))).first()

    async def asset_bindings(self, session, asset, *, lock=True):
        condition = AssetStockBinding.asset_register_id == asset.id if isinstance(asset, AssetRegister) else AssetStockBinding.location_item_id == asset.id
        statement = select(AssetStockBinding).where(condition, AssetStockBinding.quantity > 0).order_by(AssetStockBinding.id)
        return (await session.exec(statement.with_for_update() if lock else statement)).all()

    async def selections(self, session, line_id):
        return (await session.exec(select(AssetStockSelection).where(
            AssetStockSelection.stock_order_line_id == line_id).order_by(AssetStockSelection.binding_id))).all()

    async def has_item_binding(self, session, item_id):
        if (await session.exec(select(AssetStockReceipt.id).where(
            AssetStockReceipt.item_id == item_id, AssetStockReceipt.is_reversed.is_(False),
            AssetStockReceipt.registered_quantity < AssetStockReceipt.quantity).limit(1))).first() is not None:
            return True
        return (await session.exec(select(AssetStockBinding.id).join(
            AssetStockReceipt, AssetStockReceipt.id == AssetStockBinding.receipt_id,
        ).where(AssetStockReceipt.item_id == item_id, AssetStockBinding.quantity > 0).limit(1))).first() is not None

    async def binding_options(self, session, *, user, item_id, warehouse_id, page, page_size, keyword=None):
        conditions = [*scoped_conditions(AssetStockBinding, user, "asset_register:transfer"),
            self.visible_asset_condition(user, "asset_register:transfer"),
            AssetStockBinding.quantity > 0, AssetStockReceipt.item_id == item_id,
            AssetStockReceipt.org_id == AssetStockBinding.org_id,
            AssetStockReceipt.is_reversed.is_(False)]
        conditions.append(AssetStockBinding.warehouse_id == warehouse_id)
        if warehouse_id is not None:
            conditions.append(exists(select(InvWarehouse.id).where(
                InvWarehouse.id == AssetStockBinding.warehouse_id,
                InvWarehouse.org_id == AssetStockBinding.org_id,
                InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
            )))
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            conditions.append(or_(
                exists(select(AssetRegister.id).where(AssetRegister.id == AssetStockBinding.asset_register_id,
                    or_(AssetRegister.asset_no.ilike(pattern), AssetRegister.serial_no.ilike(pattern)))),
                exists(select(MdItem.id).where(MdItem.id == AssetStockReceipt.item_id,
                    or_(MdItem.item_name.ilike(pattern), MdItem.specification.ilike(pattern)))),
            ))
        statement = select(AssetStockBinding, AssetStockReceipt).select_from(AssetStockBinding).join(
            AssetStockReceipt, AssetStockReceipt.id == AssetStockBinding.receipt_id,
        ).where(*conditions)
        total = (await session.exec(select(func.count()).select_from(statement.subquery()))).one()
        return total, (await session.exec(statement.order_by(AssetStockBinding.id).offset((page - 1) * page_size).limit(page_size))).all()


    async def binding_from_source_line(self, session, binding, source_line_id):
        """逐段沿实物父链核对原借出明细，不按物料或序列号猜同一件实物。"""
        current, visited = binding, set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            found = (await session.exec(select(AssetStockSelection.id).where(
                AssetStockSelection.stock_order_line_id == source_line_id,
                AssetStockSelection.result_binding_id == current.id).limit(1))).first()
            if found is not None:
                return True
            current = await session.get(AssetStockBinding, current.previous_binding_id) if current.previous_binding_id else None
        return False


stock_repository = StockAssetRepository()
