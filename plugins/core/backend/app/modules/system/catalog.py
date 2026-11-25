"""系统管理的权限与菜单（组织、部门、用户、角色、权限、菜单、字典、参数、日志）。"""

from dataclasses import replace

from app.framework.catalog import MenuDef, MiniappMenuDef, PermissionDef, crud_permissions

PERMISSIONS = [
    *crud_permissions("organization", "组织", "system"),
    PermissionDef("organization:import", "导入组织架构", "system"),
    *crud_permissions("department", "部门", "system"),
    *crud_permissions("user_profile", "用户", "system", actions=("list", "detail", "create", "update", "delete")),
    PermissionDef("user_profile:reset_password", "重置用户密码", "system"),
    *crud_permissions("user_authorization", "用户组织授权", "system", actions=("list", "detail", "create", "delete")),
    *crud_permissions("user_role", "用户角色", "system", actions=("list", "detail", "create", "delete")),
    *crud_permissions("role", "角色", "system"),
    *crud_permissions("role_permission", "角色权限", "system", actions=("list", "detail", "create", "update", "delete")),
    *crud_permissions("role_menu", "角色菜单", "system", actions=("list", "detail", "create", "delete")),
    *crud_permissions("role_miniapp_menu", "角色小程序菜单", "system", actions=("list", "detail", "create", "delete")),
    *crud_permissions("permission", "权限", "system", actions=("list", "detail", "update")),
    *crud_permissions("menu", "菜单", "system"),
    *crud_permissions("miniapp_menu", "小程序菜单", "system"),
    *crud_permissions("dictionary", "字典", "system"),
    *crud_permissions("dictionary_item", "字典项", "system"),
    *crud_permissions("system_setting", "系统参数", "system", actions=("list", "detail", "update", "export")),
    PermissionDef("operation_log:list", "查询操作日志", "system"),
    PermissionDef("operation_log:detail", "查看操作日志", "system"),
    PermissionDef("login_log:list", "查询登录日志", "system"),
    PermissionDef("online_user:list", "查看在线用户", "system"),
    PermissionDef("online_user:kick", "强制用户下线", "system"),
    PermissionDef("scheduled_task:list", "查看定时任务", "system"),
    PermissionDef("plugin:manage", "管理租户应用", "system"),
]

MENUS = [
    MenuDef("SystemManagement", "系统管理", "directory", path="/system", icon="ri:settings-3-line", sort_no=90),
    MenuDef("SystemUser", "用户管理", "menu", parent_key="SystemManagement", path="/system/user/index", component="system/user/index", icon="ri:admin-line", permission_key="user_profile:list", sort_no=1),
    MenuDef("SystemRole", "角色管理", "menu", parent_key="SystemManagement", path="/system/role/index", component="system/role/index", icon="ri:shield-user-line", previous_icons=("ri:admin-fill", "ri/admin-fill"), permission_key="role:list", sort_no=2),
    MenuDef("SystemMenu", "菜单管理", "menu", parent_key="SystemManagement", path="/system/menu/index", component="system/menu/index", icon="ri:menu-line", previous_icons=("ep:menu", "ep/menu"), permission_key="menu:list", sort_no=3),
    MenuDef("PermissionManagement", "权限管理", "menu", parent_key="SystemManagement", path="/system/permission/index", component="system/permission/index", icon="ri:key-2-line", permission_key="permission:list", sort_no=4),
    MenuDef("SystemDept", "组织架构", "menu", parent_key="SystemManagement", path="/system/dept/index", component="system/dept/index", icon="ri:git-branch-line", permission_key="department:list", sort_no=5),
    MenuDef("MiniappMenuManagement", "小程序菜单管理", "menu", parent_key="SystemManagement", path="/system/miniapp-menu/index", component="system/miniapp-menu/index", icon="ri:apps-2-line", permission_key="miniapp_menu:list", sort_no=6),
    MenuDef("DictionaryManagement", "字典管理", "menu", parent_key="SystemManagement", path="/system/dict/index", component="system/dict/index", icon="ri:book-2-line", permission_key="dictionary:list", sort_no=7),
    MenuDef("SensitiveDataAudit", "敏感数据审计", "menu", parent_key="SystemManagement", path="/system/sensitive-audit/index", component="system/sensitive-audit/index", icon="ri:shield-check-line", permission_key="operation_log:list", sort_no=9),
    MenuDef("PluginManagement", "应用管理", "menu", parent_key="SystemManagement", path="/system/plugins/index", component="system/plugins/index", icon="ri:apps-line", permission_key="plugin:manage", sort_no=8, previous_names=("能力包管理",)),
]

# 小程序菜单（门户：字典 sys_miniapp_portal）。页面路径对应 miniprogram/src/pages。
MINIAPP_MENUS = [
    MiniappMenuDef("standard", "home", "首页", path="/pages/home/index", sort_no=1),
    MiniappMenuDef("standard", "todo", "统一待办", path="/pages/todo/index", sort_no=2),
    MiniappMenuDef("standard", "messages", "消息", path="/pages/messages/index", sort_no=3),
    MiniappMenuDef("standard", "profile", "我的", path="/pages/profile/index", sort_no=4),
]


# 独立业务页签改为二级目录下的三级页面，保留旧入口路径与授权记录。
_source_menu = next(menu for menu in MENUS if menu.key == 'DictionaryManagement')
MENUS = [replace(menu, menu_type_code="directory", component=None, previous_components=('system/dict/index',), flex_form={"route": {"redirect": '/system/dict/types'}}) if menu.key == 'DictionaryManagement' else menu for menu in MENUS]
MENUS.append(MenuDef('DictionaryTypes', '字典类型', "menu", parent_key='DictionaryManagement', path='/system/dict/types', component='system/dict/index', icon=_source_menu.icon, permission_key='dictionary:list', sort_no=1, flex_form={"route": {"meta": {'menuView': 'types', 'menuGroup': 'DictionaryManagement'}}}))
MENUS.append(MenuDef('DictionaryItems', '字典项', "menu", parent_key='DictionaryManagement', path='/system/dict/items', component='system/dict/index', icon=_source_menu.icon, permission_key='dictionary_item:list', sort_no=2, flex_form={"route": {"meta": {'menuView': 'items', 'menuGroup': 'DictionaryManagement'}}}))
