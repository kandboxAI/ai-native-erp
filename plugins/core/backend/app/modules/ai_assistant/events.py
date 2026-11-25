"""受控任务的文字及阶段快照流；每次发布重新校验身份、权限与数据范围。"""
import asyncio
import json

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies import get_current_user
from . import service


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_events(request, user, session_id, run_id):
    token = request.headers["authorization"].split(" ", 1)[1]
    previous = None
    previous_progress = None
    try:
        while not await request.is_disconnected():
            run = await service.get_run(user, session_id, run_id)
            steps = [item.model_dump(exclude_none=True) for item in run.progress]
            answer_changed = run.answer != previous or run.status != "running"
            if answer_changed or steps != previous_progress:
                current = await get_current_user(request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
                run = await service.get_run(current, session_id, run_id)
                steps = [item.model_dump(exclude_none=True) for item in run.progress]
                if steps != previous_progress:
                    yield event("progress", {"steps": steps})
                    previous_progress = steps
                if run.answer != previous or run.status != "running":
                    previous = run.answer
                    yield event("snapshot", {"answer": run.answer, "status": run.status})
                if run.status != "running":
                    if run.status != "completed":
                        yield event("error", {"message": run.message or "本轮未完成，请重试", "code": run.error_code})
                    else:
                        yield event("done", {"run_id": str(run_id)})
                    return
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)
    except HTTPException as error:
        message = "登录已失效，请重新登录 ERP 后继续" if error.status_code == 401 else str(error.detail)
        yield event("error", {"message": message, "code": error.status_code})
