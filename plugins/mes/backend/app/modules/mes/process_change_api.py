from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_permissions
from app.core.response import success_response

from .process_change_service import MANAGE, process_change_service

LIST = "mes:work_order:list"
router = APIRouter(prefix="/work-orders/{order_id}/process-changes")


class ProcessChangeBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    version_no: int = Field(ge=1)
    operation_id: UUID
    new_process_id: UUID
    new_equipment_id: UUID | None = None
    disposition_code: Literal["keep", "reinspect", "rework"]
    reason: str = Field(min_length=1, max_length=1000)
    starter_choices: dict[str, list[UUID]] | None = None


class DispositionBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    note: str = Field(default="", max_length=1000)


@router.get("", summary="查询工单工艺变更记录及可选工序")
async def overview(order_id: UUID, user=Depends(require_permissions([LIST]))):
    return success_response(await process_change_service.overview(order_id, user))


@router.post("", summary="提交工艺变更审批及已加工件处置安排")
async def submit(order_id: UUID, body: ProcessChangeBody, user=Depends(require_permissions([LIST, MANAGE]))):
    return success_response(await process_change_service.submit(order_id, body, user))


@router.post("/{change_id}/{action}", summary="确认工艺变更处置或安排返工")
async def dispose(order_id: UUID, change_id: UUID, action: Literal["apply", "pass", "rework", "arrange", "cancel"],
                  body: DispositionBody, user=Depends(require_permissions([LIST]))):
    return success_response(await process_change_service.dispose(order_id, change_id, action, body, user))
