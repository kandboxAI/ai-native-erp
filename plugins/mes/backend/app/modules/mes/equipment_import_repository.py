"""设备及其来源追溯的数据访问；不访问或修改其他模块业务表。"""
from sqlalchemy import select, text
from app.auth.scope_filters import scoped_conditions
from .archive_models import MesEquipment, MesEquipmentProcess, MesProcess
from .external_import_models import MesExternalImportRow


class EquipmentImportRepository:
    async def missing(self, session):
        present = set((await session.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all())
        required = [(MesEquipmentProcess.__tablename__, col.name) for col in MesEquipmentProcess.__table__.columns]
        required.append((MesExternalImportRow.__tablename__, "equipment_id"))
        return [f"{table}.{column}" for table, column in required if (table, column) not in present]

    async def processes(self, session, user, org_id):
        return (await session.execute(select(MesProcess).where(MesProcess.org_id == org_id,
            *scoped_conditions(MesProcess, user, "mes:archive:process:manage")))).scalars().all()

    async def equipment(self, session, user, org_id):
        return (await session.execute(select(MesEquipment).where(MesEquipment.org_id == org_id,
            *scoped_conditions(MesEquipment, user, "mes:archive:equipment:manage")))).scalars().all()

    async def sources(self, session, user, org_id):
        return (await session.execute(select(MesExternalImportRow).where(MesExternalImportRow.org_id == org_id,
            MesExternalImportRow.source_system_key == "gendanbao", MesExternalImportRow.record_type_key == "equipment_archive",
            *scoped_conditions(MesExternalImportRow, user, "mes:archive:equipment:manage")))).scalars().all()

    def add(self, session, row): session.add(row)


repository = EquipmentImportRepository()
