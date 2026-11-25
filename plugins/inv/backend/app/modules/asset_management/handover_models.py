"""资产交接单模型：支持单件资产与场所数量资产的分项接收。"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)


class AssetHandover(SQLModel, table=True):
    """资产交接单：一行代表一次由同一交出人发起的资产交接。"""

    __tablename__ = "asset_handover"
    __table_args__ = (
        Index("uk_asset_handover_org_id_handover_no", "org_id", "handover_no", unique=True),
        Index("idx_asset_handover_source", "source_type_code", "source_id"),
        Index("uk_asset_handover_source_type_code_source_id_org_id", "source_type_code", "source_id", "org_id", unique=True,
              postgresql_where=text("source_id IS NOT NULL AND status_code <> 'voided'")),
        {
            "comment": "资产交接单：一行代表一次由同一交出人发起、可由接任教师或后勤科分项接收的资产交接。"
        },
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    handover_no: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "交接单号；所属组织内唯一"},
    )
    source_type_code: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "来源类型；字典 asset_handover_source_type"},
    )
    source_id: UUID | None = Field(
        default=None,
        nullable=True,
        sa_column_kwargs={"comment": "来源业务记录；多态引用教师离职交接等业务单据，不声明外键"},
    )
    transferor_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "交出人；租户内用户；敏感级别：个人"},
    )
    transferor_name_snapshot: str = Field(
        max_length=128,
        nullable=False,
        sa_column_kwargs={"comment": "交出人姓名；快照：创建交接单时的姓名；敏感级别：个人"},
    )
    status_code: str = Field(
        default="draft",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "交接状态；字典 asset_handover_status"},
    )
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本号"})
    remark: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "交接备注；敏感级别：内部"},
    )
    submitted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "提交接收时间"},
    )
    submitted_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "提交人"},
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "全部明细接收完成时间"},
    )
    completed_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "最后完成交接的人"},
    )
    voided_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "作废时间"},
    )
    voided_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "作废人"},
    )
    void_reason: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "作废原因；敏感级别：内部"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field()


class AssetHandoverLine(SQLModel, table=True):
    """资产交接明细：一行代表一个资产目标及其接收结果。"""

    __tablename__ = "asset_handover_line"
    __table_args__ = (
        CheckConstraint(
            "(asset_register_id is not null) <> (location_item_id is not null)",
            name="one_target",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "asset_register_id is null or quantity = 1",
            name="individual_quantity_one",
        ),
        Index("idx_asset_handover_line_handover_id_sort_no", "handover_id", "sort_no"),
        {
            "comment": "资产交接明细：一行代表一项单件资产或场所数量资产的交接目标及接收结果。"
        },
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    handover_id: UUID = Field(
        foreign_key="asset_handover.id",
        ondelete="CASCADE",
        nullable=False,
        sa_column_kwargs={"comment": "资产交接单"},
    )
    asset_register_id: UUID | None = Field(
        default=None,
        foreign_key="asset_register.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "单件资产；与场所数量资产二选一"},
    )
    location_item_id: UUID | None = Field(
        default=None,
        foreign_key="asset_location_item.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "场所数量资产；与单件资产二选一"},
    )
    asset_no_snapshot: str | None = Field(
        default=None,
        max_length=64,
        nullable=True,
        sa_column_kwargs={"comment": "资产编号；快照：创建交接单时的资产编号"},
    )
    asset_name_snapshot: str = Field(
        max_length=200,
        nullable=False,
        sa_column_kwargs={"comment": "资产名称；快照：创建交接单时的物料名称"},
    )
    specification_snapshot: str | None = Field(
        default=None,
        max_length=255,
        nullable=True,
        sa_column_kwargs={"comment": "规格型号；快照：创建交接单时的规格型号"},
    )
    quantity: Decimal = Field(
        sa_type=Numeric(18, 3),
        nullable=False,
        sa_column_kwargs={"comment": "交接数量；按单位快照计量"},
    )
    unit_code_snapshot: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "计量单位；字典 md_unit；快照：创建交接单时的单位"},
    )
    disposition_code: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "处理方式；字典 asset_handover_disposition"},
    )
    from_location_id: UUID | None = Field(
        default=None, foreign_key="asset_location.id", ondelete="RESTRICT", nullable=True,
        sa_column_kwargs={"comment": "交接前固定位置；个人保管时为空，责任人由 from_custodian_user_id 留档"},
    )
    from_department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "交接前责任部门"},
    )
    from_custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "交接前保管人；敏感级别：个人"},
    )
    to_location_id: UUID = Field(
        foreign_key="asset_location.id",
        ondelete="RESTRICT",
        nullable=False,
        sa_column_kwargs={"comment": "交接后资产位置"},
    )
    to_department_id: UUID = Field(
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        nullable=False,
        sa_column_kwargs={"comment": "交接后责任部门"},
    )
    to_custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "交接后保管人；移交教师时必填；敏感级别：个人"},
    )
    status_code: str = Field(
        default="pending",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "明细接收状态；字典 asset_handover_line_status"},
    )
    rejection_reason: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "拒收原因；敏感级别：内部"},
    )
    confirmed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "接收确认时间"},
    )
    confirmed_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "接收确认人"},
    )
    sort_no: int = Field(default=0, nullable=False, sa_column_kwargs={"comment": "显示顺序"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    flex_form: dict[str, Any] = flex_form_field()
