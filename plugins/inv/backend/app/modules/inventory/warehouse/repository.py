"""仓库数据访问。当前后勤库存只保留仓库粒度，不设库位。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import resolve_write_org_id, table_scope_condition, ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.crud.repository import SqlModelCrudRepository
from app.modules.organization.models import SysOrg
from app.modules.organization.service import service as organization_service
from app.modules.department.models import SysDepartment
from app.modules.user_profile.models import SysUser

from ..constants import SYSTEM_WAREHOUSE_NOS
from ..warehouse_scope import warehouse_condition
from .access_repository import repository as access_repository
from app.modules.location.public import require_location, register_consumer, read_location_metadata

from ..models import InvStockBalance, InvStockOrder, InvStockOrderLine, InvWarehouse
from .schemas import WarehouseItem, WarehouseOption, WarehouseDepartmentReference, WarehouseCustodianReference, requisition_approval_context


async def org_names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    ids = {item for item in ids if item is not None}
    if not ids:
        return {}
    rows = (await session.exec(select(SysOrg.id, SysOrg.org_name).where(SysOrg.id.in_(ids)))).all()
    return {row[0]: row[1] for row in rows}


def _uuid(value: Any) -> UUID | None:
    return None if value in (None, "") else UUID(str(value))


class WarehouseRepository(SqlModelCrudRepository):
    def _department_reference_statement(self, org_id):
        """调用方先授权根组织；只读取该有效组织子树的部门目录引用。"""
        return select(SysDepartment.id, SysDepartment.org_id, SysDepartment.parent_id,
            SysDepartment.department_no, SysDepartment.department_name, SysOrg.org_name).join(
            SysOrg, SysOrg.id == SysDepartment.org_id).where(
            SysDepartment.deleted_at.is_(None), SysDepartment.is_active.is_(True),
            SysDepartment.org_id.in_(organization_service.descendant_ids_query([org_id])))

    async def department_reference(self, session, department_id, org_id):
        if department_id is None:
            return None
        row = (await session.exec(self._department_reference_statement(org_id).where(
            SysDepartment.id == department_id))).first()
        return WarehouseDepartmentReference.model_validate(dict(row._mapping)) if row else None

    async def department_options(self, session, user, permission, *, org_id):
        """授权根组织后，发布本级及有效下级组织的部门目录；不授予下级业务记录访问权。"""
        ensure_org_access(user, org_id, permission)
        rows = (await session.exec(self._department_reference_statement(org_id).order_by(
            SysOrg.org_name, SysDepartment.department_name, SysDepartment.department_no, SysDepartment.id))).all()
        by_id = {row.id: row for row in rows}
        organizations = (await session.exec(select(SysOrg.id, SysOrg.parent_id, SysOrg.org_name).where(
            SysOrg.id.in_(organization_service.descendant_ids_query([org_id]))))).all()
        by_org = {row.id: row for row in organizations}
        def label(row):
            parts, seen, current = [], set(), row
            while current is not None and current.id not in seen and current.org_id == row.org_id:
                seen.add(current.id)
                parts.append(current.department_name)
                current = by_id.get(current.parent_id)
            org_parts, seen_orgs, current_org = [], set(), by_org.get(row.org_id)
            while current_org is not None and current_org.id not in seen_orgs:
                seen_orgs.add(current_org.id)
                if current_org.id == org_id and org_parts:
                    break
                org_parts.append(current_org.org_name)
                current_org = by_org.get(current_org.parent_id)
            return " / ".join([*reversed(org_parts), *reversed(parts)])
        return [{"value": str(row.id), "label": label(row), "org_id": str(row.org_id)} for row in rows]

    async def validate_asset_department(self, session, department_id, org_id):
        if department_id is None:
            return
        row = await self.department_reference(session, department_id, org_id)
        if row is None:
            raise AppException("责任部门须为仓库本级或有效下级组织的有效部门（未删除且已启用）", status_code=400)

    async def validate_requisition_approval_department(self, session, department_id, org_id):
        if department_id is not None and await self.department_reference(session, department_id, org_id) is None:
            raise AppException("领用审批部门须为仓库本级或有效下级组织的有效部门（未删除且已启用）", status_code=400)

    async def requisition_approval_contexts(self, session, warehouses):
        """调用方先校验仓库/申请访问权；仅发布该仓库有效组织子树内部门的 ID、名称。"""
        result = {}
        for warehouse in warehouses:
            department = await self.department_reference(session, warehouse.requisition_approval_department_id, warehouse.org_id)
            result[warehouse.id] = requisition_approval_context(department)
        return result

    def _custodian_statement(self, org_id):
        return select(SysUser.id, SysUser.org_id, SysUser.display_name, SysOrg.org_name).join(SysOrg, SysOrg.id == SysUser.org_id).where(
            SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
            SysUser.org_id.in_(organization_service.descendant_ids_query([org_id])))

    async def custodian_reference(self, session, user_id, org_id):
        if user_id is None:
            return None
        row = (await session.exec(self._custodian_statement(org_id).where(SysUser.id == user_id))).first()
        return WarehouseCustodianReference.model_validate(dict(row._mapping)) if row else None

    async def custodian_options(self, session, user, permission, *, org_id):
        ensure_org_access(user, org_id, permission)
        rows = (await session.exec(self._custodian_statement(org_id).order_by(SysUser.display_name, SysUser.id))).all()
        return [{"value": str(row.id), "label": f"{row.org_name} / {row.display_name}", "org_id": str(row.org_id)} for row in rows]

    async def validate_asset_custodian(self, session, user_id, org_id):
        if user_id and await self.custodian_reference(session, user_id, org_id) is None:
            raise AppException("资产保管人须属于仓库本级或有效下级组织，且未删除、已启用", status_code=400)

    async def asset_registration_target(self, session, warehouse_id, user):
        statement = select(InvWarehouse).where(InvWarehouse.id == warehouse_id,
            InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True))
        for permission in ("inventory_inbound:create", "inventory_inbound:confirm"):
            condition = table_scope_condition(InvWarehouse, user, permission)
            if condition is not None:
                statement = statement.where(condition)
        return (await session.exec(statement.with_for_update(read=True))).first()

    async def create_org_options(self, session: AsyncSession, current_user: AuthenticatedUser) -> list[dict[str, str]]:
        """仓库新增的跨模块只读契约：仅组织 ID/名称，按新增权限的数据范围过滤。"""
        statement = select(SysOrg.id, SysOrg.org_name).where(SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True))
        scope = table_scope_condition(SysOrg, current_user, "inventory_warehouse:create")
        if scope is not None:
            statement = statement.where(scope)
        rows = (await session.exec(statement.order_by(SysOrg.org_name, SysOrg.id))).all()
        return [{"value": str(row.id), "label": row.org_name} for row in rows]

    async def create(self, session: AsyncSession, payload: dict[str, Any], current_user: AuthenticatedUser):
        org_id = resolve_write_org_id(current_user, payload.get("org_id"), "inventory_warehouse:create")
        await require_location(session, payload["location_id"], org_id, for_update=True)
        await self.validate_asset_department(session, payload.get("default_asset_department_id"), org_id)
        await self.validate_requisition_approval_department(session, payload.get("requisition_approval_department_id"), org_id)
        await self.validate_asset_custodian(session, payload.get("default_asset_custodian_user_id"), org_id)
        organization = (await session.exec(select(SysOrg.id).where(
            SysOrg.id == org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
        ))).first()
        if organization is None:
            raise AppException("所属组织不存在或已停用", status_code=status.HTTP_400_BAD_REQUEST)
        exists = (await session.exec(select(InvWarehouse.id).where(
            InvWarehouse.org_id == org_id,
            InvWarehouse.warehouse_no == payload["warehouse_no"],
            InvWarehouse.deleted_at.is_(None),
        ))).first()
        if exists is not None:
            raise AppException("该组织下仓库编号已存在", status_code=status.HTTP_409_CONFLICT)
        try:
            return await super().create(session, {**payload, "org_id": org_id}, current_user)
        except IntegrityError as exc:
            await session.rollback()
            if getattr(exc.orig, "sqlstate", None) == "23505" or getattr(exc.orig, "pgcode", None) == "23505":
                raise AppException("该组织下仓库编号已存在", status_code=status.HTTP_409_CONFLICT) from exc
            raise

    async def _enrich(self, session: AsyncSession, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = await org_names(session, {_uuid(item.get("org_id")) for item in items})
        for item in items:
            approval_department_id = item.get("requisition_approval_department_id")
            approval_department = await self.department_reference(session, _uuid(approval_department_id), _uuid(item.get("org_id")))
            item.update(requisition_approval_context(approval_department))
            # 编辑时保留原引用，失效部门仅不再作为审批展示名称发布。
            item["requisition_approval_department_id"] = approval_department_id
            department_id = _uuid(item.get("default_asset_department_id"))
            department = await self.department_reference(session, department_id, _uuid(item.get("org_id"))) if department_id else None
            item["default_asset_department_name"] = department.department_name if department else None
            custodian = await self.custodian_reference(session, _uuid(item.get("default_asset_custodian_user_id")), _uuid(item.get("org_id")))
            item["default_asset_custodian_name"] = custodian.display_name if custodian else None
            item["org_name"] = names.get(_uuid(item.get("org_id")))
            location_id = _uuid(item.get("location_id"))
            master = await read_location_metadata(session, location_id, _uuid(item.get("org_id"))) if location_id else None
            item["location_name"] = master.location_name if master else None
            item["latitude"] = str(master.latitude) if master else None
            item["longitude"] = str(master.longitude) if master else None
            item["coordinate_system_code"] = master.coordinate_system_code if master else None
        return items

    async def list(self, session: AsyncSession, params, current_user: AuthenticatedUser) -> dict[str, Any]:
        result = await super().list(session, params, current_user)
        result["items"] = await self._enrich(session, result["items"])
        return result

    async def detail(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser):
        item = await super().detail(session, item_id, current_user)
        if item is None:
            return None
        return WarehouseItem.model_validate((await self._enrich(session, [item.model_dump(mode="json")]))[0])

    async def update(self, session: AsyncSession, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        entity = (
            await session.exec(
                self._scoped_detail_statement(item_id, current_user, action="update")
            )
        ).one_or_none()
        if entity is None:
            raise AppException("仓库不存在或无权修改", status_code=status.HTTP_404_NOT_FOUND)
        if "location_id" in payload:
            await require_location(session, payload["location_id"], entity.org_id, for_update=True)
        if "default_asset_department_id" in payload:
            await self.validate_asset_department(session, payload["default_asset_department_id"], entity.org_id)
        if "requisition_approval_department_id" in payload:
            await self.validate_requisition_approval_department(session, payload["requisition_approval_department_id"], entity.org_id)
        if "default_asset_custodian_user_id" in payload:
            await self.validate_asset_custodian(session, payload["default_asset_custodian_user_id"], entity.org_id)
        forbidden = payload.keys() - {"warehouse_name", "location", "location_id", "default_asset_department_id", "default_asset_custodian_user_id", "requisition_approval_department_id"}
        if forbidden:
            raise AppException("仓库只允许修改名称、位置、领用审批部门及资产责任设置", status_code=status.HTTP_409_CONFLICT)
        allowed = {key: value for key, value in payload.items() if key in {"warehouse_name", "location", "location_id", "default_asset_department_id", "default_asset_custodian_user_id", "requisition_approval_department_id"}}
        return await super().update(session, item_id, allowed, current_user)

    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        del session, item_id, current_user
        raise AppException("请通过仓库服务执行删除校验", status_code=status.HTTP_409_CONFLICT)

    async def lock_for_deletion(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> InvWarehouse | None:
        return (await session.exec(self._scoped_detail_statement(
            item_id, current_user, action="delete", for_update=True,
        ))).one_or_none()

    async def ensure_empty_for_deletion(self, session: AsyncSession, warehouse_id: UUID) -> None:
        # 不按总和判断：不同批次/状态的正负数量不能互相抵消；预留、借出等也必须清零。
        stock = (await session.exec(select(InvStockBalance.id).where(
            InvStockBalance.warehouse_id == warehouse_id,
            or_(InvStockBalance.quantity != 0, InvStockBalance.reserved_quantity != 0),
        ).limit(1))).first()
        if stock is not None:
            raise AppException("仓库仍有库存或预留数量，清空后才能删除", status_code=status.HTTP_409_CONFLICT)
        line_reference = select(InvStockOrderLine.id).where(
            InvStockOrderLine.stock_order_id == InvStockOrder.id,
            or_(InvStockOrderLine.from_warehouse_id == warehouse_id, InvStockOrderLine.to_warehouse_id == warehouse_id),
        ).exists()
        pending = (await session.exec(select(InvStockOrder.id).where(
            InvStockOrder.status_code.notin_(["confirmed", "voided"]),
            or_(InvStockOrder.from_warehouse_id == warehouse_id, InvStockOrder.to_warehouse_id == warehouse_id, line_reference),
        ).limit(1))).first()
        if pending is not None:
            raise AppException("仓库存在未完成的库存单据，请先处理后再删除", status_code=status.HTTP_409_CONFLICT)

    async def mark_deleted(self, session: AsyncSession, warehouse: InvWarehouse, current_user: AuthenticatedUser) -> None:
        now = utc_now()
        warehouse.deleted_at = now
        warehouse.deleted_by = current_user.user_id
        warehouse.updated_at = now
        warehouse.updated_by = current_user.user_id
        session.add(warehouse)
        await session.flush()

    async def options(
        self,
        session: AsyncSession,
        current_user: AuthenticatedUser,
        permission_key: str,
        scope_key=None,
        *, additional_permissions: tuple[str, ...] = (),
    ) -> list[WarehouseOption]:
        """按调用方真实权限的数据范围返回所有启用仓库。"""
        statement = (
            select(InvWarehouse, SysOrg.org_name)
            .join(SysOrg, SysOrg.id == InvWarehouse.org_id)
            .where(
                warehouse_condition(scope_key, current_user),
                InvWarehouse.deleted_at.is_(None),
                InvWarehouse.is_active.is_(True),
            )
            .order_by(InvWarehouse.warehouse_no)
        )
        scope = table_scope_condition(InvWarehouse, current_user, permission_key)
        if scope is not None:
            statement = statement.where(scope)
        for permission in additional_permissions:
            extra_scope = table_scope_condition(InvWarehouse, current_user, permission)
            if extra_scope is not None:
                statement = statement.where(extra_scope)
        rows = (await session.exec(statement)).all()
        return [
            WarehouseOption(
                id=warehouse.id,
                org_id=warehouse.org_id,
                org_name=org_name,
                warehouse_no=warehouse.warehouse_no,
                warehouse_name=warehouse.warehouse_name,
                warehouse_type_code=warehouse.warehouse_type_code,
                location_id=warehouse.location_id,
                default_asset_department_id=warehouse.default_asset_department_id,
                default_asset_custodian_user_id=warehouse.default_asset_custodian_user_id,
                location=warehouse.location,
                label=warehouse.warehouse_name,
            )
            for warehouse, org_name in rows
        ]

    async def get_many(self, session: AsyncSession, ids: set[UUID], *, lock=False) -> dict[UUID, InvWarehouse]:
        ids = {item for item in ids if item is not None}
        if not ids:
            return {}
        statement = select(InvWarehouse).where(
                    InvWarehouse.id.in_(ids),
                    InvWarehouse.deleted_at.is_(None),
                    InvWarehouse.is_active.is_(True),
                ).order_by(InvWarehouse.id)
        statement = statement.with_for_update() if lock else statement.with_for_update(read=True, of=InvWarehouse)
        rows = (await session.exec(statement)).all()
        return {row.id: row for row in rows}

    async def get_by_no(self, session: AsyncSession, warehouse_no: str) -> InvWarehouse | None:
        return (
            await session.exec(
                select(InvWarehouse).where(
                    InvWarehouse.warehouse_no == warehouse_no,
                    InvWarehouse.deleted_at.is_(None),
                    InvWarehouse.is_active.is_(True),
                )
            )
        ).one_or_none()


warehouse_repository = WarehouseRepository(
    table_model=InvWarehouse,
    item_model=WarehouseItem,
    writable_columns=["org_id", "warehouse_no", "warehouse_name", "location", "is_active", "location_id", "default_asset_department_id", "default_asset_custodian_user_id", "requisition_approval_department_id"],
    searchable_columns=["warehouse_no", "warehouse_name", "location"],
    filterable_columns=["org_id", "is_active"],
    scope_resource="inventory_warehouse",
    organization_write_kind="any",
)


async def _location_referenced(session, location_id):
    return (await session.exec(select(InvWarehouse.id).where(InvWarehouse.location_id == location_id).limit(1))).first() is not None


register_consumer("warehouse", table_name="inv_warehouse", reference=_location_referenced,
    permissions=("inventory_warehouse:create", "inventory_warehouse:update"))
