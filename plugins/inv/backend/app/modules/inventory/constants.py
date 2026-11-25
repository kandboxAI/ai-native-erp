"""库存模块的字典取值与单据表单约定。

- 方向、库存状态、单据状态取自字典（inv_stock_direction、inv_stock_status、inv_stock_order_status）。
- 单据类型记录保留历史关联；当前业务规则由 stock_order.rules 按稳定类型编号固定。
- 类型的 required_field_config：
    {"form": "inbound", "no_prefix": "RK", "required": ["counterparty_name_snapshot"]}
  form 决定该类型在哪个页面出现、使用哪组权限；required 为保存/提交时必填的单据字段。
"""

from __future__ import annotations

# 历史预置编号仅供幂等初始化和演示重置；不得作为普通业务的仓库白名单。
GENERAL_WAREHOUSE_NO = "HQ-01"
CANTEEN_WAREHOUSE_NO = "CANTEEN"
SYSTEM_WAREHOUSE_NOS = (GENERAL_WAREHOUSE_NO, CANTEEN_WAREHOUSE_NO)
DEFAULT_LOCATION_NO = "DEFAULT"

DIRECTION_IN = "in"
DIRECTION_OUT = "out"
DIRECTION_MOVE = "move"
DIRECTION_STATUS = "status"
DIRECTION_ADJUST = "adjust"
DIRECTIONS = (DIRECTION_IN, DIRECTION_OUT, DIRECTION_MOVE, DIRECTION_STATUS, DIRECTION_ADJUST)

STOCK_AVAILABLE = "available"
STOCK_LENT = "lent"

ORDER_DRAFT = "draft"
ORDER_SUBMITTED = "submitted"
ORDER_APPROVED = "approved"
ORDER_CONFIRMED = "confirmed"
ORDER_VOIDED = "voided"

FORM_INBOUND = "inbound"
FORM_OUTBOUND = "outbound"
FORM_TRANSFER = "transfer"
FORM_LEND = "lend"
FORM_RETURN = "return"
FORM_DAMAGE = "damage"
FORM_ADJUST = "adjust"

# 表单 → 权限资源（权限标识沿用原有页面的 inventory_inbound:* 等）
FORM_PERMISSION_RESOURCE = {
    FORM_INBOUND: "inventory_inbound",
    FORM_OUTBOUND: "inventory_outbound",
    FORM_TRANSFER: "inventory_transfer",
    FORM_LEND: "inventory_lend",
    FORM_RETURN: "inventory_lend",
    FORM_DAMAGE: "inventory_damage",
    FORM_ADJUST: "inventory_stocktake",
}
# 类型没有配置 form 时按方向取默认表单
DIRECTION_DEFAULT_FORM = {
    DIRECTION_IN: FORM_INBOUND,
    DIRECTION_OUT: FORM_OUTBOUND,
    DIRECTION_MOVE: FORM_TRANSFER,
    DIRECTION_STATUS: FORM_LEND,
    DIRECTION_ADJUST: FORM_ADJUST,
}

# 单据上可以被 required 配置要求必填的字段
REQUIRABLE_ORDER_FIELDS = {
    "from_warehouse_id": "来源仓库",
    "to_warehouse_id": "目标仓库",
    "counterparty_party_id": "往来方",
    "counterparty_name_snapshot": "往来方名称",
    "department_id": "领用部门",
    "purpose": "用途",
    "reason": "原因",
    "handling_method_code": "处理方式",
    "expected_return_date": "预计归还日期",
}


def type_form(order_type) -> str:
    from .stock_order.rules import stock_order_rule
    rule = stock_order_rule(order_type)
    if rule is not None:
        return rule.form
    config = getattr(order_type, "required_field_config", None) or {}
    form = config.get("form") if isinstance(config, dict) else None
    return form or DIRECTION_DEFAULT_FORM.get(order_type.direction_code, FORM_INBOUND)


def type_permission_resource(order_type) -> str:
    return FORM_PERMISSION_RESOURCE.get(type_form(order_type), "inventory_inbound")


def type_required_fields(order_type) -> list[str]:
    from .stock_order.rules import stock_order_rule
    rule = stock_order_rule(order_type)
    if rule is not None:
        return list(rule.required)
    config = getattr(order_type, "required_field_config", None) or {}
    required = config.get("required") if isinstance(config, dict) else None
    return [field for field in (required or []) if field in REQUIRABLE_ORDER_FIELDS]


def type_no_prefix(order_type) -> str:
    from .stock_order.rules import stock_order_rule
    rule = stock_order_rule(order_type)
    if rule is not None:
        return rule.no_prefix
    config = getattr(order_type, "required_field_config", None) or {}
    prefix = config.get("no_prefix") if isinstance(config, dict) else None
    return (prefix or "KC").strip().upper()
