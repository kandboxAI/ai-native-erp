from sqlalchemy import case, and_, or_, func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.framework.db.models import utc_now
from .models import SysTodo, SysTodoAssignee


async def upsert(session, *, user_ids, **values):
    # 唯一键由数据库执行，定时扫描和业务重试共用同一事项。
    await session.execute(insert(SysTodo).values(**values).on_conflict_do_nothing(index_elements=["dedup_key"]))
    todo = (await session.exec(select(SysTodo).where(SysTodo.dedup_key == values["dedup_key"]))).one()
    if todo.status_code == "pending":
        for user_id in set(user_ids):
            await session.execute(insert(SysTodoAssignee).values(
                todo_id=todo.id, org_id=todo.org_id, user_id=user_id,
                created_by=values.get("created_by"), updated_by=values.get("created_by"),
            ).on_conflict_do_nothing(index_elements=["todo_id", "user_id"]))
    return todo


async def assigned(session, todo_id, user_id, *, lock=False):
    stmt = select(SysTodo, SysTodoAssignee).join(SysTodoAssignee, SysTodoAssignee.todo_id == SysTodo.id).where(
        SysTodo.id == todo_id, SysTodoAssignee.user_id == user_id)
    return (await session.exec(stmt.with_for_update() if lock else stmt)).first()


async def pending_for_type(session, type_key):
    rows = await session.exec(select(SysTodo, SysTodoAssignee).outerjoin(
        SysTodoAssignee, SysTodoAssignee.todo_id == SysTodo.id,
    ).where(SysTodo.todo_type_key == type_key, SysTodo.status_code == "pending"))
    result = {}
    for todo, assignee in rows:
        _, assignees = result.setdefault(todo.source_id, (todo, {}))
        if assignee is not None:
            assignees[assignee.user_id] = assignee
    return result


async def sync_pending_assignees(session, todo, assignees, user_ids):
    for user_id, assignee in assignees.items():
        status = "pending" if user_id in user_ids else "cancelled"
        if assignee.status_code != status:
            assignee.status_code = status
            assignee.handled_at = None
            assignee.updated_at = utc_now()
            session.add(assignee)
    for user_id in user_ids - assignees.keys():
        await session.execute(insert(SysTodoAssignee).values(
            todo_id=todo.id, org_id=todo.org_id, user_id=user_id,
        ).on_conflict_do_nothing(index_elements=["todo_id", "user_id"]))


async def mine(session, user_id, query, source_queries, *, as_of=None):
    stmt = select(SysTodo, SysTodoAssignee).join(SysTodoAssignee, SysTodoAssignee.todo_id == SysTodo.id).where(
        SysTodoAssignee.user_id == user_id, SysTodoAssignee.status_code == "pending", SysTodo.status_code == "pending")
    stmt = stmt.where(or_(*(and_(SysTodo.todo_type_key == key, SysTodo.source_id.in_(sources))
                            for key, sources in source_queries.items())))
    if query.keyword:
        stmt = stmt.where(SysTodo.title.icontains(query.keyword, autoescape=True))
    if not query.include_overdue:
        stmt = stmt.where(or_(SysTodo.due_at.is_(None), SysTodo.due_at >= (as_of or utc_now())))
    total = (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    ordering = [SysTodo.arrived_at.desc(), SysTodo.id.desc()] if query.sort_by == "arrived_at" else [
        case((SysTodo.priority_code == "urgent", 0), (SysTodo.priority_code == "important", 1), else_=2),
        SysTodo.due_at.asc().nulls_last(), SysTodo.arrived_at.desc(), SysTodo.id,
    ]
    rows = (await session.exec(stmt.order_by(*ordering)
        .offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
    return rows, total


async def close(session, todo, *, status_code, user_id=None):
    todo.status_code = status_code
    todo.updated_at, todo.updated_by = utc_now(), user_id
    if status_code == "completed":
        todo.completed_at, todo.completed_by = utc_now(), user_id
    session.add(todo)
    rows = (await session.exec(select(SysTodoAssignee).where(SysTodoAssignee.todo_id == todo.id))).all()
    for row in rows:
        if row.status_code == "pending":
            row.status_code = "handled" if row.user_id == user_id and status_code == "completed" else "cancelled"
            row.handled_at = utc_now() if row.status_code == "handled" else None
            row.updated_at, row.updated_by = utc_now(), user_id
            session.add(row)
    await session.flush()


async def mark_handled(session, todo, user_ids):
    rows = (await session.exec(select(SysTodoAssignee).where(
        SysTodoAssignee.todo_id == todo.id, SysTodoAssignee.user_id.in_(user_ids),
        SysTodoAssignee.status_code == "pending"))).all()
    for row in rows:
        row.status_code, row.handled_at, row.updated_at = "handled", utc_now(), utc_now()
        row.updated_by = row.user_id
        session.add(row)


async def assignment_options(session, org_id, keyword):
    from app.modules.notification_center.repository import repository as notifications
    candidates = await notifications.all_user_ids(session, org_id)
    from app.modules.user_profile.models import SysUser
    from app.modules.role.models import SysRole
    users = (await session.exec(select(SysUser).where(SysUser.id.in_(candidates),
        SysUser.display_name.icontains(keyword, autoescape=True)).order_by(SysUser.display_name).limit(50))).all()
    roles = (await session.exec(select(SysRole).where(SysRole.deleted_at.is_(None), SysRole.is_active.is_(True))
                               .order_by(SysRole.role_name))).all()
    return {"users": [{"value": str(row.id), "label": row.display_name} for row in users],
            "roles": [{"value": str(row.id), "label": row.role_name} for row in roles]}
