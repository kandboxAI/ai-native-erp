"""跨业务物理位置主数据，不包含资产、库存和巡查业务配置。"""
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, Index, Numeric, Text, text
from sqlmodel import Field, SQLModel
from app.framework.db.models import (audit_user_field, bool_field, created_at_field, deleted_at_field, flex_form_field, id_field, org_field, updated_at_field)


class MdLocation(SQLModel, table=True):
    __tablename__ = "md_location"
    __table_args__ = (
        Index("uk_md_location_org_id_location_no", "org_id", "location_no", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("latitude between -90 and 90", name="latitude_range"),
        CheckConstraint("longitude between -180 and 180", name="longitude_range"),
        CheckConstraint("parent_id is null or parent_id <> id", name="parent_not_self"),
        {"comment": "物理位置：一行代表一个校区、区域、建筑、楼层、房间或室外点位；经纬度必填。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    location_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "位置编号；组织内有效记录唯一"})
    location_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "位置名称"})
    location_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "位置类型；字典 md_location_type"})
    parent_id: UUID | None = Field(default=None, foreign_key="md_location.id", ondelete="RESTRICT", index=True, sa_column_kwargs={"comment": "上级物理位置；同组织空间层级"})
    latitude: Decimal = Field(sa_type=Numeric(10, 7), nullable=False, sa_column_kwargs={"comment": "纬度，单位：度；坐标系见 coordinate_system_code；敏感级别：内部定位信息"})
    longitude: Decimal = Field(sa_type=Numeric(10, 7), nullable=False, sa_column_kwargs={"comment": "经度，单位：度；坐标系见 coordinate_system_code；敏感级别：内部定位信息"})
    coordinate_system_code: str = Field(default="gcj02", max_length=32, nullable=False, sa_column_kwargs={"comment": "坐标系；字典 md_coordinate_system"})
    location_description: str | None = Field(default=None, max_length=500, sa_column_kwargs={"comment": "物理位置补充说明；敏感级别：内部"})
    sort_no: int = Field(default=0, nullable=False, sa_column_kwargs={"comment": "同级显示顺序，数值越小越靠前"})
    is_active: bool = bool_field("是否启用；上级停用时本位置不可供新业务选择", default=True)
    version_no: int = Field(default=1, nullable=False, sa_column_kwargs={"comment": "乐观锁版本号"})
    remark: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "备注；敏感级别：内部，自由文本默认不向 AI 发布"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；与删除时间成对", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
