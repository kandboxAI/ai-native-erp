from dataclasses import dataclass
from typing import Awaitable, Callable

from app.framework.catalog import iter_module_attr
from app.framework.deployment import module_plugin_owner


@dataclass(frozen=True)
class TodoType:
    key: str
    label: str
    # 处理器必须检查当前业务权限、范围与来源状态；不可读返回 None。
    present: Callable[..., Awaitable[dict | None]]
    execute: Callable[..., Awaitable[dict]]
    sources: Callable[..., Awaitable[object]]
    create: Callable[..., Awaitable[object]] | None = None


def registered_types(user=None) -> dict[str, TodoType]:
    result = {}
    for module in iter_module_attr("todo_types"):
        if user is not None:
            owner = module_plugin_owner(module.__name__.split(".")[2])
            if owner and owner not in user.enabled_plugin_keys:
                continue
        for item in module.TODO_TYPES:
            if item.key in result:
                raise ValueError(f"重复待办类型：{item.key}")
            result[item.key] = item
    return result
