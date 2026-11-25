"""Validated request models for the Harness-only query endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from resource_query.models import QueryPlan


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "ilike", "is_null"]
    value: Any = None


class QueryOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Literal["asc", "desc"]


class QueryAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: Literal["count", "sum", "avg", "min", "max"]
    field: str | None = None


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["catalog", "query", "plan"]
    plan: QueryPlan | None = None
    resource: str | None = None
    fields: list[str] | None = Field(default=None, min_length=1, max_length=24)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=20)
    order: list[QueryOrder] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
    include_count: bool = False
    aggregate: QueryAggregate | None = None
    group_by: list[str] = Field(default_factory=list, max_length=3)
    catalog_revision: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_plan_envelope(self):
        if self.operation == "plan":
            if self.plan is None:
                raise ValueError("关联查询需要 plan")
            if self.model_fields_set - {"operation", "plan", "catalog_revision"}:
                raise ValueError("关联查询的字段、筛选和分页参数必须放在 plan 中")
        elif self.plan is not None:
            raise ValueError("plan 只能用于关联查询")
        return self
