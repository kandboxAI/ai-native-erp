from sqlalchemy import and_, func, or_, select
from app.auth.scope_filters import resolve_effective_data_scope, scoped_conditions
from .exception_models import MesExceptionCase, MesExceptionEvent
from .models import MesWorkOrder, MesWorkOrderOperation


def case_conditions(user, permission):
    # 本业务的 self 明确定义为“本人提出或本人负责”，仍限定可访问组织；related 沿用底座默认拒绝。
    if resolve_effective_data_scope(user, permission) == "self":
        return [*scoped_conditions(MesExceptionCase, user, permission, data_scope="organization"),
            or_(MesExceptionCase.created_by == user.user_id, MesExceptionCase.assigned_user_id == user.user_id)]
    return scoped_conditions(MesExceptionCase, user, permission)


class ExceptionRepository:
    @staticmethod
    def add(session, row): session.add(row)

    def statement(self, user, permission="mes:exception:list"):
        return select(MesExceptionCase, MesWorkOrder.work_order_no).join(MesWorkOrder,
            and_(MesWorkOrder.id == MesExceptionCase.work_order_id, MesWorkOrder.org_id == MesExceptionCase.org_id)
        ).where(*case_conditions(user, permission), MesWorkOrder.deleted_at.is_(None))

    async def page(self, session, query, user, now):
        case = MesExceptionCase
        statement = self.statement(user)
        if query.work_order_id: statement = statement.where(case.work_order_id == query.work_order_id)
        if query.status_code: statement = statement.where(case.status_code == query.status_code)
        if query.assigned_to_me: statement = statement.where(case.assigned_user_id == user.user_id)
        if query.overdue_only: statement = statement.where(case.status_code != "closed", case.due_at < now)
        if query.keyword and query.keyword.strip():
            word = f"%{query.keyword.strip()}%"
            statement = statement.where(or_(case.case_no.ilike(word), case.title.ilike(word), MesWorkOrder.work_order_no.ilike(word)))
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(case.due_at, case.id).offset((query.page-1)*query.page_size).limit(query.page_size))).all()
        return rows, total

    async def get(self, session, identifier, user, permission, *, lock=False):
        statement = self.statement(user, permission).where(MesExceptionCase.id == identifier).execution_options(populate_existing=True)
        if lock: statement = statement.with_for_update(of=MesExceptionCase)
        return (await session.execute(statement)).first()

    async def by_key(self, session, user_id, key):
        return (await session.execute(select(MesExceptionCase).where(MesExceptionCase.created_by == user_id,
            MesExceptionCase.idempotency_key == key))).scalars().first()

    async def history(self, session, identifier, page, size):
        statement = select(MesExceptionEvent).where(MesExceptionEvent.case_id == identifier)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(MesExceptionEvent.created_at.desc(), MesExceptionEvent.id.desc()).offset((page-1)*size).limit(size))).scalars().all()
        return rows, total

    async def orders(self, session, query, user):
        order = MesWorkOrder
        conditions = [*scoped_conditions(order, user, "mes:work_order:list"), *scoped_conditions(order, user, "mes:exception:create"), order.status_code != "cancelled"]
        if query.keyword:
            word=f"%{query.keyword.strip()}%"
            conditions.append(or_(order.work_order_no.ilike(word), order.product_item_name_snapshot.ilike(word)))
        return (await session.execute(select(order.id, order.org_id, order.work_order_no, order.product_item_name_snapshot)
            .where(*conditions).order_by(order.created_at.desc(), order.id).limit(50))).all()

    async def source(self, session, identifier, user):
        return (await session.execute(select(MesWorkOrder).where(MesWorkOrder.id == identifier,
            *scoped_conditions(MesWorkOrder, user, "mes:work_order:list"), *scoped_conditions(MesWorkOrder, user, "mes:exception:create"))
            .with_for_update())).scalars().first()

    async def operation(self, session, identifier, order):
        return (await session.execute(select(MesWorkOrderOperation).where(MesWorkOrderOperation.id == identifier,
            MesWorkOrderOperation.work_order_id == order.id, MesWorkOrderOperation.org_id == order.org_id,
            MesWorkOrderOperation.deleted_at.is_(None)))).scalars().first()

    async def operations(self, session, order):
        return (await session.execute(select(MesWorkOrderOperation.id, MesWorkOrderOperation.operation_name_snapshot)
            .where(MesWorkOrderOperation.work_order_id == order.id, MesWorkOrderOperation.org_id == order.org_id,
                MesWorkOrderOperation.deleted_at.is_(None)).order_by(MesWorkOrderOperation.sequence_no))).all()

    async def operation_names(self, session, identifiers):
        if not identifiers: return {}
        return dict((await session.execute(select(MesWorkOrderOperation.id, MesWorkOrderOperation.operation_name_snapshot).where(
            MesWorkOrderOperation.id.in_(identifiers), MesWorkOrderOperation.deleted_at.is_(None)))).all())

    async def reminder_candidates(self, session, now, cutoff):
        return (await session.execute(select(MesExceptionCase).join(MesWorkOrder, MesWorkOrder.id == MesExceptionCase.work_order_id).where(
            MesExceptionCase.deleted_at.is_(None), MesWorkOrder.deleted_at.is_(None), MesExceptionCase.status_code != "closed",
            func.coalesce(MesExceptionCase.flex_form["demo"].as_boolean(),False).is_(False),
            MesExceptionCase.due_at < now, or_(MesExceptionCase.last_reminded_at.is_(None), MesExceptionCase.last_reminded_at < cutoff)
        ).order_by(MesExceptionCase.due_at, MesExceptionCase.id).limit(100).with_for_update(of=MesExceptionCase, skip_locked=True))).scalars().all()

    async def is_ready(self, session):
        return all((await session.execute(select(func.to_regclass("mes_exception_case"), func.to_regclass("mes_exception_event")))).one())


exception_repository = ExceptionRepository()
