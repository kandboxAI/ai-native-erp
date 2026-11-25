"""工作流待办适配器；审批资格和快捷通过沿用工作流公开能力。"""
from app.modules.todo.registry import TodoType
from app.modules.workflow.task.service import workflow_task_service
from app.modules.workflow.runtime.service import workflow_runtime_service
from app.modules.workflow.runtime.repository import APPROVAL_TODO_TYPE, runtime_repository
from app.modules.workflow.todo_service import repair_pending_assignments


async def present(session, todo, user):
    return await workflow_task_service.todo_item(session, todo.source_id, user)


async def execute(todo_id, action_key, body, user):
    from app.framework.db.session import get_session_context
    from app.modules.todo.service import assigned_todo
    from app.core.exceptions import AppException
    async with get_session_context() as session:
        pair = await assigned_todo(session, todo_id, user.user_id)
        if pair is None or action_key not in {"approve", "retry_analysis"}:
            raise AppException("待办不存在或操作不可用", 409)
        item = await present(session, pair[0], user)
        if not item or action_key not in {a["key"] for a in item["actions"]}:
            raise AppException("当前操作不可用，请刷新待办", 409)
        task_id = pair[0].source_id
    if action_key == "retry_analysis":
        return await workflow_task_service.retry_analysis(task_id, user)
    return await workflow_runtime_service.advance_task(task_id=task_id, comment=body.comment or "待办快捷同意", current_user=user)


async def sources(session, user):
    await repair_pending_assignments(session, user)
    return runtime_repository.todo_sources(user)


TODO_TYPES = [TodoType(APPROVAL_TODO_TYPE, "审批", present, execute, sources)]
