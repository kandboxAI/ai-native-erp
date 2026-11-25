from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from app.framework.db.ids import uuid7

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .process_catalog import ProcessType

Positive = Annotated[Decimal, Field(gt=0, le=Decimal("100000000"), allow_inf_nan=False)]
NonNegative = Annotated[Decimal, Field(ge=0, le=Decimal("100000000"), allow_inf_nan=False)]


class Specs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str = Field(default="", max_length=200)
    treatment: str = Field(default="", max_length=500)
    hardness: str = Field(default="", max_length=200)
    tolerance: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=10000)
    stock_length: Positive | None = None
    stock_width: Positive | None = None
    stock_height: Positive | None = None
    density: Positive | None = None
    material_price: Positive | None = None
    material_rule_no: str | None = Field(default=None, max_length=60)
    material_price_unit_code: Literal["kg", "mm"] = "kg"
    material_billing_length: Positive | None = None
    external_unit_cost: NonNegative = Decimal("0")
    other_batch_cost: NonNegative = Decimal("0")
    is_requirements_confirmed: bool = False
    parameter_sources: dict[str, dict] = Field(default_factory=dict)


class MaterialDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["selected", "unmatched", "uncertain"]
    rule_no: str | None = Field(default=None, max_length=60)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def check_selection(self):
        if (self.status == "selected") != bool(self.rule_no):
            raise ValueError("只有确定选材时才能返回材料规则编号")
        return self


class MaterialSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_no: int = Field(ge=1)
    cloud_allowed: bool = False


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid7()), min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    process_id: UUID | None = None
    process_no_snapshot: str | None = Field(default=None, max_length=64)
    machine: str = Field(default="", max_length=120)
    process_type_code: ProcessType | None = None
    quote_rule_no: str | None = Field(default=None, min_length=1, max_length=60)
    pricing_mode_code: Literal["hourly", "external"] = "hourly"
    external_rate: NonNegative | None = None
    external_minimum_unit: NonNegative = Decimal("0")
    external_weight_basis_code: Literal["stock", "net"] = "stock"
    external_price_unit_code: Literal["kg", "m2"] = "kg"
    external_area_mm2: Positive | None = None
    unit_hours: NonNegative | None = None
    hourly_rate: Positive | None = None
    note: str = Field(default="", max_length=1000)
    estimate_basis: str = Field(default="", max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    estimate_quantity: int | None = Field(default=None, ge=1, le=1000000)
    origin_code: Literal["manual", "ai"] = "manual"
    source_job_id: str | None = Field(default=None, max_length=36)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    parameter_sources: dict[str, dict] = Field(default_factory=dict)


class PartEdit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1000000)
    version_no: int = Field(ge=1)
    specs: Specs
    operations: list[Operation] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_operation_ids(self):
        if len({row.id for row in self.operations}) != len(self.operations):
            raise ValueError("工序标识不能重复")
        return self


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto", "local"] = "auto"
    cloud_allowed: bool = False


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdoptDraft(BaseModel):
    version_no: int = Field(ge=1)


class AIFact(BaseModel):
    key: Literal["material", "treatment", "hardness", "tolerance", "drawing_number", "requirement"]
    value: str = Field(min_length=1, max_length=2000)
    page: int = Field(ge=1, le=20)
    bbox: tuple[float, float, float, float]
    evidence_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def valid_region(self):
        x0, y0, x1, y1 = self.bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("证据框必须是页面左上角为原点的 0..1 坐标")
        return self


class AIOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    machine: str = Field(default="", max_length=120)
    process_type_code: ProcessType | None = None
    pricing_mode_code: Literal["hourly", "external"] = "hourly"
    unit_hours: NonNegative | None = None
    estimate_basis: str = Field(default="", max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def explained_estimate(self):
        if self.unit_hours is not None and not self.estimate_basis.strip():
            raise ValueError("工时估算必须说明依据和采用的条件")
        return self


class AIProcessDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_no: str = Field(min_length=1, max_length=60)
    used: bool
    process_no: str | None = Field(default=None, max_length=64)
    unit_hours: NonNegative | None = None
    reason: str = Field(min_length=1, max_length=2000)
    work_content: str = Field(default="", max_length=1000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)


class AIProcessPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessments: list[AIProcessDecision] = Field(max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=30)
    uncovered_requirements: list[str] = Field(default_factory=list, max_length=30)


class AIExtraction(BaseModel):
    facts: list[AIFact] = Field(default_factory=list, max_length=80)
    operations: list[AIOperation] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=30)
