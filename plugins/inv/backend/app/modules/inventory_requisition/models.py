"""物资领用申请、明细和不可变操作记录。"""
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text
from sqlalchemy.schema import conv
from sqlmodel import Field, SQLModel
from app.framework.db.models import audit_user_field, created_at_field, flex_form_field, id_field, org_field, updated_at_field

class InvMaterialRequisition(SQLModel, table=True):
    """一张教职工物资领用申请。"""

    __tablename__ = "inv_material_requisition"
    __table_args__ = (
        Index("uk_inv_material_requisition_request_no", "request_no", unique=True),
        {"comment": "物资领用申请；一次提交可按仓库拆为多张申请，每张申请只对应一个仓库。",
         "info": {"retired_check_constraints": ("ck_inv_material_requisition_material_requisition_status",)}},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    request_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "申请单号"})
    submission_batch_no: str = Field(
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "提交批次号；一次混合申请拆分出的申请共用同一批次号"},
    )
    applicant_user_id: UUID = Field(
        foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={"comment": "申请人"}
    , ondelete='RESTRICT')
    applicant_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "申请人姓名快照"})
    applicant_org_id: UUID | None = Field(default=None, foreign_key="sys_org.id", ondelete="RESTRICT", index=True,
        sa_column_kwargs={"comment": "申请人提交时所属主组织；与发放仓库所属 org_id 分别记录，历史未记录时为空"})
    applicant_org_name_snapshot: str | None = Field(default=None, max_length=128,
        sa_column_kwargs={"comment": "申请来源组织名称快照；按提交时组织名称留档，历史记录不推断回填"})
    department_id: UUID | None = Field(
        default=None, foreign_key="sys_department.id", index=True, nullable=True, sa_column_kwargs={"comment": "申请部门"}
    , ondelete='RESTRICT')
    department_name_snapshot: str | None = Field(
        default=None, max_length=128, nullable=True, sa_column_kwargs={"comment": "申请部门名称快照"}
    )
    warehouse_id: UUID = Field(
        foreign_key="inv_warehouse.id",
        ondelete="RESTRICT",
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "申请领用仓库；引用库存仓库"},
    )
    purpose: str = Field(sa_type=Text, nullable=False, sa_column_kwargs={"comment": "领用用途"})
    custody_location_note: str | None = Field(default=None, max_length=200,
        sa_column_kwargs={"comment": "申领人选填的使用地点说明；个人保管不绑定固定位置；敏感：未审核自由文本，不进入模型上下文"})
    status_code: str = Field(
        max_length=32, index=True, nullable=False, sa_column_kwargs={"comment": "申请状态；字典 inv_material_requisition_status"}
    )
    approval_note: str | None = Field(default=None, max_length=500, nullable=True, sa_column_kwargs={"comment": "审批意见"})
    approved_by: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '审批通过人；引用租户用户'}, ondelete='RESTRICT')
    approved_by_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '审批通过人姓名快照；敏感：个人'})
    approved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '审批通过时间'})
    rejected_by: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '驳回人；引用租户用户'}, ondelete='RESTRICT')
    rejected_by_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '驳回人姓名快照；敏感：个人'})
    rejected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '驳回时间'})
    withdrawn_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '申请撤回时间'})
    issued_by: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '发放人；引用租户用户'}, ondelete='RESTRICT')
    issued_by_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '发放人姓名快照；敏感：个人'})
    issued_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '发放时间'})
    received_by: UUID | None = audit_user_field("签收人；引用租户用户", ondelete="RESTRICT")
    received_by_name_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "签收人姓名快照；敏感：个人"})
    received_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "申请人实际确认收货时间；历史单据不自动补录"})
    stock_order_id: UUID | None = Field(
        default=None, foreign_key="inv_stock_order.id", index=True, nullable=True, sa_column_kwargs={"comment": "发放生成的出库单"}
    , ondelete='RESTRICT')
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field()

class InvMaterialRequisitionLine(SQLModel, table=True):
    """领用申请中的物资明细。"""

    __tablename__ = "inv_material_requisition_line"
    __table_args__ = (
        Index("uk_inv_material_requisition_line_request_line", "requisition_id", "line_no", unique=True),
        CheckConstraint("quantity > 0", name="ck_inv_material_requisition_line_quantity_positive"),
        CheckConstraint("issued_quantity IS NULL OR (issued_quantity > 0 AND issued_quantity <= quantity)", name=conv("ck_inv_material_requisition_line_issued_quantity")),
        {"comment": "物资领用申请明细；物资名称、规格和单位保留申请时快照。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(ondelete='RESTRICT')
    requisition_id: UUID = Field(foreign_key='inv_material_requisition.id', index=True, nullable=False, sa_column_kwargs={'comment': '领用申请引用；申请提交后保留'}, ondelete='RESTRICT')
    line_no: int = Field(nullable=False, sa_column_kwargs={'comment': '明细行号；申请内唯一'})
    item_id: UUID = Field(foreign_key='md_item.id', index=True, nullable=False, sa_column_kwargs={'comment': '物料引用'}, ondelete='RESTRICT')
    item_no_snapshot: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '申请时的物料编号快照'})
    item_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '申请时的物料名称快照'})
    specification_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '申请时的规格快照'})
    unit_code_snapshot: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '申请时的计量单位快照；字典 md_unit'})
    quantity: Decimal = Field(sa_type=Numeric(18, 3), nullable=False, sa_column_kwargs={'comment': '申请数量；单位由 unit_code_snapshot 指定'})
    issued_quantity: Decimal | None = Field(default=None, sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "实际发放数量；单位沿用申请单位；历史记录为空，按当时整单发放规则核对申请数量"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人', ondelete='SET NULL')

class InvMaterialRequisitionEvent(SQLModel, table=True):
    """申请时间线；只追加，不提供修改和删除接口。"""
    __tablename__ = 'inv_material_requisition_event'
    __table_args__ = ({'comment': '物资领用申请操作时间线。'},)
    id: UUID = id_field()
    org_id: UUID = org_field()
    requisition_id: UUID = Field(foreign_key="inv_material_requisition.id", index=True, nullable=False, sa_column_kwargs={'comment': '领用申请引用；申请提交后保留'}, ondelete='RESTRICT')
    event_type_code: str = Field(
        max_length=32, nullable=False, sa_column_kwargs={"comment": "操作类型；字典 inv_material_requisition_event_type"}
    )
    from_status_code: str | None = Field(
        default=None, max_length=32, nullable=True, sa_column_kwargs={"comment": "操作前状态；字典 inv_material_requisition_status"}
    )
    to_status_code: str = Field(
        max_length=32, nullable=False, sa_column_kwargs={"comment": "操作后状态；字典 inv_material_requisition_status"}
    )
    note: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '操作说明；敏感：未审核自由文本，不进入模型上下文'})
    operator_user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '操作人；引用租户用户'}, ondelete='RESTRICT')
    operator_name_snapshot: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '操作时姓名快照；敏感：个人'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")


class InvMaterialRequisitionReceiptLine(SQLModel, table=True):
    """一次签收或异常反馈中的一行核对结果，只追加。"""

    __tablename__ = "inv_material_requisition_receipt_line"
    __table_args__ = (
        Index("uk_inv_material_requisition_receipt_line_event_line", "event_id", "requisition_line_id", unique=True),
        CheckConstraint("received_quantity >= 0 AND exception_quantity >= 0", name=conv("ck_inv_material_requisition_receipt_line_nonnegative")),
        {"comment": "领用收货核对明细；一行为一次签收或异常反馈中对一条领用明细的核对，保留历次结果。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field()
    event_id: UUID = Field(foreign_key="inv_material_requisition_event.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属收货操作记录"})
    requisition_line_id: UUID = Field(foreign_key="inv_material_requisition_line.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "被核对的领用明细"})
    received_quantity: Decimal = Field(sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次核对的实际收到数量；单位沿用领用明细，含收到但破损或错发的数量"})
    exception_quantity: Decimal = Field(default=Decimal("0"), sa_type=Numeric(18, 3), sa_column_kwargs={"comment": "本次核对的问题数量；单位沿用领用明细"})
    exception_type_code: str | None = Field(default=None, max_length=32, sa_column_kwargs={"comment": "异常类型；字典 inv_requisition_receipt_exception_type；正常签收为空"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("反馈人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()

