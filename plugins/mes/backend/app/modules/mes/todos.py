"""询价交接待办由真实业务状态派生，不创建流程实例或发送通知。"""
from urllib.parse import urlencode

from app.framework.db.session import get_session_context
from app.framework.todos import TodoItem, TodoPage, TodoSource, todo_datetime
from .quotation_repository import repository


async def load(user, limit, *, keyword=""):
    async with get_session_context() as session:
        rows, total = await repository.todos(session, user, limit, **({"keyword": keyword} if keyword else {}))
        items = []
        for row in rows:
            if row.status_code == "final_review":
                label, mode = "待报价复审", "final_review"
            elif row.status_code == "review":
                label, mode = ("复审退回初审" if row.return_reason else "待报价初审"), "review"
            elif row.status_code == "draft":
                label, mode = "待补充询价资料", "sales"
            else:
                label, mode = ("报价退回修改" if row.return_reason else "待工程报价"), "engineering"
            items.append(TodoItem(
                id=f"mes.quotation:{row.id}:{row.status_code}",
                title=f"{row.quote_no} · R{row.revision} · {row.title}",
                description=label,
                arrived_at=todo_datetime(row.updated_at or row.created_at),
                path="/mes/quotations?" + urlencode({"quote_id": str(row.id), "mode": mode}),
            ))
        return TodoPage(items, total)


async def search(user, keyword, limit):
    return await load(user, limit, keyword=keyword)


TODO_SOURCE = TodoSource("mes.quotation", ("mes:quotation:list",), load, search)
