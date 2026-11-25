from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.db.pagination import PageParams


class RequisitionApprovalContext(BaseModel):
    """已授权仓库的当前审批展示配置，不代表历史审批归属或操作授权。"""
    requisition_approval_department_id: UUID | None = None
    requisition_approval_department_name: str | None = None
    requisition_approval_label: str = "领用审批"


def requisition_approval_context(department: "WarehouseDepartmentReference | None") -> dict:
    name = department.department_name.strip() if department else ""
    # 仅缩短展示名称；保留完整部门名，绝不据名称或部门配置授予权限。
    short_name = name[:-1] if len(name) > 2 and name.endswith(("科", "处")) else name
    return RequisitionApprovalContext(
        requisition_approval_department_id=department.id if department else None,
        requisition_approval_department_name=name or None,
        requisition_approval_label=f"{short_name}审批" if short_name else "领用审批",
    ).model_dump(mode="json")


class WarehouseDepartmentReference(BaseModel):
    """已授权仓库所属组织子树内的部门引用；不含人员、审计或业务明细。"""
    id: UUID
    org_id: UUID
    department_name: str
    org_name: str


class WarehouseCustodianReference(BaseModel):
    """已授权组织子树内的保管人目录引用，仅发布姓名与归属。"""
    id: UUID
    org_id: UUID
    display_name: str


class WarehouseCreate(BaseModel):
    """通过新增权限及组织数据范围创建仓库。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    org_id: UUID
    warehouse_no: str = Field(..., min_length=1, max_length=64)
    warehouse_name: str = Field(..., min_length=1, max_length=128)
    requisition_approval_department_id: UUID | None = None
    default_asset_department_id: UUID | None = None
    default_asset_custodian_user_id: UUID | None = None
    location_id: UUID
    location: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    warehouse_name: str | None = Field(default=None, min_length=1, max_length=128)
    requisition_approval_department_id: UUID | None = None
    default_asset_department_id: UUID | None = None
    default_asset_custodian_user_id: UUID | None = None
    location_id: UUID | None = None
    location: str | None = Field(default=None, max_length=255)

    @field_validator("location_id")
    @classmethod
    def require_location_reference(cls, value):
        if value is None:
            raise ValueError("统一位置不能清空，请选择有效位置")
        return value

    @field_validator("warehouse_name")
    @classmethod
    def require_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("仓库名称不能为空")
        return value

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        return value or None


class WarehouseItem(RequisitionApprovalContext):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    default_asset_department_id: UUID | None = None
    default_asset_custodian_user_id: UUID | None = None
    default_asset_department_name: str | None = None
    default_asset_custodian_name: str | None = None
    org_id: UUID
    org_name: str | None = None
    warehouse_no: str
    warehouse_name: str
    warehouse_type_code: str = "general"
    location_id: UUID | None = None
    location_name: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    coordinate_system_code: str | None = None
    location: str | None = None
    is_active: bool
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class WarehouseListQuery(PageParams):
    org_id: UUID | None = None
    is_active: bool | None = None


class WarehouseOption(BaseModel):
    id: UUID
    default_asset_department_id: UUID | None = None
    default_asset_custodian_user_id: UUID | None = None
    org_id: UUID
    org_name: str | None = None
    warehouse_no: str
    warehouse_name: str
    warehouse_type_code: str = "general"
    location_id: UUID | None = None
    location: str | None = None
    label: str


class RequisitionScopeSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_updated_at: AwareDatetime
    recipient_org_ids: list[UUID] = Field(default_factory=list, max_length=500)

    @field_validator("recipient_org_ids")
    @classmethod
    def unique_organizations(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("申领组织不能重复")
        return values


class WarehouseAccessSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_updated_at: AwareDatetime
    user_ids: list[UUID] = Field(default_factory=list, max_length=500)

    @field_validator("user_ids")
    @classmethod
    def unique_users(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("管理账号不能重复")
        return values
