from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import warehouse_repository
from .schemas import WarehouseOption
from .deletion import validate_warehouse_delete

WAREHOUSE_OPTION_PERMISSIONS = (
    "inventory_movement:list",
    "inventory_warehouse:list",
    "inventory_warehouse:create",
    "inventory_product:list",
    "inventory_item:list",
    "inventory_stock_alert:list",
    "inventory_inbound:list",
    "inventory_outbound:list",
    "inventory_transfer:list",
    "inventory_lend:list",
    "inventory_damage:list",
    "inventory_stocktake:list",
    "inventory_requisition:create",
    "inventory_requisition:list",
    "inventory_requisition:approve",
    "inventory_requisition:issue",
)

DEPARTMENT_OPTION_PERMISSIONS = frozenset({
    "inventory_warehouse:create", "inventory_warehouse:update",
    "inventory_inbound:create", "inventory_inbound:update", "inventory_inbound:confirm",
})


class WarehouseService(CrudService):
    async def requisition_approval_contexts(self, session, warehouses):
        """仅用于调用方已授权的仓库，按当前有效配置提供领用审批展示元数据。"""
        return await warehouse_repository.requisition_approval_contexts(session, warehouses)

    async def custodian_options(self, user, org_id, permission_key):
        if permission_key not in DEPARTMENT_OPTION_PERMISSIONS or permission_key not in user.permissions:
            raise AppException("无权选择资产保管人", status_code=403)
        async with get_session_context() as session:
            return await warehouse_repository.custodian_options(session, user, permission_key, org_id=org_id)

    async def department_options(self, user, org_id, permission_key):
        if permission_key not in DEPARTMENT_OPTION_PERMISSIONS or permission_key not in user.permissions:
            raise AppException("无权选择责任部门", status_code=403)
        ensure_org_access(user, org_id, permission_key)
        async with get_session_context() as session:
            return await warehouse_repository.department_options(session, user, permission_key, org_id=org_id)

    def shared_requisition_condition(self, user):
        """供领用模块复用的仓库级共享候选查询契约。"""
        from .requisition_scope_repository import repository
        return repository.shared_condition(user)

    def shared_requisition_recipient_condition(self, org_id):
        """仅供已鉴权申请发放核验接收组织，不返回仓库或人员目录。"""
        from .requisition_scope_repository import repository
        return repository.recipient_condition(org_id)

    async def delete(self, item_id: str, current_user: AuthenticatedUser) -> bool:
        if "inventory_warehouse:delete" not in current_user.permissions:
            raise AppException("无权删除仓库", status_code=status.HTTP_403_FORBIDDEN)
        async with get_session_context() as session:
            warehouse = await warehouse_repository.lock_for_deletion(session, item_id, current_user)
            if warehouse is None:
                return False
            await warehouse_repository.ensure_empty_for_deletion(session, warehouse.id)
            await validate_warehouse_delete(session, warehouse)
            await warehouse_repository.mark_deleted(session, warehouse, current_user)
            await session.commit()
            return True

    async def create_org_options(self, current_user: AuthenticatedUser) -> list[dict[str, str]]:
        if "inventory_warehouse:create" not in current_user.permissions:
            raise AppException("无权新增仓库", status_code=status.HTTP_403_FORBIDDEN)
        async with get_session_context() as session:
            return await warehouse_repository.create_org_options(session, current_user)

    async def options(self, current_user: AuthenticatedUser, scope_key=None) -> list[WarehouseOption]:
        permission_key = next(
            (key for key in WAREHOUSE_OPTION_PERMISSIONS if key in current_user.permissions),
            None,
        )
        if permission_key is None:
            raise AppException("无权查看仓库选项", status_code=status.HTTP_403_FORBIDDEN)
        async with get_session_context() as session:
            return await warehouse_repository.options(session, current_user, permission_key,
                **({"scope_key": scope_key} if scope_key else {}))


warehouse_service = WarehouseService(repository=warehouse_repository, session_getter=get_session_context)
