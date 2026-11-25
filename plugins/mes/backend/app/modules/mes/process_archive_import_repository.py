"""工艺档案离线导入的数据访问；范围继承真实档案/路线/工单权限。"""
from sqlalchemy import select, or_
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from .archive_models import MesProcess, MesProcessDependency, MesEquipment, MesEquipmentProcess
from .external_import_models import MesExternalImportRow
from .external_import_repository import repository as import_repository
from .models import MesProcessTemplate, MesProcessTemplateOperation, MesWorkOrderOperation


class ProcessArchiveImportRepository:
    def add(self, session, row):
        session.add(row)

    async def lock_import(self, session, org_id):
        await import_repository.lock(session, org_id)

    async def processes(self, session, user, org_id):
        return (await session.execute(select(MesProcess).where(MesProcess.org_id == org_id,
            *scoped_conditions(MesProcess, user, "mes:archive:process:manage")))).scalars().all()

    async def route_sources(self, session, user, org_id):
        return (await session.execute(select(MesExternalImportRow).where(MesExternalImportRow.org_id == org_id,
            MesExternalImportRow.source_system_key == "gendanbao", MesExternalImportRow.record_type_key == "route_step",
            *scoped_conditions(MesExternalImportRow, user, "mes:work_order:manage")))).scalars().all()

    async def template_operations(self, session, user, org_id):
        return (await session.execute(select(MesProcessTemplateOperation).join(MesProcessTemplate,
            MesProcessTemplateOperation.template_id == MesProcessTemplate.id).where(MesProcessTemplateOperation.org_id == org_id,
            *scoped_conditions(MesProcessTemplateOperation, user, "mes:process_template:manage"),
            *scoped_conditions(MesProcessTemplate, user, "mes:process_template:manage")))).scalars().all()

    async def templates(self, session, user, org_id):
        return (await session.execute(select(MesProcessTemplate).where(MesProcessTemplate.org_id == org_id,
            *scoped_conditions(MesProcessTemplate, user, "mes:process_template:manage")))).scalars().all()

    async def check_references(self, session, derived, allowed):
        if not derived:
            return
        ids = list(derived)
        # 全量检查这些明确拥有者 ID 的引用，只返回是否阻止修改，不泄露其他范围业务字段。
        for model in (MesEquipment, MesEquipmentProcess, MesWorkOrderOperation, MesProcessTemplateOperation, MesProcessDependency):
            condition = model.process_id.in_(ids)
            if model is MesProcessDependency:
                condition = or_(condition, model.previous_process_id.in_(ids))
            conditions = [condition, model.deleted_at.is_(None)]
            if model is MesProcessTemplateOperation and allowed:
                conditions.append(model.id.not_in(allowed))
            found = (await session.execute(select(model.id).where(*conditions).limit(1))).first()
            if found:
                raise AppException("临时工艺存在其他路线、设备、前置关系或工单引用，未自动替换", 409)


repository = ProcessArchiveImportRepository()
