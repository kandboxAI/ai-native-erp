from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.pagination import PageParams


class SupplierCreate(BaseModel):
    supplier_no: str | None = Field(default=None, max_length=64, description="不传时自动生成")
    supplier_name: str = Field(..., min_length=1, max_length=128)
    category_id: UUID | None = None
    party_type_code: str = Field(default="organization", max_length=64, description="字典 md_party_type；名称与类型存放在主体 md_party")
    party_id: UUID | None = Field(default=None, description="已有主体时直接引用；不传时按名称新建主体")
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    settlement_method_code: str | None = Field(default=None, max_length=64)
    settlement_cycle_code: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class SupplierUpdate(BaseModel):
    supplier_no: str | None = Field(default=None, max_length=64)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=128)
    category_id: UUID | None = None
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    settlement_method_code: str | None = Field(default=None, max_length=64)
    settlement_cycle_code: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class SupplierItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supplier_no: str
    supplier_name: str = ""  # 取自主体 md_party.display_name
    category_id: UUID | None = None
    category_name: str | None = None
    party_type_code: str = "organization"  # 取自主体
    party_id: UUID
    contact_name: str | None = None
    contact_phone: str | None = None
    settlement_method_code: str | None = None
    settlement_cycle_code: str | None = None
    is_active: bool
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime
    updated_by: UUID | None = None


class SupplierListQuery(PageParams):
    category_id: UUID | None = None
    party_type_code: str | None = None
    is_active: bool | None = None


class SupplierOption(BaseModel):
    id: UUID
    supplier_no: str
    supplier_name: str
    category_name: str | None = None


class SupplierBankAccountWrite(BaseModel):
    account_name: str = Field(..., min_length=1, max_length=128)
    account_no: str = Field(..., min_length=4, max_length=64, description="明文账号，只写不读；保存为密文与脱敏值")
    bank_name: str | None = Field(default=None, max_length=128)
    is_primary: bool = False


class SupplierBankAccountItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supplier_id: UUID
    account_name: str
    account_no_masked: str | None = None
    bank_name: str | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime
