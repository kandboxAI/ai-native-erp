"""已有流程审批待办通过公开服务参与统一列表。"""
from app.framework.todos import TodoItem, TodoPage, TodoSource, todo_datetime
from app.modules.workflow.task.schemas import WorkflowTaskListQuery
from app.modules.workflow.task.service import workflow_task_service


async def load(user, limit):
    items, total, page = [], 0, 1
    while len(items) < limit:
        result = await workflow_task_service.list_tasks(
            WorkflowTaskListQuery(page=page, page_size=100, status_code="pending"), user)
        total = result["total"]
        items.extend(TodoItem(
            id=f"workflow:{row['id']}",
            title=row.get("business_summary") or row["task_name"] or row["business_type_code"],
            description=row["task_name"] or "待我审批",
            arrived_at=todo_datetime(row.get("arrived_at")),
            path="/system/workflow-task/index",
        ) for row in result["items"])
        if not result["items"] or len(items) >= total:
            break
        page += 1
    return TodoPage(items[:limit], total)


TODO_SOURCE = TodoSource("workflow", ("workflow_task:list", "workflow_task:complete"), load)
