"""合并只读业务待办与统一待办时，不重复、不丢分页、不放宽业务范围。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from app.framework import todos
from app.framework.todos import TodoSource, TodoPage, TodoItem
from app.modules.todo import service, projection
from app.modules.todo.schemas import TodoQuery

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def projected(identifier, minute=0):
    return TodoItem(identifier, identifier, "待报价", NOW - timedelta(minutes=minute), "/business/quote")


def test_registered_modules_skip_legacy_projection_but_independent_plugins_remain(monkeypatch):
    modules = {
        "todo_types": [NS(__name__="app.modules.workflow.todo_types")],
        "todos": [NS(__name__="app.modules.workflow.todos", TODO_SOURCE=TodoSource("workflow", (), AsyncMock())),
                  NS(__name__="app.modules.business.todos", TODO_SOURCE=TodoSource("business", ("quote:list",), AsyncMock()))],
    }
    monkeypatch.setattr(todos, "iter_module_attr", lambda key: modules[key])
    monkeypatch.setattr(todos, "module_plugin_owner", lambda name: "business" if name == "business" else None)
    user = NS(permissions=["quote:list"], enabled_plugin_keys=["business"])
    assert [source.key for source in todos.sources(user, exclude_registered=True)] == ["business"]
    user.enabled_plugin_keys = []
    assert list(todos.sources(user, exclude_registered=True)) == []
    assert [source.key for source in todos.sources(user)] == ["workflow"]


def test_keyword_uses_source_search_and_keeps_full_filtered_total(monkeypatch):
    load = AsyncMock()
    search = AsyncMock(return_value=TodoPage([projected("BJ-1")], 37))
    monkeypatch.setattr(projection, "sources", lambda *args, **kw: [TodoSource("quote", (), load, search)])
    rows, total = asyncio.run(projection.pending_projections(NS(), "BJ", 6))
    assert total == 37 and len(rows) == 1
    assert rows[0]["is_projection"] and rows[0]["actions"] == []
    search.assert_awaited_once_with(NS(), "BJ", 6)
    load.assert_not_awaited()


def test_sources_without_search_do_not_claim_unfiltered_keyword_totals(monkeypatch):
    load = AsyncMock()
    monkeypatch.setattr(projection, "sources", lambda *args, **kw: [TodoSource("quote", (), load)])
    assert asyncio.run(projection.pending_projections(NS(), "missing", 10)) == ([], 0)
    load.assert_not_awaited()


def test_global_page_combines_priority_deadlines_and_projection_arrival(monkeypatch):
    @asynccontextmanager
    async def session():
        yield NS()
    monkeypatch.setattr(service, "get_session_context", session)
    monkeypatch.setattr(service, "registered_types", lambda user: {"work": NS(sources=AsyncMock(return_value=[]))})
    rows = [dict(id="urgent", priority_code="urgent", arrived_at=NOW, due_at=None),
            dict(id="due", priority_code="normal", arrived_at=NOW, due_at=NOW),
            dict(id="ordinary", priority_code="normal", arrived_at=NOW-timedelta(minutes=2), due_at=None)]
    read = AsyncMock(return_value=([(NS(todo_type_key="work", **item), NS()) for item in rows], 3))
    monkeypatch.setattr(service.repository, "mine", read)
    async def present(_session, todo, *_args, **_kwargs):
        return vars(todo)
    monkeypatch.setattr(service, "present", present)
    monkeypatch.setattr(projection, "pending_projections", AsyncMock(return_value=(
        [dict(id="quote", priority_code="normal", arrived_at=NOW-timedelta(minutes=1), due_at=None)], 1)))
    result = asyncio.run(service.mine(TodoQuery(page=2, page_size=2), NS(user_id="user")))
    assert result["total"] == 4
    assert [item["id"] for item in result["items"]] == ["quote", "ordinary"]
    fetched = read.await_args.args[2]
    assert (fetched.page, fetched.page_size) == (1, 4)


def test_projection_only_user_sees_business_tasks_without_persisted_assignees(monkeypatch):
    @asynccontextmanager
    async def session():
        yield NS()
    monkeypatch.setattr(service, "get_session_context", session)
    monkeypatch.setattr(service, "registered_types", lambda user: {})
    monkeypatch.setattr(projection, "pending_projections", AsyncMock(return_value=(
        [dict(id="quote", priority_code="normal", arrived_at=NOW, due_at=None)], 1)))
    read = AsyncMock()
    monkeypatch.setattr(service.repository, "mine", read)
    result = asyncio.run(service.mine(TodoQuery(), NS(user_id="user")))
    assert result["total"] == 1 and result["items"][0]["id"] == "quote"
    read.assert_not_awaited()
