"""MES 库存编排；调用 inv 公开契约，不复制记账、审批、余额和流水。"""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from app.core.exceptions import AppException
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.inventory import public as stock

from .inventory_models import MesInventoryPosting
from .inventory_repository import inventory_repository as repo
from .delivery_service import request_hash
from .report_repository import report_repository
from .warehouse_policy import validate_warehouse
from . import warehouse_scenes  # 登记普通制造收发校验，inv 不反向依赖 MES。

SOURCE = "mes_work_order"
TYPES = {"issue": ("MES_PRODUCTION_ISSUE", "生产领料", "out"), "return": ("MES_PRODUCTION_RETURN", "生产退料", "in"),
         "receipt": ("MES_PRODUCTION_RECEIPT", "成品入库", "in"), "shipment": ("MES_SHIPMENT_OUT", "出货出库", "out")}
for _index, (_number, _name, _direction) in enumerate(TYPES.values()):
    stock.register_stock_order_rule(stock.StockOrderRule(
        type_no=_number, name=_name, direction=_direction,
        from_status="available" if _direction == "out" else None,
        to_status="available" if _direction == "in" else None, approval=False,
        form="inbound" if _direction == "in" else "outbound",
        no_prefix="MESRK" if _direction == "in" else "MESCK", sort_no=200 + _index,
        source_managed=True, warehouse_scope_key="mes"))
_context = ContextVar("mes_inventory_request", default=None)


@contextmanager
def inventory_request(row, stage):
    token = _context.set((row, stage))
    try: yield
    finally: _context.reset(token)


def active(state, *, confirmed=False):
    if state is None or state["is_reversed"]: return False
    return state["status_code"] == "confirmed" if confirmed else state["status_code"] != "voided"


class MesInventoryService:
    async def snapshot(self, session, order_id):
        rows = await repo.postings(session, order_id)
        states = await stock.get_stock_order_states(session, [row.stock_order_id for row in rows])
        if any(row.stock_order_id not in states for row in rows): raise AppException("库存来源记录不完整，请检查关联单据", 409)
        return [(row, states[row.stock_order_id]) for row in rows]

    async def produced(self, session, order):
        if getattr(order, "is_process_change_repair", False):
            return Decimal(0)
        operations = await repo.operations(session, order.id)
        last = max(operations, key=lambda row: row.sequence_no) if operations else None
        eligible = order.status_code in {"released", "in_progress", "completed"} and last is not None and last.status_code in {"pending", "dispatched", "completed"} and (not last.is_quality_required or last.status_code == "completed")
        return last.good_quantity if eligible else Decimal(0)

    async def receipt_reserved(self, session, order_id, *, exclude=None):
        return sum((row.quantity for row, state in await self.snapshot(session, order_id)
            if row.id != exclude and row.posting_type_code == "receipt" and active(state)), Decimal(0))

    async def warehouse_remaining(self, session, order_id, warehouse_id, *, exclude=None):
        rows = await self.snapshot(session, order_id)
        received = sum((row.quantity for row, state in rows if row.posting_type_code == "receipt" and row.warehouse_id == warehouse_id and active(state, confirmed=True)), Decimal(0))
        reserved = sum((row.quantity for row, state in rows if row.id != exclude and row.posting_type_code == "shipment" and row.warehouse_id == warehouse_id and active(state)), Decimal(0))
        return max(Decimal(0), received - reserved)

    async def shipment_allocations(self, session, shipments, states):
        pending = [row.stock_order_id for row in shipments if states[row.stock_order_id]["status_code"] != "confirmed"]
        result = await stock.get_stock_order_allocations(session, pending)
        for row in shipments:
            if states[row.stock_order_id]["status_code"] == "confirmed":
                result[row.stock_order_id] = await stock.get_stock_order_lots(session, row.stock_order_id)
        return result

    async def finished_lots(self, session, row, *, exclude=None):
        """工单自己的已记账入库批次，扣除该工单尚有效的出货预留。禁止退回全局 FIFO。"""
        snapshot = await self.snapshot(session, row.work_order_id)
        remaining = {}
        for receipt, state in snapshot:
            if receipt.posting_type_code != "receipt" or receipt.warehouse_id != row.warehouse_id or not active(state, confirmed=True): continue
            for entry in await stock.get_stock_order_lots(session, receipt.stock_order_id):
                if entry["item_id"] != row.item_id or entry["warehouse_id"] != row.warehouse_id: continue
                if entry["lot_id"] is None: raise AppException("该工单存在未绑定批次的历史成品入库；请核对库存并冲销后重新入库，不能混用其他工单库存", 409)
                remaining[entry["lot_id"]] = remaining.get(entry["lot_id"], Decimal(0)) + entry["quantity"]
        if remaining:
            for receipt in await repo.receipts_for_items(session, row.warehouse_id, {row.item_id}):
                if receipt.work_order_id == row.work_order_id: continue
                if any(entry["lot_id"] in remaining for entry in await stock.get_stock_order_lots(session, receipt.stock_order_id)):
                    raise AppException("历史成品批次被多个工单共用，请核对并拆分后再出货，禁止混发", 409)
        shipments = [entry for entry, state in snapshot if entry.id != exclude and entry.posting_type_code == "shipment" and entry.warehouse_id == row.warehouse_id and active(state)]
        plans = await self.shipment_allocations(session, shipments, {entry.stock_order_id: state for entry, state in snapshot})
        for shipment in shipments:
            entries = plans.get(shipment.stock_order_id, [])
            if not entries or any(entry["lot_id"] is None for entry in entries):
                raise AppException("存在未绑定工单批次的历史出货申请，请先取消并重新创建", 409)
            if sum((entry["quantity"] for entry in entries), Decimal(0)) != shipment.quantity:
                raise AppException("出货批次明细数量与来源申请不一致，请核对库存", 409)
            for entry in entries:
                lot = entry["lot_id"]
                if entry["item_id"] != row.item_id or (entry.get("warehouse_id") or shipment.warehouse_id) != row.warehouse_id or lot not in remaining:
                    raise AppException("出货批次不属于本工单，库存来源需要核对", 409)
                remaining[lot] -= entry["quantity"]
        if any(quantity < 0 for quantity in remaining.values()): raise AppException("工单批次出货占用超出入库数量", 409)
        return remaining

    async def validate_shipment_lots(self, session, row, lines):
        remaining = await self.finished_lots(session, row, exclude=row.id)
        for line in lines:
            if line.lot_id is None or line.lot_id not in remaining: raise AppException("出货批次不属于本工单，禁止混发", 409)
            remaining[line.lot_id] -= line.quantity
        if any(quantity < 0 for quantity in remaining.values()): raise AppException("本工单成品批次可出货数量不足", 409)

    async def has_active(self, session, order_id, *, output_only=False):
        return any(active(state) and (not output_only or row.posting_type_code in {"receipt", "shipment"}) for row, state in await self.snapshot(session, order_id))

    async def has_history(self, session, order_id):
        return bool(await repo.postings(session, order_id))

    async def validate(self, session, row, order, *, exclude=None):
        if row.org_id != order.org_id: raise AppException("库存单据与工单组织不一致")
        if row.posting_type_code == "issue" and order.status_code not in {"released", "in_progress"}:
            raise AppException("只有已发布或生产中的工单可以领料", 409)
        operations = await repo.operations(session, order.id)
        if row.operation_id and row.operation_id not in {op.id for op in operations}: raise AppException("所选工序不属于本工单")
        if row.posting_type_code in {"receipt", "shipment"}:
            if row.item_id != order.product_item_id or row.unit_code != order.unit_code: raise AppException("成品物料或基本单位与工单快照不一致")
            if await report_repository.pending_for_order(session, order.id): raise AppException("工单有报工变更审批，请处理完成后办理库存", 409)
        if row.posting_type_code == "receipt":
            from .delivery_repository import delivery_repository
            direct = await delivery_repository.direct_shipped_quantity(session, order.id)
            remaining = await self.produced(session, order) - direct - await self.receipt_reserved(session, order.id, exclude=exclude)
            if row.quantity > remaining: raise AppException("成品可入库数量不足；请先完成末道报工并结束执行，直发和已申请入库不能重复占用产出", 409)
        elif row.posting_type_code == "shipment":
            if row.quantity > await self.warehouse_remaining(session, order.id, row.warehouse_id, exclude=exclude):
                raise AppException("该工单在所选仓库的可出货入库数量不足", 409)
        elif row.posting_type_code == "return":
            original = await repo.posting(session, row.source_posting_id)
            if original is None or original.work_order_id != order.id or original.posting_type_code != "issue": raise AppException("原领料记录不属于本工单")
            states = await stock.get_stock_order_states(session, {original.stock_order_id})
            if not active(states.get(original.stock_order_id), confirmed=True): raise AppException("只有已记账且未冲销的领料可以退料", 409)
            if (row.item_id, row.warehouse_id, row.operation_id, row.unit_code) != (original.item_id, original.warehouse_id, original.operation_id, original.unit_code):
                raise AppException("退料物料、仓库、工序及单位必须与原领料一致")
            lots = await stock.get_stock_order_lots(session, original.stock_order_id)
            issued = sum((entry["quantity"] for entry in lots if entry["lot_id"] == row.lot_id and entry["item_id"] == row.item_id and entry["warehouse_id"] == row.warehouse_id), Decimal(0))
            returned = sum((entry.quantity for entry, state in await self.snapshot(session, order.id) if entry.id != exclude and entry.source_posting_id == original.id and entry.lot_id == row.lot_id and active(state)), Decimal(0))
            if row.quantity > issued - returned: raise AppException("该领料批次可退数量不足；按原领料实际批次退回，不能超退", 409)

    async def require_access(self, session, row, user):
        permission = "mes:shipment:manage" if row.posting_type_code == "shipment" else "mes:inventory:manage"
        if permission not in user.permissions: raise AppException("缺少来源业务管理权限", 403)
        visible = await repo.posting(session, row.id, user=user, permission=permission)
        if visible is None: raise AppException("库存来源记录超出当前业务数据范围", 403)

    async def create_in_session(self, session, row, user, *, business_date=None, confirm=True):
        await validate_warehouse(session, row)
        spec = await stock.get_stock_order_type(session, TYPES[row.posting_type_code][0])
        direction = TYPES[row.posting_type_code][2]
        if spec["direction_code"] != direction or spec["is_negative_allowed"]:
            raise AppException("生产库存类型方向不匹配或开启负库存，请检查配置")
        expected_status = spec["default_from_status_code"] if direction == "out" else spec["default_to_status_code"]
        if expected_status not in {None, "available"}: raise AppException("当前生产业务仅支持可用库存状态，请检查类型配置")
        entries = [(row.lot_id, row.quantity)]
        if row.posting_type_code == "receipt" and row.lot_id is not None:
            raise AppException("成品入库自动建立独立工单批次，不能指定已有批次", 409)
        if row.posting_type_code == "shipment":
            remaining = row.quantity
            entries = []
            for lot, quantity in (await self.finished_lots(session, row)).items():
                take = min(remaining, quantity)
                if take > 0: entries.append((lot, take))
                remaining -= take
                if remaining == 0: break
            if remaining > 0: raise AppException("本工单成品批次可出货数量不足", 409)
        lines = [stock.StockOrderLine(item_id=row.item_id, lot_id=lot, quantity=quantity, unit_code=row.unit_code, unit_price=row.unit_price,
            lot_no=f"MES-{uuid7().hex}" if row.posting_type_code == "receipt" else None,
            from_stock_status_code="available" if direction == "out" else None, to_stock_status_code="available" if direction == "in" else None)
            for lot, quantity in entries]
        with inventory_request(row, "create"):
            result = await stock.create_stock_order(session, stock.StockOrderCreate(order_type_id=spec["id"], org_id=row.org_id,
                from_warehouse_id=row.warehouse_id if direction == "out" else None,
                to_warehouse_id=row.warehouse_id if direction == "in" else None, source_doc_type_code=SOURCE, source_doc_id=row.work_order_id,
                reason=row.note or TYPES[row.posting_type_code][1], remark=row.note,
                lines=lines, submit=True,
                **({"business_date": business_date} if business_date is not None else {})), user)
        row.stock_order_id = result["id"]
        repo.add(session, row)
        await session.flush()
        if confirm and not spec["is_approval_required"]:
            with inventory_request(row, "confirm"):
                await stock.confirm_stock_order(session, row.stock_order_id, user)
        return row

    async def create(self, body, user):
        async with get_session_context() as session:
            existing = await repo.by_key(session, user.user_id, body.idempotency_key)
            if existing:
                if existing.request_hash != request_hash(body): raise AppException("幂等键已用于不同库存申请", 409)
                await self.require_access(session, existing, user)
                return await self.item(session, existing)
            order = await repo.order(session, body.work_order_id, user, lock=True)
            if order is None: raise AppException("生产工单不存在或无权操作", 404)
            item = await stock.get_active_item(session, body.item_id)
            if item is None: raise AppException("物料不存在或已停用")
            if getattr(item, "is_serial_controlled", False): raise AppException("序列号物料的逐件库存跟踪尚未接入，当前不能办理")
            row = MesInventoryPosting(org_id=order.org_id, work_order_id=order.id, operation_id=body.operation_id,
                posting_type_code=body.posting_type_code, source_posting_id=body.source_posting_id,
                stock_order_id=uuid7(), item_id=item.id, item_no_snapshot=item.item_no, item_name_snapshot=item.item_name,
                warehouse_id=body.warehouse_id, lot_id=body.lot_id, quantity=body.quantity, unit_code=item.unit_code,
                unit_price=body.unit_price, note=body.note, idempotency_key=body.idempotency_key,
                request_hash=request_hash(body), created_by=user.user_id, updated_by=user.user_id)
            await self.validate(session, row, order)
            await self.create_in_session(session, row, user, business_date=body.business_date)
            result = await self.item(session, row)
            await session.commit()
            return result

    async def item(self, session, row, number=None):
        state = (await stock.get_stock_order_states(session, {row.stock_order_id}))[row.stock_order_id]
        return dict(id=row.id, org_id=row.org_id, work_order_id=row.work_order_id, work_order_no=number,
            operation_id=row.operation_id, posting_type_code=row.posting_type_code, source_posting_id=row.source_posting_id,
            shipment_line_id=row.shipment_line_id, item_id=row.item_id, item_no=row.item_no_snapshot, item_name=row.item_name_snapshot,
            warehouse_id=row.warehouse_id, lot_id=row.lot_id, quantity=str(row.quantity), unit_code=row.unit_code,
            stock_order_id=row.stock_order_id, order_no=state["order_no"], status_code="reversed" if state["is_reversed"] else state["status_code"],
            business_date=state["business_date"], note=row.note)

    async def page(self, query, user):
        async with get_session_context() as session:
            rows, total = await repo.page(session, query, user)
            return dict(items=[await self.item(session, row, number) for row, number in rows], total=total, page=query.page, page_size=query.page_size)

    async def action(self, posting_id, action, reason, user):
        if not reason.strip(): raise AppException("请填写操作理由")
        async with get_session_context() as session:
            row = await repo.posting(session, posting_id, user=user, permission="mes:inventory:manage")
            if row is None: raise AppException("库存业务记录不存在或无权访问", 404)
            if row.posting_type_code == "shipment": raise AppException("仓储出货请从出货单完成或取消", 409)
            # Persisted stock mutations lock inv first, then validators lock the MES parent.
            # Creation locks the MES parent and inserts new inv rows, never waiting on another persisted inv row.
            with inventory_request(row, action):
                if action == "confirm": await stock.confirm_stock_order(session, row.stock_order_id, user)
                elif action == "cancel": await stock.cancel_stock_order(session, row.stock_order_id, reason, user)
                else: raise AppException("不支持的库存动作", 422)
            result = await self.item(session, row)
            await session.commit()
            return result

    async def finish_shipment(self, session, shipment, lines, orders, user):
        records = await repo.shipment_postings(session, shipment.id)
        if not records:
            for line in lines:
                order = orders[line.work_order_id]
                item = await stock.get_active_item(session, line.product_item_id)
                if item is None or getattr(item, "is_serial_controlled", False): raise AppException("产品已停用或需要尚未接入的序列号跟踪")
                row = MesInventoryPosting(org_id=shipment.org_id, work_order_id=order.id, stock_order_id=uuid7(),
                    posting_type_code="shipment", shipment_line_id=line.id, item_id=line.product_item_id,
                    item_no_snapshot=line.product_item_no_snapshot, item_name_snapshot=line.product_item_name_snapshot,
                    warehouse_id=shipment.warehouse_id, quantity=line.quantity, unit_code=line.unit_code,
                    note=f"出货 {shipment.shipment_no}", idempotency_key=f"shipment:{line.id}", request_hash=str(line.id),
                    created_by=user.user_id, updated_by=user.user_id)
                await self.validate(session, row, order)
                await self.create_in_session(session, row, user, business_date=shipment.business_date, confirm=False)
                records.append(row)
        if {row.shipment_line_id for row in records} != {line.id for line in lines}:
            raise AppException("出货与库存来源明细不完整，请检查关联记录", 409)
        states = await stock.get_stock_order_states(session, [row.stock_order_id for row in records])
        if any(not active(states.get(row.stock_order_id)) for row in records): raise AppException("来源库存单据已作废或冲销，请取消并重新创建出货", 409)
        if any(states[row.stock_order_id]["status_code"] in {"draft", "submitted"} for row in records):
            return False
        for row in records:
            if states[row.stock_order_id]["status_code"] != "confirmed":
                with inventory_request(row, "confirm"):
                    await stock.confirm_stock_order(session, row.stock_order_id, user)
        return True

    async def cancel_shipment(self, session, shipment, reason, user):
        for row in await repo.shipment_postings(session, shipment.id):
            with inventory_request(row, "cancel"):
                await stock.cancel_stock_order(session, row.stock_order_id, reason, user)

    async def validate_reversal(self, session, row, order):
        snapshot = await self.snapshot(session, order.id)
        if row.posting_type_code == "issue" and any(entry.source_posting_id == row.id and active(state) for entry, state in snapshot):
            raise AppException("原领料已有退料，请先冲销退料，再冲销原领料", 409)
        if row.posting_type_code == "receipt":
            actual = {entry["lot_id"] for entry in await stock.get_stock_order_lots(session, row.stock_order_id)}
            shipments = [entry for entry, state in snapshot if entry.posting_type_code == "shipment" and entry.warehouse_id == row.warehouse_id and active(state)]
            plans = await self.shipment_allocations(session, shipments, {entry.stock_order_id: state for entry, state in snapshot})
            if any(not plans.get(entry.stock_order_id) or any(plan["lot_id"] is None for plan in plans[entry.stock_order_id]) for entry in shipments):
                raise AppException("成品入库已被出货占用，请先取消未绑定批次的历史出货", 409)
            if any(entry["lot_id"] in actual for entries in plans.values() for entry in entries):
                raise AppException("成品入库批次已被出货占用，请先取消关联出货", 409)
            received = sum((entry.quantity for entry, state in snapshot if entry.id != row.id and entry.posting_type_code == "receipt" and entry.warehouse_id == row.warehouse_id and active(state, confirmed=True)), Decimal(0))
            shipped = sum((entry.quantity for entry, state in snapshot if entry.posting_type_code == "shipment" and entry.warehouse_id == row.warehouse_id and active(state)), Decimal(0))
            if received < shipped: raise AppException("成品入库已被出货占用，请先取消关联出货", 409)


inventory_service = MesInventoryService()


async def mutation_guard(session, order, user, action):
    row = await repo.posting(session, stock_order_id=order.id)
    if row is None: raise AppException("MES 库存来源关联缺失，不能直接修改", 409)
    await inventory_service.require_access(session, row, user)
    context = _context.get()
    matched = context is not None and context[0].id == row.id
    if not matched and (action in {"create", "update", "delete"} or row.posting_type_code == "shipment" and action == "confirm"):
        raise AppException("该单据由 MES 业务维护，请从生产消耗、成品入库或出货页面操作", 409)


async def validate_write(session, order, order_type, lines, user):
    if order.source_doc_type_code != SOURCE and order_type.type_no not in {entry[0] for entry in TYPES.values()}: return
    context = _context.get()
    if context is None or context[1] != "create": raise AppException("MES 库存单据必须从来源业务创建", 409)
    row = context[0]
    if order.source_doc_type_code != SOURCE or order.source_doc_id != row.work_order_id or order.org_id != row.org_id or order_type.type_no != TYPES[row.posting_type_code][0]:
        raise AppException("库存来源类型、工单或组织与业务申请不一致")
    if not lines or sum((line.quantity for line in lines), Decimal(0)) != row.quantity or any((line.item_id, line.unit_code) != (row.item_id, row.unit_code) for line in lines) or row.posting_type_code != "shipment" and len(lines) != 1:
        raise AppException("库存明细与来源业务申请不一致")
    for line in lines:
        warehouse = (line.from_warehouse_id or order.from_warehouse_id) if order_type.direction_code == "out" else (line.to_warehouse_id or order.to_warehouse_id)
        if warehouse != row.warehouse_id or row.lot_id is not None and line.lot_id != row.lot_id:
            raise AppException("库存仓库或批次与来源业务申请不一致")
        if row.posting_type_code == "return" and line.lot_id != row.lot_id: raise AppException("退料必须退回原领料批次")
        if row.posting_type_code == "receipt" and line.lot_id is None: raise AppException("成品入库必须建立独立工单批次", 409)
    if row.posting_type_code == "shipment": await inventory_service.validate_shipment_lots(session, row, lines)
    row.lot_id, row.stock_order_id = lines[0].lot_id if len(lines) == 1 else None, order.id


async def validate_confirmation(session, order, order_type, lines, user):
    if order.source_doc_type_code != SOURCE and order_type.type_no not in {entry[0] for entry in TYPES.values()}: return
    original_id = order.reversal_of_order_id or order.id
    row = await repo.posting(session, stock_order_id=original_id)
    if row is None or order.source_doc_type_code != SOURCE or order.source_doc_id != row.work_order_id or order.org_id != row.org_id:
        raise AppException("库存来源与 MES 关联不一致", 409)
    if order_type.type_no != TYPES[row.posting_type_code][0] or order_type.direction_code != TYPES[row.posting_type_code][2] or order_type.is_negative_allowed:
        raise AppException("库存单据类型配置与生产业务不一致")
    await inventory_service.require_access(session, row, user)
    if row.posting_type_code == "shipment":
        context = _context.get()
        if context is None or context[0].id != row.id: raise AppException("出货库存单据只能随来源出货单记账或冲销", 409)
    parent = await repo.order(session, row.work_order_id, lock=True)
    if parent is None: raise AppException("来源工单已不可用", 409)
    if order.reversal_of_order_id:
        await inventory_service.validate_reversal(session, row, parent)
    else:
        await validate_warehouse(session, row)
        if not lines or sum((line.quantity for line in lines), Decimal(0)) != row.quantity or any((line.item_id, line.unit_code) != (row.item_id, row.unit_code) for line in lines) or row.posting_type_code != "shipment" and (len(lines) != 1 or lines[0].lot_id != row.lot_id):
            raise AppException("库存明细已偏离来源申请，不能记账", 409)
        outbound = TYPES[row.posting_type_code][2] == "out"
        for line in lines:
            if row.posting_type_code == "receipt" and line.lot_id is None: raise AppException("成品入库必须绑定工单批次，请取消旧申请后重新入库", 409)
            warehouse = (line.from_warehouse_id or order.from_warehouse_id) if outbound else (line.to_warehouse_id or order.to_warehouse_id)
            status = (line.from_stock_status_code or order_type.default_from_status_code or "available") if outbound else (line.to_stock_status_code or order_type.default_to_status_code or "available")
            if warehouse != row.warehouse_id or status != "available": raise AppException("库存仓库或可用状态已偏离来源申请，不能记账", 409)
        if row.posting_type_code == "shipment": await inventory_service.validate_shipment_lots(session, row, lines)
        await inventory_service.validate(session, row, parent, exclude=row.id)


async def refresh_consumed(session, order, order_type, lines, user):
    parent = await repo.order(session, order.source_doc_id, lock=True)
    if parent is None: raise AppException("库存来源工单不可用", 409)
    snapshot = await inventory_service.snapshot(session, parent.id)
    for requirement in await repo.requirements(session, parent.id):
        quantity = sum((row.quantity * (1 if row.posting_type_code == "issue" else -1) for row, state in snapshot if
            row.operation_id == requirement.operation_id and row.item_id == requirement.item_id and row.posting_type_code in {"issue", "return"} and active(state, confirmed=True)), Decimal(0))
        if quantity < 0: raise AppException("退料大于领料，请检查来源数量", 409)
        if requirement.consumed_quantity != quantity:
            requirement.consumed_quantity = quantity
            requirement.updated_at, requirement.updated_by = utc_now(), user.user_id


async def protect_finished_lots(session, order, order_type, lines, user):
    """防止普通出入库、调拨或调整绕过工单批次约束；仅保护制造成品。"""
    if order.source_doc_type_code == SOURCE and order_type.type_no in {TYPES["receipt"][0], TYPES["shipment"][0]}: return
    for line in lines:
        ids = {value for value in (line.from_warehouse_id or order.from_warehouse_id, line.to_warehouse_id or order.to_warehouse_id) if value}
        for warehouse_id in ids:
            warehouse = await stock.get_stock_warehouse(session, warehouse_id)
            if warehouse and warehouse["warehouse_type_code"] == "mes_finished":
                raise AppException("制造成品仓只接受工单成品入库和仓储出货，请从 MES 来源业务操作", 409)
            # 历史共用仓也不能用全局 FIFO 消耗其他工单的成品。
            receipts = await repo.receipts_for_items(session, warehouse_id, {line.item_id})
            for receipt in receipts:
                lots = {entry["lot_id"] for entry in await stock.get_stock_order_lots(session, receipt.stock_order_id)}
                if lots and (line.lot_id is None or line.lot_id in lots):
                    raise AppException("该物料含工单隔离成品，请通过 MES 仓储出货；其他库存须明确选择非工单批次", 409)


stock.register_write_validator(protect_finished_lots)
stock.register_confirmation_validator(protect_finished_lots)
stock.register_write_validator(validate_write)
stock.register_confirmation_validator(validate_confirmation)
stock.register_source_mutation_guard(SOURCE, mutation_guard)
stock.register_source_document_handler(SOURCE, refresh_consumed)
