from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class OrganizationImportOptions(BaseModel):
    allow_update_existing: bool = False


class OrganizationImportRow(BaseModel):
    row_no: int
    node_type: str
    org_name: str
    parent_org_name: str | None = None
    leader_name: str | None = None
    contact_phone: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    department_name: str | None = None
    parent_department_name: str | None = None
    sort_no: int = 0
    is_active: bool = True
    remark: str | None = None

    @field_validator("node_type")
    @classmethod
    def normalize_node_type(cls, value: str) -> str:
        text = str(value or "").strip()
        if text in {"集团", "group"}:
            return "group"
        if text in {"组织", "organization"}:
            return "organization"
        if text in {"部门", "department"}:
            return "department"
        raise ValueError("类型必须为集团、组织或部门")


class OrganizationImportError(BaseModel):
    sheet: str
    row: int
    field: str | None = None
    message: str


class OrganizationImportWarning(BaseModel):
    sheet: str
    row: int
    message: str


class OrganizationImportSummary(BaseModel):
    rows: int = 0
    groups: int = 0
    organizations: int = 0
    departments: int = 0


class OrganizationValidationResult(BaseModel):
    valid: bool
    summary: OrganizationImportSummary
    errors: list[OrganizationImportError] = Field(default_factory=list)
    warnings: list[OrganizationImportWarning] = Field(default_factory=list)


class OrganizationImportResult(OrganizationValidationResult):
    created_groups: int = 0
    updated_groups: int = 0
    created_organizations: int = 0
    updated_organizations: int = 0
    created_departments: int = 0
    updated_departments: int = 0
