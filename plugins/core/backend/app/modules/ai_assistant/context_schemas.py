"""当前用户 AI 上下文契约；业务身份不能由客户端提交。"""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PersonalInstructions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(default="", max_length=2000)


class PersonalTemplatePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool = Field(strict=True)


class PromptTemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_name: str = Field(min_length=1, max_length=128)
    role_id: UUID
    instructions: str = Field(min_length=1, max_length=4000)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_target(self):
        if not self.template_name.strip() or not self.instructions.strip():
            raise ValueError("模板名称和正文不能为空")
        return self


class PositionKnowledge(BaseModel):
    position_id: UUID
    position_name: str
    knowledge_base_id: UUID
    knowledge_base_name: str
    overview_document_id: UUID | None = None
    version_no: int | None = None
    summary: str = ""
    can_contribute: bool = False


class ContextContribution(BaseModel):
    """提供器只返回本人岗位说明和安全变量，不返回业务记录或人员姓名。"""
    facts: list[str] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)
    position_knowledge: list[PositionKnowledge] = Field(default_factory=list)
