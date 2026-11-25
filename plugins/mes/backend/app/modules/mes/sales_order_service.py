import hashlib
import json
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from uuid import UUID

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.file.service import service as files
from app.modules.inventory.public import get_active_item, find_active_items_by_numbers, ensure_active_item
from app.modules.dictionary.service import service as dictionary_service
from .sales_order_models import MesSalesOrder as Order, MesSalesOrderLine as Line, MesSalesProduction as Batch, MesSalesAllocation as Allocation, MesSalesOrderEvent as Event
from .sales_order_repository import repository as repo
from .quotation_repository import repository as quotes
from .schemas import ProductionOrderCreate, WorkOrderCreate
from .service import service as production
from .drawing_files import DRAWING_SCENE
from .quotation_production import production_operations
from .process_matching import matching_catalog, bind_production_operations
from .sales_pricing import validate_price


def require(user, *permissions):
    if not set(permissions).issubset(user.permissions):
        raise AppException("缺少客户订单操作权限", 403)


def request_hash(body):
    return hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def allocated(rows):
    result = {}
    for link, work_order in rows:
        if work_order.deleted_at is None and work_order.status_code != "cancelled":
            result[link.order_line_id] = result.get(link.order_line_id, Decimal(0)) + link.quantity
    return result


def product_number(order, line, unit_code):
    values = [str(order.org_id), str(order.customer_id), line.drawing_no_snapshot.strip().casefold(),
        line.drawing_revision_snapshot.strip().casefold(), line.material_snapshot.strip().casefold(), unit_code]
    return "P-" + hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:24].upper()


def matching_unit(unit_name, names):
    value = unit_name.strip().casefold()
    matches = {code for code in names if code.casefold() == value}
    if not matches:
        matches = {code for code, label in names.items() if label.strip().casefold() == value}
    if not matches and value in {"pcs", "piece", "pieces"}:
        matches = {code for code, label in names.items() if label.strip() == "件"}
    return next(iter(matches)) if len(matches) == 1 else None


def check_production_unit(source, unit_code, names):
    expected = matching_unit(source.unit_name_snapshot, names)
    if expected is None:
        raise AppException(f"{source.drawing_no_snapshot}：订单单位“{source.unit_name_snapshot}”无法匹配系统单位，请核对单位字典", 422)
    if expected != unit_code:
        raise AppException(f"{source.drawing_no_snapshot}：订单单位“{source.unit_name_snapshot}”与生产货品单位“{names.get(unit_code, unit_code)}”不一致，不能直接安排生产", 422)


def require_production_approval(order):
    if order.status_code == "confirmed":
        raise AppException("请先审核客户订单，再生成生产工单", 409)
    if order.status_code != "approved":
        raise AppException("当前客户订单状态不允许安排生产", 409)


class SalesOrderService:
    async def production_defaults(self, identifier, user):
        require(user, "mes:sales_order:list", "mes:sales_order:release", "mes:work_order:create")
        units = await dictionary_service.options(["md_unit"])
        names = {item["item_code"]: item["item_name"] for item in units.get("md_unit", [])}
        async with get_session_context() as session:
            order = await repo.get(session, identifier, user, "mes:sales_order:release")
            require_production_approval(order)
            resolve_write_org_id(user, order.org_id, "mes:work_order:create")
            lines = await repo.lines(session, order)
            codes = {line.id: matching_unit(line.unit_name_snapshot, names) for line in lines}
            numbers = [line.drawing_no_snapshot for line in lines]
            numbers.extend(product_number(order, line, codes[line.id]) for line in lines if codes[line.id])
            candidates = await find_active_items_by_numbers(session, numbers)
            by_number = {}
            for item in candidates:
                by_number.setdefault(item["item_no"].strip().lower(), []).append(item)
            previous = {}
            for link, work in await repo.allocations(session, order):
                if work.deleted_at is None and work.status_code != "cancelled":
                    previous.setdefault(link.order_line_id, set()).add(work.product_item_id)
            results = []
            for line in lines:
                history = previous.get(line.id, set())
                matches = by_number.get(line.drawing_no_snapshot.strip().lower(), [])
                match_source = "drawing_no"
                if codes[line.id]:
                    exact = by_number.get(product_number(order, line, codes[line.id]).lower(), [])
                    if exact:
                        matches, match_source = exact, "catalog"
                if history:
                    match_source = "previous"
                    matches = []
                    if len(history) == 1:
                        item = await get_active_item(session, next(iter(history)))
                        if item:
                            matches = [dict(id=item.id, item_no=item.item_no, item_name=item.item_name, unit_code=item.unit_code)]
                item = matches[0] if len(matches) == 1 and len(history) <= 1 else None
                status = "matched" if item else "ambiguous" if len(matches) > 1 or len(history) > 1 else "not_found"
                if item and codes[line.id] and item["unit_code"] != codes[line.id]:
                    status = "unit_mismatch"
                create = status == "not_found"
                results.append(dict(order_line_id=str(line.id),
                    product_item_id=str(item["id"]) if item else None,
                    item_no=item["item_no"] if item else line.drawing_no_snapshot,
                    item_name=item["item_name"] if item else line.description_snapshot,
                    unit_code=item["unit_code"] if item else codes[line.id],
                    order_unit_code=codes[line.id], material= line.material_snapshot,
                    is_create_product=create, can_create="inventory_product:create" in user.permissions,
                    match_source=match_source if item else None,
                    match_status=status))
        for row in results:
            row["unit_name"] = names.get(row["unit_code"], row["unit_code"])
        return dict(lines=results, unit_names=names)

    async def data(self, session, order, *, detail=True):
        result = order.model_dump(mode="json", exclude={"request_hash", "idempotency_key", "flex_form", "deleted_at", "deleted_by"})
        lines = await repo.lines(session, order)
        allocation_rows = await repo.allocations(session, order)
        assigned = allocated(allocation_rows)
        result.update(line_count=len(lines), amount=str(sum((line.quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for line in lines)),
            remaining_count=sum(assigned.get(line.id, Decimal(0)) < line.quantity for line in lines))
        if detail:
            result["events"] = [row.model_dump(mode="json") for row in await repo.events(session, order)]
            result["lines"] = [dict(**line.model_dump(mode="json", exclude={"flex_form", "deleted_at", "deleted_by"}),
                allocated_quantity=format(assigned.get(line.id, Decimal(0)), ".3f"),
                remaining_quantity=format(max(Decimal(0), line.quantity-assigned.get(line.id, Decimal(0))), ".3f")) for line in lines]
            for value, line in zip(result["lines"], lines, strict=True):
                value.update(quantity=format(line.quantity, ".3f"), unit_price=format(line.unit_price, ".2f"),
                    quoted_quantity_snapshot=format(line.quoted_quantity_snapshot, ".3f"),
                    original_unit_price_snapshot=format(line.original_unit_price_snapshot, ".2f"))
            result["productions"] = [dict(id=str(batch.id), production_order_id=str(batch.production_order_id),
                production_order_no=batch.production_order_no_snapshot, created_at=batch.created_at,
                lines=[dict(order_line_id=str(link.order_line_id), work_order_id=str(work.id), quantity=str(link.quantity),
                    status_code=work.status_code) for link, work in allocation_rows if link.production_id == batch.id]) for batch in await repo.batches(session, order)]
        return result

    async def page(self, user, query):
        require(user, "mes:sales_order:list")
        async with get_session_context() as session:
            rows, total = await repo.page(session, user, query)
            return dict(items=[await self.data(session, row, detail=False) for row in rows], total=total, page=query.page, page_size=query.page_size)

    async def detail(self, identifier, user):
        require(user, "mes:sales_order:list")
        async with get_session_context() as session:
            return await self.data(session, await repo.get(session, identifier, user))

    async def source_customers(self, user, keyword=""):
        require(user, "mes:sales_order:list", "mes:sales_order:manage", "mes:quotation:list")
        async with get_session_context() as session:
            return [dict(id=str(row.id), name=row.name) for row in await repo.source_customers(session, user, keyword)]

    async def sources(self, user, keyword="", quotation_id=None, page=1, size=20, customer_id=None):
        require(user, "mes:sales_order:list", "mes:sales_order:manage", "mes:quotation:list")
        async with get_session_context() as session:
            rows, total = await repo.sources(session, user, keyword, quotation_id, page, size, customer_id)
            result = []
            for line, quote in rows:
                result.append(dict(id=str(line.id), quotation_id=str(quote.id), quotation_version_no=quote.version_no,
                    quote_no=quote.quote_no, revision=quote.revision, org_id=str(quote.org_id), customer_id=str(quote.customer_id),
                    customer_name_snapshot=quote.customer_name_snapshot, currency=quote.currency,
                    drawing_no=line.drawing_no, drawing_revision=line.drawing_revision, description=line.description,
                    material=line.quoted_material, quantity=str(line.quantity), unit_price=str(line.unit_price),
                    unit_name=line.unit_name, lead_days=line.lead_days,
                    quantity_tiers=[dict(id=str(t.id), quantity=str(t.quantity), unit_price=str(t.unit_price)) for t in await quotes.tiers(session, line.id)]))
            return dict(items=result, total=total, page=page, page_size=size)

    async def create(self, body, user):
        require(user, "mes:sales_order:list", "mes:sales_order:manage", "mes:quotation:list")
        digest = request_hash(body)
        async with get_session_context() as session:
            existing = await repo.existing(session, body.idempotency_key, user)
            if existing:
                if existing.request_hash != digest:
                    raise AppException("请勿使用同一提交标识确认不同订单", 409)
                return await self.data(session, existing)
            by_id = {}
            for value in sorted(body.lines, key=lambda row: str(row.quotation_line_id)):
                by_id[value.quotation_line_id] = await repo.quote_line(session, value.quotation_line_id, user)
            for quote_id in sorted({quote.id for _, quote in by_id.values()}, key=str):
                await quotes.get(session, quote_id, user, "mes:quotation:list", lock=True)
            context = set()
            for value in body.lines:
                line, quote = by_id[value.quotation_line_id]
                if quote.status_code != "quoted" or quote.version_no != value.quotation_version_no:
                    raise AppException("仅可使用当前已审核通过的报价版本，请重新核对来源", 409)
                resolve_write_org_id(user, quote.org_id, "mes:sales_order:manage")
                context.add((quote.org_id, quote.customer_id, quote.currency))
            if len(context) != 1:
                raise AppException("同一客户订单只能选择同组织、同客户、同币种的报价", 422)
            first = by_id[body.lines[0].quotation_line_id][1]
            order = Order(org_id=first.org_id, order_no=f"SO-{utc_now():%Y%m%d}-{uuid7().hex[-12:]}",
                customer_id=first.customer_id, customer_name_snapshot=first.customer_name_snapshot,
                currency=first.currency, customer_po_no=body.customer_po_no, note=body.note,
                idempotency_key=body.idempotency_key, request_hash=digest, created_by=user.user_id, updated_by=user.user_id)
            repo.add(session, order)
            await session.flush()
            changes = []
            for index, value in enumerate(body.lines, 1):
                source, quote = by_id[value.quotation_line_id]
                tier = None
                if value.quotation_tier_id:
                    tier = next((t for t in await quotes.tiers(session, source.id) if t.id == value.quotation_tier_id), None)
                    if tier is None:
                        raise AppException("数量档不属于选定报价货品", 422)
                base_quantity, base_price = (tier.quantity, tier.unit_price) if tier else (source.quantity, source.unit_price)
                if base_price is None:
                    raise AppException("所选数量档尚未完成报价", 422)
                validate_price(base_price, value.unit_price, value.discount_rate, source.drawing_no)
                # 非原档数量允许人工确认成交，禁止无提示套用其他档价格。
                if (value.quantity, value.unit_price) != (base_quantity, base_price):
                    if not value.is_price_confirmed or not value.adjustment_reason:
                        raise AppException(f"{source.drawing_no}：数量或价格已调整，请填写原因并确认成交价格", 422)
                    changes.append(f"{source.drawing_no}: 数量 {base_quantity}→{value.quantity}，单价 {base_price}→{value.unit_price}；{value.adjustment_reason}")
                repo.add(session, Line(org_id=order.org_id, order_id=order.id, sequence_no=index,
                    quotation_line_id=source.id, quotation_tier_id=value.quotation_tier_id,
                    quote_no_snapshot=quote.quote_no, quotation_revision_snapshot=quote.revision,
                    drawing_no_snapshot=source.drawing_no, drawing_revision_snapshot=source.drawing_revision,
                    description_snapshot=source.description, material_snapshot=source.quoted_material,
                    unit_name_snapshot=source.unit_name, quoted_quantity_snapshot=base_quantity,
                    original_unit_price_snapshot=base_price, quantity=value.quantity, unit_price=value.unit_price, discount_rate=value.discount_rate,
                    due_date=value.due_date, adjustment_reason=value.adjustment_reason, created_by=user.user_id, updated_by=user.user_id))
            repo.add(session, Event(org_id=order.org_id, order_id=order.id, action_key="confirm", note="确认客户订单\n"+"\n".join(changes), created_by=user.user_id))
            await session.flush()
            result = await self.data(session, order)
            await session.commit()
            return result

    async def approve(self, identifier, body, user):
        permission = "mes:sales_order:approve"
        require(user, "mes:sales_order:list", permission)
        async with get_session_context() as session:
            order = await repo.get(session, identifier, user, permission, lock=True)
            if order.status_code != "confirmed" or order.version_no != body.version_no:
                raise AppException("客户订单状态或版本已变化，请刷新后审核", 409)
            resolve_write_org_id(user, order.org_id, permission)
            lines = await repo.lines(session, order)
            if not lines:
                raise AppException("客户订单缺少成交货品，请核对后再审核", 422)
            for line in lines:
                if line.quantity <= 0 or not line.due_date:
                    raise AppException(f"{line.drawing_no_snapshot}：请核对成交数量和承诺交期", 422)
                validate_price(line.original_unit_price_snapshot, line.unit_price, line.discount_rate, line.drawing_no_snapshot)
            order.status_code = "approved"
            order.version_no += 1
            order.updated_at, order.updated_by = utc_now(), user.user_id
            repo.add(session, Event(org_id=order.org_id, order_id=order.id, action_key="approve",
                note=f"已核对成交货品、数量、价格及承诺交期（审核版本 {body.version_no}）", created_by=user.user_id))
            await session.flush()
            result = await self.data(session, order)
            await session.commit()
            return result

    async def release(self, identifier, body, user):
        require(user, "mes:sales_order:list", "mes:sales_order:release", "mes:work_order:create")
        digest = request_hash(body)
        async with get_session_context() as session:
            order = await repo.get(session, identifier, user, "mes:sales_order:release", lock=True)
            previous = await repo.release_existing(session, order, body.idempotency_key)
            if previous:
                if previous.request_hash != digest:
                    raise AppException("本次生产安排的提交内容已变化", 409)
                return await self.data(session, order)
            require_production_approval(order)
            if order.version_no != body.version_no:
                raise AppException("客户订单状态或版本已变化，请重新核对", 409)
            resolve_write_org_id(user, order.org_id, "mes:work_order:create")
            lines = {line.id: line for line in await repo.lines(session, order)}
            assigned = allocated(await repo.allocations(session, order))
            products = []
            number = f"PO-{utc_now():%Y%m%d}-{uuid7().hex[-12:]}"
            items, to_create, routes = {}, [], {}
            process_catalogue = None
            units = await dictionary_service.options(["md_unit"])
            unit_names = {item["item_code"]: item["item_name"] for item in units.get("md_unit", [])}
            for index, value in enumerate(body.lines, 1):
                source = lines.get(value.order_line_id)
                if source is None:
                    raise AppException("货品不属于当前客户订单", 422)
                if assigned.get(source.id, Decimal(0)) + value.quantity > source.quantity:
                    raise AppException(f"{source.drawing_no_snapshot}：超过订单尚未安排的数量", 409)
                adopted = await repo.adopted_process(session, order, source, user)
                routes[source.id] = production_operations(adopted, source.drawing_no_snapshot, value.quantity)
                if routes[source.id]:
                    if process_catalogue is None:
                        process_catalogue = await matching_catalog(session, order.org_id, user, "mes:work_order:create", lock=True)
                    bind_production_operations(routes[source.id], adopted, process_catalogue)
                if value.is_create_product:
                    expected = matching_unit(source.unit_name_snapshot, unit_names)
                    code = value.product_unit_code or expected
                    if code not in unit_names or (expected and code != expected):
                        raise AppException(f"{source.drawing_no_snapshot}：请核对订单单位并选择有效的生产单位", 422)
                    check_production_unit(source, code, unit_names)
                    to_create.append((product_number(order, source, code), source, code))
                else:
                    item = await get_active_item(session, value.product_item_id)
                    if item is None:
                        raise AppException("所选生产物料不存在或已停用", 422)
                    check_production_unit(source, item.unit_code, unit_names)
                    items[source.id] = item
            # inv 的编号锁按稳定顺序获取，建档、工单和数量分配共同提交或回滚。
            for item_no, source, code in sorted(to_create, key=lambda entry: entry[0]):
                items[source.id] = await ensure_active_item(session, item_no=item_no,
                    item_name=f"{source.drawing_no_snapshot} · {source.description_snapshot}"[:128],
                    specification=f"{source.material_snapshot[:56]} / {source.drawing_revision_snapshot[:24]} / {item_no}",
                    unit_code=code, user=user)
            for index, value in enumerate(body.lines, 1):
                source = lines[value.order_line_id]
                item = items[source.id]
                drawings = []
                for binding in await quotes.files(session, source.quotation_line_id):
                    original, content = await files.read_content(session, binding.attachment_id, user=user)
                    ticket = await files.upload_bytes(scene_code=DRAWING_SCENE, file_name=original.original_file_name,
                        content_type=original.content_type, content=content, user=user)
                    drawings.append(UUID(str(ticket["id"])))
                products.append(WorkOrderCreate(org_id=order.org_id, work_order_no=f"{number}-{index:03}",
                    product_item_id=item.id, planned_quantity=value.quantity, publish=False,
                    processing_type_code=value.processing_type_code, operations=routes[source.id],
                    due_at=datetime.combine(source.due_date, time(23, 59), ZoneInfo("Asia/Shanghai")),
                    drawing_attachment_ids=drawings, drawing_revision_label=source.drawing_revision_snapshot,
                    material_name_snapshot=source.material_snapshot.strip() or None,
                    note=f"客户订单 {order.order_no}；图号 {source.drawing_no_snapshot}；加工材料 {source.material_snapshot}；来源 {source.quote_no_snapshot} R{source.quotation_revision_snapshot}"))
            created = await production.create_production_in_session(session, ProductionOrderCreate(
                org_id=order.org_id, production_order_no=number, project_name=order.customer_po_no or order.order_no,
                customer_id=order.customer_id, products=products, note=f"来源客户订单 {order.order_no}"), user,
                source_order_id=order.id, source_line_ids=[value.order_line_id for value in body.lines])
            batch = Batch(org_id=order.org_id, order_id=order.id, production_order_id=UUID(created["id"]),
                production_order_no_snapshot=number, idempotency_key=body.idempotency_key, request_hash=digest,
                created_by=user.user_id, updated_by=user.user_id)
            repo.add(session, batch)
            await session.flush()
            for value, work_id in zip(body.lines, created["work_order_ids"], strict=True):
                repo.add(session, Allocation(org_id=order.org_id, production_id=batch.id, order_line_id=value.order_line_id,
                    work_order_id=UUID(work_id), quantity=value.quantity, created_by=user.user_id, updated_by=user.user_id))
            order.version_no += 1
            order.updated_at, order.updated_by = utc_now(), user.user_id
            repo.add(session, Event(org_id=order.org_id, order_id=order.id, action_key="release", note=f"生成生产工单 {number}，共 {len(products)} 项货品", created_by=user.user_id))
            await session.flush()
            result = await self.data(session, order)
            await session.commit()
            return result

    async def cancel(self, identifier, body, user):
        require(user, "mes:sales_order:list", "mes:sales_order:manage")
        async with get_session_context() as session:
            order = await repo.get(session, identifier, user, "mes:sales_order:manage", lock=True)
            if order.status_code not in {"confirmed", "approved"} or order.version_no != body.version_no:
                raise AppException("订单状态或版本已变化", 409)
            if any(allocated(await repo.allocations(session, order)).values()):
                raise AppException("订单已有有效生产安排，请先按生产流程处理后再取消", 409)
            order.status_code = "cancelled"
            order.version_no += 1
            order.updated_at, order.updated_by = utc_now(), user.user_id
            repo.add(session, Event(org_id=order.org_id, order_id=order.id, action_key="cancel", note=body.note, created_by=user.user_id))
            await session.flush()
            result = await self.data(session, order)
            await session.commit()
            return result

    async def update(self, identifier, body, user):
        require(user, "mes:sales_order:list", "mes:sales_order:manage")
        async with get_session_context() as session:
            order = await repo.get(session, identifier, user, "mes:sales_order:manage", lock=True)
            if order.status_code not in {"confirmed", "approved"} or order.version_no != body.version_no:
                raise AppException("订单状态或版本已变化，请重新核对", 409)
            if any(allocated(await repo.allocations(session, order)).values()):
                raise AppException("订单已有有效生产安排，成交信息已锁定；请先处理未执行的生产安排", 409)
            lines = {line.id: line for line in await repo.lines(session, order)}
            if set(lines) != {line.id for line in body.lines}:
                raise AppException("请提交当前订单完整货品，不能增加、删除或替换来源", 422)
            changes = []
            for value in body.lines:
                line = lines[value.id]
                discount_rate = value.discount_rate if "discount_rate" in value.model_fields_set else (
                    line.discount_rate if value.unit_price == line.unit_price else None)
                validate_price(line.original_unit_price_snapshot, value.unit_price, discount_rate, line.drawing_no_snapshot)
                if (line.quantity, line.unit_price) != (value.quantity, value.unit_price):
                    if not value.is_price_confirmed or not value.adjustment_reason:
                        raise AppException(f"{line.drawing_no_snapshot}：请填写数量或价格调整原因并确认成交价", 422)
                    changes.append(f"{line.drawing_no_snapshot}：数量 {line.quantity}→{value.quantity}，成交价 {line.unit_price}→{value.unit_price}；{value.adjustment_reason}")
                    line.adjustment_reason = value.adjustment_reason
                if line.due_date != value.due_date:
                    changes.append(f"{line.drawing_no_snapshot}：交付日期 {line.due_date}→{value.due_date}")
                line.quantity, line.unit_price, line.due_date = value.quantity, value.unit_price, value.due_date
                if line.discount_rate != discount_rate:
                    changes.append(f"{line.drawing_no_snapshot}：折扣倍率 {line.discount_rate}→{discount_rate}（空为手动价）")
                line.discount_rate = discount_rate
                line.updated_at, line.updated_by = utc_now(), user.user_id
            order.customer_po_no, order.note = body.customer_po_no, body.note
            if order.status_code == "approved":
                order.status_code = "confirmed"
                changes.append("修改后需重新审核")
            order.version_no += 1
            order.updated_at, order.updated_by = utc_now(), user.user_id
            repo.add(session, Event(org_id=order.org_id, order_id=order.id, action_key="update", note="修改成交信息\n"+"\n".join(changes), created_by=user.user_id))
            await session.flush()
            result = await self.data(session, order)
            await session.commit()
            return result


service = SalesOrderService()
