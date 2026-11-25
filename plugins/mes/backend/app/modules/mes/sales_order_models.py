"""已成交客户订单及生产安排；报价原价、成交事实与生产数量分别保存。"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Numeric, Text
from sqlmodel import Field, SQLModel
from app.framework.db.models import id_field, org_field, created_at_field, audit_user_field
from .quotation_models import QuotationFields


class MesSalesOrder(QuotationFields, table=True):
    __tablename__ = "mes_sales_order"
    __table_args__ = (
        Index("uk_mes_sales_order_org_id_order_no", "org_id", "order_no", unique=True),
        Index("uk_mes_sales_order_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        {"comment": "客户订单；一行代表客户一次确认的成交，不等于报价或生产工单。"},
    )
    order_no: str = Field(max_length=64, sa_column_kwargs={"comment": "客户订单号；组织内唯一"})
    customer_id: UUID = Field(foreign_key="mes_customer.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "订单客户；引用 MES 客户档案"})
    customer_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "接单时的客户简称；不进入 AI"})
    customer_po_no: str = Field(default="", max_length=64, sa_column_kwargs={"comment": "客户采购单号；外部编号，可空"})
    currency: str = Field(max_length=3, sa_column_kwargs={"comment": "成交 ISO 币种，与来源报价一致"})
    status_code: str = Field(default="confirmed", max_length=32, sa_column_kwargs={"comment": "字典 mes_sales_order_status；已确认或已取消"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "订单乐观锁版本；生产安排及取消时递增"})
    note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "接单说明；自由文本不进入 AI"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "创建确认幂等键；同一提交人唯一"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "原始确认请求 SHA256；用于拒绝同键不同内容"})


class MesSalesOrderLine(QuotationFields, table=True):
    __tablename__ = "mes_sales_order_line"
    __table_args__ = (
        Index("uk_mes_sales_order_line_order_id_sequence_no", "order_id", "sequence_no", unique=True),
        Index("idx_mes_sales_order_line_quotation_line_id", "quotation_line_id"),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND original_unit_price_snapshot >= 0", name="valid_values"),
        CheckConstraint("discount_rate IS NULL OR (discount_rate > 0 AND discount_rate <= 1)", name="valid_discount_rate"),
        {"comment": "客户订单成交货品；一行代表本次选中的一个报价货品及数量档，保留成交时快照。"},
    )
    order_id: UUID = Field(foreign_key="mes_sales_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属客户订单"})
    sequence_no: int = Field(sa_column_kwargs={"comment": "订单内显示顺序，从 1 开始"})
    quotation_line_id: UUID = Field(foreign_key="mes_quotation_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "采用的已审核报价货品；通过其所属询价追溯修订"})
    quotation_tier_id: UUID | None = Field(default=None, foreign_key="mes_quotation_price_tier.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "采用的额外数量档；为空表示主数量及主单价"})
    quote_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "接单时来源报价单号"})
    quotation_revision_snapshot: int = Field(sa_column_kwargs={"comment": "接单时来源报价修订号"})
    drawing_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "成交时客户图号"})
    drawing_revision_snapshot: str = Field(default="", max_length=32, sa_column_kwargs={"comment": "成交时图纸版本"})
    description_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "成交时货品描述；不进入 AI"})
    material_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "成交时工程采用材料"})
    unit_name_snapshot: str = Field(max_length=16, sa_column_kwargs={"comment": "成交时计量单位文本；转生产时须确认与物料单位一致"})
    quoted_quantity_snapshot: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "选用数量档的询价数量；不是订购上限"})
    original_unit_price_snapshot: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "选用报价数量档的原始未税单价；币种同订单，成交改价不覆盖"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次订购数量，单位见单位快照"})
    unit_price: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "本次确认的成交未税单价；币种同订单"})
    discount_rate: Decimal | None = Field(default=None, sa_type=Numeric(5, 4), sa_column_kwargs={"comment": "成交折扣倍率；1为不打折，0.7为七折；空表示手动成交价或历史未记录档位，以原价和成交价为准"})
    due_date: date = Field(sa_column_kwargs={"comment": "客户订单承诺交付日期；不直接等同报价交期天数"})
    adjustment_reason: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "数量或成交价调整原因；不进入 AI"})


class MesSalesProduction(QuotationFields, table=True):
    __tablename__ = "mes_sales_production"
    __table_args__ = (
        Index("uk_mes_sales_production_production_order_id", "production_order_id", unique=True),
        Index("uk_mes_sales_production_order_id_idempotency_key", "order_id", "idempotency_key", unique=True),
        {"comment": "订单生产安排；一行代表一次安排产生的一张多货品生产工单。"},
    )
    order_id: UUID = Field(foreign_key="mes_sales_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源客户订单"})
    production_order_id: UUID = Field(foreign_key="mes_production_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次生成的生产项目；所有本次货品共同归属"})
    production_order_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "生成时生产工单编号"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "同一订单内生产安排幂等键"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "生产安排请求 SHA256"})


class MesSalesAllocation(QuotationFields, table=True):
    __tablename__ = "mes_sales_allocation"
    __table_args__ = (
        Index("uk_mes_sales_allocation_work_order_id", "work_order_id", unique=True),
        Index("idx_mes_sales_allocation_order_line_id", "order_line_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        {"comment": "订单生产分配；一行代表一次安排的一项货品数量，取消的执行工单不再占用待安排数量。"},
    )
    production_id: UUID = Field(foreign_key="mes_sales_production.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属本次生产安排"})
    order_line_id: UUID = Field(foreign_key="mes_sales_order_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源客户订单货品"})
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次产生的货品执行工单；仍使用现有生产生命周期"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次安排的订单单位数量；与执行工单计划数量一致"})


class MesSalesOrderEvent(SQLModel, table=True):
    __tablename__ = "mes_sales_order_event"
    __table_args__ = ({"comment": "订单动作审计；一行代表一次确认、生产安排或取消，只追加。"},)
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    order_id: UUID = Field(foreign_key="mes_sales_order.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "来源客户订单"})
    action_key: str = Field(max_length=32, sa_column_kwargs={"comment": "稳定动作标识 confirm/update/release/cancel"})
    note: str = Field(default="", sa_type=Text, sa_column_kwargs={"comment": "动作说明及调整依据；不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("操作人；租户用户", ondelete="RESTRICT")
