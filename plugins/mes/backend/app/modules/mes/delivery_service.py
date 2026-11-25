"""出货及对账的数量、金额和生命周期；仓储模式通过 inv 公开服务记账。"""
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context

from .delivery_models import MesShipment, MesShipmentLine, MesReconciliation, MesReconciliationLine
from .delivery_repository import delivery_repository as repo
from .repository import repository
from .report_repository import report_repository
from .warehouse_policy import allows


def amount(value):
    value = Decimal(value)
    if not value.is_finite() or abs(value) >= Decimal("10000000000000000"):
        raise AppException("金额超出允许范围")
    result = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not result.is_finite() or abs(result) >= Decimal("10000000000000000"):
        raise AppException("金额超出允许范围")
    return result


def request_hash(body):
    exclude = {"idempotency_key"}
    for field in ("sales_order_id", "customer_id"):
        if getattr(body, field, None) is None:
            exclude.add(field)
    return sha256(json.dumps(body.model_dump(mode="json", exclude=exclude), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plain(row, fields):
    return {name: str(value) if isinstance(value := getattr(row, name), Decimal) else value for name in fields}


SHIPMENT_FIELDS = ("id", "org_id", "shipment_no", "customer_no_snapshot", "customer_name_snapshot", "business_date", "fulfillment_mode_code", "warehouse_id", "status_code", "version_no", "note", "posted_at", "cancelled_at", "cancellation_reason", "created_at")
RECONCILIATION_FIELDS = ("id", "org_id", "reconciliation_no", "customer_no_snapshot", "customer_name_snapshot", "period_start", "period_end", "status_code", "version_no", "note", "confirmed_at", "cancelled_at", "cancellation_reason", "created_at")
LINE_FIELDS = ("id", "work_order_id", "product_item_id", "work_order_no_snapshot", "product_item_no_snapshot", "product_item_name_snapshot", "unit_code", "quantity", "unit_price", "amount")


class DeliveryService:
    @staticmethod
    def config(kind):
        if kind == "shipments": return MesShipment, "mes:shipment", SHIPMENT_FIELDS
        if kind == "reconciliations": return MesReconciliation, "mes:reconciliation", RECONCILIATION_FIELDS
        raise AppException("单据类型不存在", 404)

    @staticmethod
    def check_version(row, body):
        if row.version_no != body.version_no: raise AppException("单据已变化，请刷新后重试", 409)

    @staticmethod
    def touch(row, user):
        row.version_no += 1
        row.updated_at, row.updated_by = utc_now(), user.user_id

    async def document_detail(self, session, kind, row):
        _, _, fields = self.config(kind)
        result = plain(row, fields)
        if kind == "shipments":
            lines = [plain(line, LINE_FIELDS) for line in await repo.shipment_lines(session, row.id)]
            result["order_currency_snapshot"] = row.order_currency_snapshot
            if row.status_code == "draft":
                prices = await repo.draft_order_prices(session, row, {line["work_order_id"] for line in lines})
                for line in lines:
                    price = prices.get(line["work_order_id"])
                    if price:
                        line.update(order_unit_price=str(price.unit_price), order_currency=price.currency)
            if row.fulfillment_mode_code == "stock":
                from .inventory_repository import inventory_repository
                from .inventory_service import inventory_service
                result["stock_orders"] = [await inventory_service.item(session, entry) for entry in await inventory_repository.shipment_postings(session, row.id)]
        else:
            lines = []
            result["order_currency_snapshot"] = None
            for line, source, number, business_date, currency in await repo.reconciliation_lines(session, row.id):
                item = plain(source, LINE_FIELDS)
                item.update(plain(line, ("id", "shipment_line_id", "quantity", "unit_price", "adjustment_amount", "adjustment_reason", "amount")))
                item.update(shipment_no=number, business_date=business_date)
                lines.append(item)
                result["order_currency_snapshot"] = currency
        result.update(lines=lines, total_amount=str(amount(sum((Decimal(line["amount"]) for line in lines), Decimal(0)))))
        return result

    async def detail(self, kind, document_id, user):
        model, permission, _ = self.config(kind)
        async with get_session_context() as session:
            row = await repo.document(session, model, document_id, user, f"{permission}:list")
            if row is None: raise AppException("单据不存在或无权访问", 404)
            return await self.document_detail(session, kind, row)

    async def documents(self, kind, query, user):
        _, _, fields = self.config(kind)
        async with get_session_context() as session:
            rows, total = await repo.documents(session, kind, query, user)
            return dict(items=[dict(**plain(row, fields), total_amount=str(value), order_currency_snapshot=currency)
                for row, value, currency in rows], total=total, page=query.page, page_size=query.page_size)

    async def customer_options(self, user, keyword, limit, sales_order_id=None):
        async with get_session_context() as session:
            rows = await repo.customer_options(session, user, keyword, limit, sales_order_id)
            return [
                dict(**plain(row[0], ("id", "org_id", "customer_no", "customer_name")),
                     sales_order_no=row[1] if sales_order_id else None)
                for row in rows
            ]

    @staticmethod
    async def get_customer(session, identifier, user, org_id=None):
        customer = await repo.customer(session, identifier, user)
        if customer is None or (org_id is not None and customer.org_id != org_id):
            raise AppException("客户已停用、跨组织或不在出货权限范围内，请重新选择", 403)
        return customer

    async def sales_order_options(self, user, customer_id, keyword, limit):
        async with get_session_context() as session:
            customer = await self.get_customer(session, customer_id, user)
            rows = await repo.sales_order_options(session, customer, user, keyword, limit)
            return [dict(id=row.id, order_no=row.order_no, customer_po_no=row.customer_po_no) for row in rows]

    async def available(self, session, order):
        from .inventory_service import inventory_service
        operations = await repository.work_order_operations(session, order.id)
        last = max(operations, key=lambda row: row.sequence_no) if operations else None
        # Final-step output, never the sum of all operations; waiting inspection is not shippable.
        eligible = (not getattr(order, "is_process_change_repair", False)
            and order.status_code in {"released", "in_progress", "completed"} and last is not None
            and last.status_code in {"pending", "dispatched", "completed"}
            and (not last.is_quality_required or last.status_code == "completed"))
        produced = last.good_quantity if eligible else Decimal(0)
        shipped = await repo.direct_shipped_quantity(session, order.id)
        reserved = await inventory_service.receipt_reserved(session, order.id)
        return max(Decimal(0), produced - shipped - reserved), produced, shipped

    async def sources(self, kind, query, user):
        async with get_session_context() as session:
            if kind == "shipments":
                org_id = query.org_id
                customer = None
                if query.customer_id:
                    customer = await self.get_customer(session, query.customer_id, user, org_id)
                    org_id = customer.org_id
                if query.fulfillment_mode_code == "stock":
                    from app.modules.inventory import public as stock
                    warehouses = await stock.list_stock_warehouses(session, user, "inventory_outbound:create", scope_key="mes")
                    warehouse = next((row for row in warehouses if row["id"] == query.warehouse_id), None)
                    if warehouse is None or not allows(warehouse, "shipment"): raise AppException("请先选择有权操作的制造成品仓库", 403)
                    if org_id and org_id != warehouse["org_id"]:
                        raise AppException("请选择客户所属组织的仓库", 422)
                    org_id = warehouse["org_id"]
                rows, total = await repo.source_orders(session, query, user, customer=customer, org_id=org_id)
                items = []
                for order, project, sale, order_price in rows:
                    remaining, produced, shipped = await self.available(session, order)
                    if query.fulfillment_mode_code == "stock":
                        from .inventory_service import inventory_service
                        remaining = await inventory_service.warehouse_remaining(session, order.id, query.warehouse_id) if order.org_id == warehouse["org_id"] else Decimal(0)
                    linked_customer = sale or (project and (project.customer_id or project.customer_no_snapshot))
                    snapshot = customer if customer and linked_customer else None
                    has_price = sale is not None and sale.status_code != "cancelled" and order_price is not None
                    items.append(dict(work_order_id=order.id, org_id=order.org_id, work_order_no=order.work_order_no,
                        product_item_name=order.product_item_name_snapshot, unit_code=order.unit_code, available_quantity=str(remaining),
                        produced_quantity=str(produced), shipped_quantity=str(shipped),
                        customer_id=sale.customer_id if sale else project.customer_id if project else None,
                        sales_order_no=sale.order_no if sale else None,
                        has_order_source=order.source_sales_order_line_id is not None,
                        order_unit_price=str(order_price) if has_price else None,
                        order_currency=sale.currency if has_price else None,
                        customer_no_snapshot=snapshot.customer_no if snapshot else project.customer_no_snapshot if project else None,
                        customer_name_snapshot=snapshot.customer_name if snapshot else project.customer_name_snapshot if project else None))
            else:
                rows, total = await repo.source_lines(session, query, user)
                items = [dict(**plain(line, LINE_FIELDS), shipment_no=header.shipment_no, business_date=header.business_date,
                    org_id=header.org_id, customer_no_snapshot=header.customer_no_snapshot, customer_name_snapshot=header.customer_name_snapshot,
                    order_currency_snapshot=header.order_currency_snapshot) for line, header in rows]
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)

    async def shipment_orders(self, session, lines, user, org_id, customer, *, check_customer=True, customer_id=None, sales_order_id=None):
        ids = {line.work_order_id for line in lines}
        orders = await repo.lock_orders(session, ids, user)
        if len(orders) != len(ids): raise AppException("所选工单不存在或超出出货数据范围", 403)
        for order in orders:
            if order.org_id != org_id: raise AppException("一张出货单只能包含同一组织的工单")
            project = await repo.project(session, order.production_order_id)
            sale = await repo.work_order_sale(session, order) if (customer_id or sales_order_id) and order.source_sales_order_line_id else None
            source_customer = sale.customer_id if sale else project.customer_id if project else None
            if sales_order_id and (sale is None or sale.id != sales_order_id):
                raise AppException("出货明细必须来自所选客户订单", 422)
            if check_customer and customer_id and source_customer and source_customer != customer_id:
                raise AppException("出货客户与来源工单的客户不一致", 422)
            if check_customer and (not customer_id or not source_customer) and project and project.customer_no_snapshot and project.customer_no_snapshot != customer:
                raise AppException("出货客户编号与来源项目不一致")
        return {row.id: row for row in orders}

    async def validate_shipment(self, session, lines, orders):
        for line in lines:
            order = orders[line.work_order_id]
            if await report_repository.pending_for_order(session, order.id):
                raise AppException("来源工单有报工变更审批，请处理完成后出货", 409)
            remaining, _, _ = await self.available(session, order)
            if line.quantity > remaining: raise AppException(f"工单 {order.work_order_no} 可出货数量不足；请结束末道执行或检验后刷新，不能超量出货", 409)

    @staticmethod
    async def shipment_prices(session, lines, orders, org_id):
        sources = await repo.shipment_order_prices(session, org_id, {
            order.source_sales_order_line_id for order in orders.values() if order.source_sales_order_line_id
        })
        prices, currencies = {}, set()
        for line in lines:
            order = orders[line.work_order_id]
            if order.source_sales_order_line_id:
                source = sources.get(order.source_sales_order_line_id)
                if source is None:
                    raise AppException(f"工单 {order.work_order_no} 缺少有效的客户订单价格，请核对来源", 409)
                prices[order.id] = source.unit_price
                currencies.add(source.currency)
            else:
                if line.unit_price is None:
                    raise AppException(f"工单 {order.work_order_no} 没有关联客户订单，请填写人民币含税单价", 422)
                prices[order.id] = line.unit_price
                currencies.add(None)
        if len(currencies) != 1:
            raise AppException("一张出货单只能使用同一币种和计价口径，请分开出货", 422)
        return prices, currencies.pop()

    async def save_shipment(self, body, user, document_id=None):
        org_id = resolve_write_org_id(user, body.org_id, "mes:shipment:manage")
        async with get_session_context() as session:
            if document_id is None:
                existing = await repo.by_key(session, MesShipment, user.user_id, body.idempotency_key)
                if existing:
                    if existing.request_hash != request_hash(body): raise AppException("幂等键已用于不同内容", 409)
                    return await self.document_detail(session, "shipments", existing)
            customer_id = getattr(body, "customer_id", None)
            customer_no, customer_name = body.customer_no_snapshot, body.customer_name_snapshot
            if customer_id:
                customer = await self.get_customer(session, customer_id, user, org_id)
                customer_no, customer_name = customer.customer_no, customer.customer_name
            orders = await self.shipment_orders(session, body.lines, user, org_id, customer_no,
                customer_id=customer_id, sales_order_id=body.sales_order_id)
            prices, currency = await self.shipment_prices(session, body.lines, orders, org_id)
            if body.fulfillment_mode_code == "direct":
                await self.validate_shipment(session, body.lines, orders)
            else:
                from .inventory_service import inventory_service
                from app.modules.inventory import public as stock
                warehouses = await stock.list_stock_warehouses(session, user, "inventory_outbound:create", scope_key="mes")
                warehouse = next((entry for entry in warehouses if entry["id"] == body.warehouse_id), None)
                if warehouse is None or warehouse["org_id"] != org_id or not allows(warehouse, "shipment"):
                    raise AppException("请选择同组织且有权操作的制造成品仓库", 403)
                for line in body.lines:
                    if line.quantity > await inventory_service.warehouse_remaining(session, line.work_order_id, body.warehouse_id):
                        raise AppException("所选仓库的工单入库可出货数量不足", 409)
            fields = {field: getattr(body, field) for field in ("business_date", "fulfillment_mode_code", "warehouse_id", "note")}
            fields.update(customer_no_snapshot=customer_no, customer_name_snapshot=customer_name, order_currency_snapshot=currency)
            if document_id:
                row = await repo.document(session, MesShipment, document_id, user, "mes:shipment:manage", lock=True)
                if row is None: raise AppException("出货单不存在或无权修改", 404)
                self.check_version(row, body)
                if row.status_code != "draft" or row.org_id != org_id: raise AppException("只有草稿可修改，且不能更换组织", 409)
                if body.shipment_no is not None:
                    fields["shipment_no"] = body.shipment_no
                await repo.replace_shipment_lines(session, row.id)
                for name, value in fields.items(): setattr(row, name, value)
                self.touch(row, user)
            else:
                fields["shipment_no"] = body.shipment_no or f"SH-{body.business_date:%Y%m%d}-{uuid7().hex[12:].upper()}"
                row = MesShipment(org_id=org_id, **fields, idempotency_key=body.idempotency_key,
                    request_hash=request_hash(body), created_by=user.user_id, updated_by=user.user_id)
                repo.add(session, row)
                await session.flush()
            for source in body.lines:
                order = orders[source.work_order_id]
                price = prices[order.id]
                repo.add(session, MesShipmentLine(org_id=org_id, shipment_id=row.id, work_order_id=order.id,
                    product_item_id=order.product_item_id, work_order_no_snapshot=order.work_order_no,
                    product_item_no_snapshot=order.product_item_no_snapshot, product_item_name_snapshot=order.product_item_name_snapshot,
                    unit_code=order.unit_code, quantity=source.quantity, unit_price=price, amount=amount(source.quantity * price),
                    created_by=user.user_id, updated_by=user.user_id))
            await session.flush()
            result = await self.document_detail(session, "shipments", row)
            await session.commit()
            return result

    async def shipment_action(self, document_id, action, body, user):
        async with get_session_context() as session:
            seed = await repo.document(session, MesShipment, document_id, user, "mes:shipment:manage")
            if seed is None: raise AppException("出货单不存在或无权操作", 404)
            lines = await repo.shipment_lines(session, seed.id)
            orders = await self.shipment_orders(session, lines, user, seed.org_id, seed.customer_no_snapshot, check_customer=action != "cancel")
            row = await repo.document(session, MesShipment, document_id, user, "mes:shipment:manage", lock=True)
            self.check_version(row, body)
            # Draft edits can change source lines; never act on the pre-lock snapshot.
            lines = await repo.shipment_lines(session, row.id)
            if any(line.work_order_id not in orders for line in lines): raise AppException("出货明细已变化，请刷新", 409)
            if action == "post":
                if row.status_code not in {"draft", "awaiting_stock"}: raise AppException("只有草稿或待库存办理单据可确认出货", 409)
                if row.status_code == "draft" and row.order_currency_snapshot is None and any(order.source_sales_order_line_id for order in orders.values()):
                    raise AppException("这张草稿尚未采用客户订单单价，请编辑并重新保存后再确认出货", 409)
                if row.fulfillment_mode_code == "stock":
                    from .inventory_service import inventory_service
                    complete = await inventory_service.finish_shipment(session, row, lines, orders, user)
                    row.status_code = "posted" if complete else "awaiting_stock"
                    if complete: row.posted_at, row.posted_by = utc_now(), user.user_id
                else:
                    await self.validate_shipment(session, lines, orders)
                    row.status_code, row.posted_at, row.posted_by = "posted", utc_now(), user.user_id
            elif action == "cancel":
                if row.status_code == "cancelled": raise AppException("该出货单已取消", 409)
                if not (body.reason or "").strip(): raise AppException("取消出货必须填写理由")
                if await repo.is_occupied(session, [line.id for line in lines]): raise AppException("出货明细已进入对账，请先取消关联对账单", 409)
                if row.fulfillment_mode_code == "stock":
                    from .inventory_service import inventory_service
                    await inventory_service.cancel_shipment(session, row, body.reason.strip(), user)
                row.status_code, row.cancelled_at, row.cancelled_by = "cancelled", utc_now(), user.user_id
                row.cancellation_reason = body.reason.strip()
            else: raise AppException("不支持的出货动作", 422)
            self.touch(row, user)
            result = await self.document_detail(session, "shipments", row)
            await session.commit()
            return result

    async def save_reconciliation(self, body, user):
        org_id = resolve_write_org_id(user, body.org_id, "mes:reconciliation:manage")
        async with get_session_context() as session:
            existing = await repo.by_key(session, MesReconciliation, user.user_id, body.idempotency_key)
            if existing:
                if existing.request_hash != request_hash(body): raise AppException("幂等键已用于不同内容", 409)
                return await self.document_detail(session, "reconciliations", existing)
            ids = [line.shipment_line_id for line in body.lines]
            locked = await repo.lock_shipments_for_lines(session, ids, user)
            allowed = {row.id for row in locked}
            sources = await repo.selected_source_lines(session, ids)
            if len(sources) != len(ids) or any(header.id not in allowed for _, header in sources): raise AppException("出货明细不存在或超出对账数据范围", 403)
            if await repo.is_occupied(session, ids): raise AppException("部分出货明细已被其他对账单占用，请刷新", 409)
            if len({header.order_currency_snapshot for _, header in sources}) != 1:
                raise AppException("一张对账单只能使用同一币种和计价口径，请分别对账", 422)
            for _, header in sources:
                if header.status_code != "posted": raise AppException("只能对已确认且未取消的出货进行对账", 409)
                if header.org_id != org_id or header.customer_no_snapshot != body.customer_no_snapshot:
                    raise AppException("对账明细必须属于同一组织和客户编号")
                if not body.period_start <= header.business_date <= body.period_end: raise AppException("出货日期不在对账期间内")
            row = MesReconciliation(org_id=org_id, **{name: getattr(body, name) for name in ("reconciliation_no", "customer_no_snapshot", "customer_name_snapshot", "period_start", "period_end", "note")},
                idempotency_key=body.idempotency_key, request_hash=request_hash(body), created_by=user.user_id, updated_by=user.user_id)
            repo.add(session, row)
            await session.flush()
            by_id = {line.id: line for line, _ in sources}
            for entry in body.lines:
                source = by_id[entry.shipment_line_id]
                final_amount = amount(source.amount + entry.adjustment_amount)
                if final_amount < 0: raise AppException("调整后的对账金额不能为负")
                repo.add(session, MesReconciliationLine(org_id=org_id, reconciliation_id=row.id, shipment_line_id=source.id,
                    quantity=source.quantity, unit_price=source.unit_price, adjustment_amount=entry.adjustment_amount,
                    adjustment_reason=(entry.adjustment_reason or "").strip() or None, amount=final_amount,
                    created_by=user.user_id, updated_by=user.user_id))
            await session.flush()
            result = await self.document_detail(session, "reconciliations", row)
            await session.commit()
            return result

    async def reconciliation_action(self, document_id, action, body, user):
        async with get_session_context() as session:
            seed = await repo.document(session, MesReconciliation, document_id, user, "mes:reconciliation:manage")
            if seed is None: raise AppException("对账单不存在或无权操作", 404)
            sources = await repo.reconciliation_lines(session, seed.id)
            locked = await repo.lock_shipments_for_lines(session, [line.shipment_line_id for line, *_ in sources], user)
            row = await repo.document(session, MesReconciliation, document_id, user, "mes:reconciliation:manage", lock=True)
            self.check_version(row, body)
            if len({source.shipment_id for _, source, *_ in sources}) != len(locked): raise AppException("关联出货超出当前数据范围", 403)
            if action == "confirm":
                if row.status_code != "draft" or any(source.status_code != "posted" for source in locked): raise AppException("对账或来源出货状态已变化", 409)
                row.status_code, row.confirmed_at, row.confirmed_by = "confirmed", utc_now(), user.user_id
            elif action == "cancel":
                if row.status_code == "cancelled": raise AppException("该对账单已取消", 409)
                if not (body.reason or "").strip(): raise AppException("取消对账必须填写理由")
                row.status_code, row.cancelled_at, row.cancelled_by = "cancelled", utc_now(), user.user_id
                row.cancellation_reason = body.reason.strip()
                for line, *_ in sources:
                    line.reservation_released_at = row.cancelled_at
                    line.updated_at, line.updated_by = utc_now(), user.user_id
            else: raise AppException("不支持的对账动作", 422)
            self.touch(row, user)
            result = await self.document_detail(session, "reconciliations", row)
            await session.commit()
            return result


delivery_service = DeliveryService()
