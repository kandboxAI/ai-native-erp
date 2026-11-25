"""现有浏览器助手的传输适配：数组与 SSE 格式由已有 Widget 决定。

常规 /api/ai 会话接口仍使用统一响应；这里仅转换现有 Widget 的协议，
复用公开会话服务，不执行业务查询或将客户端身份参数交给 DSH。
"""
import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.modules.ai_assistant import conversations, service

router = APIRouter(prefix="/api/ai/widget/ai_native", tags=["智能助手界面适配"], include_in_schema=False)
CLIENT_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,128}$"


class WidgetMessage(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str = Field(pattern=CLIENT_ID_PATTERN)
    request_id: str = Field(default="", max_length=128)
    # 旧界面可发送 route_path 等展示字段；身份、工具与模型均由服务端决定。


def _event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: WidgetMessage, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    access_token = request.headers["authorization"].split(" ", 1)[1]
    async def events():
        try:
            record = await conversations.resolve_conversation(user, body.conversation_id)
            run = await service.send_message(user, UUID(record["session_id"]), body.message, access_token, surface="web")
            await conversations.remember_question(user, record, body.message)
            previous_steps = None
            while True:
                if await request.is_disconnected():
                    return
                # 阶段信息也属于本会话，每次发布前重新验证登录及当前授权。
                current_user = await get_current_user(request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token))
                run = await service.get_run(current_user, run.session_id, run.run_id)
                steps = [item.model_dump(exclude_none=True) for item in run.progress]
                if steps != previous_steps:
                    yield _event("progress", {"steps": steps})
                    previous_steps = steps
                if run.status != "running":
                    break
                yield ": keep-alive\n\n"
                await asyncio.sleep(1)
            if run.answer:
                yield _event("delta", {"delta": run.answer})
            if run.status != "completed":
                yield _event("error", {"message": run.message or "本轮未完成，请重试", "code": run.error_code})
                return
            yield _event("done", {"request_id": body.request_id, "conversation_id": body.conversation_id, "run_id": str(run.run_id)})
        except HTTPException as error:
            message = "登录已失效，请重新登录 ERP 后继续" if error.status_code == 401 else str(error.detail)
            yield _event("error", {"message": message, "code": error.status_code})
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/chat/conversations")
async def list_conversations(limit: int = Query(default=100, ge=1, le=500), user: AuthenticatedUser = Depends(get_current_user)):
    return await conversations.list_conversations(user, limit)


@router.get("/chat/conversations/{client_id}/messages")
async def messages(client_id: str = Path(pattern=CLIENT_ID_PATTERN), limit: int = Query(default=500, ge=1, le=500), user: AuthenticatedUser = Depends(get_current_user)):
    return await conversations.messages(user, client_id, limit)


@router.delete("/chat/conversations/{client_id}/messages")
async def clear(client_id: str = Path(pattern=CLIENT_ID_PATTERN), user: AuthenticatedUser = Depends(get_current_user)):
    await conversations.clear(user, client_id)
    return {"cleared": True}


@router.delete("/chat/conversations/{client_id}")
async def delete(client_id: str = Path(pattern=CLIENT_ID_PATTERN), user: AuthenticatedUser = Depends(get_current_user)):
    await conversations.clear(user, client_id, delete=True)
    return {"deleted": True}


@router.delete("/chat/conversations")
async def delete_all(user: AuthenticatedUser = Depends(get_current_user)):
    await conversations.delete_all(user)
    return {"cleared": True}


@router.get("/skills")
async def skills(user: AuthenticatedUser = Depends(get_current_user)):
    # 首期不向此界面发布文件制作技能；查询工具由 DSH 服务端配置加载。
    return {"skills": []}


@router.get("/audit")
async def audit(user: AuthenticatedUser = Depends(get_current_user)):
    raise HTTPException(501, "当前智能体界面暂不提供审计查询，请使用 ERP 审计功能")
