"""库存模块内部共用的小工具。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

QTY_QUANTUM = Decimal("0.001")
MONEY_QUANTUM = Decimal("0.01")


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def qty(value: Any) -> Decimal:
    return to_decimal(value).quantize(QTY_QUANTUM)


def money(value: Any) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANTUM)
