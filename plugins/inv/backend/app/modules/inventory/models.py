"""表模型（md_item_category、md_item、inv_warehouse、inv_lot、inv_stock_balance、inv_stock_transaction、inv_stock_order_type、inv_stock_order、inv_stock_order_line）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import conv
from sqlmodel import Field, SQLModel
from app.framework.db.models import audit_user_field, bool_field, created_at_field, deleted_at_field, flex_form_field, id_field, org_field, updated_at_field

class MdItemCategory(SQLModel, table=True):
    """物料分类：一行为一个物料分类。"""
    __tablename__ = 'md_item_category'
    __table_args__ = (Index('uk_md_item_category_category_name', 'category_name', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '物料分类：一行为一个物料分类。'})
    id: UUID = id_field()
    category_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '分类名称'})
    parent_id: UUID | None = Field(default=None, foreign_key='md_item_category.id', index=True, nullable=True, sa_column_kwargs={'comment': '上级分类'}, ondelete='RESTRICT')
    description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class MdItem(SQLModel, table=True):
    """物料：一行为一种物料（办公用品、耗材、教具、设备等）。"""
    __tablename__ = 'md_item'
    __table_args__ = (Index('uk_md_item_item_no', 'item_no', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '物料：一行为一种物料（办公用品、耗材、教具、设备等）。唯一的物料主数据；库存数量不在这里，在库存余额。'})
    id: UUID = id_field()
    item_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '物料编号'})
    item_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '物料名称'})
    category_id: UUID | None = Field(default=None, foreign_key='md_item_category.id', index=True, nullable=True, sa_column_kwargs={'comment': '物料分类'}, ondelete='RESTRICT')
    specification: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '规格型号'})
    unit_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '基本单位；字典 md_unit'})
    sub_unit_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '辅助单位；字典 md_unit'})
    unit_price: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), nullable=True, sa_column_kwargs={'comment': '参考单价'})
    # 迁移兼容：保留旧值供人工核对；当前预警只读取 inv_item_warehouse_setting。
    min_quantity: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={'comment': '旧全局库存下限；仅迁移兼容留存，当前预警使用物料仓库设置'})
    max_quantity: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={'comment': '旧全局库存上限；仅迁移兼容留存，当前预警使用物料仓库设置'})
    default_supplier_id: UUID | None = Field(default=None, foreign_key='md_supplier.id', index=True, nullable=True, sa_column_kwargs={'comment': '默认供应商'}, ondelete='RESTRICT')
    is_lot_controlled: bool = bool_field('是否批次管理', default=False)
    is_asset_managed: bool = bool_field('是否纳入实物资产管理；开启后新收货同步登记资产；不代表财务固定资产认定', default=False)
    default_asset_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '默认资产类型；字典 asset_type'})
    default_asset_management_mode_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '历史资产登记方式兼容字段；字典 asset_management_mode；新资产统一逐件编号，旧值不再控制收货登记'})
    shelf_life_days: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '保质期（天）'})
    is_active: bool = bool_field('是否启用', default=True)
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvWarehouse(SQLModel, table=True):
    """仓库：一行为一个仓库。"""
    __tablename__ = 'inv_warehouse'
    location_id: UUID | None = Field(default=None, foreign_key="md_location.id", ondelete="RESTRICT", index=True,
        sa_column_kwargs={"comment": "仓库所在物理位置；引用 md_location.id；历史仓库待人工关联"})
    __table_args__ = (Index('uk_inv_warehouse_org_id_warehouse_no', 'org_id', 'warehouse_no', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '仓库：一行为一个仓库。'})
    id: UUID = id_field()
    requisition_approval_department_id: UUID | None = Field(default=None, foreign_key='sys_department.id', ondelete='RESTRICT', index=True, sa_column_kwargs={'comment': '领用审批展示部门；引用仓库本级或有效下级组织的启用部门；按当前配置展示，不授予审批权限，不作为历史审批部门快照；敏感级别：内部'})
    default_asset_department_id: UUID | None = Field(default=None, foreign_key='sys_department.id', ondelete='RESTRICT', sa_column_kwargs={'comment': '仓库责任部门；入库自动登记时默认带出，可在单据明细调整；可选本级及有效下级组织中已启用且未删除的部门'})
    default_asset_custodian_user_id: UUID | None = Field(default=None, foreign_key='sys_user.id', ondelete='RESTRICT', sa_column_kwargs={'comment': '仓库资产保管人；登记资产时默认带出，可调整；引用本级及有效下级组织的启用租户用户；敏感级别：个人'})
    org_id: UUID = org_field(index=False, ondelete='RESTRICT')
    warehouse_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '仓库编号'})
    warehouse_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '仓库名称'})
    warehouse_type_code: str = Field(default='general', max_length=64, nullable=False,
        sa_column_kwargs={'server_default': text("'general'"), 'comment': '仓库类型；字典 inv_warehouse_type；默认 general（综合仓）'})
    location: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '仓库位置；楼栋、楼层或房间等位置说明；可为空'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class InvItemWarehouse(SQLModel, table=True):
    """物料适用仓库：一个物料允许进入一个仓库的一段有效关系。"""
    __tablename__ = "inv_item_warehouse"
    __table_args__ = (
        Index("uk_inv_item_warehouse_item_id_warehouse_id", "item_id", "warehouse_id", unique=True,
              postgresql_where=text("valid_to is null")),
        Index("idx_inv_item_warehouse_warehouse_id", "warehouse_id"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_inv_item_warehouse_period")),
        {"comment": "物料适用仓库：一行代表物料允许入库到指定仓库的一段有效关系；独立于库存数量和安全阈值。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    item_id: UUID = Field(foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "适用物料"})
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "允许入库的仓库；与 org_id 组织一致"})
    valid_from: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={"comment": "适用关系生效时间；左闭右开"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={"comment": "适用关系终止时间；为空表示持续有效"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field("已校验租户扩展配置；不存放仓库 ID 数组")


class InvWarehouseRequisitionOrg(SQLModel, table=True):
    """一个仓库向一个指定组织开放申领的一段有效关系。"""

    __tablename__ = "inv_warehouse_requisition_org"
    __table_args__ = (
        Index("uk_inv_warehouse_requisition_org_warehouse_id_recipient_org_id", "warehouse_id", "recipient_org_id", unique=True,
              postgresql_where=text("valid_to is null")),
        Index("idx_inv_warehouse_requisition_org_recipient_org_id_valid_to", "recipient_org_id", "valid_to"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_inv_warehouse_requisition_org_period")),
        {"comment": "仓库申领共享组织：一行为一个仓库向一个指定组织开放申领的有效期间；撤销结束有效期，保留历史。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "开放申领的仓库；所属组织与 org_id 一致"})
    recipient_org_id: UUID = Field(foreign_key="sys_org.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "获准申领的组织；精确匹配申请人的当前主组织，不自动包含下级"})
    valid_from: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={"comment": "授权生效时间；带时区，左闭右开"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "授权终止时间；为空表示持续有效，不覆盖历史授权"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()


class InvWarehouseUser(SQLModel, table=True):
    """仓库账号授权：一行为一个账号管理一个仓库的一段有效关系。"""

    __tablename__ = "inv_warehouse_user"
    __table_args__ = (
        Index("uk_inv_warehouse_user_warehouse_id_user_id", "warehouse_id", "user_id", unique=True,
              postgresql_where=text("valid_to is null")),
        Index("idx_inv_warehouse_user_user_id_valid_to", "user_id", "valid_to"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_inv_warehouse_user_period")),
        {"comment": "仓库管理账号：一行为一个租户账号对一个仓库的有效授权期间；配合关联数据范围，不授予功能权限或扩大组织范围。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "授权管理的仓库；所属组织须与 org_id 一致"})
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "获授权的租户账号；实际动作仍校验功能权限和组织范围"})
    valid_from: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={"comment": "授权生效时间；带时区，左闭右开"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "授权终止时间；为空表示持续有效；撤销保留历史"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field("扩展字段；已校验的租户扩展配置，不存放授权账号数组")


class InvItemWarehouseSetting(SQLModel, table=True):
    """物料仓库设置：一行为一种物料在一个仓库的安全库存阈值。"""

    __tablename__ = "inv_item_warehouse_setting"
    __table_args__ = (
        Index(
            "uk_inv_item_warehouse_setting_item_id_warehouse_id",
            "item_id",
            "warehouse_id",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        CheckConstraint("min_quantity >= 0", name="ck_inv_item_warehouse_setting_min_quantity"),
        CheckConstraint("max_quantity > min_quantity", name="ck_inv_item_warehouse_setting_quantity_range"),
        {'comment': '物料仓库设置：一行为一种物料在一个仓库的安全库存阈值；用于低库存补货和库存积压预警。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    item_id: UUID = Field(foreign_key="md_item.id", nullable=False, sa_column_kwargs={'comment': '物料'})
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", index=True, nullable=False, sa_column_kwargs={'comment': '仓库'})
    min_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '安全库存下限；可用库存小于或等于该值时预警'})
    max_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '补货目标及库存上限；必须大于安全库存下限'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvLot(SQLModel, table=True):
    """批次：一行为一种物料的一个批次。"""
    __tablename__ = 'inv_lot'
    __table_args__ = (Index('uk_inv_lot_item_id_lot_no', 'item_id', 'lot_no', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '批次：一行为一种物料的一个批次。'})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete='RESTRICT')
    item_id: UUID = Field(foreign_key='md_item.id', nullable=False, sa_column_kwargs={'comment': '物料'}, ondelete='RESTRICT')
    lot_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '批次号；物料内唯一'})
    production_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '生产日期'})
    expiry_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '有效期至'})
    supplier_id: UUID | None = Field(default=None, foreign_key='md_supplier.id', index=True, nullable=True, sa_column_kwargs={'comment': '供应商'}, ondelete='RESTRICT')
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvStockBalance(SQLModel, table=True):
    """库存余额：一行为一种物料在一个仓库、批次、库存状态下的当前余额。"""

    __tablename__ = "inv_stock_balance"
    __table_args__ = (
        Index("uk_inv_stock_balance_item_id_warehouse_id_lot_id_stock_status", "item_id", "warehouse_id", "lot_id", "stock_status_code", "owner_party_id", unique=True, postgresql_nulls_not_distinct=True),
        {'comment': '库存余额：一行为一种物料在一个仓库、批次、库存状态下的当前余额。当前状态，只能由库存流水驱动更新；不能与流水直接相加。历史时点库存由流水回推。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    item_id: UUID = Field(foreign_key="md_item.id", nullable=False, sa_column_kwargs={'comment': '物料'})
    warehouse_id: UUID = Field(foreign_key="inv_warehouse.id", index=True, nullable=False, sa_column_kwargs={'comment': '仓库'})
    lot_id: UUID | None = Field(default=None, foreign_key="inv_lot.id", index=True, nullable=True, sa_column_kwargs={'comment': '批次'})
    stock_status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '库存状态；字典 inv_stock_status'})
    owner_party_id: UUID | None = Field(default=None, foreign_key='md_party.id', index=True, nullable=True, sa_column_kwargs={'comment': '库存所有者；空表示自有'}, ondelete='RESTRICT')
    quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '账面数量'})
    reserved_quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '预留数量'})
    version_no: int = Field(nullable=False, sa_column_kwargs={'comment': '版本号；乐观锁'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvStockTransaction(SQLModel, table=True):
    """库存流水：一行为一次库存变化。"""
    __tablename__ = 'inv_stock_transaction'
    __table_args__ = (Index('uk_inv_stock_transaction_transaction_no', 'transaction_no', unique=True), {'comment': '库存流水：一行为一次库存变化。只由库存单据确认时生成，只追加不修改。'})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete='RESTRICT')
    transaction_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '流水号'})
    transaction_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '流水方向；字典 inv_transaction_type'})
    item_id: UUID = Field(foreign_key="md_item.id", index=True, nullable=False, sa_column_kwargs={'comment': '物料'})
    from_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '来源仓库；入库为空'})
    to_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '目标仓库；出库为空'})
    lot_id: UUID | None = Field(default=None, foreign_key="inv_lot.id", index=True, nullable=True, sa_column_kwargs={'comment': '批次'})
    from_stock_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '来源库存状态；字典 inv_stock_status'})
    to_stock_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '目标库存状态；字典 inv_stock_status'})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '数量；正数'})
    stock_order_id: UUID = Field(foreign_key='inv_stock_order.id', index=True, nullable=False, sa_column_kwargs={'comment': '库存单据'}, ondelete='RESTRICT')
    stock_order_line_id: UUID = Field(foreign_key='inv_stock_order_line.id', index=True, nullable=False, sa_column_kwargs={'comment': '单据明细'}, ondelete='RESTRICT')
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '业务发生时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvStockOrderType(SQLModel, table=True):
    """库存单据类型：一行为一种库存单据类型（如采购入库、领用出库、调拨、借出）。"""
    __tablename__ = 'inv_stock_order_type'
    __table_args__ = (Index('uk_inv_stock_order_type_type_no', 'type_no', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '库存单据类型：一行为一种库存单据类型（如采购入库、领用出库、调拨、借出）。类型是租户可配置的数据；代码按 `direction_code` 等属性记账。'})
    id: UUID = id_field()
    type_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '类型编号'})
    type_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '类型名称'})
    direction_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '方向；字典 inv_stock_direction'})
    default_from_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '默认来源库存状态；字典 inv_stock_status'})
    default_to_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '默认目标库存状态；字典 inv_stock_status'})
    is_approval_required: bool = bool_field('是否需要审批', default=False)
    wf_definition_id: UUID | None = Field(default=None, foreign_key='wf_definition.id', index=True, nullable=True, sa_column_kwargs={'comment': '审批流程'}, ondelete='RESTRICT')
    required_field_config: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '必填字段配置'})
    is_negative_allowed: bool = bool_field('是否允许负库存', default=False)
    is_builtin: bool = bool_field('是否内置', default=False)
    is_active: bool = bool_field('是否启用', default=True)
    sort_no: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '排序'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvStockOrder(SQLModel, table=True):
    """库存单据：一行为一张库存单据（入库、出库、调拨、借出、归还、报损、盘点调整等）。"""
    __tablename__ = 'inv_stock_order'
    __table_args__ = (Index('uk_inv_stock_order_order_no', 'order_no', unique=True), {'comment': '库存单据：一行为一张库存单据（入库、出库、调拨、借出、归还、报损、盘点调整等）。所有改变库存的动作都用这一张单据，按类型区分；确认（记账）后不可修改，更正只能冲销。'})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete='RESTRICT')
    order_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '单号'})
    order_type_id: UUID = Field(foreign_key='inv_stock_order_type.id', index=True, nullable=False, sa_column_kwargs={'comment': '单据类型'}, ondelete='RESTRICT')
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '领用申请状态；字典 inv_material_requisition_status'})
    business_date: date = Field(nullable=False, sa_column_kwargs={'comment': '业务日期'})
    from_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '默认来源仓库'})
    to_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '默认目标仓库'})
    counterparty_party_id: UUID | None = Field(default=None, foreign_key="md_party.id", index=True, nullable=True, sa_column_kwargs={'comment': '往来方；供应商、领用人、借用人'})
    counterparty_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '往来方名称；快照'})
    department_id: UUID | None = Field(default=None, foreign_key='sys_department.id', index=True, nullable=True, sa_column_kwargs={'comment': '领用部门'}, ondelete='RESTRICT')
    purpose: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '用途'})
    reason: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '原因'})
    handling_method_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '报损处理方式；字典 inv_handling_method'})
    expected_return_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '预计归还日期'})
    source_doc_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '上游单据类型；字典 inv_source_doc_type'})
    source_doc_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '上游单据；多态引用：采购订单、领用申请、借用申请、生产工单'})
    reversal_of_order_id: UUID | None = Field(default=None, foreign_key='inv_stock_order.id', index=True, nullable=True, sa_column_kwargs={'comment': '冲销的原单据'}, ondelete='RESTRICT')
    total_amount: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), nullable=True, sa_column_kwargs={'comment': '金额合计'})
    currency_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '币种；字典 md_currency'})
    wf_instance_id: UUID | None = Field(default=None, foreign_key='wf_instance.id', index=True, nullable=True, sa_column_kwargs={'comment': '审批实例'}, ondelete='RESTRICT')
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '确认（记账）时间'})
    confirmed_by: UUID | None = Field(default=None, foreign_key='sys_user.id', index=True, nullable=True, sa_column_kwargs={'comment': '确认人'}, ondelete='RESTRICT')
    voided_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '作废时间'})
    voided_by: UUID | None = Field(default=None, foreign_key='sys_user.id', index=True, nullable=True, sa_column_kwargs={'comment': '作废人'}, ondelete='RESTRICT')
    void_reason: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '作废原因'})
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class InvStockOrderLine(SQLModel, table=True):
    """库存单据明细：一行为单据中的一个物料行。"""
    __tablename__ = 'inv_stock_order_line'
    __table_args__ = (Index('uk_inv_stock_order_line_stock_order_id_line_no', 'stock_order_id', 'line_no', unique=True), {'comment': '库存单据明细：一行为单据中的一个物料行。'})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete='RESTRICT')
    stock_order_id: UUID = Field(foreign_key='inv_stock_order.id', nullable=False, sa_column_kwargs={'comment': '库存单据'}, ondelete='RESTRICT')
    line_no: int = Field(nullable=False, sa_column_kwargs={'comment': '行号'})
    item_id: UUID = Field(foreign_key="md_item.id", index=True, nullable=False, sa_column_kwargs={'comment': '物料'})
    lot_id: UUID | None = Field(default=None, foreign_key="inv_lot.id", index=True, nullable=True, sa_column_kwargs={'comment': '批次'})
    from_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '来源仓库；为空时取单据默认值'})
    to_warehouse_id: UUID | None = Field(default=None, foreign_key="inv_warehouse.id", index=True, nullable=True, sa_column_kwargs={'comment': '目标仓库；为空时取单据默认值'})
    from_stock_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '来源库存状态；字典 inv_stock_status；为空时取类型默认值'})
    to_stock_status_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '目标库存状态；字典 inv_stock_status；为空时取类型默认值'})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '数量；正数'})
    unit_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '单位；字典 md_unit'})
    unit_price: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), nullable=True, sa_column_kwargs={'comment': '单价'})
    amount: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), nullable=True, sa_column_kwargs={'comment': '金额'})
    source_line_id: UUID | None = Field(default=None, foreign_key='inv_stock_order_line.id', index=True, nullable=True, sa_column_kwargs={'comment': '关联明细；归还行引用借出行、冲销行引用原行'}, ondelete='RESTRICT')
    counted_quantity: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), nullable=True, sa_column_kwargs={'comment': '实盘数量；盘点调整'})
    remark: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '备注'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
