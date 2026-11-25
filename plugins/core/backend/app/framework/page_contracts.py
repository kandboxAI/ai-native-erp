"""插件声明通用页面可使用的后端实体；校验过程不访问数据库。"""

from dataclasses import dataclass, field
from collections.abc import Iterable

from app.framework.catalog import MenuDef, iter_module_attr


@dataclass(frozen=True)
class PageContract:
    component: str
    selector_key: str
    ready_values: frozenset[str]
    unbound_values: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


def check_page_contracts(menus: Iterable[MenuDef], contracts=None) -> dict:
    """只核对当前组件与接口的绑定；不据此判定整个业务是否已实现。"""
    if contracts is None:
        contracts = [item for module in iter_module_attr("page_contracts") for item in getattr(module, "PAGE_CONTRACTS", ())]
    by_component = {}
    for contract in contracts:
        if contract.component in by_component:
            raise ValueError(f"页面契约重复：{contract.component}")
        if set(contract.unbound_values) & contract.ready_values:
            raise ValueError(f"页面契约同时声明已绑定和未绑定：{contract.component}")
        if any(not reason.strip() for reason in contract.unbound_values.values()):
            raise ValueError(f"页面契约缺少接口未绑定说明：{contract.component}")
        if set(contract.aliases) & (contract.ready_values | set(contract.unbound_values)):
            raise ValueError(f"页面契约别名覆盖实体：{contract.component}")
        if not set(contract.aliases.values()) <= contract.ready_values:
            raise ValueError(f"页面契约别名未指向已绑定实体：{contract.component}")
        by_component[contract.component] = contract
    ready = []
    unbound = []
    for menu in menus:
        component = (menu.component or "").removeprefix("/").removesuffix(".vue")
        contract = by_component.get(component)
        if contract is None:
            continue
        meta = (menu.flex_form.get("route") or {}).get("meta") or {}
        value = meta.get(contract.selector_key)
        canonical = contract.aliases.get(value, value) if isinstance(value, str) else None
        entry = {"menu_key": menu.key, "path": menu.path, "entity": value}
        if canonical in contract.ready_values:
            ready.append(entry)
        elif canonical in contract.unbound_values:
            unbound.append({**entry, "message": contract.unbound_values[canonical]})
        else:
            raise ValueError(f"菜单 {menu.key} ({menu.path}) 的页面 {component} 使用未登记的 {contract.selector_key}：{value}")
    return {"ready": ready, "unbound": unbound}
