"""审批条件字段白名单与结构化表达式编译。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.core.exceptions import AppException

from .design_models import (
    ConditionExpression,
    ExclusiveGatewayNode,
    ParallelGatewayNode,
    FlowDesignV2,
    FlowDesignV3,
    FlowNodeV3,
)

FieldType = Literal["number", "string", "boolean"]


@dataclass(frozen=True)
class ConditionField:
    key: str
    label: str
    field_type: FieldType
    sample: str | int | float | bool

    def as_dict(self) -> dict[str, Any]:
        operators = ["eq", "ne"]
        if self.field_type == "number":
            operators = ["eq", "ne", "gt", "gte", "lt", "lte"]
        return {
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "operators": operators,
        }


COMMON_FIELDS: tuple[ConditionField, ...] = ()

BUSINESS_CONDITION_FIELDS: dict[str, tuple[ConditionField, ...]] = {
    "student_leave": (
        ConditionField("applicant_type_code", "申请人类型（student/parent/homeroom）", "string", "parent"),
        ConditionField("leave_days", "请假天数", "number", 1),
    ),
}

OPERATOR_SYMBOLS = {
    "eq": "==",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def condition_fields_for(business_type: str) -> list[ConditionField]:
    return [*COMMON_FIELDS, *BUSINESS_CONDITION_FIELDS.get(business_type, ())]


def condition_field_items(business_type: str) -> list[dict[str, Any]]:
    return [field.as_dict() for field in condition_fields_for(business_type)]


def validation_variables_for(business_type: str) -> dict[str, Any]:
    return {field.key: field.sample for field in condition_fields_for(business_type)}


def _field_map(business_type: str) -> dict[str, ConditionField]:
    return {field.key: field for field in condition_fields_for(business_type)}


def validate_condition_expression(expression: ConditionExpression, business_type: str) -> None:
    field = _field_map(business_type).get(expression.field)
    if field is None:
        raise AppException(
            f"业务类型「{business_type}」不支持条件字段「{expression.field}」",
            status_code=400,
        )
    if field.field_type != "number" and expression.operator not in {"eq", "ne"}:
        raise AppException(f"字段「{field.label}」只支持等于或不等于", status_code=400)
    value = expression.value
    if field.field_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise AppException(f"字段「{field.label}」的条件值必须是数字", status_code=400)
    if field.field_type == "boolean" and not isinstance(value, bool):
        raise AppException(f"字段「{field.label}」的条件值必须是布尔值", status_code=400)
    if field.field_type == "string" and not isinstance(value, str):
        raise AppException(f"字段「{field.label}」的条件值必须是文本", status_code=400)


def _iter_v3_gateways(nodes: list[FlowNodeV3]):
    for node in nodes:
        if isinstance(node, ExclusiveGatewayNode):
            yield node
        if isinstance(node, (ExclusiveGatewayNode, ParallelGatewayNode)):
            for branch in node.branches:
                yield from _iter_v3_gateways(branch.nodes)


def validate_design_conditions(
    design: FlowDesignV2 | FlowDesignV3, business_type: str
) -> None:
    if isinstance(design, FlowDesignV3):
        gateways = list(_iter_v3_gateways(design.nodes))
        if not gateways:
            return
        if not condition_fields_for(business_type):
            raise AppException(
                f"业务类型「{business_type}」没有可用于审批分支的字段",
                status_code=400,
            )
        for gateway in gateways:
            for branch in gateway.branches:
                if branch.condition is not None:
                    validate_condition_expression(branch.condition, business_type)
        return

    if design.mode != "conditional" or design.gateway is None:
        return
    if not condition_fields_for(business_type):
        raise AppException(
            f"业务类型「{business_type}」没有可用于审批分支的字段",
            status_code=400,
        )
    for branch in design.gateway.branches:
        if branch.condition is not None:
            validate_condition_expression(branch.condition, business_type)


def compile_condition_expression(expression: ConditionExpression) -> str:
    """仅从受控字段、运算符和值生成表达式，禁止保存任意可执行文本。"""
    symbol = OPERATOR_SYMBOLS[expression.operator]
    value = expression.value
    if isinstance(value, bool):
        literal = "True" if value else "False"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        literal = str(value)
    else:
        literal = json.dumps(value, ensure_ascii=False)
    return f"{expression.field} {symbol} {literal}"
