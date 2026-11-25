"""统一记账服务：库存单据确认时调用，是改变库存余额、写入库存流水的唯一入口。

规则（MES 领域数据模型 §6、§7.6）：
- 根据代码维护的固定业务规则记账，不读取租户的可编辑处理配置：
    in      入库：目标仓库 + 目标状态 增加
    out     出库：来源仓库 + 来源状态 减少
    move    调拨：来源减少、目标增加（同一条流水同时填写来源与目标仓库）
    status  状态转换（借出、归还）：同一仓库，来源状态减少、目标状态增加
    adjust  调整（盘点）：按“实盘数 − 账面数”生成增或减的流水
- 每条流水：from_warehouse_id 有值则来源余额减少，to_warehouse_id 有值则目标余额增加；余额可由流水重算。
- 一个事务内：按物料加咨询锁（排序后加锁），锁定余额行，按版本号更新余额，写流水；余额不足时报错，禁止负库存。
- 未指定批次的扣减按“无批次 → 有效期早 → 入库早”的顺序在批次间分配，一行明细可以生成多条流水。
- 归还行（source_line_id 引用借出行）按借出时各批次的数量减去已归还数量分配。
- 冲销单（reversal_of_order_id）逐条反向原单据的流水。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import AppException
from app.framework.db.models import utc_now

from ..common import qty
from ..constants import (
    DIRECTION_ADJUST,
    DIRECTION_IN,
    DIRECTION_MOVE,
    DIRECTION_OUT,
    DIRECTION_STATUS,
    STOCK_AVAILABLE,
)
from ..models import InvStockOrder, InvStockOrderLine, InvStockOrderType, InvStockTransaction, InvWarehouse, MdItem
from ..warning.service import alert_transitions
from ..warning.repository import repository as warning_repository
from .repository import repository
from .rules import fixed_order_type, validate_stock_statuses


@dataclass
class Leg:
    line: InvStockOrderLine
    item_id: UUID
    lot_id: UUID | None
    quantity: Decimal
    transaction_type_code: str
    from_warehouse_id: UUID | None = None
    from_status: str | None = None
    to_warehouse_id: UUID | None = None
    to_status: str | None = None


def _insufficient(item: MdItem | None, warehouse: InvWarehouse | None, status_code: str, available: Decimal, needed: Decimal) -> AppException:
    item_label = f"{item.item_name}（{item.item_no}）" if item else "物料"
    warehouse_label = warehouse.warehouse_name if warehouse else "仓库"
    return AppException(
        f"库存不足：{item_label} 在 {warehouse_label}（{status_code}）可用 {available.normalize():f}，需要 {needed.normalize():f}",
        status_code=status.HTTP_409_CONFLICT,
    )


class Poster:
    def __init__(self, session: AsyncSession, order: InvStockOrder, order_type: InvStockOrderType, user_id: UUID | None) -> None:
        self.session = session
        self.order = order
        self.order_type = fixed_order_type(order_type, require_supported=order.reversal_of_order_id is None)
        self.user_id = user_id
        self.items: dict[UUID, MdItem] = {}
        self.warehouses: dict[UUID, InvWarehouse] = {}

    # ───────── 解析明细 ─────────
    def _from_status(self, line: InvStockOrderLine) -> str:
        return line.from_stock_status_code or self.order_type.default_from_status_code or STOCK_AVAILABLE

    def _to_status(self, line: InvStockOrderLine) -> str:
        return line.to_stock_status_code or self.order_type.default_to_status_code or STOCK_AVAILABLE

    def _warehouse(self, warehouse_id: UUID | None, label: str, line: InvStockOrderLine) -> UUID:
        if warehouse_id is None or warehouse_id not in self.warehouses:
            raise AppException(f"第 {line.line_no} 行缺少有效的{label}", status_code=status.HTTP_400_BAD_REQUEST)
        return warehouse_id

    async def _allocate(
        self,
        line: InvStockOrderLine,
        *,
        warehouse_id: UUID,
        status_code: str,
        quantity: Decimal,
        lot_id: UUID | None,
        lot_quotas: dict[UUID | None, Decimal] | None = None,
    ) -> list[tuple[UUID | None, Decimal]]:
        """从 (仓库, 状态) 的余额中分配数量，返回 [(批次, 数量)]。"""
        tracked = getattr(self, "tracking_quotas", {}).get(line.id)
        if tracked is not None:
            lot_quotas = tracked if lot_quotas is None else {
                lot: min(amount, lot_quotas.get(lot, Decimal("0"))) for lot, amount in tracked.items()
            }
        rows = await repository.lock_balances(
            self.session,
            item_id=line.item_id,
            warehouse_id=warehouse_id,
            stock_status_code=status_code,
            lot_id=lot_id,
            any_lot=lot_id is None,
        )
        remaining = quantity
        allocations: list[tuple[UUID | None, Decimal]] = []
        total_available = Decimal("0")
        for balance, _lot in rows:
            available = Decimal(balance.quantity) - Decimal(balance.reserved_quantity)
            if lot_quotas is not None:
                available = min(available, lot_quotas.get(balance.lot_id, Decimal("0")))
            if available <= 0:
                continue
            total_available += available
            if remaining <= 0:
                continue
            take = min(available, remaining)
            allocations.append((balance.lot_id, take))
            remaining -= take
        if remaining > 0:
            raise _insufficient(self.items.get(line.item_id), self.warehouses.get(warehouse_id), status_code, total_available, quantity)
        return allocations

    async def _legs_for_line(self, line: InvStockOrderLine) -> list[Leg]:
        validate_stock_statuses(self.order_type, [line])
        direction = self.order_type.direction_code
        quantity = qty(line.quantity)
        if direction != DIRECTION_ADJUST and quantity <= 0:
            raise AppException(f"第 {line.line_no} 行数量必须大于 0", status_code=status.HTTP_400_BAD_REQUEST)
        from_warehouse = line.from_warehouse_id or self.order.from_warehouse_id
        to_warehouse = line.to_warehouse_id or self.order.to_warehouse_id

        if direction == DIRECTION_IN:
            to_id = self._warehouse(to_warehouse, "目标仓库", line)
            return [Leg(line, line.item_id, line.lot_id, quantity, DIRECTION_IN, to_warehouse_id=to_id, to_status=self._to_status(line))]

        if direction == DIRECTION_OUT:
            from_id = self._warehouse(from_warehouse, "来源仓库", line)
            from_status = self._from_status(line)
            allocations = await self._allocate(line, warehouse_id=from_id, status_code=from_status, quantity=quantity, lot_id=line.lot_id)
            return [
                Leg(line, line.item_id, lot_id, part, DIRECTION_OUT, from_warehouse_id=from_id, from_status=from_status)
                for lot_id, part in allocations
            ]

        if direction == DIRECTION_MOVE:
            from_id = self._warehouse(from_warehouse, "来源仓库", line)
            to_id = self._warehouse(to_warehouse, "目标仓库", line)
            if from_id == to_id:
                raise AppException(f"第 {line.line_no} 行来源与目标仓库相同", status_code=status.HTTP_400_BAD_REQUEST)
            from_status = self._from_status(line)
            to_status = line.to_stock_status_code or self.order_type.default_to_status_code or from_status
            allocations = await self._allocate(line, warehouse_id=from_id, status_code=from_status, quantity=quantity, lot_id=line.lot_id)
            return [
                Leg(line, line.item_id, lot_id, part, DIRECTION_MOVE, from_id, from_status, to_id, to_status)
                for lot_id, part in allocations
            ]

        if direction == DIRECTION_STATUS:
            warehouse_id = self._warehouse(from_warehouse or to_warehouse, "仓库", line)
            from_status, to_status = self._from_status(line), self._to_status(line)
            if from_status == to_status:
                raise AppException("状态转换单据的来源与目标库存状态不能相同", status_code=status.HTTP_400_BAD_REQUEST)
            quotas = await self._return_quotas(line) if line.source_line_id is not None else None
            allocations = await self._allocate(
                line, warehouse_id=warehouse_id, status_code=from_status, quantity=quantity, lot_id=line.lot_id, lot_quotas=quotas
            )
            return [
                Leg(line, line.item_id, lot_id, part, DIRECTION_STATUS, warehouse_id, from_status, warehouse_id, to_status)
                for lot_id, part in allocations
            ]

        if direction == DIRECTION_ADJUST:
            warehouse_id = self._warehouse(to_warehouse or from_warehouse, "仓库", line)
            status_code = line.to_stock_status_code or self.order_type.default_to_status_code or STOCK_AVAILABLE
            if line.counted_quantity is None:
                raise AppException(f"第 {line.line_no} 行缺少实盘数量", status_code=status.HTTP_400_BAD_REQUEST)
            await repository.lock_balances(
                self.session, item_id=line.item_id, warehouse_id=warehouse_id, stock_status_code=status_code, lot_id=line.lot_id
            )
            book = await repository.book_quantity(
                self.session, item_id=line.item_id, warehouse_id=warehouse_id, lot_id=line.lot_id, stock_status_code=status_code
            )
            diff = qty(line.counted_quantity) - book
            line.quantity = abs(diff)
            if diff > 0:
                return [Leg(line, line.item_id, line.lot_id, diff, DIRECTION_ADJUST, to_warehouse_id=warehouse_id, to_status=status_code)]
            if diff < 0:
                return [Leg(line, line.item_id, line.lot_id, -diff, DIRECTION_ADJUST, from_warehouse_id=warehouse_id, from_status=status_code)]
            return []

        raise AppException(f"不支持的单据方向：{direction}", status_code=status.HTTP_400_BAD_REQUEST)

    async def _return_quotas(self, line: InvStockOrderLine) -> dict[UUID | None, Decimal]:
        """归还行：借出行各批次已转为来源状态的数量，减去已确认归还的数量。"""
        source = (await repository.get_lines_by_ids(self.session, {line.source_line_id})).get(line.source_line_id)
        if source is None or source.item_id != line.item_id:
            raise AppException(f"第 {line.line_no} 行引用的借出明细无效", status_code=status.HTTP_400_BAD_REQUEST)
        source_order = await repository.get_order(self.session, source.stock_order_id)
        if source_order is None or source_order.status_code != "confirmed":
            raise AppException(f"第 {line.line_no} 行引用的借出单未确认", status_code=status.HTTP_400_BAD_REQUEST)
        from_status = self._from_status(line)
        quotas: dict[UUID | None, Decimal] = {}
        for transaction in await repository.line_transactions(self.session, {source.id}):
            if transaction.to_stock_status_code == from_status:
                quotas[transaction.lot_id] = quotas.get(transaction.lot_id, Decimal("0")) + Decimal(transaction.quantity)
        for lot_id, returned in (await repository.returned_by_lot(self.session, source.id)).items():
            quotas[lot_id] = quotas.get(lot_id, Decimal("0")) - returned
        remaining = sum((value for value in quotas.values() if value > 0), Decimal("0"))
        if qty(line.quantity) > remaining:
            raise AppException(
                f"第 {line.line_no} 行归还数量 {qty(line.quantity).normalize():f} 超过未归还数量 {remaining.normalize():f}",
                status_code=status.HTTP_409_CONFLICT,
            )
        return quotas

    async def _reversal_legs(self, lines: list[InvStockOrderLine]) -> list[Leg]:
        line_by_source = {line.source_line_id: line for line in lines}
        legs: list[Leg] = []
        for transaction in await repository.order_transactions(self.session, self.order.reversal_of_order_id):
            line = line_by_source.get(transaction.stock_order_line_id)
            if line is None:
                continue
            legs.append(
                Leg(
                    line,
                    transaction.item_id,
                    transaction.lot_id,
                    Decimal(transaction.quantity),
                    transaction.transaction_type_code,
                    from_warehouse_id=transaction.to_warehouse_id,
                    from_status=transaction.to_stock_status_code,
                    to_warehouse_id=transaction.from_warehouse_id,
                    to_status=transaction.from_stock_status_code,
                )
            )
        # 冲销的扣减一侧同样不能出现负库存
        for leg in legs:
            if leg.from_warehouse_id is None:
                continue
            rows = await repository.lock_balances(
                self.session,
                item_id=leg.item_id,
                warehouse_id=leg.from_warehouse_id,
                stock_status_code=leg.from_status or STOCK_AVAILABLE,
                lot_id=leg.lot_id,
            )
            available = sum((Decimal(row.quantity) - Decimal(row.reserved_quantity) for row, _ in rows), Decimal("0"))
            if available < leg.quantity:
                raise _insufficient(self.items.get(leg.item_id), self.warehouses.get(leg.from_warehouse_id), leg.from_status or "", available, leg.quantity)
        return legs

    # ───────── 记账 ─────────
    async def _apply(self, leg: Leg, seq: int, occurred_at: datetime) -> InvStockTransaction:
        if leg.from_warehouse_id is not None:
            warehouse = self.warehouses[leg.from_warehouse_id]
            balance = await repository.ensure_balance(
                self.session,
                org_id=warehouse.org_id,
                item_id=leg.item_id,
                warehouse_id=leg.from_warehouse_id,
                lot_id=leg.lot_id,
                stock_status_code=leg.from_status or STOCK_AVAILABLE,
                user_id=self.user_id,
            )
            after = await repository.change_balance(self.session, balance, -leg.quantity, self.user_id)
            reserved = Decimal(balance.reserved_quantity)
            if after < reserved:
                raise _insufficient(self.items.get(leg.item_id), warehouse, leg.from_status or "", after + leg.quantity - reserved, leg.quantity)
        if leg.to_warehouse_id is not None:
            warehouse = self.warehouses[leg.to_warehouse_id]
            balance = await repository.ensure_balance(
                self.session,
                org_id=warehouse.org_id,
                item_id=leg.item_id,
                warehouse_id=leg.to_warehouse_id,
                lot_id=leg.lot_id,
                stock_status_code=leg.to_status or STOCK_AVAILABLE,
                user_id=self.user_id,
            )
            await repository.change_balance(self.session, balance, leg.quantity, self.user_id)
        org_warehouse = self.warehouses[leg.from_warehouse_id or leg.to_warehouse_id]
        return InvStockTransaction(
            org_id=org_warehouse.org_id,
            transaction_no=f"{self.order.order_no}-{seq:03d}",
            transaction_type_code=leg.transaction_type_code,
            item_id=leg.item_id,
            from_warehouse_id=leg.from_warehouse_id,
            to_warehouse_id=leg.to_warehouse_id,
            lot_id=leg.lot_id,
            from_stock_status_code=leg.from_status if leg.from_warehouse_id else None,
            to_stock_status_code=leg.to_status if leg.to_warehouse_id else None,
            quantity=leg.quantity,
            stock_order_id=self.order.id,
            stock_order_line_id=leg.line.id,
            occurred_at=occurred_at,
            created_by=self.user_id,
        )

    async def post(self, lines: list[InvStockOrderLine]) -> dict[str, Any]:
        if not lines:
            raise AppException("单据没有明细", status_code=status.HTTP_400_BAD_REQUEST)
        await repository.lock_items(self.session, [line.item_id for line in lines])
        self.items = await repository.items(self.session, {line.item_id for line in lines})
        warehouse_ids: set[UUID | None] = {self.order.from_warehouse_id, self.order.to_warehouse_id}
        for line in lines:
            warehouse_ids.update({line.from_warehouse_id, line.to_warehouse_id})
        if self.order.reversal_of_order_id is not None:
            for transaction in await repository.order_transactions(self.session, self.order.reversal_of_order_id):
                warehouse_ids.update({transaction.from_warehouse_id, transaction.to_warehouse_id})
        self.warehouses = await repository.get_warehouses(self.session, warehouse_ids)
        if set(self.warehouses) != {value for value in warehouse_ids if value is not None}:
            raise AppException("单据包含已删除、停用或不存在的仓库", status_code=status.HTTP_409_CONFLICT)
        await repository.validate_balance_organizations(
            self.session,
            item_ids={line.item_id for line in lines},
            warehouse_ids=set(self.warehouses),
        )
        from .tracking import prepare_tracking
        self.tracking_quotas = await prepare_tracking(
            self.session, self.order, lines, getattr(self, "current_user", None),
            order_type=self.order_type, items=self.items, warehouses=self.warehouses,
        )

        affected = {
            (line.item_id, warehouse.org_id, warehouse.id)
            for line in lines
            for warehouse in self.warehouses.values()
        }
        before = await repository.available_by_item_warehouse(self.session, affected)
        thresholds = await warning_repository.thresholds_for_keys(self.session, affected)

        occurred_at = utc_now()
        transactions: list[InvStockTransaction] = []
        if self.order.reversal_of_order_id is not None:
            for leg in await self._reversal_legs(lines):
                transactions.append(await self._apply(leg, len(transactions) + 1, occurred_at))
        else:
            # 逐行分配并立即记账：同一单据中多行扣减同一余额时，后面的行看到的是已扣减后的数量
            for line in lines:
                for leg in await self._legs_for_line(line):
                    transactions.append(await self._apply(leg, len(transactions) + 1, occurred_at))
        await repository.add_transactions(self.session, transactions)
        # 所有过账入口（含领用和行业公开调用）在同一事务执行追踪，失败一并回滚。
        from .tracking import post_tracking
        await post_tracking(self.session, self.order, self.order_type, lines, self.items,
                            self.warehouses, transactions, getattr(self, "current_user", None))

        after = await repository.available_by_item_warehouse(self.session, affected)
        alerts = alert_transitions(self.items, thresholds, before, after)
        return {"transaction_count": len(transactions), "alerts": alerts}


async def post_order(
    session: AsyncSession,
    order: InvStockOrder,
    order_type: InvStockOrderType,
    lines: list[InvStockOrderLine],
    user_id: UUID | None,
    *, current_user=None,
) -> dict[str, Any]:
    """确认（记账）。调用方须已锁定单据行（select ... for update）并在同一事务中提交。"""
    poster = Poster(session, order, order_type, user_id)
    poster.current_user = current_user
    return await poster.post(lines)
