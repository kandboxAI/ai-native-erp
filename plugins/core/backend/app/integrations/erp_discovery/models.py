from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.harness_query_schemas import QueryFilter


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Relation(StrictModel):
    target: str
    field: str
    target_field: str = "id"
    cardinality: Literal["many_to_one", "one_to_one", "one_to_many"]


class ResourceSemantics(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=512)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    domain: str = Field(default="system", max_length=80)
    grain: str = Field(default="", max_length=512)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list, max_length=12)


class MetricSemantics(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=512)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    resource: str
    function: Literal["count", "sum", "avg", "min", "max"]
    field: str | None = None
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=10)
    unit: str = Field(max_length=30)


class Semantics(StrictModel):
    version: Literal[1]
    resources: dict[str, ResourceSemantics]
    metrics: dict[str, MetricSemantics] = Field(default_factory=dict)
