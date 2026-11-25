"""统一待办的只读投影；业务模块通过 todos.py 声明来源，不复制业务状态机。"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.auth.schemas import AuthenticatedUser
from app.db.pagination import PageParams
from app.framework.catalog import iter_module_attr
from app.framework.datetime_local import parse_datetime_input
from app.framework.deployment import module_plugin_owner


@dataclass(frozen=True)
class TodoItem:
    id: str
    title: str
    description: str
    arrived_at: datetime | None
    path: str

    def timestamp(self) -> float:
        return self.arrived_at.timestamp() if self.arrived_at else float("-inf")

    def data(self) -> dict:
        return {**vars(self), "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None}


@dataclass(frozen=True)
class TodoPage:
    items: list[TodoItem]
    total: int


@dataclass(frozen=True)
class TodoSource:
    key: str
    permissions: tuple[str, ...]
    load: Callable[[AuthenticatedUser, int], Awaitable[TodoPage]]
    search: Callable[[AuthenticatedUser, str, int], Awaitable[TodoPage]] | None = None


def todo_datetime(value) -> datetime | None:
    parsed = parse_datetime_input(value) if value else None
    return parsed.replace(tzinfo=timezone.utc) if parsed and parsed.tzinfo is None else parsed


def sources(user: AuthenticatedUser, *, exclude_registered=False):
    registered_modules = {module.__name__.rsplit('.', 1)[0]
                          for module in iter_module_attr("todo_types")} if exclude_registered else set()
    seen = set()
    for module in iter_module_attr("todos"):
        if module.__name__.rsplit('.', 1)[0] in registered_modules:
            continue
        owner = module_plugin_owner(module.__name__.split(".")[-2])
        if owner and owner not in user.enabled_plugin_keys:
            continue
        source = module.TODO_SOURCE
        if source.key in seen:
            raise ValueError(f"重复的待办来源：{source.key}")
        seen.add(source.key)
        if set(source.permissions).issubset(user.permissions):
            yield source


async def list_my_todos(user: AuthenticatedUser, params: PageParams) -> dict:
    # 每个来源仅读取全局分页所需的前 N 项，再统一排序；总数来自各来源的完整计数。
    limit = params.page * params.page_size
    items, total = [], 0
    for source in sources(user):
        result = await source.load(user, limit)
        items.extend(result.items)
        total += result.total
    items.sort(key=lambda item: (item.timestamp(), item.id), reverse=True)
    start = (params.page - 1) * params.page_size
    return dict(items=[item.data() for item in items[start:start + params.page_size]],
                total=total, page=params.page, page_size=params.page_size)
