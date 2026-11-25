"""制造档案的数据访问，所有查询均限定租户上下文及业务组织范围。"""
from sqlalchemy import select, func, or_
from app.auth.scope_filters import scoped_conditions
from app.framework.db.models import utc_now
from .archive_models import MesProcess, MesProcessDependency, MesEquipment, MesEquipmentProcess


def equipment_process_condition(equipment, process_id):
    return or_(equipment.process_id == process_id, select(MesEquipmentProcess.id).where(
        MesEquipmentProcess.equipment_id == equipment.id, MesEquipmentProcess.org_id == equipment.org_id,
        MesEquipmentProcess.process_id == process_id, MesEquipmentProcess.deleted_at.is_(None)).exists())


def generic_equipment_condition(equipment):
    return equipment.process_id.is_(None) & ~select(MesEquipmentProcess.id).where(
        MesEquipmentProcess.equipment_id == equipment.id, MesEquipmentProcess.org_id == equipment.org_id,
        MesEquipmentProcess.deleted_at.is_(None)).exists()


class ArchiveRepository:
    async def has_active_equipment(self,session,process_id):
        return (await session.execute(select(MesEquipmentProcess.id).join(MesEquipment,MesEquipment.id==MesEquipmentProcess.equipment_id)
            .where(MesEquipmentProcess.process_id==process_id,MesEquipmentProcess.is_active.is_(True),MesEquipmentProcess.deleted_at.is_(None),
                MesEquipment.is_active.is_(True),MesEquipment.deleted_at.is_(None)))).first() is not None
    async def matching_processes(self, session, org_id, user, permission):
        """核价/生产动作选用契约；仅返回工艺匹配字段，不读取备注、定价和人员。"""
        from app.core.exceptions import AppException
        if permission not in {"mes:work_order:create", "mes:quote:analyze", "mes:quote:manage", "mes:quote:list", "mes:quote:rules"} or permission not in user.permissions:
            raise AppException("缺少工艺匹配权限", 403)
        fields = (MesProcess.id, MesProcess.process_no, MesProcess.process_name,
            MesProcess.processing_type_code, MesProcess.is_quality_required)
        return (await session.execute(select(*fields).where(MesProcess.org_id == org_id,
            MesProcess.is_active.is_(True), *scoped_conditions(MesProcess, user, permission))
            .order_by(MesProcess.process_no, MesProcess.id))).mappings().all()

    async def lock_organization(self, session, org_id):
        # 同组织的档案修改串行，防止前置关系并发成环或刚校验的引用被停用。
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"mes.archive:{org_id}", 0))))

    async def page(self, session, spec, query, user, permission):
        model, no, name = spec[:3]
        conditions = scoped_conditions(model, user, permission)
        if query.org_id: conditions.append(model.org_id == query.org_id)
        if query.is_active is not None: conditions.append(model.is_active == query.is_active)
        if model is MesEquipment:
            if query.applicable_process_id:
                conditions.append(or_(equipment_process_condition(model, query.applicable_process_id), generic_equipment_condition(model)))
            if query.generic_equipment_only: conditions.append(generic_equipment_condition(model))
        if query.keyword:
            value = f"%{query.keyword.strip()}%"
            conditions.append(or_(getattr(model, no).ilike(value), getattr(model, name).ilike(value)))
        total = (await session.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()
        rows = (await session.execute(select(model).where(*conditions).order_by(model.sort_no, getattr(model, no), model.id)
            .offset((query.page-1)*query.page_size).limit(query.page_size))).scalars().all()
        return rows, total

    async def get(self, session, model, identifier, *, user=None, permission=None):
        conditions = [model.id == identifier, model.deleted_at.is_(None)]
        if user: conditions.extend(scoped_conditions(model, user, permission))
        return (await session.execute(select(model).where(*conditions))).scalars().first()

    async def number_exists(self, session, spec, org_id, number, exclude=None):
        model, no, *_ = spec
        conditions = [model.org_id == org_id, getattr(model, no) == number, model.deleted_at.is_(None)]
        if exclude: conditions.append(model.id != exclude)
        return (await session.execute(select(model.id).where(*conditions).limit(1))).first() is not None

    async def dependencies(self, session, org_id):
        return (await session.execute(select(MesProcessDependency).where(MesProcessDependency.org_id == org_id,
            MesProcessDependency.deleted_at.is_(None)))).scalars().all()

    async def replace_dependencies(self, session, org_id, process_id, ids, user_id):
        rows = [row for row in await self.dependencies(session, org_id) if row.process_id == process_id]
        kept = set()
        for row in rows:
            if row.previous_process_id in ids: kept.add(row.previous_process_id)
            else:
                row.deleted_at, row.deleted_by = utc_now(), user_id
                row.updated_at, row.updated_by = utc_now(), user_id
        for identifier in set(ids) - kept:
            session.add(MesProcessDependency(org_id=org_id, process_id=process_id, previous_process_id=identifier,
                created_by=user_id, updated_by=user_id))

    def add(self, session, row): session.add(row)

    async def equipment_process_ids(self, session, equipment):
        ids = (await session.execute(select(MesEquipmentProcess.process_id).where(
            MesEquipmentProcess.equipment_id == equipment.id, MesEquipmentProcess.org_id == equipment.org_id,
            MesEquipmentProcess.deleted_at.is_(None)))).scalars().all()
        return sorted(set(ids) | ({equipment.process_id} if equipment.process_id else set()), key=str)

    async def equipment_accepts(self, session, equipment, process_id):
        ids = await self.equipment_process_ids(session, equipment)
        return not ids or process_id in ids

    async def replace_equipment_processes(self, session, equipment, ids, user_id):
        rows = (await session.execute(select(MesEquipmentProcess).where(MesEquipmentProcess.equipment_id == equipment.id,
            MesEquipmentProcess.org_id == equipment.org_id, MesEquipmentProcess.deleted_at.is_(None)))).scalars().all()
        kept = set()
        for row in rows:
            if row.process_id in ids:
                kept.add(row.process_id)
            else:
                row.deleted_at, row.deleted_by = utc_now(), user_id
                row.updated_at, row.updated_by = utc_now(), user_id
        for identifier in set(ids) - kept:
            session.add(MesEquipmentProcess(org_id=equipment.org_id, equipment_id=equipment.id, process_id=identifier,
                created_by=user_id, updated_by=user_id))
        equipment.process_id = ids[0] if len(ids) == 1 else None


archive_repository = ArchiveRepository()
