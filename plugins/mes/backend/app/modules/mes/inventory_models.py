"""MES 与统一库存单据的关系；库存余额和流水仍只由 inv 拥有。"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Index, Numeric, Text
from sqlmodel import Field, SQLModel
from app.framework.db.models import audit_user_field, created_at_field, flex_form_field, id_field, org_field, updated_at_field


class MesInventoryPosting(SQLModel, table=True):
    __tablename__ = "mes_inventory_posting"
    __table_args__ = (
        Index("uk_mes_inventory_posting_stock_order_id", "stock_order_id", unique=True),
        Index("uk_mes_inventory_posting_shipment_line_id", "shipment_line_id", unique=True),
        Index("uk_mes_inventory_posting_created_by_idempotency_key", "created_by", "idempotency_key", unique=True),
        Index("idx_mes_inventory_posting_work_order_id", "work_order_id"),
        Index("idx_mes_inventory_posting_source_posting_id", "source_posting_id"),
        CheckConstraint("quantity > 0", name="ck_mes_inventory_posting_quantity"),
        {"comment": "MES 库存业务关联；一行对应一张单物料库存单据，状态和冲销取 inv 事实，不复制库存余额。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属生产工单；库存来源单据指向同一工单"})
    operation_id: UUID | None = Field(default=None, foreign_key="mes_work_order_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "可选工序；必须属于本工单，领退料时可关联"})
    posting_type_code: str = Field(max_length=64, sa_column_kwargs={"comment": "业务类型；字典 mes_inventory_posting_type"})
    stock_order_id: UUID = Field(foreign_key="inv_stock_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "统一库存单据；调用公开服务创建后同一事务保存"})
    source_posting_id: UUID | None = Field(default=None, foreign_key="mes_inventory_posting.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "生产退料对应的已确认原领料；按实际记账批次控制退料数量"})
    shipment_line_id: UUID | None = Field(default=None, foreign_key="mes_shipment_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "仓储出货对应的出货明细；每条明细仅有一张来源出库单"})
    item_id: UUID = Field(foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "业务物料；产品入库和出货必须与工单产品一致"})
    item_no_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "申请时物料编号快照"})
    item_name_snapshot: str = Field(max_length=128, sa_column_kwargs={"comment": "申请时物料名称快照；不进入 AI"})
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际领出或存入仓库；与单据、工单组织一致"})
    lot_id: UUID | None = Field(default=None, foreign_key="inv_lot.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "指定或入库生成的批次；领料未指定时实际扣减批次以 inv 流水为准"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "申请数量；单位见 unit_code，待审批单据占业务额度但不改变实际库存"})
    unit_code: str = Field(max_length=64, sa_column_kwargs={"comment": "物料基本计量单位；字典 md_unit"})
    unit_price: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "可选库存入库成本单价；人民币元，不是出货销售单价"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "领退料或入库说明；不进入 AI"})
    idempotency_key: str = Field(max_length=128, sa_column_kwargs={"comment": "创建请求幂等键；同一提交人唯一"})
    request_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "创建请求 SHA256；校验重试内容"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("申请人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict = flex_form_field()
