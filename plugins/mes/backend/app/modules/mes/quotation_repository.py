from sqlalchemy import select, func, or_, and_, delete, case
from sqlalchemy.orm import aliased
from uuid import UUID
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from .quotation_models import MesQuotation as Quote, MesQuotationLine as Line, MesQuotationFile as File, MesQuotationCnc as Cnc, MesQuotationEvent as Event
from .archive_models import MesCustomer
from .quotation_models import MesQuotationPriceTier as Tier


class QuotationRepository:
    async def historical_references(self, session, quote_id, user):
        """一次查询取得每个当前图号最匹配的已审核历史，不扩大组织/客户/权限范围。"""
        previous, item, tier = aliased(Quote), aliased(Line), aliased(Tier)
        price = case((item.quantity == Line.quantity, item.unit_price), else_=tier.unit_price)
        comparable = and_(previous.currency == Quote.currency,
            item.drawing_revision == Line.drawing_revision,
            func.lower(func.trim(item.customer_material)) == func.lower(func.trim(Line.customer_material)),
            item.surface_treatment == Line.surface_treatment,
            func.lower(func.trim(item.unit_name)) == func.lower(func.trim(Line.unit_name)), price.is_not(None))
        statement = select(Line.id.label("line_id"), item.id.label("quotation_line_id"),
            previous.quote_no, previous.revision, previous.updated_at.label("quoted_at"), previous.currency,
            item.drawing_revision, item.quoted_material, item.weight_kg, item.unit_name,
            case((price.is_not(None), Line.quantity), else_=item.quantity).label("quantity"),
            case((price.is_not(None), price), else_=item.unit_price).label("unit_price"),
            comparable.label("is_compatible"),
            func.row_number().over(partition_by=Line.id,
                order_by=(comparable.desc(), previous.updated_at.desc(), previous.id.desc(), item.sequence_no)).label("rank")
            ).select_from(Quote).join(Line, Line.quotation_id == Quote.id)
        statement = statement.join(previous, and_(previous.org_id == Quote.org_id,
            previous.customer_id == Quote.customer_id, previous.id != Quote.id))
        statement = statement.join(item, and_(item.quotation_id == previous.id, item.org_id == previous.org_id,
            func.lower(func.trim(item.drawing_no)) == func.lower(func.trim(Line.drawing_no))))
        statement = statement.outerjoin(tier, and_(tier.line_id == item.id, tier.org_id == previous.org_id,
            tier.quantity == Line.quantity, tier.deleted_at.is_(None)))
        ranked = statement.where(Quote.id == quote_id, Line.org_id == Quote.org_id, Line.deleted_at.is_(None),
            previous.status_code == "quoted", item.deleted_at.is_(None), item.unit_price.is_not(None),
            *scoped_conditions(Quote, user, "mes:quotation:list"), *scoped_conditions(Quote, user, "mes:quotation:price"),
            *scoped_conditions(previous, user, "mes:quotation:list"), *scoped_conditions(previous, user, "mes:quotation:price")
            ).subquery()
        rows = (await session.execute(select(ranked).where(ranked.c.rank == 1))).mappings().all()
        return {row["line_id"]: dict(row) for row in rows}

    async def customer_order_count(self, session, quote_id, user):
        from .sales_order_models import MesSalesOrder as Order, MesSalesOrderLine as OrderLine
        return (await session.execute(select(func.count(func.distinct(Order.id))).join(OrderLine, OrderLine.order_id == Order.id)
            .join(Line, Line.id == OrderLine.quotation_line_id).where(Line.quotation_id == quote_id,
                OrderLine.org_id == Order.org_id, Line.org_id == Order.org_id, OrderLine.deleted_at.is_(None),
                *scoped_conditions(Order, user, "mes:sales_order:list")))).scalar_one()

    async def tiers(self, session, line_id):
        return (await session.execute(select(Tier).where(Tier.line_id == line_id, Tier.deleted_at.is_(None)).order_by(Tier.quantity))).scalars().all()

    async def replace_tiers(self, session, line, quantities, user, *, clear_prices=False):
        current = {row.quantity: row for row in await self.tiers(session, line.id)}
        # 已审核报价不可编辑；有订单引用的旧档仅软删除，不删除历史外键。
        for quantity, row in current.items():
            if quantity not in quantities:
                row.deleted_at, row.deleted_by = utc_now(), user.user_id
        for quantity in quantities:
            row = current.get(quantity)
            if row is None:
                # 取回曾移除的同数量档以满足唯一约束；不恢复其旧价格。
                row = (await session.execute(select(Tier).where(Tier.line_id == line.id, Tier.quantity == quantity))).scalar_one_or_none()
                if row is None:
                    row = Tier(org_id=line.org_id, line_id=line.id, quantity=quantity, created_by=user.user_id)
                    session.add(row)
                row.deleted_at = row.deleted_by = None
                row.unit_price, row.calculation_note = None, ""
            elif clear_prices:
                row.unit_price, row.calculation_note = None, ""
            row.updated_at, row.updated_by = utc_now(), user.user_id

    async def historical_prices(self, session, user, drawing_no, customer_id, page, size):
        statement = select(Quote, Line).join(Line, Line.quotation_id == Quote.id).where(
            *scoped_conditions(Quote, user, "mes:quotation:list"),
            *scoped_conditions(Quote, user, "mes:quotation:price"),
            Line.deleted_at.is_(None), Line.org_id == Quote.org_id, Quote.status_code == "quoted",
            func.lower(Line.drawing_no) == drawing_no.strip().lower())
        if customer_id:
            statement = statement.where(Quote.customer_id == customer_id)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Quote.updated_at.desc(), Quote.id.desc(), Line.sequence_no).offset((page-1)*size).limit(size))).all()
        return rows, total
    async def todos(self, session, user, limit, *, keyword=""):
        stages = []
        if "mes:quotation:price" in user.permissions:
            # 工程是共享待办池；保存不完成交接，提交审核后所有候选人的待办同步消失。
            stages.append(and_(Quote.status_code.in_(("pending", "pricing")),
                *scoped_conditions(Quote, user, "mes:quotation:price")))
        if "mes:quotation:approve" in user.permissions:
            reviewers = [or_(Quote.engineer_user_id.is_(None), Quote.engineer_user_id != user.user_id)]
            if "mes:quotation:approve_self" in user.permissions:
                reviewers.append(and_(Quote.engineer_user_id == user.user_id,
                    *scoped_conditions(Quote, user, "mes:quotation:approve_self")))
            stages.append(and_(Quote.status_code.in_(("review", "final_review")),
                or_(*reviewers),
                *scoped_conditions(Quote, user, "mes:quotation:approve")))
        if "mes:quotation:manage" in user.permissions:
            stages.append(and_(Quote.status_code == "draft", Quote.return_reason != "",
                or_(Quote.owner_user_id == user.user_id,
                    and_(Quote.owner_user_id.is_(None), Quote.created_by == user.user_id)),
                *scoped_conditions(Quote, user, "mes:quotation:manage")))
        if not stages:
            return [], 0
        statement = select(Quote).where(*scoped_conditions(Quote, user, "mes:quotation:list"), or_(*stages))
        if keyword.strip():
            statement = statement.where(or_(Quote.quote_no.icontains(keyword.strip(), autoescape=True),
                                            Quote.title.icontains(keyword.strip(), autoescape=True)))
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Quote.updated_at.desc(), Quote.id.desc()).limit(limit))).scalars().all()
        return rows, total

    def add(self, session, row):
        session.add(row)

    async def get(self, session, identifier, user, permission, *, lock=False):
        identifier = UUID(str(identifier))
        statement = select(Quote).where(Quote.id == identifier, *scoped_conditions(Quote, user, permission)).execution_options(populate_existing=True)
        if permission != "mes:quotation:list":
            statement = statement.where(*scoped_conditions(Quote, user, "mes:quotation:list"))
        if lock:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise AppException("询价不存在或无权访问", 404)
        return row

    async def visible(self, session, identifier, user, permission):
        return (await session.execute(select(Quote.id).where(Quote.id == identifier,
            *scoped_conditions(Quote, user, permission)))).first() is not None

    async def page(self, session, user, keyword, status, page, size):
        statement = select(Quote).where(*scoped_conditions(Quote, user, "mes:quotation:list"))
        if keyword:
            statement = statement.where(or_(Quote.quote_no.icontains(keyword, autoescape=True), Quote.title.icontains(keyword, autoescape=True), Quote.customer_name_snapshot.icontains(keyword, autoescape=True)))
        if status:
            statement = statement.where(Quote.status_code == status)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Quote.created_at.desc(), Quote.id.desc()).offset((page-1)*size).limit(size))).scalars().all()
        return rows, total

    async def customer(self, session, identifier, org_id):
        row = (await session.execute(select(MesCustomer).where(MesCustomer.id == identifier, MesCustomer.org_id == org_id, MesCustomer.deleted_at.is_(None), MesCustomer.is_active.is_(True)))).scalar_one_or_none()
        if row is None:
            raise AppException("客户不存在、停用或不属于所选组织", 422)
        return row

    async def customers(self, session, org_id):
        return (await session.execute(select(MesCustomer).where(MesCustomer.org_id == org_id, MesCustomer.deleted_at.is_(None), MesCustomer.is_active.is_(True)).order_by(MesCustomer.customer_no).limit(500))).scalars().all()

    async def lines(self, session, quote):
        return (await session.execute(select(Line).where(Line.quotation_id == quote.id, Line.org_id == quote.org_id, Line.deleted_at.is_(None)).order_by(Line.sequence_no))).scalars().all()

    async def files(self, session, line_id):
        return (await session.execute(select(File).where(File.line_id == line_id, File.deleted_at.is_(None)))).scalars().all()

    async def file_access(self, session, user, line_id):
        return (await session.execute(select(Line.id).join(Quote, Line.quotation_id == Quote.id).where(
            Line.id == line_id, Line.org_id == Quote.org_id, Line.deleted_at.is_(None),
            *scoped_conditions(Quote, user, "mes:quotation:list")))).first() is not None

    async def replace_files(self, session, line, values, user):
        await session.execute(delete(File).where(File.line_id == line.id))
        for value in values:
            session.add(File(line_id=line.id, org_id=line.org_id, attachment_id=value.attachment_id, kind=value.kind, created_by=user.user_id, updated_by=user.user_id))

    async def cnc_links(self, session, line_id):
        return (await session.execute(select(Cnc).where(Cnc.line_id == line_id, Cnc.deleted_at.is_(None)).order_by(Cnc.created_at.desc(), Cnc.id.desc()))).scalars().all()

    async def history(self, session, quote):
        return (await session.execute(select(Event).where(Event.quotation_id == quote.id, Event.org_id == quote.org_id).order_by(Event.created_at, Event.id))).scalars().all()

    async def family(self, session, quote):
        return (await session.execute(select(Quote).where(Quote.org_id == quote.org_id, Quote.quote_no == quote.quote_no, Quote.deleted_at.is_(None)).order_by(Quote.revision))).scalars().all()

    async def next_revision(self, session, quote):
        # 草稿软删除后仍保留原修订号及审计，修订序号继续递增。
        result = await session.execute(select(func.max(Quote.revision)).where(
            Quote.org_id == quote.org_id, Quote.quote_no == quote.quote_no))
        return result.scalar_one() + 1

    async def revisions_in_progress(self, session, quote):
        return any(row.status_code not in {"quoted", "voided"} for row in await self.family(session, quote))


repository = QuotationRepository()
