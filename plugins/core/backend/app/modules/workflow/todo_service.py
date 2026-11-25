"""工作流拥有来源状态；调用待办公共能力同步，不在通知投递中创建审批事项。"""
from app.modules.todo import service as todos
from .runtime.repository import APPROVAL_TODO_TYPE, runtime_repository


def task_targets(task_id):
    return {"web": f"/system/workflow-task/approval?task_id={task_id}",
            "miniapp": f"/pages/todo-detail/index?id={task_id}"}


async def sync_task(session, task, user_id=None):
    candidates = await runtime_repository.candidates(session, task.id)
    todo = await todos.publish(
        session, user_ids=candidates, todo_type_key=APPROVAL_TODO_TYPE, source_id=task.id,
        dedup_key=f"{APPROVAL_TODO_TYPE}:{task.id}", title=task.task_name,
        org_id=task.org_id, arrived_at=task.arrived_at, created_by=user_id, updated_by=user_id,
    )
    acted = await runtime_repository.approved_user_ids(session, task.id)
    await todos.mark_handled(session, todo, acted)
    if task.status_code != "pending":
        await todos.finish(session, todo,
            status_code="completed" if task.status_code == "completed" else "cancelled",
            user_id=task.completed_by)


async def sync_instance(session, instance_id, user_id=None):
    await session.flush()
    for task in await runtime_repository.tasks_for_instances(session, [instance_id]):
        await sync_task(session, task, user_id)


async def repair_pending_assignments(session, user):
    tasks = await runtime_repository.pending_tasks_missing_todo(session, user)
    for task in tasks:
        await sync_task(session, task)
    if tasks:
        await session.commit()
