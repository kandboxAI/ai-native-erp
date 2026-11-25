"""仓库申领共享的只读目录契约、授权查询与有效期维护。"""
from uuid import UUID

from sqlalchemy import false
from sqlmodel import select

from app.auth.scope_filters import table_scope_condition
from app.framework.db.models import utc_now
from app.modules.organization.models import SysOrg
from app.modules.organization.service import service as organization_service
from ..models import InvWarehouse, InvWarehouseRequisitionOrg

SCOPE_PERMISSION = "inventory_warehouse:requisition_scope"


class RequisitionScopeRepository:
    async def managed_warehouse(self, session, warehouse_id: UUID, user, *, lock=False):
        statement = select(InvWarehouse).where(InvWarehouse.id == warehouse_id, InvWarehouse.deleted_at.is_(None))
        scope = table_scope_condition(InvWarehouse, user, SCOPE_PERMISSION)
        if scope is not None:
            statement = statement.where(scope)
        if lock:
            statement = statement.with_for_update(of=InvWarehouse)
        return (await session.exec(statement)).first()

    async def organization_options(self, session, owner_org_id: UUID):
        # 仅在仓库管理授权通过后调用。跨模块只读取有效组织 ID、名称及父节点。
        descendants = organization_service.descendant_ids_query([owner_org_id])
        rows = (await session.exec(select(SysOrg.id, SysOrg.org_name, SysOrg.parent_id).where(
            SysOrg.id.in_(descendants), SysOrg.id != owner_org_id,
        ).order_by(SysOrg.org_name, SysOrg.id))).all()
        return [{"id": row.id, "org_name": row.org_name, "parent_id": row.parent_id} for row in rows]

    async def current_grants(self, session, warehouse_id: UUID):
        return list((await session.exec(select(InvWarehouseRequisitionOrg).where(
            InvWarehouseRequisitionOrg.warehouse_id == warehouse_id,
            InvWarehouseRequisitionOrg.valid_to.is_(None),
        ).order_by(InvWarehouseRequisitionOrg.id))).all())

    async def organization_names(self, session, ids: set[UUID]):
        if not ids:
            return {}
        rows = (await session.exec(select(SysOrg.id, SysOrg.org_name).where(SysOrg.id.in_(ids)))).all()
        return {row.id: row.org_name for row in rows}

    async def replace(self, session, warehouse, current, wanted: set[UUID], user):
        now = utc_now()
        retained = set()
        for row in current:
            if row.recipient_org_id in wanted:
                retained.add(row.recipient_org_id)
            else:
                row.valid_to = now
                row.updated_at = now
                row.updated_by = user.user_id
                session.add(row)
        for org_id in sorted(wanted - retained, key=str):
            session.add(InvWarehouseRequisitionOrg(
                org_id=warehouse.org_id, warehouse_id=warehouse.id, recipient_org_id=org_id,
                valid_from=now, created_by=user.user_id, updated_by=user.user_id,
            ))
        warehouse.updated_at = now
        warehouse.updated_by = user.user_id
        session.add(warehouse)
        await session.flush()

    def shared_condition(self, user):
        """公开领用候选查询契约：仅当前主组织明确获准的仓库，不授予管理权限。"""
        if user.org_id is None or "inventory_requisition:create" not in user.permissions:
            return false()
        return self.recipient_condition(user.org_id)

    def recipient_condition(self, org_id):
        """已鉴权申请发放的组织引用契约；只核对共享关系，不授予账号申领/管理权限。"""
        ancestors = organization_service.ancestor_ids_query([org_id])
        return select(InvWarehouseRequisitionOrg.id).where(
            InvWarehouseRequisitionOrg.warehouse_id == InvWarehouse.id,
            InvWarehouseRequisitionOrg.org_id == InvWarehouse.org_id,
            InvWarehouseRequisitionOrg.recipient_org_id == org_id,
            InvWarehouseRequisitionOrg.valid_to.is_(None),
            InvWarehouseRequisitionOrg.valid_from <= utc_now(),
            InvWarehouse.org_id.in_(ancestors),
        ).correlate(InvWarehouse).exists()


repository = RequisitionScopeRepository()
