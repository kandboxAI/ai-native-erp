"""出货单据的人工补录参数与版本化渲染契约。"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


DocumentKind = Literal["packing_list", "customs_draft", "invoice_request", "commercial_invoice", "domestic_invoice", "domestic_contract"]
Measure = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
NetWeight = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=6)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=3)]
Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class PackedLine(DocumentInput):
    shipment_line_id: UUID
    quantity: Quantity
    net_weight_kg: NetWeight


class PackingBox(DocumentInput):
    box_no: str = Field(min_length=1, max_length=40)
    gross_weight_kg: Measure
    length_cm: Measure
    width_cm: Measure
    height_cm: Measure
    lines: list[PackedLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_box(self):
        if len({line.shipment_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("同一箱内相同出货货品请合并数量")
        if sum(line.net_weight_kg for line in self.lines) > self.gross_weight_kg:
            raise ValueError("箱内净重合计不能超过毛重")
        return self


MaterialFamily = Literal["aluminum", "steel", "engineering_plastic"]
MaterialSelection = Literal["aluminum", "steel", "engineering_plastic", "individual"]


class DeclarationFields(DocumentInput):
    declared_name: str = Field(default="", max_length=160)
    hs_code: str | None = Field(default=None, pattern=r"^[0-9]{6,10}$")
    origin_country: Country | None = None
    declaration_elements: str = Field(default="", max_length=1500)
    customer_tariff_no: str | None = Field(default=None, pattern=r"^[0-9]{6,12}$")


class CustomsLine(DeclarationFields):
    shipment_line_id: UUID
    material_group: MaterialSelection | None = None
    material_name: str = Field(default="", max_length=256)


class CustomsProfile(DeclarationFields):
    material_group: MaterialFamily


class ExportDetails(DocumentInput):
    invoice_no: str = Field(default="", max_length=80)
    contract_no: str = Field(default="", max_length=80)
    contract_date: date | None = None
    seller_name_en: str = Field(default="", max_length=180)
    seller_address_en: str = Field(default="", max_length=400)
    seller_contact: str = Field(default="", max_length=80)
    seller_phone: str = Field(default="", max_length=64)
    buyer_contact: str = Field(default="", max_length=80)
    buyer_phone: str = Field(default="", max_length=64)
    buyer_eori_vat: str = Field(default="", max_length=64)
    payment_terms: str = Field(default="", max_length=180)
    payment_instructions: str = Field(default="", max_length=1200)
    marks: str = Field(default="", max_length=400)
    package_type: str = Field(default="", max_length=64)
    shipping_method: str = Field(default="", max_length=64)
    transport_vehicle: str = Field(default="", max_length=80)
    loading_port: str = Field(default="", max_length=80)
    destination_port: str = Field(default="", max_length=80)
    destination_name_zh: str = Field(default="", max_length=80)
    trade_country: Country | None = None
    domestic_source: str = Field(default="", max_length=120)
    seller_credit_no: str = Field(default="", max_length=32)
    producer_name: str = Field(default="", max_length=180)
    producer_credit_no: str = Field(default="", max_length=32)
    customs_office: str = Field(default="", max_length=80)
    supervision_mode: str = Field(default="", max_length=80)
    exemption_nature: str = Field(default="", max_length=80)
    exemption_method: str = Field(default="", max_length=80)
    declaration_date: date | None = None
    customs_record_no: str = Field(default="", max_length=80)
    licence_no: str = Field(default="", max_length=80)
    edi_list_no: str = Field(default="", max_length=80)
    freight: str = Field(default="", max_length=80)
    insurance: str = Field(default="", max_length=80)
    other_fees: str = Field(default="", max_length=80)
    related_party_confirmation: str = Field(default="", max_length=16)
    price_influence_confirmation: str = Field(default="", max_length=16)
    royalty_confirmation: str = Field(default="", max_length=16)
    self_payment_confirmation: str = Field(default="", max_length=16)
    declarant_contact: str = Field(default="", max_length=120)
    signed_at: str = Field(default="", max_length=80)
    contract_terms: str = Field(default="", max_length=1000)
    customs_note: str = Field(default="", max_length=1000)


class DomesticDetails(DocumentInput):
    invoice_no: str = Field(default="", max_length=80)
    contract_no: str = Field(default="", max_length=80)
    contract_date: date | None = None
    signed_at: str = Field(default="", max_length=80)
    seller_phone: str = Field(default="", max_length=64)
    buyer_phone: str = Field(default="", max_length=64)
    payment_terms: str = Field(default="", max_length=180)
    contract_terms: str = Field(default="", max_length=1000)


class ShipmentDocumentBody(DocumentInput):
    version_no: int = Field(ge=1)
    trade_mode: Literal["domestic", "export"]
    seller_name: str = Field(min_length=1, max_length=180)
    seller_address: str = Field(default="", max_length=400)
    buyer_name: str = Field(min_length=1, max_length=180)
    buyer_address: str = Field(default="", max_length=400)
    buyer_tax_no: str = Field(default="", max_length=64)
    destination_country: Country | None = None
    trade_term: str = Field(default="", max_length=32)
    transport_no: str = Field(default="", max_length=80)
    include_commercial_invoice: bool = False
    boxes: list[PackingBox] = Field(default_factory=list, max_length=100)
    customs: list[CustomsLine] = Field(default_factory=list, max_length=100)
    customs_profiles: list[CustomsProfile] = Field(default_factory=list, max_length=3)
    export_details: ExportDetails | None = None
    domestic_details: DomesticDetails | None = None

    @model_validator(mode="after")
    def validate_trade(self):
        if self.trade_mode == "domestic":
            if (self.boxes or self.customs or self.customs_profiles or self.export_details
                    or self.include_commercial_invoice or self.destination_country not in {None, "CN"}):
                raise ValueError("国内出货单据不接受出口或装箱资料")
            return self
        if self.domestic_details is not None:
            raise ValueError("出口单据请填写商业单据资料")
        if not self.destination_country or self.destination_country == "CN":
            raise ValueError("出口单据需填写境外目的国家或地区代码")
        if not self.seller_address or not self.buyer_address:
            raise ValueError("出口单据需填写发货方和收货方地址")
        if not self.boxes or len({box.box_no.casefold() for box in self.boxes}) != len(self.boxes):
            raise ValueError("请填写装箱资料，箱号不得重复")
        if sum(len(box.lines) for box in self.boxes) > 500:
            raise ValueError("每批最多录入 500 条箱内明细")
        if len({line.shipment_line_id for line in self.customs}) != len(self.customs):
            raise ValueError("同一出货货品只能补录一条报关资料")
        if len({profile.material_group for profile in self.customs_profiles}) != len(self.customs_profiles):
            raise ValueError("同一材料类别只能设置一份分组申报资料")
        return self


class ShipmentInvoiceBody(DocumentInput):
    invoice_no: str = Field(min_length=1, max_length=80)
    issued_date: date
    attachment_id: UUID
