from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, tuple_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import org_column_scope_condition, table_scope_condition
from app.modules.department.models import SysDepartment
from app.modules.organization.models import SysOrg
from app.modules.user_profile.models import SysUser
from app.modules.inventory.warehouse.service import warehouse_service
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.inventory.constants import STOCK_AVAILABLE
from app.modules.inventory.models import (
    InvStockBalance,
    InvStockOrder,
    InvStockOrderType,
    InvWarehouse,
    MdItem,
    MdItemCategory,
)

from .models import InvMaterialRequisition, InvMaterialRequisitionEvent, InvMaterialRequisitionLine, InvMaterialRequisitionReceiptLine
from .schemas import RequisitionListQuery


class RequisitionRepository:
    async def personal_custody_recipient(self, session, request):
        """已鉴权申请的最小人员引用；仅核对原申领人及其当前部门，不发布人员目录。"""
        recipient = (await session.exec(select(SysUser).where(
            SysUser.id == request.applicant_user_id, SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
        ).with_for_update())).first()
        if recipient is None:
            return None
        warehouse = (await session.exec(select(InvWarehouse).where(
            InvWarehouse.id == request.warehouse_id, InvWarehouse.org_id == request.org_id,
            InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
            or_(InvWarehouse.org_id == recipient.org_id, warehouse_service.shared_requisition_recipient_condition(recipient.org_id)),
        ))).first()
        org = (await session.exec(select(SysOrg.id).where(
            SysOrg.id == recipient.org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
        ))).first()
        if warehouse is None or org is None:
            return None
        if recipient.department_id is not None:
            department = (await session.exec(select(SysDepartment.id).where(
                SysDepartment.id == recipient.department_id, SysDepartment.org_id == recipient.org_id,
                SysDepartment.deleted_at.is_(None), SysDepartment.is_active.is_(True),
            ))).first()
            if department is None:
                return None
        return {"custodian_user_id": recipient.id, "department_id": recipient.department_id,
                "custody_location_note": request.custody_location_note}

    async def organization_name(self, session, org_id: UUID):
        """申请来源组织只读契约：当前登录身份的组织 ID 及名称，用于提交时快照。"""
        return (await session.exec(select(SysOrg.org_name).where(
            SysOrg.id == org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
        ))).first()

    async def is_visible(self, session, row, user, permission: str) -> bool:
        condition = table_scope_condition(InvMaterialRequisition, user, permission)
        if condition is None:
            return True
        return (await session.exec(select(InvMaterialRequisition.id).where(
            InvMaterialRequisition.id == row.id, condition
        ))).first() is not None

    async def event(self, session, event_id: UUID):
        return (await session.exec(select(InvMaterialRequisitionEvent).where(InvMaterialRequisitionEvent.id == event_id))).first()

    async def receipt_lines(self, session, event_ids: list[UUID]):
        if not event_ids:
            return []
        return list((await session.exec(select(InvMaterialRequisitionReceiptLine).where(
            InvMaterialRequisitionReceiptLine.event_id.in_(event_ids)
        ).order_by(InvMaterialRequisitionReceiptLine.id))).all())

    async def has_open_warehouse_requests(self, session: AsyncSession, warehouse_id: UUID) -> bool:
        return (await session.exec(select(InvMaterialRequisition.id).where(
            InvMaterialRequisition.warehouse_id == warehouse_id,
            InvMaterialRequisition.status_code.in_(["submitted", "approved"]),
        ).limit(1))).first() is not None

    async def department_name(self, session: AsyncSession, department_id: UUID | None) -> str | None:
        if department_id is None:
            return None
        return (await session.exec(select(SysDepartment.department_name).where(SysDepartment.id == department_id))).first()

    async def items(self, session: AsyncSession, item_ids: set[UUID]) -> dict[UUID, MdItem]:
        if not item_ids:
            return {}
        rows = (
            await session.exec(
                select(MdItem).where(MdItem.id.in_(item_ids), MdItem.deleted_at.is_(None), MdItem.is_active.is_(True))
            )
        ).all()
        return {row.id: row for row in rows}

    async def unit_names(self, session: AsyncSession, unit_codes: set[str]) -> dict[str, str]:
        if not unit_codes:
            return {}
        rows = (
            await session.exec(
                select(SysDictItem.item_code, SysDictItem.item_name)
                .join(SysDict, SysDict.id == SysDictItem.dict_id)
                .where(
                    SysDict.dict_code == "md_unit",
                    SysDict.is_active.is_(True),
                    SysDict.deleted_at.is_(None),
                    SysDictItem.item_code.in_(unit_codes),
                    SysDictItem.is_active.is_(True),
                    SysDictItem.deleted_at.is_(None),
                )
            )
        ).all()
        return {code: name for code, name in rows}

    async def material_options(
        self, session: AsyncSession, warehouse_ids: set[UUID], keyword: str | None = None
    ) -> list[dict[str, Any]]:
        available = func.coalesce(
            func.sum(
                case(
                    (
                        InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                        InvStockBalance.quantity - InvStockBalance.reserved_quantity,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        statement = (
            select(MdItem, MdItemCategory.category_name, InvWarehouse, available.label("available_quantity"))
            .join(InvStockBalance, InvStockBalance.item_id == MdItem.id)
            .join(InvWarehouse, InvWarehouse.id == InvStockBalance.warehouse_id)
            .join(MdItemCategory, MdItemCategory.id == MdItem.category_id, isouter=True)
            .where(
                MdItem.deleted_at.is_(None),
                MdItem.is_active.is_(True),
                InvStockBalance.warehouse_id.in_(warehouse_ids),
                InvWarehouse.deleted_at.is_(None),
                InvWarehouse.is_active.is_(True),
            )
            .group_by(MdItem.id, MdItemCategory.category_name, InvWarehouse.id)
            .order_by(InvWarehouse.warehouse_name, MdItem.item_name)
        )
        if keyword:
            pattern = f"%{keyword.strip()}%"
            statement = statement.where(
                or_(MdItem.item_no.ilike(pattern), MdItem.item_name.ilike(pattern), MdItem.specification.ilike(pattern))
            )
        rows = (await session.exec(statement.limit(200))).all()
        return [
            {
                "id": item.id,
                "warehouse_id": warehouse.id,
                "warehouse_no": warehouse.warehouse_no,
                "warehouse_name": warehouse.warehouse_name,
                "item_no": item.item_no,
                "item_name": item.item_name,
                "category_name": category_name,
                "specification": item.specification,
                "unit_code": item.unit_code,
                "available_quantity": Decimal(quantity or 0),
            }
            for item, category_name, warehouse, quantity in rows
        ]

    async def available_by_item_warehouse(
        self, session: AsyncSession, keys: set[tuple[UUID, UUID]]
    ) -> dict[tuple[UUID, UUID], Decimal]:
        if not keys:
            return {}
        rows = (
            await session.exec(
                select(
                    InvStockBalance.item_id,
                    InvStockBalance.warehouse_id,
                    func.sum(InvStockBalance.quantity - InvStockBalance.reserved_quantity),
                )
                .where(
                    tuple_(InvStockBalance.item_id, InvStockBalance.warehouse_id).in_(keys),
                    InvStockBalance.stock_status_code == STOCK_AVAILABLE,
                )
                .group_by(InvStockBalance.item_id, InvStockBalance.warehouse_id)
            )
        ).all()
        result: dict[tuple[UUID, UUID], Decimal] = {}
        for item_id, warehouse_id, quantity in rows:
            key = (item_id, warehouse_id)
            if key in keys:
                result[key] = Decimal(quantity or 0)
        return result

    async def accessible_warehouses(
        self, session: AsyncSession, user: AuthenticatedUser, permission_key: str,
        *, lock: bool = False,
    ) -> dict[UUID, InvWarehouse]:
        conditions = [InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True)]
        scope = (org_column_scope_condition(InvWarehouse.org_id, user, permission_key)
                 if permission_key == "inventory_requisition:create"
                 else table_scope_condition(InvWarehouse, user, permission_key))
        if scope is not None:
            if permission_key == "inventory_requisition:create":
                scope = or_(scope, warehouse_service.shared_requisition_condition(user))
            conditions.append(scope)
        statement = select(InvWarehouse).where(*conditions).order_by(InvWarehouse.id)
        if lock:
            statement = statement.with_for_update(read=True, of=InvWarehouse)
        rows = (await session.exec(statement)).all()
        if lock and permission_key == "inventory_requisition:create" and rows:
            # 范围撤销与提交共用仓库行锁。锁等待结束后用新语句重查，避免使用等待前的授权快照。
            fresh_conditions = [InvWarehouse.deleted_at.is_(None), InvWarehouse.is_active.is_(True),
                                InvWarehouse.id.in_([row.id for row in rows])]
            fresh_scope = org_column_scope_condition(InvWarehouse.org_id, user, permission_key)
            if fresh_scope is not None:
                fresh_conditions.append(or_(fresh_scope, warehouse_service.shared_requisition_condition(user)))
            rows = (await session.exec(select(InvWarehouse).where(*fresh_conditions).order_by(InvWarehouse.id))).all()
        return {row.id: row for row in rows}

    async def warehouse(self, session: AsyncSession, warehouse_id: UUID) -> InvWarehouse | None:
        """仅用于历史申请展示，保留已删除仓库的名称；新申请使用 accessible_warehouses。"""
        return (
            await session.exec(
                select(InvWarehouse).where(
                    InvWarehouse.id == warehouse_id,
                )
            )
        ).first()

    async def add(
        self,
        session: AsyncSession,
        request: InvMaterialRequisition,
        lines: list[InvMaterialRequisitionLine],
        event: InvMaterialRequisitionEvent,
    ) -> None:
        session.add(request)
        session.add_all(lines)
        session.add(event)
        await session.flush()

    async def get(
        self, session: AsyncSession, request_id: UUID, *, for_update: bool = False
    ) -> InvMaterialRequisition | None:
        statement = select(InvMaterialRequisition).where(InvMaterialRequisition.id == request_id)
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).first()

    async def lines(self, session: AsyncSession, request_id: UUID) -> list[InvMaterialRequisitionLine]:
        return list(
            (
                await session.exec(
                    select(InvMaterialRequisitionLine)
                    .where(InvMaterialRequisitionLine.requisition_id == request_id)
                    .order_by(InvMaterialRequisitionLine.line_no)
                )
            ).all()
        )

    async def events(self, session: AsyncSession, request_id: UUID) -> list[InvMaterialRequisitionEvent]:
        return list(
            (
                await session.exec(
                    select(InvMaterialRequisitionEvent)
                    .where(InvMaterialRequisitionEvent.requisition_id == request_id)
                    .order_by(InvMaterialRequisitionEvent.created_at, InvMaterialRequisitionEvent.id)
                )
            ).all()
        )

    async def stock_order_no(self, session: AsyncSession, stock_order_id: UUID | None) -> str | None:
        if stock_order_id is None:
            return None
        return (await session.exec(select(InvStockOrder.order_no).where(InvStockOrder.id == stock_order_id))).first()

    async def list_requests(
        self,
        session: AsyncSession,
        query: RequisitionListQuery,
        current_user: AuthenticatedUser,
        *,
        mine: bool,
    ) -> tuple[int, list[InvMaterialRequisition]]:
        conditions: list[Any] = []
        if mine:
            conditions.append(InvMaterialRequisition.applicant_user_id == current_user.user_id)
        else:
            scope = table_scope_condition(InvMaterialRequisition, current_user, "inventory_requisition:list")
            if scope is not None:
                conditions.append(scope)
        if query.status_code:
            conditions.append(InvMaterialRequisition.status_code == query.status_code)
        if query.department_id:
            conditions.append(InvMaterialRequisition.department_id == query.department_id)
        if query.warehouse_id:
            conditions.append(InvMaterialRequisition.warehouse_id == query.warehouse_id)
        if query.keyword:
            pattern = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    InvMaterialRequisition.request_no.ilike(pattern),
                    InvMaterialRequisition.applicant_name_snapshot.ilike(pattern),
                    InvMaterialRequisition.department_name_snapshot.ilike(pattern),
                    InvMaterialRequisition.purpose.ilike(pattern),
                )
            )
        base = select(InvMaterialRequisition).where(*conditions)
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(InvMaterialRequisition.created_at.desc())
                .limit(query.page_size)
                .offset((query.page - 1) * query.page_size)
            )
        ).all()
        return int(total or 0), list(rows)

    async def requisition_type(self, session: AsyncSession) -> InvStockOrderType | None:
        return (
            await session.exec(
                select(InvStockOrderType).where(
                    InvStockOrderType.type_no == "REQUISITION_OUT",
                    InvStockOrderType.deleted_at.is_(None),
                )
            )
        ).first()


repository = RequisitionRepository()

