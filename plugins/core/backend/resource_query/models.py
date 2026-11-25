from typing import Any, Literal, Annotated

import json
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Alias = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")]
FieldRef = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}\.[A-Za-z_][A-Za-z0-9_]{0,63}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanRoot(StrictModel):
    resource: str = Field(min_length=1, max_length=160)
    alias: Alias = "root"


class PlanJoin(StrictModel):
    from_alias: Alias
    relation_id: str = Field(min_length=1, max_length=100)
    alias: Alias
    kind: Literal["inner", "left"] = "inner"


class PlanSelect(StrictModel):
    field: FieldRef
    as_: Alias = Field(alias="as")


class PlanFilter(StrictModel):
    field: FieldRef
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "ilike", "is_null"]
    value: Any = None

    @field_validator("value")
    @classmethod
    def bounded_values(cls, value):
        items = value if isinstance(value, list) else [value]
        if len(items) > 100:
            raise ValueError("筛选值过多")
        for item in items:
            if item is not None and not isinstance(item, (str, int, float, bool)):
                raise ValueError("筛选只接受标量值")
            if isinstance(item, str) and len(item) > 1024:
                raise ValueError("筛选文本过长")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("筛选数值必须有限")
        return value


class PlanAggregate(StrictModel):
    function: Literal["count", "sum", "avg", "min", "max"]
    field: FieldRef | None = None
    as_: Alias = Field(alias="as")


class PlanOrder(StrictModel):
    field: Alias
    direction: Literal["asc", "desc"] = "asc"


class QueryPlan(StrictModel):
    version: Literal[1] = 1
    root: PlanRoot
    # The host supplies the execution limit; the complete plan has a byte bound.
    joins: list[PlanJoin] = Field(default_factory=list)
    select: list[PlanSelect] = Field(default_factory=list, max_length=24)
    filters: list[PlanFilter] = Field(default_factory=list, max_length=20)
    group_by: list[FieldRef] = Field(default_factory=list, max_length=3)
    aggregates: list[PlanAggregate] = Field(default_factory=list, max_length=6)
    order: list[PlanOrder] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
    include_count: bool = False

    @model_validator(mode="after")
    def bounded_plan(self):
        if len(json.dumps(self.model_dump(mode="json", by_alias=True), ensure_ascii=False).encode("utf-8")) > 65536:
            raise ValueError("查询计划超过 64 KiB，请减少筛选值")
        return self
