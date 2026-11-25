from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from . import repository
from .registry import registered_types


# 业务模块使用这些公开能力参与调用方事务，SQL 仍由本模块 Repository 持有。
async def publish(session, **values):
    return await repository.upsert(session, **values)


async def finish(session, todo, *, status_code, user_id=None):
    await repository.close(session, todo, status_code=status_code, user_id=user_id)


async def mark_handled(session, todo, user_ids):
    await repository.mark_handled(session, todo, user_ids)


async def pending_for_type(session, type_key):
    return await repository.pending_for_type(session, type_key)


async def refresh_pending(session, todo, assignees, user_ids, *, title, summary, priority_code, due_at):
    await repository.sync_pending_assignees(session, todo, assignees, user_ids)
    for field, value in dict(title=title, summary=summary, priority_code=priority_code, due_at=due_at).items():
        if getattr(todo, field) != value:
            setattr(todo, field, value)
            todo.updated_at = utc_now()
            session.add(todo)


async def assigned_todo(session, todo_id, user_id, *, lock=False):
    return await repository.assigned(session, todo_id, user_id, lock=lock)


def require_type(key, user):
    adapter = registered_types(user).get(key)
    if adapter is None:
        raise AppException("该待办业务当前不可用", 409)
    return adapter


async def present(session, todo, assignee, user, adapter, *, for_priority=False, as_of=None):
    business = await adapter.present(session, todo, user)
    if business is None:
        return None
    if not for_priority:
        business.pop("priority_summary", None)
    pending = todo.status_code == "pending" and assignee.status_code == "pending"
    actions = business.pop("actions", []) if pending else []
    targets = business.pop("targets", {"web": business.get("path", "")})
    return {"id": str(todo.id), "todo_type_key": todo.todo_type_key, "type_label": adapter.label,
            "source_id": str(todo.source_id), "title": todo.title, "summary": todo.summary,
            "status_code": todo.status_code, "assignee_status_code": assignee.status_code,
            "priority_code": todo.priority_code, "arrived_at": todo.arrived_at, "due_at": todo.due_at,
            **business, "targets": targets, "path": targets.get("web", ""), "actions": actions,
            "is_overdue": pending and todo.due_at is not None and todo.due_at < (as_of or utc_now())}


async def mine(query, user, *, for_priority=False):
    as_of = utc_now()
    adapters = registered_types(user)
    from .projection import pending_projections, merged_page
    projected, projected_total = ([], 0) if for_priority else await pending_projections(
        user, query.keyword, query.page * query.page_size)
    merged = bool(projected_total)
    fetch_query = query.model_copy(update={"page": 1, "page_size": query.page * query.page_size}) if merged else query
    async with get_session_context() as session:
        items = []
        sources = {key: await adapter.sources(session, user) for key, adapter in adapters.items()}
        rows, total = await repository.mine(session, user.user_id, fetch_query, sources, as_of=as_of) if sources else ([], 0)
        for todo, assignee in rows:
            adapter = adapters.get(todo.todo_type_key)
            if adapter:
                item = await present(session, todo, assignee, user, adapter, for_priority=for_priority, as_of=as_of)
                if item is not None:
                    items.append(item)
        return {"items": merged_page(items + projected, query) if merged else items, "total": total + projected_total,
                "page": query.page, "page_size": query.page_size}


async def detail(todo_id, user):
    async with get_session_context() as session:
        pair = await repository.assigned(session, todo_id, user.user_id)
        if pair is None:
            raise AppException("待办不存在或无权查看", 404)
        todo, assignee = pair
        item = await present(session, todo, assignee, user, require_type(todo.todo_type_key, user))
        if item is None:
            raise AppException("待办不存在或无权查看", 404)
        if assignee.read_at is None:
            assignee.read_at = utc_now()
            session.add(assignee)
            await session.commit()
        return item


async def act(todo_id, action_key, body, user):
    async with get_session_context() as session:
        pair = await repository.assigned(session, todo_id, user.user_id)
        if pair is None:
            raise AppException("待办不存在或无权办理", 404)
        todo, assignee = pair
        adapter = require_type(todo.todo_type_key, user)
        item = await present(session, todo, assignee, user, adapter)
        if item is None or action_key not in {a["key"] for a in item["actions"]}:
            raise AppException("当前不可执行该待办操作，请刷新后重试", 409)
        # 处理器负责业务锁与事务，详情页和待办入口共用业务校验。
        return await adapter.execute(todo_id, action_key, body, user)


async def create(body, user):
    async with get_session_context() as session:
        todo = await create_in_session(session, body, user)
        await session.commit()
        return {"id": str(todo.id)}


async def create_in_session(session, body, user):
    if "todo:create" not in user.permissions:
        raise AppException("缺少创建业务待办权限", 403)
    adapter = require_type(body.todo_type_key, user)
    if adapter.create is None:
        raise AppException("该类型由业务自动生成，不能手动创建", 422)
    return await adapter.create(session, body, user)


async def assignment_options(org_id, keyword, user):
    from app.auth.scope_filters import ensure_org_access
    ensure_org_access(user, org_id, "todo:create")
    async with get_session_context() as session:
        return await repository.assignment_options(session, org_id, keyword)
