from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, le=100000000, max_digits=18, decimal_places=2, allow_inf_nan=False)]
Quantity = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=18, decimal_places=3, allow_inf_nan=False)]
Weight = Annotated[Decimal, Field(ge=0, le=1000000, decimal_places=6, allow_inf_nan=False)]
ExchangeRate = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=18, decimal_places=8, allow_inf_nan=False)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QuotationFileBody(StrictBody):
    attachment_id: UUID
    kind: Literal["pdf", "model"]


class QuotationLineBody(StrictBody):
    id: UUID | None = None
    drawing_no: str = Field(min_length=1, max_length=64)
    drawing_revision: str = Field(default="A", max_length=32)
    description: str = Field(default="", max_length=128)
    quantity: Quantity
    unit_name: str = Field(default="件", min_length=1, max_length=16)
    customer_material: str = Field(default="", max_length=128)
    surface_treatment: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=1000)
    files: list[QuotationFileBody] = Field(default_factory=list, max_length=2)
    quantity_tiers: list[Quantity] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def unique_files(self):
        if len(set([self.quantity, *self.quantity_tiers])) != len(self.quantity_tiers) + 1:
            raise ValueError("数量档不能重复，最多五档（含主数量）")
        if len({row.kind for row in self.files}) != len(self.files):
            raise ValueError("每项货品最多一份 PDF 和一份模型")
        return self


class QuotationBody(StrictBody):
    org_id: UUID | None = None
    version_no: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=128)
    customer_id: UUID
    currency: Literal["CNY", "EUR", "USD"] = "EUR"
    deadline: date | None = None
    note: str = Field(default="", max_length=1000)
    lines: list[QuotationLineBody] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_lines(self):
        keys = [(row.drawing_no.casefold(), row.drawing_revision.casefold()) for row in self.lines]
        ids = [row.id for row in self.lines if row.id]
        if len(set(keys)) != len(keys) or len(set(ids)) != len(ids):
            raise ValueError("图号版本或明细标识重复")
        return self


class EngineeringTier(StrictBody):
    id: UUID
    unit_price: Money | None = None
    calculation_note: str = Field(default="", max_length=1000)


class EngineeringLine(StrictBody):
    id: UUID
    quoted_material: str = Field(default="", max_length=128)
    weight_kg: Weight | None = None
    unit_price: Money | None = None
    engineering_note: str = Field(default="", max_length=1000)
    quantity_tiers: list[EngineeringTier] = Field(default_factory=list, max_length=4)


class EngineeringBody(StrictBody):
    version_no: int = Field(ge=1)
    lines: list[EngineeringLine] = Field(min_length=1, max_length=500)


class QuotationCommand(StrictBody):
    version_no: int = Field(ge=1)
    note: str = Field(default="", max_length=1000)


class QuotationApprovalTier(StrictBody):
    id: UUID
    unit_price: Money


class QuotationDeliveryLine(StrictBody):
    id: UUID
    lead_days: int = Field(ge=1, le=3650)
    unit_price: Money | None = None
    quantity_tiers: list[QuotationApprovalTier] | None = Field(default=None, max_length=4)


class QuotationApprovalBody(QuotationCommand):
    lines: list[QuotationDeliveryLine] = Field(min_length=1, max_length=500)
    price_adjustment_reason: str = Field(default="", max_length=1000)


class QuotationCncBody(QuotationCommand):
    cloud_allowed: bool = False
    is_retry: bool = False


class QuotationAdoptBody(QuotationCommand):
    cnc_quote_id: UUID
    exchange_rate: ExchangeRate | None = None
    exchange_rate_reference: str | None = Field(default=None, max_length=2048)
    is_confirmed: bool = False


class QuotationAdoptionPreview(QuotationCommand):
    line_ids: list[UUID] = Field(min_length=1, max_length=500)
    exchange_rate: ExchangeRate | None = None

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.line_ids)) != len(self.line_ids):
            raise ValueError("请选择不重复的货品")
        return self


class QuotationAdoptionItem(StrictBody):
    line_id: UUID
    cnc_quote_id: UUID


class QuotationBatchAdopt(QuotationCommand):
    lines: list[QuotationAdoptionItem] = Field(min_length=1, max_length=500)
    is_confirmed: bool = False
    exchange_rate: ExchangeRate | None = None
    exchange_rate_reference: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({row.line_id for row in self.lines}) != len(self.lines):
            raise ValueError("请选择不重复的货品")
        return self
