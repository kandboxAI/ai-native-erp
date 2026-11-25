"""销售询价：关系明细、附件引用及追加审计，不把整张单据存入 JSON。"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Numeric, Text, text
from sqlmodel import Field, SQLModel
from app.framework.db.models import (id_field, org_field, created_at_field, updated_at_field,
    audit_user_field, deleted_at_field, flex_form_field)


class QuotationFields(SQLModel):
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；租户用户", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesQuotation(QuotationFields, table=True):
    __tablename__ = "mes_quotation"
    __table_args__ = (
        Index("uk_mes_quotation_org_id_quote_no_revision", "org_id", "quote_no", "revision", unique=True),
        Index("uk_mes_quotation_open_revision", "org_id", "quote_no", unique=True,
            postgresql_where=text("status_code NOT IN ('quoted', 'voided') AND deleted_at IS NULL")),
        CheckConstraint("version_no > 0 AND revision > 0", name="positive_versions"),
        {"comment": "销售询价报价；一行代表一张报价单的一个修订，不代表客户已成交。"},
    )
    quote_no: str = Field(max_length=64, sa_column_kwargs={"comment": "报价单号；服务端生成，同单修订共用"})
    revision: int = Field(default=1, sa_column_kwargs={"comment": "报价修订；同组织单号内唯一"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "乐观锁版本；每次业务修改递增"})
    title: str = Field(max_length=128, sa_column_kwargs={"comment": "询价名称；自由文本不进入 AI"})
    customer_id: UUID = Field(foreign_key="mes_customer.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属组织内客户档案"})
    customer_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "客户业务简称快照，不进入 AI"})
    currency: str = Field(max_length=3, sa_column_kwargs={"comment": "ISO 币种标识；CNY、EUR、USD，不是字典字段"})
    deadline: date | None = Field(default=None, sa_column_kwargs={"comment": "报价截止日期；非订单交付日期"})
    status_code: str = Field(default="draft", max_length=32, sa_column_kwargs={"comment": "字典 mes_quotation_status；业务录入、待工程、工程中、待初审、待复审、审核通过、已作废"})
    owner_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "业务负责人；租户用户，可空时以创建人负责"})
    engineer_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "工程负责人；租户用户，可空表示待工程领取"})
    note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "询价说明；不进入 AI"})
    return_reason: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "退回补充或审核退回原因；不进入 AI"})


class MesQuotationLine(QuotationFields, table=True):
    __tablename__ = "mes_quotation_line"
    __table_args__ = (
        Index("uk_mes_quotation_line_quotation_id_sequence_no", "quotation_id", "sequence_no", unique=True, postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("quantity > 0 AND (unit_price IS NULL OR unit_price >= 0) AND (weight_kg IS NULL OR weight_kg >= 0) AND (lead_days IS NULL OR lead_days > 0)", name="valid_values"),
        {"comment": "询价货品明细；一行代表某修订中一个图号版本的一次数量询价。"},
    )
    quotation_id: UUID = Field(foreign_key="mes_quotation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价修订"})
    sequence_no: int = Field(sa_column_kwargs={"comment": "单内显示顺序；从 1 开始"})
    drawing_no: str = Field(max_length=64, sa_column_kwargs={"comment": "客户图号；外部业务编号，不是内部外键"})
    drawing_revision: str = Field(default="", max_length=32, sa_column_kwargs={"comment": "本次采用的图纸版本"})
    description: str = Field(default="", max_length=128, sa_column_kwargs={"comment": "零件描述；默认不进入 AI"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "询价数量；单位由 unit_name 明确，不代表订购上限"})
    unit_name: str = Field(default="件", max_length=16, sa_column_kwargs={"comment": "客户询价计量单位文本；不冒充 md_unit 字典值"})
    customer_material: str = Field(default="", max_length=128, sa_column_kwargs={"comment": "客户要求材料；保留原始要求"})
    quoted_material: str = Field(default="", max_length=128, sa_column_kwargs={"comment": "工程采用材料；与客户要求分开保存"})
    weight_kg: Decimal | None = Field(default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "工程填写的单件净重量；kg，不是毛坯重量"})
    unit_price: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "工程确认的对客未税单价；币种同报价头"})
    lead_days: int | None = Field(default=None, sa_column_kwargs={"comment": "报价交期；自然日，实际订单日期另行确认"})
    surface_treatment: str = Field(default="", max_length=500, sa_column_kwargs={"comment": "客户表面处理要求；仅确认的制造字段可用于加工分析"})
    note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "客户备注；不自动进入 AI"})
    engineering_note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "工程内部说明；不对客导出或发送 AI"})
    adopted_cnc_quote_id: UUID | None = Field(default=None, foreign_key="mes_cnc_quote.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次人工采用的真实加工核价快照；非自动对客价格"})


class MesQuotationFile(QuotationFields, table=True):
    __tablename__ = "mes_quotation_file"
    __table_args__ = (Index("uk_mes_quotation_file_line_id_kind", "line_id", "kind", unique=True),
        {"comment": "询价附件引用；一行代表货品当前的一份 PDF 或 STP/STEP，原件由 L1 文件模块管理。"})
    line_id: UUID = Field(foreign_key="mes_quotation_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价货品"})
    attachment_id: UUID = Field(foreign_key="file_attachment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "L1 原件；修订可共享已授权原件引用，不重复绑定"})
    kind: str = Field(max_length=8, sa_column_kwargs={"comment": "文件格式标识 pdf/model；依据经过校验的扩展名"})


class MesQuotationPriceTier(QuotationFields, table=True):
    __tablename__ = "mes_quotation_price_tier"
    __table_args__ = (
        Index("uk_mes_quotation_price_tier_line_id_quantity", "line_id", "quantity", unique=True),
        CheckConstraint("quantity > 0 AND (unit_price IS NULL OR unit_price >= 0)", name="valid_values"),
        {"comment": "报价额外数量档；一行代表货品主数量以外一个明确数量及对应价格，不是自动折扣区间。"},
    )
    line_id: UUID = Field(foreign_key="mes_quotation_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属报价修订的货品"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本档询价数量；单位沿用货品，不能与主数量重复"})
    unit_price: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "本档工程确认对客未税单价；币种同报价"})
    calculation_note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "本档人工核算依据；不默认对客导出或发送 AI"})


class MesQuotationCnc(QuotationFields, table=True):
    __tablename__ = "mes_quotation_cnc"
    __table_args__ = (Index("idx_mes_quotation_cnc_line_id_created_at", "line_id", "created_at"),
        {"comment": "销售询价到加工核价的来源关系；一行代表货品一次真实核价准备，保留历次依据。"})
    line_id: UUID = Field(foreign_key="mes_quotation_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源货品"})
    part_id: UUID = Field(foreign_key="mes_cnc_part.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "真实加工询价零件"})
    source_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "文件、数量和制造要求摘要；用于采用前检查来源是否变化"})


class MesQuotationEvent(SQLModel, table=True):
    __tablename__ = "mes_quotation_event"
    __table_args__ = (Index("idx_mes_quotation_event_quotation_id_created_at", "quotation_id", "created_at"),
        {"comment": "询价业务审计；一行代表一次保存、提交、退回、审核或采用动作，只追加。"})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    quotation_id: UUID = Field(foreign_key="mes_quotation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价修订"})
    action_key: str = Field(max_length=32, sa_column_kwargs={"comment": "稳定业务动作标识"})
    version_no_snapshot: int = Field(sa_column_kwargs={"comment": "动作完成后的业务版本"})
    note: str = Field(default="", sa_type=Text, sa_column_kwargs={"comment": "动作或审核说明；不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("动作人；当前租户用户", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()
