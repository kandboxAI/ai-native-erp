"""L1 固定路由与所选业务插件的清单路由。"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter

from app.auth.api import router as auth_router
from app.modules.ai_assistant.api import router as ai_assistant_router
from app.modules.ai_assistant.context_api import router as ai_context_router
from app.integrations.server_assistant_widget import router as assistant_widget_router
from app.framework.plugin import iter_plugin_routers
from app.framework.plugin_api import router as plugin_admin_router
from app.integrations.harness_api import router as harness_api_router
from app.integrations.harness_query import router as harness_query_router
from app.integrations.harness_navigation import router as harness_navigation_router
from app.modules.department.api import router as department_router
from app.modules.position.api import router as position_router
from app.modules.dictionary.api import router as dictionary_router
from app.modules.dictionary_item.api import router as dictionary_item_router
from app.modules.file.api import router as file_router
from app.modules.harness_discovery.api import router as harness_discovery_router
from app.modules.llm_gateway.api import router as llm_gateway_router
from app.modules.login_log.api import router as login_log_router
from app.modules.menu.api import router as menu_router
from app.modules.miniapp_menu.api import router as miniapp_menu_router
from app.modules.notice_announcement.api import router as notice_announcement_router
from app.modules.notification_center.api import router as notification_center_router
from app.modules.operation_log.api import router as operation_log_router
from app.modules.organization.api import router as organization_router
from app.modules.permission.api import router as permission_router
from app.modules.role.api import router as role_router
from app.modules.role_menu.api import router as role_menu_router
from app.modules.role_miniapp_menu.api import router as role_miniapp_menu_router
from app.modules.role_permission.api import router as role_permission_router
from app.modules.system.api import router as system_router
from app.modules.system_setting.api import router as system_setting_router
from app.modules.user_authorization.api import router as user_authorization_router
from app.modules.user_profile.api import router as user_profile_router
from app.modules.user_role.api import router as user_role_router
from app.modules.workflow.router import router as workflow_router
from app.modules.todo.api import router as todo_router



def _enabled_routers() -> Iterable[APIRouter]:
    # 这些是 L1 路由，始终存在；它们不能依赖教育或 MES。
    yield from (
        auth_router,
        ai_assistant_router,
        ai_context_router,
        assistant_widget_router,
        plugin_admin_router,
        system_router,
        system_setting_router,
        organization_router,
        department_router,
        position_router,
        workflow_router,
        todo_router,
        user_profile_router,
        dictionary_router,
        dictionary_item_router,
        menu_router,
        miniapp_menu_router,
        notification_center_router,
        notice_announcement_router,
        login_log_router,
        operation_log_router,
        permission_router,
        role_router,
        role_permission_router,
        role_menu_router,
        role_miniapp_menu_router,
        user_role_router,
        user_authorization_router,
        harness_query_router,
        harness_navigation_router,
        harness_api_router,
        llm_gateway_router,
        harness_discovery_router,
        file_router,
    )

    yield from iter_plugin_routers()



framework_router = APIRouter()
for router in _enabled_routers():
    framework_router.include_router(router)
