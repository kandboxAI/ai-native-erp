"""模型输出的 JSON 容量校验；不再按字段名称或内容进行隐私过滤。"""
from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def safe_scalar(value: Any) -> Any:
    # JSON 不支持 NaN/Infinity；这属于格式校验，不按号码形状改写数据。
    return None if isinstance(value, float) and not math.isfinite(value) else value


class OutputRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_depth: int = Field(default=8, ge=1, le=32)
    max_items: int = Field(default=200, ge=1, le=1000)
    max_fields: int = Field(default=200, ge=1, le=1000)
    max_nodes: int = Field(default=5000, ge=1, le=20000)


def filtered_schema(schema: dict, rules: OutputRules) -> dict:
    """保留业务接口声明的字段和类型，仅沿用集合容量限制。"""
    result = dict(schema)
    if "properties" in schema:
        result["properties"] = {name: filtered_schema(field, rules) for name, field in schema["properties"].items()}
    if "items" in schema:
        result["items"] = filtered_schema(schema["items"], rules)
        result["maxItems"] = min(schema.get("maxItems", rules.max_items), rules.max_items)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            result[key] = [filtered_schema(item, rules) for item in schema[key]]
    return result


def filter_result(value: Any, rules: OutputRules, schema: dict | None = None, depth: int = 0,
                  counts: dict[str, int] | None = None) -> Any:
    """保留已获业务接口授权的 JSON，只校验结果容量和 JSON 数值格式。"""
    counts = counts if counts is not None else {}
    if not isinstance(value, (dict, list)):
        return safe_scalar(value)
    counts["visited_nodes"] = counts.get("visited_nodes", 0) + 1
    if counts["visited_nodes"] > rules.max_nodes:
        raise ValueError("结果结构过大，请缩小查询范围或分页")
    if depth > rules.max_depth:
        raise ValueError("结果嵌套过深，请缩小查询范围")
    if isinstance(value, list):
        if len(value) > rules.max_items:
            raise ValueError("结果集合过大，请缩小查询范围或分页")
        return [filter_result(item, rules, depth=depth + 1, counts=counts) for item in value]
    if isinstance(value, dict):
        if len(value) > rules.max_fields:
            raise ValueError("结果字段数量超过容量限制")
        return {name: filter_result(item, rules, depth=depth + 1, counts=counts)
                for name, item in value.items()}
