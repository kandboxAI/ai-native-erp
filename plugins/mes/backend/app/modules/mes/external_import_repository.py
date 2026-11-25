"""导入数据访问；MES 只写自身对象，物料与库存通过 inv 公开能力维护。"""
from sqlalchemy import select, text, func

from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from .external_import_models import MesExternalImportRow
from .models import MesProductionOrder, MesWorkOrder, MesProcessTemplate, MesWorkOrderOperation
from .archive_models import MesProcess, MesProjectStage


class ExternalImportRepository:
    def add(self, session, row):
        session.add(row)
        return row

    async def lock(self, session, org_id):
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"mes:gendanbao-import:{org_id}", 0))))

    async def missing_columns(self, session):
        rows = (await session.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()"))).all()
        present = set(rows)
        requirements = [*[(MesExternalImportRow.__tablename__, c.name) for c in MesExternalImportRow.__table__.columns],
            ("mes_production_order", "source_product_count_snapshot"), ("mes_production_order", "is_import_incomplete"),
            ("mes_work_order_operation", "is_imported_snapshot"),
            *[("mes_work_order", name) for name in ("material_name_snapshot", "heat_treatment_snapshot", "surface_treatment_snapshot", "process_requirement_snapshot", "outsourced_due_at")]]
        return [f"{table}.{column}" for table, column in requirements if (table, column) not in present]

    async def sources(self, session, user, org_id):
        return (await session.execute(select(MesExternalImportRow).where(MesExternalImportRow.org_id == org_id,
            MesExternalImportRow.source_system_key == "gendanbao",
            *scoped_conditions(MesExternalImportRow, user, "mes:work_order:manage")))).scalars().all()

    async def projects(self, session, user, org_id):
        return (await session.execute(select(MesProductionOrder).where(MesProductionOrder.org_id == org_id,
            *scoped_conditions(MesProductionOrder, user, "mes:work_order:manage")))).scalars().all()

    async def works(self, session, user, org_id):
        return (await session.execute(select(MesWorkOrder).where(MesWorkOrder.org_id == org_id,
            *scoped_conditions(MesWorkOrder, user, "mes:work_order:manage")))).scalars().all()

    async def templates(self, session, user, org_id):
        return (await session.execute(select(MesProcessTemplate).where(MesProcessTemplate.org_id == org_id,
            *scoped_conditions(MesProcessTemplate, user, "mes:process_template:manage")))).scalars().all()

    async def archive(self, session, model, org_id, number):
        field = MesProcess.process_no if model is MesProcess else MesProjectStage.stage_no
        return (await session.execute(select(model).where(model.org_id == org_id, field == number, model.deleted_at.is_(None)))).scalar_one_or_none()

    async def operator(self, session, schema, email):
        from app.auth.models import AuthTenant, AuthUser
        from app.modules.user_profile.models import SysUser
        tenant = (await session.execute(select(AuthTenant).where(AuthTenant.schema_name == schema, AuthTenant.is_active.is_(True)))).scalar_one_or_none()
        account = (await session.execute(select(AuthUser).where(AuthUser.email == email, AuthUser.is_active.is_(True)))).scalar_one_or_none()
        if not tenant or not account:
            raise AppException("目标租户或配置的操作账号不存在/已停用", 409)
        member = (await session.execute(select(SysUser).where(SysUser.auth_user_id == account.id,
            SysUser.is_active.is_(True), SysUser.deleted_at.is_(None)))).scalar_one_or_none()
        if not member:
            raise AppException("操作账号没有目标租户成员", 403)
        return tenant.id, account.id


repository = ExternalImportRepository()
