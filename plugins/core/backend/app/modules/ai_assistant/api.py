from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import StreamingResponse
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from . import service, conversations, write_approval
from .schemas import SendMessage
from .events import run_events

router = APIRouter(prefix="/api/ai", tags=["智能助手"])


class InternalWriteApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    run_id: UUID
    preview: str = Field(min_length=1, max_length=8192)


class WriteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


@router.post("/internal/write-approval", include_in_schema=False)
async def request_write_approval(body: InternalWriteApproval,
                                 approval_token: str = Header(alias="x-erp-approval-token"),
                                 user: AuthenticatedUser = Depends(get_current_user)):
    outcome = await write_approval.request_decision(user, body.session_id, body.run_id, approval_token, body.preview)
    return success_response({"outcome": outcome})


@router.get("/write-approvals")
async def pending_write_approvals(surface: Literal["web", "miniapp"] = Query(...),
                                  user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await write_approval.list_pending(user, surface))


@router.post("/write-approvals/{approval_id}/decision")
async def decide_write_approval(approval_id: UUID, body: WriteDecision,
                                user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await write_approval.decide(user, approval_id, body.approved))


@router.post("/sessions")
async def create_session(user: AuthenticatedUser = Depends(get_current_user)):
    return success_response((await conversations.create_session(user)).model_dump(mode="json"))


@router.get("/sessions")
async def list_sessions(offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
                        user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await conversations.list_session_page(user, offset, limit))


@router.get("/sessions/{session_id}/messages")
async def history(session_id: UUID, limit: int = Query(default=500, ge=1, le=500), user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await conversations.session_history(user, session_id, limit))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    await conversations.delete_session(user, session_id)
    return success_response({"deleted": True})


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: UUID, body: SendMessage, request: Request,
                       user: AuthenticatedUser = Depends(get_current_user)):
    token = request.headers["authorization"].split(" ", 1)[1]
    result = await service.send_message(user, session_id, body.content, token)
    await conversations.remember_session_question(user, session_id, result.question)
    return success_response(result.model_dump(mode="json"))


@router.get("/sessions/{session_id}/runs/{run_id}")
async def get_run(session_id: UUID, run_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response((await service.get_run(user, session_id, run_id)).model_dump(mode="json"))


@router.get("/sessions/{session_id}/runs/{run_id}/events")
async def stream_run(session_id: UUID, run_id: UUID, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    await service.get_run(user, session_id, run_id)
    return StreamingResponse(run_events(request, user, session_id, run_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
