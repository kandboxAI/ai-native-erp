"""直发/仓储出货与对账；库存交给 inv 公开服务，不替代应收、收款或发票。"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import audit_user_field, created_at_field, flex_form_field, id_field, org_field, updated_at_field


class MesShipment(SQLModel, table=True):
    __tablename__ = "mes_shipment"
    __table_args__ = (
        Index("uk_mes_shipment_org_id_shipment_no", "org_id", "shipment_no", unique=True),
        Index("uk_mes_shipment_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        {"comment": "MES 出货单；一行代表一次客户直发或仓储出货，仓储模式关联 inv 记账，取消保留原记录。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    shipment_no: str = Field(max_length=64, sa_column_kwargs={"comment": "出货单号；组织内唯一，取消后不复用"})
    customer_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "出货时客户外部编号快照；未对接客户主数据，无内部外键"})
    customer_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "出货时客户名称快照；业务信息，不进入 AI"})
    business_date: date = Field(sa_column_kwargs={"comment": "实际出货业务日期"})
    status_code: str = Field(default="draft", max_length=64, sa_column_kwargs={"comment": "出货状态；字典 mes_shipment_status"})
    fulfillment_mode_code: str = Field(default="direct", max_length=64, sa_column_kwargs={"server_default": text("'direct'"), "comment": "履约方式；字典 mes_shipment_fulfillment_mode；历史单据保持生产直发"})
    warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "仓储出货的来源仓库；生产直发为空"})
    order_currency_snapshot: str | None = Field(default=None, max_length=3, sa_column_kwargs={"comment": "快照：来源客户订单的 ISO 成交币种；非空表示关联明细均为订单未税价，空表示人民币含税价"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "出货说明；自由文本不进入 AI"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "单据乐观锁版本"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "创建请求幂等键；同一提交人唯一"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "创建请求 SHA256；校验重试内容，不保存额外业务原文"})
    posted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "确认出货时间"})
    posted_by: UUID | None = audit_user_field("确认出货人", ondelete="RESTRICT")
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "取消时间；不删除单据"})
    cancelled_by: UUID | None = audit_user_field("取消人", ondelete="RESTRICT")
    cancellation_reason: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "取消理由；不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesShipmentLine(SQLModel, table=True):
    __tablename__ = "mes_shipment_line"
    __table_args__ = (
        Index("uk_mes_shipment_line_shipment_id_work_order_id", "shipment_id", "work_order_id", unique=True),
        Index("idx_mes_shipment_line_work_order_id", "work_order_id"),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND amount >= 0", name="ck_mes_shipment_line_values"),
        {"comment": "MES 出货明细；一行代表本次出货的一个工单产品；直发确认后占产出，仓储模式由关联库存申请占额度。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    shipment_id: UUID = Field(foreign_key="mes_shipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属出货单"})
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源生产执行工单；按工单控制累计出货"})
    product_item_id: UUID = Field(foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "出货产品；引用共享物料"})
    work_order_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "出货时工单号快照"})
    product_item_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "出货时产品编号快照"})
    product_item_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "出货时产品名称快照；不进入 AI"})
    unit_code: str = Field(max_length=64, sa_column_kwargs={"comment": "出货计量单位；字典 md_unit，与工单一致"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次出货数量；单位见 unit_code"})
    unit_price: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "出货计价单价；单头有订单币种时为成交未税价快照，否则为人民币含税价；非成本价"})
    amount: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "出货金额；币种及含税口径同单头，数量乘单价逐行四舍五入保留两位"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesShipmentDocumentRevision(SQLModel, table=True):
    __tablename__ = "mes_shipment_document_revision"
    __table_args__ = (
        Index("uk_mes_shipment_document_revision_shipment_id_revision_no", "shipment_id", "revision_no", unique=True),
        {"comment": "出货单据版本；一行代表一次确认生成的模板渲染快照，只追加。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    shipment_id: UUID = Field(foreign_key="mes_shipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源出货单"})
    revision_no: int = Field(sa_column_kwargs={"comment": "出货单内的生成版本号，从 1 递增"})
    shipment_version_no_snapshot: int = Field(sa_column_kwargs={"comment": "生成时来源出货单版本；用于识别明细变化"})
    is_preview: bool = Field(sa_column_kwargs={"comment": "生成时出货尚未确认，输出标明预览"})
    template_key: str = Field(max_length=32, sa_column_kwargs={"comment": "渲染模板的稳定版本标识"})
    render_snapshot: dict = Field(sa_type=JSONB, sa_column_kwargs={"comment": "版本化模板渲染输入，含抬头、打印货品行及箱单行文本和数值；不用于关联或统计；敏感：内部"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("生成单据人员", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesShipmentInvoice(SQLModel, table=True):
    __tablename__ = "mes_shipment_invoice"
    __table_args__ = (
        Index("uk_mes_shipment_invoice_shipment_id_invoice_no", "shipment_id", "invoice_no", unique=True),
        {"comment": "出货正式发票登记；一行代表一张外部开具发票与出货单的关联，只追加。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    shipment_id: UUID = Field(foreign_key="mes_shipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "关联的已确认出货单"})
    invoice_no: str = Field(max_length=80, sa_column_kwargs={"comment": "税务系统开具的发票号码；敏感：内部"})
    issued_date: date = Field(sa_column_kwargs={"comment": "发票开具日期"})
    attachment_id: UUID = Field(foreign_key="file_attachment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "已开具发票的已绑定附件；敏感：内部"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("登记发票人员", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesReconciliation(SQLModel, table=True):
    __tablename__ = "mes_reconciliation"
    __table_args__ = (
        Index("uk_mes_reconciliation_org_id_reconciliation_no", "org_id", "reconciliation_no", unique=True),
        Index("uk_mes_reconciliation_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        CheckConstraint("period_end >= period_start", name="ck_mes_reconciliation_period"),
        {"comment": "MES 客户出货对账单；一行代表一个客户在指定期间的出货对账，不登记收款或应收。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    reconciliation_no: str = Field(max_length=64, sa_column_kwargs={"comment": "对账单号；组织内唯一"})
    customer_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "对账客户外部编号快照；无内部客户主数据外键"})
    customer_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "对账客户名称快照；不进入 AI"})
    period_start: date = Field(sa_column_kwargs={"comment": "对账期间开始日期；包含当天"})
    period_end: date = Field(sa_column_kwargs={"comment": "对账期间结束日期；包含当天"})
    status_code: str = Field(default="draft", max_length=64, sa_column_kwargs={"comment": "对账状态；字典 mes_reconciliation_status"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "对账说明；不进入 AI"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "单据乐观锁版本"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "创建请求幂等键；同一提交人唯一"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "创建请求 SHA256；用于幂等内容校验"})
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "对账确认时间；表示系统操作确认，不代替客户签章"})
    confirmed_by: UUID | None = audit_user_field("对账确认人", ondelete="RESTRICT")
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "取消时间；取消同时释放出货明细对账占用"})
    cancelled_by: UUID | None = audit_user_field("取消人", ondelete="RESTRICT")
    cancellation_reason: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "取消理由；不进入 AI"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()


class MesReconciliationLine(SQLModel, table=True):
    __tablename__ = "mes_reconciliation_line"
    __table_args__ = (
        Index("uk_mes_reconciliation_line_shipment_line_id_active", "shipment_line_id", unique=True, postgresql_where=text("reservation_released_at IS NULL")),
        Index("idx_mes_reconciliation_line_reconciliation_id", "reconciliation_id"),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND amount >= 0", name="ck_mes_reconciliation_line_values"),
        {"comment": "MES 对账明细；整条引用有效出货明细并保留数量、价格快照，取消释放唯一占用但保留历史。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    reconciliation_id: UUID = Field(foreign_key="mes_reconciliation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属对账单"})
    shipment_line_id: UUID = Field(foreign_key="mes_shipment_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源出货明细；同一条只允许一张有效草稿或确认对账单"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "出货数量快照；单位沿用来源出货明细"})
    unit_price: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "快照：来源出货单价；币种和含税口径与来源出货单一致"})
    adjustment_amount: Decimal = Field(default=Decimal(0), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "本次对账调整金额；币种同来源出货，可正可负，非零必须填理由"})
    adjustment_reason: str | None = Field(default=None, max_length=1000, sa_column_kwargs={"comment": "调整原因；非零调整必填，不进入 AI"})
    amount: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "最终对账金额；币种同来源出货，来源出货金额加调整，不得为负"})
    reservation_released_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "对账取消后的占用释放时间；为空表示该出货明细仍被本对账单占用"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()
