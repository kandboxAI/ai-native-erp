"""资产入库来源、实物持有分配及库存明细选择；只由资产模块维护。"""
from datetime import datetime
from decimal import Decimal
from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Numeric, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field, bool_field, created_at_field, flex_form_field, id_field,
    org_field, updated_at_field,
)


class AssetStockRegistrationPlan(SQLModel, table=True):
    """一行为库存入库明细的资产登记责任配置；由资产模块拥有。"""
    __tablename__ = "asset_stock_registration_plan"
    __table_args__ = (
        Index("uk_asset_stock_registration_plan_stock_order_line_id", "stock_order_line_id", unique=True),
        CheckConstraint("original_amount IS NULL OR original_amount >= 0", name="original_amount_nonnegative"),
        {"comment": "入库资产登记配置：一行为一条库存明细的责任、指定编号、购置日期与单件原值；未指定责任时按收货仓库默认配置执行。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    stock_order_line_id: UUID = Field(foreign_key="inv_stock_order_line.id", ondelete="CASCADE", sa_column_kwargs={"comment": "来源库存明细；唯一"})
    department_id: UUID | None = Field(default=None, foreign_key="sys_department.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次资产责任部门；为空时取收货仓库默认部门"})
    custodian_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次资产保管人；引用租户用户；个人信息；可选"})
    asset_no: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "本次指定资产编号；仅数量为一可填，空值自动逐件生成"})
    acquired_date: date | None = Field(default=None, sa_column_kwargs={"comment": "本次登记资产的购置日期；可为空"})
    original_amount: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "本次登记资产单件原值；元；空值表示未知"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict = flex_form_field()


class AssetStockReceipt(SQLModel, table=True):
    """一行为入库流水或期初库存人工核对产生的资产登记任务。"""
    __tablename__ = "asset_stock_receipt"
    __table_args__ = (
        Index("uk_asset_stock_receipt_stock_transaction_id", "stock_transaction_id", unique=True),
        Index("uk_asset_stock_receipt_source_balance_id", "source_balance_id", unique=True),
        CheckConstraint("(stock_transaction_id IS NOT NULL) <> (source_balance_id IS NOT NULL)", name="one_source"),
        CheckConstraint("quantity > 0 AND registered_quantity >= 0 AND registered_quantity <= quantity", name="quantity"),
        {"comment": "资产收货登记任务：一行为一条入库流水或期初人工核对的应登记数量；已关联数量不因领用或退库再次累计。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    stock_transaction_id: UUID | None = Field(default=None, foreign_key="inv_stock_transaction.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源入库流水；唯一；期初人工核对时为空，不补造流水"})
    source_balance_id: UUID | None = Field(default=None, foreign_key="inv_stock_balance.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "期初人工核对的库存余额；唯一；与来源流水二选一"})
    stock_order_line_id: UUID | None = Field(default=None, foreign_key="inv_stock_order_line.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "来源入库明细；期初核对为空"})
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "收货仓库"})
    item_id: UUID = Field(foreign_key="md_item.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "待登记物料"})
    lot_id: UUID | None = Field(default=None, foreign_key="inv_lot.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "来源批次；无批次时为空"})
    management_mode_code_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "收货时登记方式快照；字典 asset_management_mode；新收货固定 individual，保留历史 batch 快照"})
    asset_type_code_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "收货时资产类型快照；字典 asset_type"})
    stock_status_code_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "收货或期初核对时库存状态快照；字典 inv_stock_status"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "应登记数量；物料基本单位"})
    registered_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "累计已关联登记数量；包含待确认资产，不包含退库重复登记"})
    is_reversed: bool = bool_field("来源入库是否已冲销；保留任务历史", default=False)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict = flex_form_field()


class AssetStockBinding(SQLModel, table=True):
    """一行为一批同来源、同资产、同库存状态的实物当前分配。"""
    __tablename__ = "asset_stock_binding"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity"),
        CheckConstraint("asset_register_id IS NULL OR quantity IN (0, 1)", name="individual_quantity"),
        CheckConstraint("(asset_register_id IS NOT NULL) <> (location_item_id IS NOT NULL)", name="one_asset"),
        Index("uk_asset_stock_binding_asset_register_id", "asset_register_id", unique=True, postgresql_where=text("quantity > 0 AND asset_register_id IS NOT NULL")),
        {"comment": "资产实物分配：一行为同来源资产的一段当前数量；仓库为空表示已领用，零数量保留流转历史；不与资产总量相加。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    receipt_id: UUID = Field(foreign_key="asset_stock_receipt.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "原始收货登记任务；退库不变更"})
    previous_binding_id: UUID | None = Field(default=None, foreign_key="asset_stock_binding.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "流转或拆分前的实物分配；保留来源链，校验借出归还身份"})
    acquisition_source_code_snapshot: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "期初关联前资产登记来源快照；字典 asset_acquisition_source；解除未流转的期初关联时恢复"})
    asset_register_id: UUID | None = Field(default=None, foreign_key="asset_register.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "单件资产；与数量资产二选一"})
    location_item_id: UUID | None = Field(default=None, foreign_key="asset_location_item.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "当前位置数量资产；与单件资产二选一"})
    warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "当前账面仓库；已领用实物为空；借出仍按库存状态记账"})
    stock_status_code: str = Field(max_length=64, sa_column_kwargs={"comment": "当前库存状态；字典 inv_stock_status；已出库时保留来源状态供追溯"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本分配当前数量；物料基本单位；流转后原分配可为零"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict = flex_form_field()


class AssetStockSelection(SQLModel, table=True):
    """一行为一条库存明细选择的一段实物及其交付目标。"""
    __tablename__ = "asset_stock_selection"
    __table_args__ = (
        Index("uk_asset_stock_selection_stock_order_line_id_binding_id", "stock_order_line_id", "binding_id", unique=True),
        CheckConstraint("quantity > 0", name="quantity"),
        {"comment": "库存资产选择：一行为单据明细关联的实物数量及责任目标；草稿随明细替换，确认后保留追溯。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    stock_order_line_id: UUID = Field(foreign_key="inv_stock_order_line.id", ondelete="CASCADE", sa_column_kwargs={"comment": "库存明细；联合唯一索引前导列"})
    binding_id: UUID = Field(foreign_key="asset_stock_binding.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "选择的来源实物分配"})
    result_binding_id: UUID | None = Field(default=None, foreign_key="asset_stock_binding.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "过账后的实物分配；未过账时为空"})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次流转数量；物料基本单位"})
    asset_no_snapshot: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "选择时单件资产编号快照；数量资产为空"})
    management_mode_code_snapshot: str = Field(max_length=64, sa_column_kwargs={"comment": "选择时登记方式快照；字典 asset_management_mode"})
    target_location_id: UUID | None = Field(default=None, foreign_key="md_location.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "交付目标统一位置；个人申领为空，仓间调拨和退库以目标仓库位置为准"})
    department_id: UUID | None = Field(default=None, foreign_key="sys_department.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "交付后责任部门；个人申领取申领人当前部门，未关联时保留原资产部门"})
    custodian_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "交付后保管人；敏感级别：个人"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict = flex_form_field()
