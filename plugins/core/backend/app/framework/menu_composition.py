"""插件声明的导航组合：只处理已授权的响应树，不改变目录归属与数据库授权。"""
from dataclasses import dataclass

from app.framework.catalog import iter_module_attr


@dataclass(frozen=True)
class MenuComposition:
    plugin_key: str
    source_key: str
    target_key: str
    aliases: tuple[tuple[str, str], ...] = ()
    # 移动的菜单标识与目标目录内排序。
    placements: tuple[tuple[str, int], ...] = ()
    route_meta: tuple[tuple[str, str], ...] = ()
    # 指定 placements 中仅保留授权路由、不展示在导航里的菜单。
    hidden_placements: tuple[str, ...] = ()


@dataclass(frozen=True)
class MenuViewRequirement:
    """消费者要求保留共享菜单的默认视图；只声明自身需求。"""
    plugin_key: str
    menu_key: str


def compose_menus(roots: list[dict], enabled_plugins: set[str]) -> list[dict]:
    """输入为本次请求新建的树；不增加节点、不放宽权限、不覆盖自定义上级。"""
    nodes = {}

    def index(children):
        for node in children:
            nodes[node["menu_key"]] = node
            index(node.get("children", []))

    index(roots)
    modules = tuple(iter_module_attr("catalog"))
    preserved = {requirement.menu_key for module in modules
        for requirement in getattr(module, "MENU_VIEW_REQUIREMENTS", ())
        if requirement.plugin_key in enabled_plugins}
    compositions = [spec for module in modules for spec in getattr(module, "MENU_COMPOSITIONS", ())
        if spec.plugin_key in enabled_plugins]
    composers_by_source: dict[str, set[str]] = {}
    for spec in compositions:
        composers_by_source.setdefault(spec.source_key, set()).add(spec.plugin_key)
    for spec in compositions:
        # 有消费者要求默认视图，或多个插件竞争同一来源时，保留原导航。
        # 同一插件可把来源菜单分别归入自己的多个目录。
        if spec.source_key in preserved or len(composers_by_source[spec.source_key]) > 1:
            continue
        source, target = nodes.get(spec.source_key), nodes.get(spec.target_key)
        if not source or not target or not target.get("is_visible", True):
            continue
        children = source.get("children", [])
        direct = {node["menu_key"]: node for node in children}
        for original, replacement in spec.aliases:
            alias = nodes.get(replacement)
            if original in direct and alias and alias.get("is_visible", True):
                # 保留隐藏路由，旧书签、收藏仍可打开。
                direct[original]["is_visible"] = False
            if original in direct:
                _route_meta(direct[original], spec.route_meta)
        for key, rank in spec.placements:
            node = direct.get(key)
            if node is None or _contains(node, spec.target_key):
                continue
            children.remove(node)
            target.setdefault("children", []).append(node)
            node["parent_id"], node["sort_no"] = target["id"], rank
            if key in spec.hidden_placements:
                node["is_visible"] = False
            _route_meta(node, spec.route_meta)
        target["children"].sort(key=lambda node: node.get("sort_no") or 0)
        if not any(node.get("is_visible", True) for node in children):
            source["is_visible"] = False
    return roots


def _route_meta(node, values):
    flex = dict(node.get("flex_form") or {})
    route = dict(flex.get("route") or {})
    route["meta"] = {**(route.get("meta") or {}), **dict(values)}
    flex["route"] = route
    node["flex_form"] = flex


def _contains(node, key):
    return node["menu_key"] == key or any(_contains(child, key) for child in node.get("children", []))
