from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator,model_validator
from app.db.pagination import PageParams


class ArchiveQuery(PageParams):
    org_id: UUID | None = None
    is_active: bool | None = None
    applicable_process_id: UUID | None = None
    generic_equipment_only: bool = False


class ArchiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    org_id: UUID
    record_no: str = Field(min_length=1, max_length=64)
    record_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4000)
    sort_no: int = Field(default=0, ge=0, le=100000)
    is_active: bool = True
    version_no: int | None = Field(default=None, ge=1)


class CustomerBody(ArchiveBody):
    reconciliation_mode_code: Literal["by_item", "by_order"] = "by_item"


class RequirementBody(ArchiveBody):
    pricing_description: str | None = Field(default=None, max_length=1000)


class ProcessBody(ArchiveBody):
    project_stage_id: UUID | None = None
    requirement_id: UUID | None = None
    processing_type_code: Literal["in_house", "outsourced", "purchased"] = "in_house"
    is_piecework: bool = False
    is_quality_required: bool = False
    is_equipment_required: bool | None = None
    execution_kind_code: Literal["machine","manual","inspection","machine_inspection","external"] | None = None

    @model_validator(mode="after")
    def machine_kind(self):
        if self.execution_kind_code:
            required=self.execution_kind_code in {"machine","machine_inspection"}
            if self.is_equipment_required is not required:raise ValueError("执行类别与是否占用本厂机器必须一致")
            if (self.execution_kind_code=="external")!=(self.processing_type_code=="outsourced"):raise ValueError("委外类型与执行类别不一致")
        return self
    previous_process_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("previous_process_ids")
    @classmethod
    def unique_previous(cls, values):
        if len(set(values)) != len(values): raise ValueError("前置工艺不能重复")
        return values


class EquipmentBody(ArchiveBody):
    process_id: UUID | None = None
    process_ids: list[UUID] | None = Field(default=None, max_length=100)
    work_center_name: str | None = Field(default=None, max_length=128)

    @field_validator("process_ids")
    @classmethod
    def unique_processes(cls, values):
        if values is not None and len(set(values)) != len(values):
            raise ValueError("设备适用工艺不能重复")
        return values
