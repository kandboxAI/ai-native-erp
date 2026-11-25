"""已授权父工单下的图纸修订查询；只操作MES自有表。"""
from sqlalchemy import func, select

from .drawing_models import MesWorkOrderDrawingFile as DrawingFile, MesWorkOrderDrawingRevision as Revision


class DrawingRepository:
    async def latest(self, session, order):
        statement = select(Revision).where(Revision.work_order_id == order.id, Revision.org_id == order.org_id)
        return (await session.execute(statement.order_by(Revision.revision_no.desc()).limit(1))).scalars().first()

    async def links(self, session, order, revision_ids):
        if not revision_ids:
            return []
        statement = select(DrawingFile).join(Revision, Revision.id == DrawingFile.revision_id).where(
            DrawingFile.revision_id.in_(revision_ids), Revision.work_order_id == order.id,
            Revision.org_id == order.org_id, DrawingFile.org_id == order.org_id,
        ).order_by(DrawingFile.sort_no, DrawingFile.id)
        return (await session.execute(statement)).scalars().all()

    async def history(self, session, order, query):
        statement = select(Revision).where(Revision.work_order_id == order.id, Revision.org_id == order.org_id)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(Revision.revision_no.desc())
            .offset((query.page - 1) * query.page_size).limit(query.page_size))).scalars().all()
        return rows, total

    @staticmethod
    def add(session, row):
        session.add(row)


drawing_repository = DrawingRepository()
