"""只写 MES 自有关系与消耗汇总，不查询或写入 inv 内部表。"""
from sqlalchemy import select, func, or_
from .inventory_models import MesInventoryPosting
from .models import MesWorkOrder, MesWorkOrderOperation, MesOperationMaterialRequirement
from .delivery_models import MesShipmentLine
from .repository import _org_conditions


class InventoryRepository:
    def add(self, session, row): session.add(row)

    async def receipts_for_items(self, session, warehouse_id, item_ids):
        return (await session.execute(select(MesInventoryPosting).where(
            MesInventoryPosting.posting_type_code == "receipt", MesInventoryPosting.warehouse_id == warehouse_id,
            MesInventoryPosting.item_id.in_(item_ids)))).scalars().all()

    async def order(self, session, order_id, user=None, permission="mes:inventory:manage", *, lock=False):
        conditions = [MesWorkOrder.id == order_id, MesWorkOrder.deleted_at.is_(None)]
        if user: conditions.extend(_org_conditions(MesWorkOrder, user, permission))
        statement = select(MesWorkOrder).where(*conditions).execution_options(populate_existing=True)
        if lock: statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    async def operations(self, session, order_id):
        return (await session.execute(select(MesWorkOrderOperation).where(MesWorkOrderOperation.work_order_id == order_id,
            MesWorkOrderOperation.deleted_at.is_(None)).order_by(MesWorkOrderOperation.sequence_no))).scalars().all()

    async def postings(self, session, order_id):
        return (await session.execute(select(MesInventoryPosting).where(MesInventoryPosting.work_order_id == order_id))).scalars().all()

    async def posting(self, session, posting_id=None, stock_order_id=None, user=None, permission="mes:inventory:list"):
        conditions = [MesInventoryPosting.id == posting_id] if posting_id else [MesInventoryPosting.stock_order_id == stock_order_id]
        if user: conditions.extend(_org_conditions(MesInventoryPosting, user, permission))
        return (await session.execute(select(MesInventoryPosting).where(*conditions))).scalars().first()

    async def by_key(self, session, user_id, key):
        return (await session.execute(select(MesInventoryPosting).where(MesInventoryPosting.created_by == user_id,
            MesInventoryPosting.idempotency_key == key))).scalars().first()

    async def page(self, session, query, user):
        conditions = [*_org_conditions(MesInventoryPosting, user, "mes:inventory:list"), MesWorkOrder.deleted_at.is_(None)]
        if query.work_order_id: conditions.append(MesInventoryPosting.work_order_id == query.work_order_id)
        if query.posting_type_code: conditions.append(MesInventoryPosting.posting_type_code == query.posting_type_code)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(MesWorkOrder.work_order_no.ilike(word), MesInventoryPosting.item_no_snapshot.ilike(word), MesInventoryPosting.item_name_snapshot.ilike(word)))
        statement = select(MesInventoryPosting, MesWorkOrder.work_order_no).join(MesWorkOrder, MesWorkOrder.id == MesInventoryPosting.work_order_id).where(*conditions)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        return (await session.execute(statement.order_by(MesInventoryPosting.created_at.desc(), MesInventoryPosting.id).offset((query.page-1)*query.page_size).limit(query.page_size))).all(), total

    async def order_options(self, session, query, user):
        conditions = [*_org_conditions(MesWorkOrder, user, "mes:inventory:manage"), MesWorkOrder.status_code != "cancelled"]
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(MesWorkOrder.work_order_no.ilike(word), MesWorkOrder.product_item_name_snapshot.ilike(word)))
        statement = select(MesWorkOrder).where(*conditions)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        return (await session.execute(statement.order_by(MesWorkOrder.created_at.desc()).offset((query.page-1)*query.page_size).limit(query.page_size))).scalars().all(), total

    async def requirements(self, session, order_id):
        return (await session.execute(select(MesOperationMaterialRequirement).join(MesWorkOrderOperation,
            MesWorkOrderOperation.id == MesOperationMaterialRequirement.operation_id).where(MesWorkOrderOperation.work_order_id == order_id,
                MesWorkOrderOperation.deleted_at.is_(None), MesOperationMaterialRequirement.deleted_at.is_(None)))).scalars().all()

    async def shipment_postings(self, session, shipment_id):
        return (await session.execute(select(MesInventoryPosting).join(MesShipmentLine, MesShipmentLine.id == MesInventoryPosting.shipment_line_id).where(
            MesShipmentLine.shipment_id == shipment_id).order_by(MesInventoryPosting.work_order_id))).scalars().all()


inventory_repository = InventoryRepository()
