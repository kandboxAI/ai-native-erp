"""出货及对账 SQL；所有业务访问使用租户事务的 search_path。"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, delete, exists, func, join, or_, select

from app.modules.inventory.public import find_active_items_by_numbers
from .archive_models import MesCustomer
from .delivery_models import MesReconciliation, MesReconciliationLine, MesShipment, MesShipmentLine, MesShipmentDocumentRevision, MesShipmentInvoice
from .models import MesProductionOrder, MesWorkOrder
from .quotation_models import MesQuotation, MesQuotationLine
from .repository import _org_conditions
from .sales_order_models import MesSalesAllocation, MesSalesOrder, MesSalesOrderLine


@dataclass(frozen=True, slots=True)
class ShipmentDocumentSource:
    line: MesShipmentLine
    sale: MesSalesOrderLine | None
    order: MesSalesOrder | None
    work_material: str | None = None
    quoted_material: str | None = None
    unit_net_weight: Decimal | None = None
    item_specification: str | None = None


class DeliveryRepository:
    @staticmethod
    def customers_statement(user):
        return select(MesCustomer).select_from(MesCustomer).where(
            *_org_conditions(MesCustomer, user, "mes:shipment:manage"), MesCustomer.is_active.is_(True)
        )

    async def customer(self, session, identifier, user):
        statement = self.customers_statement(user).where(MesCustomer.id == identifier)
        return (await session.execute(statement)).scalars().first()

    async def customer_options(self, session, user, keyword, limit, sales_order_id=None):
        statement = self.customers_statement(user)
        if sales_order_id:
            statement = statement.add_columns(MesSalesOrder.order_no).join(
                MesSalesOrder, and_(MesSalesOrder.customer_id == MesCustomer.id, MesSalesOrder.org_id == MesCustomer.org_id)
            ).where(MesSalesOrder.id == sales_order_id,
                    *_org_conditions(MesSalesOrder, user, "mes:shipment:manage"))
        if keyword.strip():
            word = f"%{keyword.strip()}%"
            statement = statement.where(or_(MesCustomer.customer_no.ilike(word), MesCustomer.customer_name.ilike(word)))
        return (await session.execute(statement.order_by(MesCustomer.customer_name, MesCustomer.id).limit(limit))).all()

    async def sales_order_options(self, session, customer, user, keyword, limit):
        order, line, work = MesSalesOrder, MesSalesOrderLine, MesWorkOrder
        visible_work = exists(select(work.id).join(
            line, and_(line.id == work.source_sales_order_line_id, line.org_id == work.org_id)
        ).where(line.order_id == order.id, line.deleted_at.is_(None), work.org_id == customer.org_id,
            *_org_conditions(work, user, "mes:shipment:manage"),
            work.status_code.in_(["released", "in_progress", "completed"])))
        statement = select(order.id, order.order_no, order.customer_po_no).where(
            order.customer_id == customer.id, order.org_id == customer.org_id,
            order.deleted_at.is_(None), visible_work,
        )
        if keyword.strip():
            word = f"%{keyword.strip()}%"
            statement = statement.where(or_(order.order_no.ilike(word), order.customer_po_no.ilike(word)))
        return (await session.execute(statement.order_by(order.created_at.desc(), order.id).limit(limit))).all()

    async def work_order_sale(self, session, work_order):
        order, line = MesSalesOrder, MesSalesOrderLine
        return (await session.execute(select(order).join(line, and_(line.order_id == order.id, line.org_id == order.org_id)).where(
            line.id == work_order.source_sales_order_line_id, order.org_id == work_order.org_id,
            line.deleted_at.is_(None), order.deleted_at.is_(None),
        ))).scalars().first()

    async def shipment_order_prices(self, session, org_id, order_line_ids):
        if not order_line_ids:
            return {}
        line, order = MesSalesOrderLine, MesSalesOrder
        statement = select(line.id, line.unit_price, order.currency).select_from(line).join(
            order, and_(order.id == line.order_id, order.org_id == line.org_id)
        ).where(line.id.in_(order_line_ids), line.org_id == org_id,
            line.deleted_at.is_(None), order.deleted_at.is_(None), order.status_code != "cancelled")
        return {row.id: row for row in (await session.execute(statement)).all()}

    async def draft_order_prices(self, session, shipment, work_order_ids):
        if not work_order_ids:
            return {}
        rows = (await session.execute(select(MesWorkOrder.id, MesWorkOrder.source_sales_order_line_id).where(
            MesWorkOrder.id.in_(work_order_ids), MesWorkOrder.org_id == shipment.org_id,
        ))).all()
        prices = await self.shipment_order_prices(session, shipment.org_id, {
            row.source_sales_order_line_id for row in rows if row.source_sales_order_line_id
        })
        return {row.id: prices[row.source_sales_order_line_id] for row in rows if row.source_sales_order_line_id in prices}

    async def direct_shipped_quantity(self, session, order_id):
        return (await session.execute(select(func.coalesce(func.sum(MesShipmentLine.quantity), 0)).join(MesShipment,
            MesShipment.id == MesShipmentLine.shipment_id).where(MesShipmentLine.work_order_id == order_id,
            MesShipment.status_code == "posted", MesShipment.fulfillment_mode_code == "direct"))).scalar_one()

    @staticmethod
    def add(session, row):
        session.add(row)

    @staticmethod
    async def page(session, statement, query, *order):
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(*order).offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

    def documents_statement(self, kind, query, user):
        model = MesShipment if kind == "shipments" else MesReconciliation
        number = model.shipment_no if kind == "shipments" else model.reconciliation_no
        conditions = [*_org_conditions(model, user, f"mes:{'shipment' if kind == 'shipments' else 'reconciliation'}:list")]
        if query.status_code: conditions.append(model.status_code == query.status_code)
        if kind == "shipments" and query.sales_order_id:
            conditions.append(exists(select(MesShipmentLine.id)
                .join(MesWorkOrder, MesWorkOrder.id == MesShipmentLine.work_order_id)
                .join(MesSalesOrderLine, MesSalesOrderLine.id == MesWorkOrder.source_sales_order_line_id)
                .where(MesShipmentLine.shipment_id == MesShipment.id, MesShipmentLine.org_id == MesShipment.org_id,
                       MesWorkOrder.org_id == MesShipment.org_id, MesSalesOrderLine.org_id == MesShipment.org_id,
                       MesSalesOrderLine.order_id == query.sales_order_id)))
        if query.keyword: conditions.append(number.ilike(f"%{query.keyword.strip()}%"))
        if query.customer:
            word = f"%{query.customer.strip()}%"
            conditions.append(or_(model.customer_no_snapshot.ilike(word), model.customer_name_snapshot.ilike(word)))
        start = model.business_date if kind == "shipments" else model.period_start
        end = model.business_date if kind == "shipments" else model.period_end
        if query.start_date: conditions.append(end >= query.start_date)
        if query.end_date: conditions.append(start <= query.end_date)
        line = MesShipmentLine if kind == "shipments" else MesReconciliationLine
        fk = line.shipment_id if kind == "shipments" else line.reconciliation_id
        total_amount = select(func.coalesce(func.sum(line.amount), 0)).where(fk == model.id).correlate(model).scalar_subquery()
        currency = model.order_currency_snapshot if kind == "shipments" else (
            select(func.max(MesShipment.order_currency_snapshot)).select_from(MesReconciliationLine)
            .join(MesShipmentLine, MesShipmentLine.id == MesReconciliationLine.shipment_line_id)
            .join(MesShipment, MesShipment.id == MesShipmentLine.shipment_id)
            .where(MesReconciliationLine.reconciliation_id == model.id, MesShipment.org_id == model.org_id)
            .correlate(model).scalar_subquery()
        )
        return select(model, total_amount.label("total_amount"), currency.label("order_currency_snapshot")).where(*conditions)

    async def documents(self, session, kind, query, user):
        model = MesShipment if kind == "shipments" else MesReconciliation
        return await self.page(session, self.documents_statement(kind, query, user), query, model.created_at.desc(), model.id)

    async def document(self, session, model, document_id, user, permission, *, lock=False):
        statement = select(model).where(model.id == document_id, *_org_conditions(model, user, permission)).execution_options(populate_existing=True)
        if lock: statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def by_key(self, session, model, user_id, key):
        return (await session.execute(select(model).where(model.created_by == user_id, model.idempotency_key == key))).scalars().first()

    async def shipment_lines(self, session, shipment_id):
        return (await session.execute(select(MesShipmentLine).where(MesShipmentLine.shipment_id == shipment_id).order_by(MesShipmentLine.created_at, MesShipmentLine.id))).scalars().all()

    async def shipment_document_lines(self, session, shipment):
        """只投影已授权出货明细所关联的报价材料与重量，不返回报价记录本身。"""
        line, work, sale, order = MesShipmentLine, MesWorkOrder, MesSalesOrderLine, MesSalesOrder
        allocation, quote_line, quote = MesSalesAllocation, MesQuotationLine, MesQuotation
        statement = (select(line, sale, order, work.material_name_snapshot, quote_line.quoted_material, quote_line.weight_kg)
            .select_from(line)
            .join(work, and_(work.id == line.work_order_id, work.org_id == line.org_id))
            .outerjoin(allocation, and_(work.source_sales_order_line_id.is_(None), allocation.work_order_id == work.id,
                allocation.org_id == line.org_id, allocation.deleted_at.is_(None)))
            .outerjoin(sale, and_(sale.id == func.coalesce(work.source_sales_order_line_id, allocation.order_line_id),
                sale.org_id == line.org_id, sale.deleted_at.is_(None)))
            .outerjoin(order, and_(order.id == sale.order_id, order.org_id == line.org_id, order.deleted_at.is_(None)))
            .outerjoin(join(quote_line, quote, and_(quote.id == quote_line.quotation_id,
                quote.org_id == quote_line.org_id, quote.deleted_at.is_(None))),
                and_(order.id.is_not(None), quote_line.id == sale.quotation_line_id, quote_line.org_id == line.org_id,
                    quote_line.deleted_at.is_(None), quote.revision == sale.quotation_revision_snapshot))
            .where(line.shipment_id == shipment.id, line.org_id == shipment.org_id)
            .order_by(line.created_at, line.id))
        rows = (await session.execute(statement)).all()
        missing_items = {
            item.product_item_id: item.product_item_no_snapshot
            for item, sale_row, _, work_material, quoted_material, _ in rows
            if not any((value or "").strip() for value in (
                sale_row.material_snapshot if sale_row else None, work_material, quoted_material,
            ))
        }
        specifications = {
            item["id"]: item["specification"]
            for item in await find_active_items_by_numbers(session, list(missing_items.values()))
            if item["id"] in missing_items
        }
        return [
            ShipmentDocumentSource(item, sale_row, order_row, work_material, quoted_material, unit_weight,
                specifications.get(item.product_item_id))
            for item, sale_row, order_row, work_material, quoted_material, unit_weight in rows
        ]

    async def shipment_document_revisions(self, session, shipment, *, limit=50):
        model = MesShipmentDocumentRevision
        return (await session.execute(select(model).where(model.shipment_id == shipment.id, model.org_id == shipment.org_id)
            .order_by(model.revision_no.desc()).limit(limit))).scalars().all()

    async def shipment_document_revision(self, session, shipment, identifier):
        model = MesShipmentDocumentRevision
        return (await session.execute(select(model).where(model.id == identifier, model.shipment_id == shipment.id,
            model.org_id == shipment.org_id))).scalar_one_or_none()

    async def shipment_invoices(self, session, shipment):
        model = MesShipmentInvoice
        return (await session.execute(select(model).where(model.shipment_id == shipment.id, model.org_id == shipment.org_id)
            .order_by(model.issued_date.desc(), model.id.desc()))).scalars().all()

    async def shipment_invoice(self, session, identifier):
        return (await session.execute(select(MesShipmentInvoice).where(MesShipmentInvoice.id == identifier))).scalar_one_or_none()

    async def reconciliation_lines(self, session, reconciliation_id):
        return (await session.execute(select(MesReconciliationLine, MesShipmentLine, MesShipment.shipment_no, MesShipment.business_date,
            MesShipment.order_currency_snapshot).join(
            MesShipmentLine, MesShipmentLine.id == MesReconciliationLine.shipment_line_id).join(MesShipment, MesShipment.id == MesShipmentLine.shipment_id).where(
            MesReconciliationLine.reconciliation_id == reconciliation_id).order_by(MesShipment.business_date, MesShipment.shipment_no, MesShipmentLine.id))).all()

    async def replace_shipment_lines(self, session, shipment_id):
        # Only draft lines can be removed; drafts are never reconciliation sources.
        await session.execute(delete(MesShipmentLine).where(MesShipmentLine.shipment_id == shipment_id))

    async def lock_orders(self, session, ids, user):
        return (await session.execute(select(MesWorkOrder).where(MesWorkOrder.id.in_(ids),
            *_org_conditions(MesWorkOrder, user, "mes:shipment:manage")).order_by(MesWorkOrder.id).with_for_update().execution_options(populate_existing=True))).scalars().all()

    async def shipped_quantity(self, session, order_id):
        # Aggregate all allocations while the parent is locked, including allocations outside the caller's scope.
        return (await session.execute(select(func.coalesce(func.sum(MesShipmentLine.quantity), 0)).join(MesShipment,
            MesShipment.id == MesShipmentLine.shipment_id).where(MesShipmentLine.work_order_id == order_id, MesShipment.status_code == "posted"))).scalar_one()

    async def has_shipments(self, session, order_id):
        return bool((await session.execute(select(exists(select(MesShipmentLine.id).join(MesShipment, MesShipment.id == MesShipmentLine.shipment_id).where(
            MesShipmentLine.work_order_id == order_id, MesShipment.status_code == "posted"))))).scalar_one())

    async def project(self, session, project_id):
        if not project_id: return None
        return (await session.execute(select(MesProductionOrder).where(MesProductionOrder.id == project_id, MesProductionOrder.deleted_at.is_(None)))).scalars().first()

    async def source_orders(self, session, query, user, *, customer=None, org_id=None):
        work, project, line, order = MesWorkOrder, MesProductionOrder, MesSalesOrderLine, MesSalesOrder
        conditions = [*_org_conditions(work, user, "mes:shipment:manage"), work.status_code.in_(["released", "in_progress", "completed"])]
        if org_id:
            conditions.append(work.org_id == org_id)
        if query.sales_order_id:
            conditions.append(order.id == query.sales_order_id)
        if customer:
            conditions.append(or_(
                order.customer_id == customer.id,
                and_(order.id.is_(None), or_(
                    project.customer_id == customer.id,
                    and_(project.customer_id.is_(None), or_(
                        func.nullif(project.customer_no_snapshot, "").is_(None),
                        project.customer_no_snapshot == customer.customer_no,
                    )),
                )),
            ))
        elif query.customer_no:
            conditions.append(or_(func.nullif(project.customer_no_snapshot, "").is_(None), project.customer_no_snapshot == query.customer_no))
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(work.work_order_no.ilike(word), work.product_item_name_snapshot.ilike(word), order.order_no.ilike(word)))
        statement = (select(work, project, order, line.unit_price).select_from(work)
            .outerjoin(project, and_(project.id == work.production_order_id, project.org_id == work.org_id, project.deleted_at.is_(None)))
            .outerjoin(line, and_(line.id == work.source_sales_order_line_id, line.org_id == work.org_id, line.deleted_at.is_(None)))
            .outerjoin(order, and_(order.id == line.order_id, order.org_id == work.org_id, order.deleted_at.is_(None))))
        return await self.page(session, statement.where(*conditions), query, work.updated_at.desc(), work.id)

    def source_lines_statement(self, user):
        occupied = exists(select(MesReconciliationLine.id).where(MesReconciliationLine.shipment_line_id == MesShipmentLine.id,
            MesReconciliationLine.reservation_released_at.is_(None)))
        return select(MesShipmentLine, MesShipment).join(MesShipment, MesShipment.id == MesShipmentLine.shipment_id).where(
            *_org_conditions(MesShipment, user, "mes:reconciliation:manage"), MesShipment.status_code == "posted", ~occupied)

    async def source_lines(self, session, query, user):
        statement = self.source_lines_statement(user)
        if query.customer: statement = statement.where(MesShipment.customer_no_snapshot == query.customer.strip())
        if query.start_date: statement = statement.where(MesShipment.business_date >= query.start_date)
        if query.end_date: statement = statement.where(MesShipment.business_date <= query.end_date)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            statement = statement.where(or_(MesShipment.shipment_no.ilike(word), MesShipmentLine.work_order_no_snapshot.ilike(word), MesShipmentLine.product_item_name_snapshot.ilike(word)))
        return await self.page(session, statement, query, MesShipment.business_date, MesShipment.id, MesShipmentLine.id)

    async def lock_shipments_for_lines(self, session, line_ids, user):
        ids = select(MesShipmentLine.shipment_id).where(MesShipmentLine.id.in_(line_ids))
        return (await session.execute(select(MesShipment).where(MesShipment.id.in_(ids),
            *_org_conditions(MesShipment, user, "mes:reconciliation:manage")).order_by(MesShipment.id).with_for_update().execution_options(populate_existing=True))).scalars().all()

    async def selected_source_lines(self, session, ids):
        return (await session.execute(select(MesShipmentLine, MesShipment).join(MesShipment, MesShipment.id == MesShipmentLine.shipment_id).where(
            MesShipmentLine.id.in_(ids)))).all()

    async def is_occupied(self, session, line_ids, *, exclude=None):
        conditions = [MesReconciliationLine.shipment_line_id.in_(line_ids), MesReconciliationLine.reservation_released_at.is_(None)]
        if exclude: conditions.append(MesReconciliationLine.reconciliation_id != exclude)
        return bool((await session.execute(select(exists(select(MesReconciliationLine.id).where(*conditions))))).scalar_one())


delivery_repository = DeliveryRepository()
