"""入库到资产的同事务闭环；库存数量只由库存拥有者过账。"""
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError

from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.ids import uuid7
from app.framework.db.session import get_session_context
from app.modules.inventory.constants import type_form
from app.modules.inventory.stock_order.tracking import register_tracking_provider, source_tracking_context
from .models import AssetLocationItem, AssetRegister
from .repository import repository as assets
from .schemas import AssetRegisterCreate, AssetRegistrationConfirm
from .service import service as asset_service
from .stock_models import AssetStockBinding, AssetStockReceipt, AssetStockSelection, AssetStockRegistrationPlan
from .stock_repository import stock_repository as repo
from .stock_schemas import StockAssetTracking


def conflict(message):
    return AppException(message, status_code=409)


def require(user, permission):
    if user is None or permission not in user.permissions:
        raise AppException(f"缺少操作权限：{permission}", status_code=403)


class StockAssetService:
    async def selection_required_item_ids_in_session(self, session, items):
        """已授权单据的物料是否需要关联实物；只发布布尔要求，不开放资产目录。"""
        result = set()
        for item in items:
            if item.is_asset_managed or await repo.has_item_binding(session, item.id):
                result.add(item.id)
        return result

    @staticmethod
    def _validate_selection_identity(order, line, binding, receipt, asset=None, warehouse=None):
        """候选和提交都保持原物料/组织边界，不用跨校区保管绕过资产权属。"""
        if receipt is None or receipt.is_reversed:
            raise conflict("所选资产的入库来源已失效，请重新选择或联系管理员核对")
        if receipt.item_id != line.item_id or (asset is not None and asset.item_id != line.item_id):
            raise conflict("所选资产与本行物资不一致，请重新选择并核对资产来源")
        if (binding.org_id != order.org_id or receipt.org_id != order.org_id
            or (asset is not None and asset.org_id != order.org_id)
            or (warehouse is not None and warehouse.org_id != binding.org_id)):
            raise conflict("所选资产的组织归属与本次出入库不一致，请联系管理员核对资产台账、入库来源、实物关联和仓库归属")

    async def issued_personal_assets_in_session(self, session, order_id, request_id):
        """已鉴权申领详情的最小发放投影；不开放资产目录或其他人员数据。"""
        if order_id is None:
            return []
        return [{"asset_no": row.asset_no_snapshot, "item_id": str(item_id), "quantity": str(row.quantity)}
                for row, item_id in await repo.issued_personal_assets(session, order_id, request_id)]

    async def _register_received_asset(self, session, receipt, warehouse, quantity, department_id, custodian_user_id, user, plan=None, remark=None):
        """仅供确认入库的同一事务使用，不提供独立补登记入口。"""
        if receipt.is_reversed or quantity > receipt.quantity - receipt.registered_quantity:
            raise conflict("入库来源状态或登记数量不一致，请刷新单据")
        if receipt.stock_status_code_snapshot == "lent":
            raise conflict("新收货不能直接登记为借出状态，请先入库再办理借出")
        location = await assets.location_for_org(session, warehouse.location_id, receipt.org_id, user=user)
        if location is None or not location.is_active:
            raise conflict("仓库位置无效，请先核对位置档案")
        common = dict(org_id=receipt.org_id, item_id=receipt.item_id, location_id=location.id,
            department_id=department_id, custodian_user_id=custodian_user_id,
            asset_type_code=receipt.asset_type_code_snapshot, status_code="idle", acquisition_source_code="stock_receipt")
        if receipt.management_mode_code_snapshot != "individual" or quantity != 1:
            raise conflict("新资产必须逐件编号，每个资产登记数量为 1")
        view = await asset_service.create_register(AssetRegisterCreate(**common,
            asset_no=plan.asset_no if plan and plan.asset_no else f"ZC-{utc_now():%Y%m%d}-{uuid7().hex}",
            acquired_date=plan.acquired_date if plan else None, original_amount=plan.original_amount if plan else None,
            remark=remark), user, session=session)
        asset = await assets.register_for_reference(session, UUID(view["id"]), receipt.org_id, for_update=True)
        binding = AssetStockBinding(org_id=receipt.org_id, receipt_id=receipt.id,
            asset_register_id=asset.id,
            warehouse_id=warehouse.id, stock_status_code=receipt.stock_status_code_snapshot,
            quantity=quantity, created_by=user.user_id, updated_by=user.user_id)
        receipt.registered_quantity += quantity
        receipt.updated_at, receipt.updated_by = utc_now(), user.user_id
        repo.add(session, receipt, binding)
        await session.flush()
        return asset

    async def ensure_registration_can_be_voided(self, session, asset):
        if asset.acquisition_source_code in {"stock_receipt", "stock_opening"} or await repo.asset_bindings(session, asset):
            raise conflict("入库生成的资产不能单独作废登记，请通过库存退库、报损或原资产流转办理")

    async def receiving_responsibility(self, session, line, warehouse, user):
        require(user, "asset_register:create")
        require(user, "asset_register:confirm")
        ensure_org_access(user, warehouse.org_id, "asset_register:create")
        ensure_org_access(user, warehouse.org_id, "asset_register:confirm")
        plan = await repo.registration_plan(session, line.id)
        department_id = plan.department_id if plan and plan.department_id else warehouse.default_asset_department_id
        custodian_user_id = plan.custodian_user_id if plan and plan.custodian_user_id else warehouse.default_asset_custodian_user_id
        if department_id is None:
            raise conflict("资产入库须指定责任部门；请在本次入库明细选择，或在仓库档案配置责任部门（例如后勤科）")
        from app.modules.inventory.public import warehouse_department_reference
        department = await warehouse_department_reference(session, owner_org_id=warehouse.org_id, department_id=department_id)
        if department is None:
            raise conflict("资产责任部门须属于收货仓库本级或有效下级组织，且部门未删除、已启用")
        await asset_service._validate_responsibility(session, department_id, custodian_user_id, user,
            "asset_register:create", reference_org_id=warehouse.org_id)
        return department_id, custodian_user_id

    async def auto_register(self, session, receipt, line, warehouse, user):
        """与库存过账共用事务；每件实物生成一个独立编号，不受旧物料登记方式影响。"""
        department_id, custodian_user_id = await self.receiving_responsibility(session, line, warehouse, user)
        plan = await repo.registration_plan(session, line.id)
        remaining = receipt.quantity - receipt.registered_quantity
        if receipt.management_mode_code_snapshot != "individual" or remaining != remaining.to_integral_value():
            raise conflict("新资产必须逐件编号，收货数量必须为整数")
        while remaining > 0:
            quantity = Decimal("1")
            created = await self._register_received_asset(session, receipt, warehouse, quantity,
                department_id, custodian_user_id, user, plan=plan, remark=line.remark)
            probe = AssetStockBinding(asset_register_id=created.id)
            asset = await repo.asset(session, probe, user=user, permission="asset_register:confirm")
            if asset is None:
                raise AppException("无权确认新建资产，入库未完成", status_code=403)
            if asset.registration_status_code == "pending_confirmation":
                await asset_service.confirm_registration("individual", asset.id,
                    AssetRegistrationConfirm(expected_version=asset.version_no), user, session=session)
            remaining -= quantity

    async def require_receiving_location(self, session, warehouse):
        """收货仓库已经由单据确定；这里只校验其档案中的位置，不让登记人重新选仓库。"""
        label = warehouse.warehouse_name
        if warehouse.location_id is None:
            raise conflict(
                f"目标仓库“{label}”已选定，但仓库档案尚未配置存放位置。"
                "请在仓库档案补充位置后重试，无需重新选择目标仓库"
            )
        from app.modules.location.public import require_location
        try:
            await require_location(session, warehouse.location_id, warehouse.org_id)
        except AppException as error:
            raise conflict(
                f"目标仓库“{label}”已选定，但配置的存放位置已失效或不属于本组织。"
                "请在仓库档案核对位置后重试，无需重新选择目标仓库"
            ) from error


    async def prepare(self, session, order, lines, user, *, order_type=None, items=None, warehouses=None):
        result = {}
        if order.reversal_of_order_id:
            return result
        for line in lines:
            selections = await repo.selections(session, line.id)
            if order_type is not None and order_type.type_no == "PURCHASE_IN" and selections:
                raise conflict("采购入库须自动登记新资产，不能关联已有资产；原资产退库请使用其他入库")
            plan = await repo.registration_plan(session, line.id)
            if plan and (order_type is None or items is None or order_type.direction_code != "in"
                or selections or not items[line.item_id].is_asset_managed):
                raise conflict("资产登记配置仅适用于开启资产管理物料的新收货入库")
            if (order_type is not None and order_type.direction_code == "in" and items is not None
                and (items[line.item_id].is_asset_managed or selections)):
                warehouse_id = line.to_warehouse_id or order.to_warehouse_id
                warehouse = (warehouses or {}).get(warehouse_id)
                if warehouse is not None:
                    await self.require_receiving_location(session, warehouse)
                    if not selections:
                        if line.quantity is not None and line.quantity != line.quantity.to_integral_value():
                            raise conflict("逐件管理的资产物料收货数量必须为整数")
                        await self.receiving_responsibility(session, line, warehouse, user)
            if not selections:
                continue
            require(user, "asset_register:transfer")
            quotas = {}
            for choice in selections:
                binding = await repo.binding(session, choice.binding_id, user)
                if binding is None:
                    raise AppException("所选实物不存在或无权访问", status_code=404)
                receipt = await repo.binding_receipt(session, binding)
                self._validate_selection_identity(order, line, binding, receipt,
                    warehouse=(warehouses or {}).get(binding.warehouse_id))
                asset = await repo.asset(session, binding, user=user)
                if asset is None or asset.registration_status_code != "confirmed" or asset.status_code not in {"in_use", "idle"}:
                    raise conflict("所选资产的登记或使用状态不允许本次流转")
                quotas[receipt.lot_id] = quotas.get(receipt.lot_id, Decimal("0")) + choice.quantity
            result[line.id] = quotas
        return result

    async def protect_manual_change(self, session, asset, *, quantity_change=False):
        """在库实物不能由资产动作绕过库存；历史资产不补造关联。"""
        if getattr(asset, "acquisition_source_code", "historical") not in {"stock_receipt", "stock_opening"}:
            return
        bindings = await repo.asset_bindings(session, asset)
        if not bindings:
            return
        if quantity_change or any(row.warehouse_id is not None for row in bindings):
            raise conflict("该资产已关联库存，请通过库存出入库、调拨或报损办理；不能单独改数量、移交或作废")


    async def move_batch_bindings(self, session, source, target, quantity):
        if getattr(source, "acquisition_source_code", "historical") not in {"stock_receipt", "stock_opening"}:
            return
        remaining = quantity
        for binding in await repo.asset_bindings(session, source):
            if remaining <= 0:
                break
            amount = min(binding.quantity, remaining)
            if amount == binding.quantity:
                binding.location_item_id = target.id
                repo.add(session, binding)
            else:
                binding.quantity -= amount
                repo.add(session, binding, AssetStockBinding(org_id=binding.org_id, receipt_id=binding.receipt_id,
                    previous_binding_id=binding.id,
                    location_item_id=target.id, quantity=amount, warehouse_id=None,
                    stock_status_code=binding.stock_status_code, created_by=target.updated_by, updated_by=target.updated_by))
            remaining -= amount
        if remaining:
            raise conflict("资产来源分配数量不一致，请先核对台账")
        target.acquisition_source_code = "stock_receipt"
        repo.add(session, target)


    async def binding_options(self, user, *, item_id, warehouse_id, page, page_size, keyword=None):
        async with get_session_context() as session:
            total, rows = await repo.binding_options(session, user=user, item_id=item_id,
                warehouse_id=warehouse_id, page=page, page_size=page_size, keyword=keyword)
            items = []
            for binding, receipt in rows:
                asset = await repo.asset(session, binding, user=user)
                if asset is None:
                    continue
                items.append({"id": str(binding.id), "quantity": str(binding.quantity),
                    "asset_no": getattr(asset, "asset_no", None), "management_mode": "individual" if binding.asset_register_id else "batch",
                    "serial_no": getattr(asset, "serial_no", None),
                    "stock_status_code": binding.stock_status_code, "registration_status_code": asset.registration_status_code,
                    "status_code": asset.status_code})
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def save(self, session, order, line, value, user):
        if value is None:
            return
        try:
            tracking = StockAssetTracking.model_validate(value)
        except ValidationError as error:
            raise AppException("资产选择配置无效：请核对数量、实物及交付目标", status_code=422) from error
        if tracking.selections:
            require(user, "asset_register:transfer")
        personal = (await source_tracking_context(session, order, user)).get("asset") if tracking.selections else None
        if tracking.registration is not None:
            if tracking.registration.asset_no and line.quantity != 1:
                raise conflict("指定资产编号时明细数量必须为一")
            repo.add(session, AssetStockRegistrationPlan(org_id=order.org_id, stock_order_line_id=line.id,
                **tracking.registration.model_dump(), created_by=user.user_id, updated_by=user.user_id))
        for choice in tracking.selections:
            binding = await repo.binding(session, choice.binding_id, user)
            if binding is None:
                raise AppException("选择的实物不存在或无权办理", status_code=404)
            receipt = await repo.binding_receipt(session, binding)
            self._validate_selection_identity(order, line, binding, receipt)
            asset = await repo.asset(session, binding, user=user)
            if asset is None:
                raise AppException("所选资产不存在或无权办理", status_code=404)
            warehouse = await repo.binding_warehouse(session, binding) if binding.warehouse_id else None
            if binding.warehouse_id and warehouse is None:
                raise conflict("所选资产的当前仓库已失效，请重新选择或联系管理员核对")
            self._validate_selection_identity(order, line, binding, receipt, asset, warehouse)
            if personal is not None:
                # 个人申领的目标身份只能由来源服务确认，忽略客户端责任覆盖。
                choice.target_location_id = None
                choice.department_id = personal["department_id"] or asset.department_id
                choice.custodian_user_id = personal["custodian_user_id"]
            if choice.target_location_id:
                location = await assets.location_for_org(session, choice.target_location_id, binding.org_id, user=user)
                if location is None or not location.is_active or location.physical_location_id is None:
                    raise conflict("请选择有效的统一物理位置")
                choice.target_location_id = location.physical_location_id
            repo.add(session, AssetStockSelection(org_id=order.org_id, stock_order_line_id=line.id,
                asset_no_snapshot=getattr(asset, "asset_no", None),
                management_mode_code_snapshot="individual" if binding.asset_register_id else "batch",
                **choice.model_dump(), created_by=user.user_id, updated_by=user.user_id))
        await session.flush()

    async def read(self, session, line):
        rows = await repo.selections(session, line.id)
        plan = await repo.registration_plan(session, line.id)
        receipts = await repo.line_receipts(session, line.id)
        if not rows and plan is None and not receipts:
            return None
        return {"registration_summary": {"quantity": str(sum((r.quantity for r in receipts), Decimal("0"))),
            "registered_quantity": str(sum((r.registered_quantity for r in receipts), Decimal("0")))} if receipts else None,
            "registration": {"department_id": str(plan.department_id) if plan.department_id else None,
            "custodian_user_id": str(plan.custodian_user_id) if plan.custodian_user_id else None,
            "asset_no": plan.asset_no, "acquired_date": plan.acquired_date.isoformat() if plan.acquired_date else None,
            "original_amount": str(plan.original_amount) if plan.original_amount is not None else None} if plan else None,
            "selections": [{"binding_id": str(row.binding_id), "quantity": str(row.quantity),
            "asset_label": row.asset_no_snapshot or "数量资产",
            "target_location_id": str(row.target_location_id) if row.target_location_id else None,
            "department_id": str(row.department_id) if row.department_id else None,
            "custodian_user_id": str(row.custodian_user_id) if row.custodian_user_id else None,
        } for row in rows]}

    async def _relocate(self, session, asset, quantity, location, department_id, custodian_user_id, user, line_id, *, custody_location_note=None):
        before_location, before_department, before_custodian = asset.location_id, asset.department_id, asset.custodian_user_id
        target = asset
        target_status = "idle" if location[1] else "in_use"
        location = location[0]
        location_id = location.id if location else None
        if isinstance(asset, AssetLocationItem) and (location_id != asset.location_id or
            (location_id is None and (quantity != asset.quantity or asset.custodian_user_id != custodian_user_id))):
            if quantity > asset.quantity:
                raise conflict("数量资产当前数量不足，请刷新后重试")
            # 个人保管的历史数量资产按本次分配独立留存，不按空位置合并不同人的责任。
            target = await assets.location_item_by_key(session, location_id, asset.item_id, for_update=True) if location_id else None
            if target is not None and (target.registration_status_code != "confirmed"
                or target.acquisition_source_code not in {"stock_receipt", "stock_opening"}
                or target.department_id != department_id or target.custodian_user_id != custodian_user_id
                or target.status_code != target_status or target.asset_type_code != asset.asset_type_code):
                raise conflict("目标位置同类数量资产的责任、类型或状态不一致，不能直接合并")
            before = asset.quantity
            asset.quantity -= quantity
            if asset.quantity == 0:
                asset.deleted_at, asset.deleted_by = utc_now(), user.user_id
            if target is None:
                target = AssetLocationItem(org_id=asset.org_id, item_id=asset.item_id, location_id=location_id,
                    quantity=quantity, unit_code_snapshot=asset.unit_code_snapshot, asset_type_code=asset.asset_type_code,
                    acquisition_source_code="stock_receipt", registration_status_code="confirmed",
                    registered_at=asset.registered_at, registered_by=asset.registered_by,
                    department_id=department_id, custodian_user_id=custodian_user_id, status_code=target_status,
                    created_by=user.user_id, updated_by=user.user_id)
            else:
                target.quantity += quantity
            repo.add(session, asset, target, asset_service.event(asset, user, "transfer_out", "库存关联流转",
                quantity_before=before, quantity_after=asset.quantity, from_location_id=before_location,
                to_location_id=location_id, source_type_code="stock_order_line", source_id=line_id))
        elif isinstance(asset, AssetLocationItem) and quantity != asset.quantity and (
            asset.department_id != department_id or asset.custodian_user_id != custodian_user_id or asset.status_code != target_status
        ):
            raise conflict("同一位置数量资产不能拆分不同责任，请选择独立交付位置")
        target.location_id, target.department_id, target.custodian_user_id = location_id, department_id, custodian_user_id
        target.custody_location_note = custody_location_note if location_id is None else None
        target.status_code = target_status
        for row in {asset.id: asset, target.id: target}.values():
            row.version_no += 1
            row.updated_at, row.updated_by = utc_now(), user.user_id
        repo.add(session, target)
        await session.flush()
        repo.add(session, asset_service.event(target, user, "transfer", "库存关联流转",
            from_location_id=before_location, to_location_id=location_id,
            from_department_id=before_department, to_department_id=department_id,
            from_custodian_user_id=before_custodian, to_custodian_user_id=custodian_user_id,
            source_type_code="stock_order_line", source_id=line_id))
        return target

    async def post(self, session, order, order_type, lines, items, warehouses, transactions, user):
        if order.reversal_of_order_id:
            receipts = await repo.source_receipts(session, order.reversal_of_order_id)
            if any(row.registered_quantity > 0 for row in receipts) or await repo.order_has_movement(session, order.reversal_of_order_id):
                raise conflict("该单据已关联资产登记或实物流转，请先通过原资产办理退库或纠正，不能单独冲销库存")
            known_lines = {row.stock_order_line_id for row in receipts}
            for line in lines:
                if line.source_line_id not in known_lines and await repo.has_item_binding(session, line.item_id):
                    raise conflict("原单据没有可核验的资产来源，当前库存已关联资产或待登记任务，不能单独冲销")
            for row in receipts:
                row.is_reversed = True
                row.updated_at, row.updated_by = utc_now(), user.user_id if user else None
                repo.add(session, row)
            return
        for line in lines:
            txs = [row for row in transactions if row.stock_order_line_id == line.id]
            choices = await repo.selections(session, line.id)
            is_managed = items[line.item_id].is_asset_managed or bool(choices)
            if not is_managed:
                is_managed = await repo.has_item_binding(session, line.item_id)
            if not is_managed:
                continue
            if user is None:
                raise conflict("资产物料过账必须提供已验证的操作身份")
            if not txs:
                if choices:
                    raise conflict("本明细没有库存变化，不能关联实物流转")
                continue
            if type_form(order_type) == "adjust" and any(row.from_warehouse_id is not None for row in txs):
                raise conflict("资产物料盘亏须先核对具体实物并办理报损处置，不能单独调整库存余额")
            if not choices and all(row.from_warehouse_id is None for row in txs):
                if not items[line.item_id].is_asset_managed:
                    continue
                item = items[line.item_id]
                if not item.default_asset_type_code:
                    raise conflict("资产物料入库前须在物料档案配置资产类型")
                await asset_service._valid_code(session, "asset_type", item.default_asset_type_code, "资产类型")
                if any(tx.quantity != tx.quantity.to_integral_value() for tx in txs):
                    raise conflict("逐件管理的资产物料收货数量必须为整数")
                for tx in txs:
                    await self.require_receiving_location(session, warehouses[tx.to_warehouse_id])
                    receipt = await repo.receipt_transaction(session, tx.id)
                    if receipt is None:
                        receipt = AssetStockReceipt(org_id=warehouses[tx.to_warehouse_id].org_id,
                            stock_transaction_id=tx.id, stock_order_line_id=line.id, warehouse_id=tx.to_warehouse_id,
                            item_id=line.item_id, lot_id=tx.lot_id, quantity=tx.quantity,
                            management_mode_code_snapshot="individual",
                            asset_type_code_snapshot=item.default_asset_type_code,
                            stock_status_code_snapshot=tx.to_stock_status_code,
                            created_by=user.user_id, updated_by=user.user_id)
                        repo.add(session, receipt)
                        await session.flush()
                    await self.auto_register(session, receipt, line, warehouses[tx.to_warehouse_id], user)
                continue
            require(user, "asset_register:transfer")
            if not choices or sum((row.quantity for row in choices), Decimal("0")) != sum((tx.quantity for tx in txs), Decimal("0")):
                raise conflict("资产物料须按本次数量选择已确认的实物；请核对入库单的自动资产登记结果")
            quotas = {}
            for tx in txs:
                key = (tx.lot_id, tx.from_warehouse_id, tx.from_stock_status_code, tx.to_warehouse_id, tx.to_stock_status_code)
                quotas[key] = quotas.get(key, Decimal("0")) + tx.quantity
            for choice in choices:
                if choice.result_binding_id:
                    raise conflict("资产明细已过账，不能重复处理")
                binding = await repo.binding(session, choice.binding_id, user)
                if binding is None or binding.quantity < choice.quantity:
                    raise conflict("所选实物已流转或数量不足，请重新选择")
                receipt = await repo.binding_receipt(session, binding)
                asset = await repo.asset(session, binding, user=user)
                if asset is None:
                    raise conflict("所选资产不存在或无权办理，请刷新后重新选择")
                self._validate_selection_identity(order, line, binding, receipt, asset,
                    warehouse=warehouses.get(binding.warehouse_id))
                if asset.registration_status_code != "confirmed" or asset.status_code not in {"idle", "in_use"}:
                    raise conflict("所选资产的登记或使用状态不允许本次流转")
                if binding.asset_register_id is not None and (choice.quantity != 1 or binding.quantity != 1):
                    raise conflict("单件资产每次必须整件流转，不能拆分数量")
                if isinstance(asset, AssetLocationItem) and sum((row.quantity for row in await repo.asset_bindings(session, asset)), Decimal("0")) != asset.quantity:
                    raise conflict("该数量资产的来源分配与台账数量不一致，不能办理流转")
                key = next((key for key, remaining in quotas.items() if remaining >= choice.quantity
                    and key[0] == receipt.lot_id and key[1] == binding.warehouse_id
                    and (key[1] is None or key[2] == binding.stock_status_code)), None)
                if key is None:
                    raise conflict("实物的仓库、批次或库存状态与本明细不一致")
                if line.source_line_id and not await repo.binding_from_source_line(session, binding, line.source_line_id):
                    raise conflict("归还实物不属于引用的原借出明细")
                quotas[key] -= choice.quantity
                to_warehouse = warehouses.get(key[3])
                if type_form(order_type) == "damage":
                    if isinstance(asset, AssetRegister):
                        asset.status_code = "disposed"
                    else:
                        asset.quantity -= choice.quantity
                        if asset.quantity == 0:
                            asset.deleted_at, asset.deleted_by = utc_now(), user.user_id
                    asset.version_no += 1
                    asset.updated_at, asset.updated_by = utc_now(), user.user_id
                    binding.quantity -= choice.quantity
                    # 零数量结果保留本次处置的原实物身份，不能再次退库。
                    result = AssetStockBinding(org_id=binding.org_id, receipt_id=binding.receipt_id,
                        previous_binding_id=binding.id,
                        asset_register_id=binding.asset_register_id, location_item_id=binding.location_item_id,
                        quantity=Decimal("0"), warehouse_id=None, stock_status_code=binding.stock_status_code,
                        created_by=user.user_id, updated_by=user.user_id)
                    repo.add(session, asset, binding, result, asset_service.event(asset, user, "status_changed", "库存报损处置",
                        source_type_code="stock_order_line", source_id=line.id))
                    await session.flush()
                    choice.result_binding_id = result.id
                    repo.add(session, choice)
                    continue
                personal = (await source_tracking_context(session, order, user)).get("asset")
                if personal is not None:
                    if to_warehouse or order_type.type_no != "REQUISITION_OUT":
                        raise conflict("个人申领责任只允许用于领用出库")
                    location = None
                    choice.target_location_id = None
                    choice.department_id = personal["department_id"] or asset.department_id
                    choice.custodian_user_id = personal["custodian_user_id"]
                else:
                    physical_id = to_warehouse.location_id if to_warehouse and key[4] == "available" else choice.target_location_id
                    if not physical_id or not choice.department_id:
                        raise conflict("资产流转须填写目标位置和责任部门；退库或调拨先配置目标仓库位置")
                    location = await assets.location_for_org(session, physical_id, asset.org_id, user=user)
                    if location is None or not location.is_active:
                        raise conflict("交付位置已停用、不属于资产组织或无权访问")
                    await asset_service._validate_responsibility(session, choice.department_id, choice.custodian_user_id, user, "asset_register:transfer")
                if to_warehouse and to_warehouse.org_id != asset.org_id:
                    raise conflict("跨组织资产权属转移须单独办理，不能仅调拨库存")
                target = await self._relocate(session, asset, choice.quantity, (location, key[4] == "available" if to_warehouse else False),
                    choice.department_id, choice.custodian_user_id, user, line.id,
                    custody_location_note=personal["custody_location_note"] if personal else None)
                binding.quantity -= choice.quantity
                binding.updated_at, binding.updated_by = utc_now(), user.user_id
                repo.add(session, binding)
                await session.flush()
                result = AssetStockBinding(org_id=binding.org_id, receipt_id=binding.receipt_id,
                    previous_binding_id=binding.id,
                    asset_register_id=target.id if isinstance(target, AssetRegister) else None,
                    location_item_id=target.id if isinstance(target, AssetLocationItem) else None,
                    warehouse_id=key[3], stock_status_code=key[4] or binding.stock_status_code,
                    quantity=choice.quantity, created_by=user.user_id, updated_by=user.user_id)
                repo.add(session, result)
                await session.flush()
                choice.result_binding_id, choice.updated_at, choice.updated_by = result.id, utc_now(), user.user_id
                repo.add(session, choice)


stock_service = StockAssetService()
register_tracking_provider("asset", stock_service)
