from uuid import UUID
from sqlalchemy import select, func, or_
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from .sales_order_models import MesSalesOrder as Order, MesSalesOrderLine as Line, MesSalesProduction as Batch, MesSalesAllocation as Allocation, MesSalesOrderEvent as Event
from .quotation_models import MesQuotation as Quote, MesQuotationLine as QuoteLine, MesQuotationCnc
from .cnc.models import CncQuote
from .models import MesWorkOrder, MesProductionOrder


class SalesOrderRepository:
    async def has_quotation_reference(self, session, quotation_id, org_id):
        """校验同组织订单来源是否仍有引用，仅返回阻止作废所需的布尔值。"""
        reference = (select(Line.id)
            .join(QuoteLine, QuoteLine.id == Line.quotation_line_id)
            .join(Order, Order.id == Line.order_id)
            .where(QuoteLine.quotation_id == quotation_id, QuoteLine.org_id == org_id,
                Line.org_id == org_id, Order.org_id == org_id,
                Line.deleted_at.is_(None), Order.deleted_at.is_(None)))
        return (await session.execute(select(reference.exists()))).scalar_one()

    async def adopted_process(self, session, order, source, user):
        """仅投影有权安排生产的订单所引用的已采用工艺；不暴露核价金额或人员信息。"""
        row = (await session.execute(select(QuoteLine.adopted_cnc_quote_id, CncQuote.inputs_snapshot)
            .select_from(Line).join(Order, Order.id == Line.order_id)
            .join(QuoteLine, QuoteLine.id == Line.quotation_line_id)
            .join(Quote, Quote.id == QuoteLine.quotation_id)
            .outerjoin(CncQuote, (CncQuote.id == QuoteLine.adopted_cnc_quote_id)
                & (CncQuote.org_id == Order.org_id)
                & select(MesQuotationCnc.id).where(MesQuotationCnc.line_id == QuoteLine.id,
                    MesQuotationCnc.part_id == CncQuote.part_id, MesQuotationCnc.org_id == Order.org_id,
                    MesQuotationCnc.deleted_at.is_(None)).correlate(QuoteLine, CncQuote, Order).exists())
            .where(Line.id == source.id, Line.order_id == order.id, Line.org_id == Order.org_id,
                Line.deleted_at.is_(None), QuoteLine.org_id == Order.org_id, QuoteLine.deleted_at.is_(None),
                Quote.org_id == Order.org_id, Quote.deleted_at.is_(None), Quote.status_code == "quoted",
                Quote.revision == Line.quotation_revision_snapshot,
                *scoped_conditions(Order, user, "mes:sales_order:list"),
                *scoped_conditions(Order, user, "mes:sales_order:release")))).one_or_none()
        if row is None:
            raise AppException("来源报价已失效或无权访问，请核对客户订单", 409)
        identifier, snapshot = row
        if identifier is None:
            return None
        if not isinstance(snapshot, dict):
            raise AppException("已采用的核价工艺快照不可用，请核对来源报价", 409)
        if not isinstance(snapshot.get("operations"), list):
            raise AppException("已采用的核价缺少工艺快照，请核对来源报价", 409)
        return snapshot["operations"]

    async def file_access(self, session, quotation_line_id, user):
        return (await session.execute(select(Line.id).join(Order, Order.id == Line.order_id).where(
            Line.quotation_line_id == quotation_line_id, Line.org_id == Order.org_id, Line.deleted_at.is_(None),
            *scoped_conditions(Order, user, "mes:sales_order:list")))).first() is not None

    def add(self, session, row):
        session.add(row)

    async def get(self, session, identifier, user, permission="mes:sales_order:list", *, lock=False):
        statement = select(Order).where(Order.id == UUID(str(identifier)),
            *scoped_conditions(Order, user, "mes:sales_order:list"), *scoped_conditions(Order, user, permission))
        if lock:
            statement = statement.with_for_update()
        row = (await session.execute(statement.execution_options(populate_existing=True))).scalar_one_or_none()
        if row is None:
            raise AppException("客户订单不存在或无权访问", 404)
        return row

    async def page(self, session, user, query):
        statement = select(Order).where(*scoped_conditions(Order, user, "mes:sales_order:list"))
        if query.keyword:
            statement = statement.where(or_(*[field.icontains(query.keyword, autoescape=True) for field in (Order.order_no, Order.customer_po_no, Order.customer_name_snapshot)]))
        if query.status_code:
            statement = statement.where(Order.status_code == query.status_code)
        if query.quotation_id:
            statement = statement.where(Order.id.in_(select(Line.order_id).join(QuoteLine, QuoteLine.id == Line.quotation_line_id).where(
                QuoteLine.quotation_id == query.quotation_id, Line.deleted_at.is_(None), Line.org_id == Order.org_id)))
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Order.created_at.desc(), Order.id.desc()).offset((query.page-1)*query.page_size).limit(query.page_size))).scalars().all()
        return rows, total

    async def existing(self, session, key, user):
        return (await session.execute(select(Order).where(Order.created_by == user.user_id, Order.idempotency_key == key,
            *scoped_conditions(Order, user, "mes:sales_order:list"), *scoped_conditions(Order, user, "mes:sales_order:manage")))).scalar_one_or_none()

    async def lines(self, session, order):
        return (await session.execute(select(Line).where(Line.order_id == order.id, Line.org_id == order.org_id, Line.deleted_at.is_(None)).order_by(Line.sequence_no))).scalars().all()

    async def allocations(self, session, order):
        return (await session.execute(select(Allocation, MesWorkOrder).join(Line, Line.id == Allocation.order_line_id)
            .join(MesWorkOrder, MesWorkOrder.id == Allocation.work_order_id)
            .where(Line.order_id == order.id, Line.org_id == order.org_id, Allocation.org_id == order.org_id,
                MesWorkOrder.org_id == order.org_id))).all()

    async def batches(self, session, order):
        return (await session.execute(select(Batch).where(Batch.order_id == order.id, Batch.org_id == order.org_id).order_by(Batch.created_at.desc(), Batch.id.desc()))).scalars().all()

    async def events(self, session, order):
        return (await session.execute(select(Event).where(Event.order_id == order.id, Event.org_id == order.org_id)
            .order_by(Event.created_at.desc(), Event.id.desc()).limit(500))).scalars().all()

    async def release_existing(self, session, order, key):
        return (await session.execute(select(Batch).where(Batch.order_id == order.id, Batch.idempotency_key == key))).scalar_one_or_none()

    async def quote_line(self, session, identifier, user, *, lock=False):
        statement = select(QuoteLine, Quote).join(Quote, Quote.id == QuoteLine.quotation_id).where(
            QuoteLine.id == identifier, QuoteLine.deleted_at.is_(None), QuoteLine.org_id == Quote.org_id,
            *scoped_conditions(Quote, user, "mes:quotation:list"))
        if lock:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).first()
        if row is None:
            raise AppException("来源报价货品不存在或无权访问", 404)
        return row

    async def source_customers(self, session, user, keyword):
        has_lines = select(QuoteLine.id).where(QuoteLine.quotation_id == Quote.id,
            QuoteLine.org_id == Quote.org_id, QuoteLine.deleted_at.is_(None)).correlate(Quote).exists()
        # 同一客户只返回一个选项，名称取用户有权查看的最新已审核报价快照。
        ranked = select(Quote.customer_id.label("id"), Quote.customer_name_snapshot.label("name"),
            func.row_number().over(partition_by=Quote.customer_id,
                order_by=(Quote.updated_at.desc(), Quote.id.desc())).label("position")).where(
                    Quote.status_code == "quoted", has_lines,
                    *scoped_conditions(Quote, user, "mes:quotation:list")).subquery()
        statement = select(ranked.c.id, ranked.c.name).where(ranked.c.position == 1)
        if keyword:
            statement = statement.where(ranked.c.name.icontains(keyword, autoescape=True))
        return (await session.execute(statement.order_by(ranked.c.name, ranked.c.id).limit(100))).all()

    async def sources(self, session, user, keyword, quotation_id, page, size, customer_id=None):
        statement = select(QuoteLine, Quote).join(Quote, Quote.id == QuoteLine.quotation_id).where(
            Quote.status_code == "quoted", QuoteLine.deleted_at.is_(None), QuoteLine.org_id == Quote.org_id,
            *scoped_conditions(Quote, user, "mes:quotation:list"))
        if quotation_id:
            statement = statement.where(Quote.id == quotation_id)
        if customer_id:
            statement = statement.where(Quote.customer_id == customer_id)
        if keyword:
            statement = statement.where(or_(*[field.icontains(keyword, autoescape=True) for field in
                (QuoteLine.drawing_no, Quote.quote_no, Quote.customer_name_snapshot)]))
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Quote.updated_at.desc(), Quote.id.desc(), QuoteLine.sequence_no).offset((page-1)*size).limit(size))).all()
        return rows, total


repository = SalesOrderRepository()
