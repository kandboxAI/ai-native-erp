"""库存演示环境定向整理。

仅处理历史演示种子创建的东、西校区 ZC01 仓库及其库存数据。默认只预览；调用方必须显式传入
``apply=True`` 才会提交。正式业务数据或存在跨模块引用时拒绝执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, or_, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now
from app.modules.inventory_requisition.models import (
    InvMaterialRequisition,
    InvMaterialRequisitionEvent,
    InvMaterialRequisitionLine,
)
from app.modules.organization.models import SysOrg

from .constants import CANTEEN_WAREHOUSE_NO, GENERAL_WAREHOUSE_NO
from .models import InvStockBalance, InvStockOrder, InvStockOrderLine, InvStockTransaction, InvWarehouse

LEGACY_ORG_NOS = {"east_campus", "west_campus"}
LEGACY_WAREHOUSE_NO = "ZC01"
LEGACY_WAREHOUSE_NAMES = {"总务仓库", "西校区仓库"}


@dataclass(frozen=True)
class DemoResetPreview:
    warehouse_ids: tuple[UUID, ...]
    order_ids: tuple[UUID, ...]
    balance_count: int
    transaction_count: int

    def as_dict(self) -> dict[str, int]:
        return {
            "warehouses": len(self.warehouse_ids),
            "orders": len(self.order_ids),
            "balances": self.balance_count,
            "transactions": self.transaction_count,
        }


class InventoryDemoResetRepository:
    async def system_summary(self, session: AsyncSession) -> list[dict[str, str | int]]:
        warehouses = list(
            (
                await session.exec(
                    select(InvWarehouse)
                    .where(
                        InvWarehouse.warehouse_no.in_((GENERAL_WAREHOUSE_NO, CANTEEN_WAREHOUSE_NO)),
                        InvWarehouse.deleted_at.is_(None),
                    )
                    .order_by(InvWarehouse.warehouse_no)
                )
            ).all()
        )
        result: list[dict[str, str | int]] = []
        for warehouse in warehouses:
            balance_count, total_quantity = (
                await session.exec(
                    select(
                        func.count(InvStockBalance.id),
                        func.coalesce(func.sum(InvStockBalance.quantity), 0),
                    ).where(InvStockBalance.warehouse_id == warehouse.id)
                )
            ).one()
            line_orders = select(InvStockOrderLine.stock_order_id).where(
                or_(
                    InvStockOrderLine.from_warehouse_id == warehouse.id,
                    InvStockOrderLine.to_warehouse_id == warehouse.id,
                )
            )
            order_count = (
                await session.exec(
                    select(func.count(InvStockOrder.id)).where(
                        or_(
                            InvStockOrder.from_warehouse_id == warehouse.id,
                            InvStockOrder.to_warehouse_id == warehouse.id,
                            InvStockOrder.id.in_(line_orders),
                        )
                    )
                )
            ).one()
            result.append(
                {
                    "warehouse_no": warehouse.warehouse_no,
                    "warehouse_name": warehouse.warehouse_name,
                    "balance_rows": int(balance_count or 0),
                    "total_quantity": str(total_quantity or 0),
                    "orders": int(order_count or 0),
                }
            )
        return result

    async def preview(self, session: AsyncSession) -> DemoResetPreview:
        warehouses = list(
            (
                await session.exec(
                    select(InvWarehouse)
                    .join(SysOrg, SysOrg.id == InvWarehouse.org_id)
                    .where(
                        InvWarehouse.warehouse_no == LEGACY_WAREHOUSE_NO,
                        InvWarehouse.warehouse_name.in_(LEGACY_WAREHOUSE_NAMES),
                        SysOrg.org_no.in_(LEGACY_ORG_NOS),
                        InvWarehouse.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        warehouse_ids = tuple(row.id for row in warehouses)
        if not warehouse_ids:
            return DemoResetPreview((), (), 0, 0)

        line_order_ids = select(InvStockOrderLine.stock_order_id).where(
            or_(
                InvStockOrderLine.from_warehouse_id.in_(warehouse_ids),
                InvStockOrderLine.to_warehouse_id.in_(warehouse_ids),
            )
        )
        orders = list(
            (
                await session.exec(
                    select(InvStockOrder).where(
                        or_(
                            InvStockOrder.from_warehouse_id.in_(warehouse_ids),
                            InvStockOrder.to_warehouse_id.in_(warehouse_ids),
                            InvStockOrder.id.in_(line_order_ids),
                        )
                    )
                )
            ).all()
        )
        order_ids = {row.id for row in orders}
        # 归还、冲销单可能只通过明细或原单关联，循环补齐整条关系链。
        while order_ids:
            line_ids = select(InvStockOrderLine.id).where(InvStockOrderLine.stock_order_id.in_(order_ids))
            related = set(
                (
                    await session.exec(
                        select(InvStockOrder.id)
                        .join(InvStockOrderLine, InvStockOrderLine.stock_order_id == InvStockOrder.id, isouter=True)
                        .where(
                            or_(
                                InvStockOrder.reversal_of_order_id.in_(order_ids),
                                InvStockOrderLine.source_line_id.in_(line_ids),
                            )
                        )
                    )
                ).all()
            )
            expanded = order_ids | related
            if expanded == order_ids:
                break
            order_ids = expanded

        balance_count = len(
            (await session.exec(select(InvStockBalance.id).where(InvStockBalance.warehouse_id.in_(warehouse_ids)))).all()
        )
        transaction_count = len(
            (
                await session.exec(
                    select(InvStockTransaction.id).where(
                        or_(
                            InvStockTransaction.stock_order_id.in_(order_ids),
                            InvStockTransaction.from_warehouse_id.in_(warehouse_ids),
                            InvStockTransaction.to_warehouse_id.in_(warehouse_ids),
                        )
                    )
                )
            ).all()
        )
        return DemoResetPreview(
            warehouse_ids=warehouse_ids,
            order_ids=tuple(sorted(order_ids, key=str)),
            balance_count=balance_count,
            transaction_count=transaction_count,
        )

    async def _requisitions(
        self, session: AsyncSession, preview: DemoResetPreview
    ) -> list[InvMaterialRequisition]:
        if not preview.warehouse_ids:
            return []
        conditions = [InvMaterialRequisition.warehouse_id.in_(preview.warehouse_ids)]
        if preview.order_ids:
            conditions.append(InvMaterialRequisition.stock_order_id.in_(preview.order_ids))
        return list((await session.exec(select(InvMaterialRequisition).where(or_(*conditions)))).all())

    async def blocking_requisitions(
        self, session: AsyncSession, preview: DemoResetPreview
    ) -> list[dict[str, str]]:
        return [
            {
                "request_no": row.request_no,
                "status_code": row.status_code,
                "purpose": row.purpose,
            }
            for row in await self._requisitions(session, preview)
        ]

    async def _assert_safe(
        self,
        session: AsyncSession,
        preview: DemoResetPreview,
        *,
        include_requisitions: bool,
    ) -> list[InvMaterialRequisition]:
        if len(preview.warehouse_ids) not in (0, 2):
            raise RuntimeError(f"预期找到 0 或 2 个历史演示仓库，实际为 {len(preview.warehouse_ids)} 个")
        requisitions = await self._requisitions(session, preview)
        if requisitions and not include_requisitions:
            raise RuntimeError("历史仓库仍被正式领用申请引用，拒绝清理")
        return requisitions

    async def apply(
        self,
        session: AsyncSession,
        preview: DemoResetPreview,
        user_id: UUID,
        *,
        include_requisitions: bool = False,
    ) -> None:
        requisitions = await self._assert_safe(
            session,
            preview,
            include_requisitions=include_requisitions,
        )
        if not preview.warehouse_ids:
            return
        requisition_ids = [item.id for item in requisitions]
        if requisition_ids:
            await session.exec(
                delete(InvMaterialRequisitionEvent).where(
                    InvMaterialRequisitionEvent.requisition_id.in_(requisition_ids)
                )
            )
            await session.exec(
                delete(InvMaterialRequisitionLine).where(
                    InvMaterialRequisitionLine.requisition_id.in_(requisition_ids)
                )
            )
            await session.exec(
                delete(InvMaterialRequisition).where(InvMaterialRequisition.id.in_(requisition_ids))
            )
        transaction_conditions = [
            InvStockTransaction.from_warehouse_id.in_(preview.warehouse_ids),
            InvStockTransaction.to_warehouse_id.in_(preview.warehouse_ids),
        ]
        if preview.order_ids:
            transaction_conditions.append(InvStockTransaction.stock_order_id.in_(preview.order_ids))
        await session.exec(delete(InvStockTransaction).where(or_(*transaction_conditions)))
        await session.exec(delete(InvStockBalance).where(InvStockBalance.warehouse_id.in_(preview.warehouse_ids)))
        if preview.order_ids:
            await session.exec(delete(InvStockOrderLine).where(InvStockOrderLine.stock_order_id.in_(preview.order_ids)))
            await session.exec(delete(InvStockOrder).where(InvStockOrder.id.in_(preview.order_ids)))
        now = utc_now()
        await session.exec(
            update(InvWarehouse)
            .where(InvWarehouse.id.in_(preview.warehouse_ids))
            .values(is_active=False, deleted_at=now, deleted_by=user_id, updated_at=now, updated_by=user_id)
        )
        await session.exec(
            update(InvWarehouse)
            .where(InvWarehouse.warehouse_no == GENERAL_WAREHOUSE_NO, InvWarehouse.deleted_at.is_(None))
            .values(warehouse_name="总仓库", is_active=True, updated_at=now, updated_by=user_id)
        )
        await session.exec(
            update(InvWarehouse)
            .where(InvWarehouse.warehouse_no == CANTEEN_WAREHOUSE_NO, InvWarehouse.deleted_at.is_(None))
            .values(warehouse_name="食堂仓库", is_active=True, updated_at=now, updated_by=user_id)
        )
        await session.flush()


repository = InventoryDemoResetRepository()
