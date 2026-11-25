from app.framework.db.session import get_session_context
from app.framework.jobs import PeriodicJob
from app.modules.todo.lifecycle_service import tables_available
from .models import InvMaterialRequisition
from .todo_repository import sync_page
from .todo_types import sync_todos


async def sync_requisition_todos():
    cursor = None
    while True:
        async with get_session_context() as session, session.begin():
            if not await tables_available(session, "sys_todo", "sys_todo_assignee", InvMaterialRequisition.__tablename__):
                return
            rows = await sync_page(session, cursor)
            if not rows:
                return
            for row in rows:
                await sync_todos(session, row)
            cursor = rows[-1].id


JOBS = [PeriodicJob("inventory_requisition.todos", 60, sync_requisition_todos)]
