"""通知中心的权限与菜单。"""

from dataclasses import replace

from app.framework.catalog import MenuDef, PermissionDef

PERMISSIONS = [
    PermissionDef("notification_center:list", "查询通知场景与通知记录", "notify"),
    PermissionDef("notification_center:detail", "查看通知场景配置", "notify"),
    PermissionDef("notification_center:create", "新增通知场景", "notify"),
    PermissionDef("notification_center:update", "修改通知场景", "notify"),
    PermissionDef("notification_center:delete", "删除通知场景", "notify"),
    PermissionDef("notification_center:publish", "发送通知与投递待发送消息", "notify"),
]

MENUS = [
    MenuDef(
        "NotificationCenter",
        "通知中心",
        "menu",
        parent_key="SystemManagement",
        path="/system/notification/index",
        component="system/notification/index",
        icon="ri:route-line",
        permission_key="notification_center:list",
        sort_no=9,
    ),
]


# 独立业务页签改为二级目录下的三级页面，保留旧入口路径与授权记录。
_source_menu = next(menu for menu in MENUS if menu.key == 'NotificationCenter')
MENUS = [replace(menu, menu_type_code="directory", component=None, previous_components=('system/notification/index',), flex_form={"route": {"redirect": '/system/notification/scenes'}}) if menu.key == 'NotificationCenter' else menu for menu in MENUS]
MENUS.append(MenuDef('NotificationScenes', '场景配置', "menu", parent_key='NotificationCenter', path='/system/notification/scenes', component='system/notification/index', icon=_source_menu.icon, permission_key='notification_center:list', sort_no=1, flex_form={"route": {"meta": {'menuView': 'scenes', 'menuGroup': 'NotificationCenter'}}}))
MENUS.append(MenuDef('NotificationHistory', '通知历史', "menu", parent_key='NotificationCenter', path='/system/notification/history', component='system/notification/index', icon=_source_menu.icon, permission_key='notification_center:list', sort_no=2, flex_form={"route": {"meta": {'menuView': 'history', 'menuGroup': 'NotificationCenter'}}}))
MENUS.append(MenuDef('NotificationReceipts', '家校回执', "menu", parent_key='NotificationCenter', path='/system/notification/receipts', component='system/notification/index', icon=_source_menu.icon, permission_key='notification_center:list', sort_no=3, flex_form={"route": {"meta": {'menuView': 'receipts', 'menuGroup': 'NotificationCenter'}}}))
MENUS.append(MenuDef('NotificationDeliveryLogs', '投递日志', "menu", parent_key='NotificationCenter', path='/system/notification/delivery-logs', component='system/notification/index', icon=_source_menu.icon, permission_key='notification_center:list', sort_no=4, flex_form={"route": {"meta": {'menuView': 'logs', 'menuGroup': 'NotificationCenter', 'menuSubView': 'delivery'}}}))
MENUS.append(MenuDef('NotificationEventLogs', '事件日志', "menu", parent_key='NotificationCenter', path='/system/notification/event-logs', component='system/notification/index', icon=_source_menu.icon, permission_key='notification_center:list', sort_no=5, flex_form={"route": {"meta": {'menuView': 'logs', 'menuGroup': 'NotificationCenter', 'menuSubView': 'event'}}}))
