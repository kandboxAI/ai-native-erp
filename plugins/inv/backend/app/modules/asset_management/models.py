"""资产位置、场所数量资产、单件设备和变更历史模型。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)


class AssetLocation(SQLModel, table=True):
    """保留资产地点旧标识；多条历史记录可关联同一统一位置。"""

    __tablename__ = "asset_location"
    __table_args__ = (
        Index("idx_asset_location_physical_location_id", "physical_location_id"),
        Index(
            "uk_asset_location_org_id_location_no",
            "org_id",
            "location_no",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        {
            "comment": "资产地点兼容记录：一行代表一个历史地点标识或内部资产关联；多条记录可关联同一统一位置，保留资产及交接历史引用。"
        },
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    physical_location_id: UUID | None = Field(default=None, foreign_key="md_location.id", ondelete="RESTRICT", nullable=True,
        sa_column_kwargs={"comment": "统一物理位置；引用 md_location.id；允许多个旧资产地点关联同一位置，组织必须一致"})
    location_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "资产地点兼容编号；历史编号保留，不随统一位置更新"})
    location_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "资产位置名称"})
    location_type_code: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "位置类型；字典 asset_location_type"},
    )
    parent_id: UUID | None = Field(
        default=None,
        foreign_key="asset_location.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "上级资产位置"},
    )
    # 历史默认值仅为保留旧数据；现行登记、调拨及地点补关联不读取或修改它们。
    default_department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "历史默认责任部门；仅保留旧值，当前资产登记不再使用"},
    )
    default_custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "历史默认保管人；仅保留旧值，当前资产登记不再使用；敏感级别：个人"},
    )
    is_active: bool = bool_field("是否启用", default=True)
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本号"})
    remark: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "备注；敏感级别：内部"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class AssetLocationItem(SQLModel, table=True):
    """历史数量资产：一行代表固定位置数量或一笔个人保管分配。"""

    __tablename__ = "asset_location_item"
    __table_args__ = (
        Index(
            "uk_asset_location_item_location_id_item_id",
            "location_id",
            "item_id",
            unique=True,
            postgresql_where=text("deleted_at is null AND registration_status_code <> 'voided'"),
        ),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("location_id IS NOT NULL OR custodian_user_id IS NOT NULL", name="custody_reference",
            info={"compare_check": True, "check_sql_equivalents": (
                "(location_id IS NOT NULL) OR (custodian_user_id IS NOT NULL)",
                "((location_id IS NOT NULL) OR (custodian_user_id IS NOT NULL))",
            )}),
        {
            "comment": "历史数量资产：一行代表一种物品在固定位置的数量或一笔个人保管分配；新资产均逐件编号，历史记录不自动转换。"
        },
    )

    id: UUID = id_field()
    acquisition_source_code: str = Field(default="historical", max_length=64, sa_column_kwargs={"server_default": text("'historical'"), "comment": "登记来源；字典 asset_acquisition_source；历史记录默认历史盘点，不补造入库关系"})
    org_id: UUID = org_field(index=False)
    location_id: UUID | None = Field(
        default=None, foreign_key="asset_location.id", ondelete="RESTRICT", index=True, nullable=True,
        sa_column_kwargs={"comment": "固定资产位置；为空表示个人保管，此时 custodian_user_id 必填"},
    )
    custody_location_note: str | None = Field(default=None, max_length=200,
        sa_column_kwargs={"comment": "个人保管的选填地点说明；不代表固定位置；敏感：未审核自由文本，不进入模型上下文"})
    item_id: UUID = Field(
        foreign_key="md_item.id",
        ondelete="RESTRICT",
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "物料；定义资产名称、规格和基本单位"},
    )
    asset_type_code: str = Field(
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "资产类型；字典 asset_type"},
    )
    quantity: Decimal = Field(
        sa_type=Numeric(18, 3),
        nullable=False,
        sa_column_kwargs={"comment": "当前数量；按物料基本单位计量"},
    )
    unit_code_snapshot: str = Field(
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "单位快照；字典 md_unit；保存建档或最近调整时的物料基本单位"},
    )
    department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "责任部门"},
    )
    custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "保管人；租户内用户；敏感级别：个人"},
    )
    status_code: str = Field(
        default="in_use",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "使用状态；字典 asset_status"},
    )
    registration_status_code: str = Field(
        default="pending_confirmation",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "登记确认状态；字典 asset_registration_status"},
    )
    registered_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "登记确认时间；确认后原始登记信息不可修改"},
    )
    registered_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "登记确认人"},
    )
    voided_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "登记作废时间"},
    )
    voided_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "登记作废人"},
    )
    void_reason: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "登记作废原因；敏感级别：内部"},
    )
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本号"})
    remark: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "备注；敏感级别：内部"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class AssetRegister(SQLModel, table=True):
    """单件设备台账：一行代表一件需要独立编号和生命周期跟踪的资产。"""

    __tablename__ = "asset_register"
    __table_args__ = (
        CheckConstraint("location_id IS NOT NULL OR custodian_user_id IS NOT NULL", name="custody_reference",
            info={"compare_check": True, "check_sql_equivalents": (
                "(location_id IS NOT NULL) OR (custodian_user_id IS NOT NULL)",
                "((location_id IS NOT NULL) OR (custodian_user_id IS NOT NULL))",
            )}),
        Index(
            "uk_asset_register_org_id_asset_no",
            "org_id",
            "asset_no",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        CheckConstraint(
            "original_amount is null or original_amount >= 0",
            name="original_amount_nonnegative",
        ),
        {
            "comment": "单件设备台账：一行代表一件需要独立编号、维修、移交或报废跟踪的资产；数量恒为一。"
        },
    )

    id: UUID = id_field()
    acquisition_source_code: str = Field(default="historical", max_length=64, sa_column_kwargs={"server_default": text("'historical'"), "comment": "登记来源；字典 asset_acquisition_source；历史记录默认历史盘点，不补造入库关系"})
    org_id: UUID = org_field(index=False)
    asset_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "资产编号；组织内有效记录唯一"})
    item_id: UUID = Field(
        foreign_key="md_item.id",
        ondelete="RESTRICT",
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "物料；定义资产名称、规格和基本单位"},
    )
    asset_type_code: str = Field(
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "资产类型；字典 asset_type"},
    )
    serial_no: str | None = Field(
        default=None,
        max_length=128,
        nullable=True,
        sa_column_kwargs={"comment": "生产序列号或出厂编号"},
    )
    location_id: UUID | None = Field(
        default=None, foreign_key="asset_location.id", ondelete="RESTRICT", index=True, nullable=True,
        sa_column_kwargs={"comment": "固定资产位置；为空表示个人保管，此时 custodian_user_id 必填"},
    )
    custody_location_note: str | None = Field(default=None, max_length=200,
        sa_column_kwargs={"comment": "个人保管的选填地点说明；不代表固定位置；敏感：未审核自由文本，不进入模型上下文"})
    department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "责任部门"},
    )
    custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "保管人；租户内用户；敏感级别：个人"},
    )
    status_code: str = Field(
        default="in_use",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "资产状态；字典 asset_status"},
    )
    acquired_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={"comment": "购置日期"})
    original_amount: Decimal | None = Field(
        default=None,
        sa_type=Numeric(18, 2),
        nullable=True,
        sa_column_kwargs={"comment": "购置原值；人民币元；仅记录，不在本期计提折旧"},
    )
    registration_status_code: str = Field(
        default="pending_confirmation",
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "登记确认状态；字典 asset_registration_status"},
    )
    registered_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "登记确认时间；确认后原始登记信息不可修改"},
    )
    registered_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "登记确认人"},
    )
    voided_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        sa_column_kwargs={"comment": "登记作废时间"},
    )
    voided_by: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "登记作废人"},
    )
    void_reason: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "登记作废原因；敏感级别：内部"},
    )
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本号"})
    remark: str | None = Field(
        default=None,
        sa_type=Text,
        nullable=True,
        sa_column_kwargs={"comment": "备注；敏感级别：内部"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间同时出现")
    flex_form: dict[str, Any] = flex_form_field()


class AssetChangeEvent(SQLModel, table=True):
    """资产变更事件：只追加，一行代表一次数量、地点、责任人或状态变化。"""

    __tablename__ = "asset_change_event"
    __table_args__ = (
        CheckConstraint(
            "(asset_register_id is not null) <> (location_item_id is not null)",
            name="one_target",
        ),
        {
            "comment": "资产变更事件：只追加，一行代表一次数量、地点、责任人或状态变化；不提供修改和删除接口。"
        },
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    asset_register_id: UUID | None = Field(
        default=None,
        foreign_key="asset_register.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "单件设备；与场所数量资产二选一"},
    )
    location_item_id: UUID | None = Field(
        default=None,
        foreign_key="asset_location_item.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "场所数量资产；与单件设备二选一"},
    )
    event_type_code: str = Field(
        max_length=64,
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "变更类型；字典 asset_change_event_type"},
    )
    quantity_before: Decimal | None = Field(
        default=None,
        sa_type=Numeric(18, 3),
        nullable=True,
        sa_column_kwargs={"comment": "变更前数量；单件设备为空"},
    )
    quantity_after: Decimal | None = Field(
        default=None,
        sa_type=Numeric(18, 3),
        nullable=True,
        sa_column_kwargs={"comment": "变更后数量；单件设备为空"},
    )
    from_location_id: UUID | None = Field(
        default=None,
        foreign_key="asset_location.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "变更前资产位置"},
    )
    to_location_id: UUID | None = Field(
        default=None,
        foreign_key="asset_location.id",
        ondelete="RESTRICT",
        index=True,
        nullable=True,
        sa_column_kwargs={"comment": "变更后资产位置"},
    )
    from_department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "变更前责任部门"},
    )
    to_department_id: UUID | None = Field(
        default=None,
        foreign_key="sys_department.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "变更后责任部门"},
    )
    from_custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "变更前保管人；敏感级别：个人"},
    )
    to_custodian_user_id: UUID | None = Field(
        default=None,
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        nullable=True,
        sa_column_kwargs={"comment": "变更后保管人；敏感级别：个人"},
    )
    from_status_code: str | None = Field(
        default=None,
        max_length=64,
        nullable=True,
        sa_column_kwargs={"comment": "变更前状态；字典 asset_status"},
    )
    from_custody_location_note_snapshot: str | None = Field(
        default=None, max_length=200,
        sa_column_kwargs={"comment": "变更前个人保管地点说明快照；作废本次责任移交时恢复；敏感级别：内部"},
    )
    to_status_code: str | None = Field(
        default=None,
        max_length=64,
        nullable=True,
        sa_column_kwargs={"comment": "变更后状态；字典 asset_status"},
    )
    source_type_code: str = Field(
        default="manual",
        max_length=64,
        nullable=False,
        sa_column_kwargs={"comment": "来源类型；字典 asset_change_source_type"},
    )
    source_id: UUID | None = Field(
        default=None,
        nullable=True,
        sa_column_kwargs={"comment": "来源业务记录；维修、报废、交接或库存明细等受控多态引用，不声明外键"},
    )
    note: str = Field(sa_type=Text, nullable=False, sa_column_kwargs={"comment": "变更原因；敏感级别：内部"})
    operator_user_id: UUID = Field(
        foreign_key="sys_user.id",
        ondelete="RESTRICT",
        index=True,
        nullable=False,
        sa_column_kwargs={"comment": "操作人"},
    )
    operator_name_snapshot: str = Field(
        max_length=128,
        nullable=False,
        sa_column_kwargs={"comment": "操作人姓名快照；敏感级别：个人"},
    )
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    flex_form: dict[str, Any] = flex_form_field()
