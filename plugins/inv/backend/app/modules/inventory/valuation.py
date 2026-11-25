from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


_MONEY_QUANTUM = Decimal("0.01")


def weighted_inventory_value(
    *,
    stock_quantity: Decimal | int | float,
    purchased_quantity: Decimal | int | float,
    purchase_value: Decimal | int | float,
) -> Decimal:
    """按已确认采购入库的加权平均成本计算当前库存价值。"""
    stock_qty = Decimal(str(stock_quantity or 0))
    purchased_qty = Decimal(str(purchased_quantity or 0))
    purchased_value = Decimal(str(purchase_value or 0))
    if stock_qty <= 0 or purchased_qty <= 0 or purchased_value <= 0:
        return Decimal("0.00")
    value = stock_qty * purchased_value / purchased_qty
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
