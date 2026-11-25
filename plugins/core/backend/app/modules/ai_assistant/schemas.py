from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)


class AssistantSession(BaseModel):
    session_id: UUID


class AssistantProgress(BaseModel):
    key: str
    label: str
    status: Literal["running", "done", "error"]
    detail: str = ""
    elapsed_ms: int | None = None
    error_code: str | None = None


class AssistantRun(BaseModel):
    run_id: UUID
    session_id: UUID
    status: Literal["running", "completed", "failed", "interrupted"]
    question: str
    answer: str = ""
    message: str = ""
    finish_reason: str | None = None
    error_code: str | None = None
    created_at: datetime | None = None
    progress: list[AssistantProgress] = Field(default_factory=list)
