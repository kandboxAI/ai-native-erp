from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.db.pagination import PageParams


# ───────── 物料分类 ─────────
class ItemCategoryCreate(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=128)
    parent_id: UUID | None = None
    description: str | None = None


class ItemCategoryUpdate(BaseModel):
    category_name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: UUID | None = None
    description: str | None = None


class ItemCategoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_name: str
    parent_id: UUID | None = None
    description: str | None = None
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class ItemCategoryListQuery(PageParams):
    parent_id: UUID | None = None


# ───────── 物料 ─────────
class ItemCreate(BaseModel):
    warehouse_ids: list[UUID] = Field(default_factory=list, max_length=500, description="物料适用仓库；未配置时不能新建普通入库")
    item_no: str | None = Field(default=None, max_length=64, description="不传时自动生成")
    item_name: str = Field(..., min_length=1, max_length=128)
    category_id: UUID | None = None
    specification: str | None = Field(default=None, max_length=128)
    unit_code: str = Field(..., min_length=1, max_length=64, description="字典 md_unit")
    sub_unit_code: str | None = Field(default=None, max_length=64)
    unit_price: Decimal | None = Field(default=None, ge=0)
    default_supplier_id: UUID | None = None
    is_asset_managed: bool = False
    default_asset_type_code: str | None = Field(default=None, max_length=64)
    default_asset_management_mode_code: Literal["individual"] | None = Field(default=None, description="兼容旧客户端；新资产固定逐件编号")
    is_lot_controlled: bool = False
    shelf_life_days: int | None = Field(default=None, ge=0)
    is_active: bool = True
    remark: str | None = None


class ItemUpdate(BaseModel):
    expected_updated_at: AwareDatetime | None = None
    warehouse_ids: list[UUID] | None = Field(default=None, max_length=500, description="省略保留原配置，空列表撤销可管理范围内的适用仓库")

    @field_validator("warehouse_ids")
    @classmethod
    def require_warehouse_list(cls, value):
        if value is None:
            raise ValueError("适用仓库须为列表，不能传空值")
        return value
    item_no: str | None = Field(default=None, max_length=64)
    item_name: str | None = Field(default=None, min_length=1, max_length=128)
    category_id: UUID | None = None
    specification: str | None = Field(default=None, max_length=128)
    unit_code: str | None = Field(default=None, max_length=64)
    sub_unit_code: str | None = Field(default=None, max_length=64)
    unit_price: Decimal | None = Field(default=None, ge=0)
    default_supplier_id: UUID | None = None
    is_asset_managed: bool = False  # 未传时由 exclude_unset 保留；显式 null 不允许
    default_asset_type_code: str | None = Field(default=None, max_length=64)
    default_asset_management_mode_code: Literal["individual"] | None = Field(default=None, description="兼容旧客户端；新资产固定逐件编号")
    is_lot_controlled: bool | None = None
    shelf_life_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    remark: str | None = None


class ItemWarehouseReference(BaseModel):
    id: UUID
    warehouse_name: str
    org_name: str
    is_available: bool


class ItemItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    can_edit_base_fields: bool = True
    warehouse_ids: list[UUID] = Field(default_factory=list)
    warehouses: list[ItemWarehouseReference] = Field(default_factory=list)
    item_no: str
    item_name: str
    category_id: UUID | None = None
    category_name: str | None = None
    specification: str | None = None
    unit_code: str
    sub_unit_code: str | None = None
    unit_price: Decimal | None = None
    default_supplier_id: UUID | None = None
    default_supplier_name: str | None = None
    is_asset_managed: bool = False
    default_asset_type_code: str | None = None
    default_asset_management_mode_code: str | None = None
    is_lot_controlled: bool
    shelf_life_days: int | None = None
    is_active: bool
    remark: str | None = None
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class ItemListQuery(PageParams):
    applicable_warehouse_id: UUID | None = Field(default=None, description="按明确配置的适用仓库筛选，不依赖库存")
    is_asset_managed: bool | None = None
    category_id: UUID | None = None
    default_supplier_id: UUID | None = None
    warehouse_id: UUID | None = Field(
        default=None,
        description="筛选在指定仓库已有库存余额或已配置安全库存阈值的物料",
    )
    is_active: bool | None = None


class ItemOptionQuery(BaseModel):
    inbound_warehouse_id: UUID | None = Field(default=None, description="普通入库目标仓库；仅返回已配置适用关系的物料，含零库存")
    inbound_action: Literal["create", "update"] = "create"
    item_id: UUID | None = None
    is_asset_managed: bool | None = Field(default=None, description="按物料是否纳入实物资产管理筛选")
    keyword: str | None = None
    category_id: UUID | None = None
    warehouse_id: UUID | None = Field(default=None, description="传入时返回该仓库的可用数量")
    org_id: UUID | None = Field(default=None, description="传入时返回该组织全部仓库的可用数量")
    in_stock_only: bool = False
    stock_status_code: str = Field(default="available", max_length=64, description="数量所属库存状态；字典 inv_stock_status")
    usage_scope_code: Literal["general_warehouse", "canteen_warehouse"] | None = Field(
        default=None,
        description=(
            "业务用途；general_warehouse 排除食堂专用食材；"
            "canteen_warehouse 返回该仓库关联物料及食堂候选食材"
        ),
    )
    limit: int = Field(default=200, ge=1, le=1000)


class ItemOption(BaseModel):
    id: UUID
    item_no: str
    item_name: str
    category_id: UUID | None = None
    category_name: str | None = None
    specification: str | None = None
    unit_code: str
    unit_price: Decimal | None = None
    is_lot_controlled: bool
    is_asset_managed: bool = False
    default_asset_type_code: str | None = None
    default_asset_management_mode_code: str | None = None
    available_quantity: Decimal | None = None
