"""代码维护的库存业务规则；租户类型记录仅保留标识及历史关联。"""
from dataclasses import dataclass

from app.core.exceptions import AppException


@dataclass(frozen=True)
class StockOrderRule:
    type_no: str
    name: str
    direction: str
    from_status: str | None
    to_status: str | None
    approval: bool
    form: str
    no_prefix: str
    required: tuple[str, ...] = ()
    sort_no: int = 0
    source_managed: bool = False
    warehouse_scope_key: str | None = None
    warehouse_type_codes: tuple[str, ...] = ()


_rules: dict[str, StockOrderRule] = {}


def register_stock_order_rule(rule: StockOrderRule) -> None:
    """业务模块在加载时登记固定规则，不接受来自租户配置或 HTTP 的规则。"""
    previous = _rules.get(rule.type_no)
    if previous is not None and previous != rule:
        raise ValueError(f"重复的库存业务规则：{rule.type_no}")
    _rules[rule.type_no] = rule


def stock_order_rule(order_type) -> StockOrderRule | None:
    return _rules.get(getattr(order_type, "type_no", ""))


def fixed_order_type(order_type, *, require_supported: bool = False):
    """返回脱离会话的有效规则副本，不覆盖历史记录。"""
    rule = stock_order_rule(order_type)
    if rule is None:
        if require_supported:
            raise AppException("该历史单据类型已停止办理新业务，请使用系统内置业务类型", status_code=409)
        return order_type
    from ..models import InvStockOrderType

    values = order_type.model_dump()
    values.update(
        direction_code=rule.direction,
        default_from_status_code=rule.from_status,
        default_to_status_code=rule.to_status,
        is_approval_required=rule.approval,
        wf_definition_id=None,
        required_field_config={"form": rule.form, "no_prefix": rule.no_prefix, "required": list(rule.required),
            **({"source_managed": True} if rule.source_managed else {}),
            **({"warehouse_scope_key": rule.warehouse_scope_key, "warehouse_type_codes": list(rule.warehouse_type_codes)} if rule.warehouse_scope_key else {})},
        is_negative_allowed=False,
        is_active=True,
        sort_no=rule.sort_no,
    )
    return InvStockOrderType.model_validate(values)


def validate_stock_statuses(order_type, lines) -> None:
    rule = stock_order_rule(order_type)
    if rule is None:
        return
    for line in lines:
        for field, expected in (("from_stock_status_code", rule.from_status), ("to_stock_status_code", rule.to_status)):
            value = getattr(line, field, None)
            if value is not None and value != expected:
                raise AppException("单据库存状态与该业务的固定处理方式不一致，请重新填写单据", status_code=409)


BUILTIN_RULES = (
    StockOrderRule("PURCHASE_IN", "采购入库", "in", None, "available", False, "inbound", "RK", sort_no=10),
    StockOrderRule("OTHER_IN", "其他入库", "in", None, "available", False, "inbound", "RK", ("reason",), 20),
    StockOrderRule("REQUISITION_OUT", "领用出库", "out", "available", None, False, "outbound", "CK", ("department_id", "counterparty_name_snapshot"), 30),
    StockOrderRule("OTHER_OUT", "其他出库", "out", "available", None, False, "outbound", "CK", ("reason",), 40),
    StockOrderRule("TRANSFER", "调拨", "move", "available", "available", True, "transfer", "DB", sort_no=50),
    StockOrderRule("LEND", "借出", "status", "available", "lent", False, "lend", "JC", ("counterparty_name_snapshot", "expected_return_date"), 60),
    StockOrderRule("RETURN", "归还", "status", "lent", "available", False, "return", "GH", sort_no=70),
    StockOrderRule("DAMAGE", "报损", "out", "available", None, True, "damage", "BS", ("reason", "handling_method_code"), 80),
    StockOrderRule("STOCKTAKE", "盘点调整", "adjust", "available", "available", False, "adjust", "PD", sort_no=90),
)
for _rule in BUILTIN_RULES:
    register_stock_order_rule(_rule)
