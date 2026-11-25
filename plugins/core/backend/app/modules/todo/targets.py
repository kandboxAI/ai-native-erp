"""业务插件声明现有菜单跳转；待办不会新增菜单或注册临时路由。"""
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.framework.catalog import iter_module_attr
from app.framework.deployment import module_plugin_owner
from app.modules.menu.service import service as menus


@dataclass(frozen=True)
class TodoWebTarget:
    type_key: str
    menu_key: str
    permissions: tuple[str, ...]
    query_param: str = "id"


async def authorized_web_target(session, user, type_key, source_id):
    candidates = []
    for module in iter_module_attr("todo_targets"):
        owner = module_plugin_owner(module.__name__.split(".")[2])
        if owner and owner not in user.enabled_plugin_keys:
            continue
        candidates.extend(item for item in module.TODO_WEB_TARGETS
            if item.type_key == type_key and set(item.permissions) <= set(user.permissions))
    if not candidates:
        return None
    key = ("todo_authorized_menu_paths", user.user_id)
    if key not in session.info:
        session.info[key] = {}
    cache = session.info[key]
    missing = {item.menu_key for item in candidates} - cache.keys()
    if missing:
        paths = await menus.authorized_paths_in_session(session, user, missing)
        cache.update({key: paths.get(key) for key in missing})
    for item in candidates:
        path = cache.get(item.menu_key)
        if path:
            target = urlsplit(path)
            query = dict(parse_qsl(target.query))
            query[item.query_param] = str(source_id)
            return urlunsplit(("", "", target.path, urlencode(query), target.fragment))
    return None
