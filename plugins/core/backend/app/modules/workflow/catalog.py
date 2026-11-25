"""审批流程的权限与菜单（字典 sys_module：workflow）。"""

from dataclasses import replace

from app.framework.catalog import MenuDef, PermissionDef, crud_permissions

PERMISSIONS = [
    *crud_permissions("workflow_definition", "流程定义", "workflow", actions=("list", "detail", "create", "update", "delete")),
    PermissionDef("workflow_task:list", "查询审批待办", "workflow"),
    PermissionDef("workflow_task:detail", "查看审批待办", "workflow"),
    PermissionDef("workflow_task:complete", "办理审批（同意/驳回）", "workflow"),
    PermissionDef("workflow_task:supervise", "查看全部审批（监督）", "workflow"),
    PermissionDef("workflow_runtime:start", "发起审批流程", "workflow"),
]

MENUS = [
    MenuDef(
        "WorkflowDefinition",
        "流程定义",
        "menu",
        parent_key="SystemManagement",
        path="/system/workflow/index",
        component="system/workflow/index",
        icon="ri:git-branch-line",
        permission_key="workflow_definition:list",
        sort_no=10,
    ),
    MenuDef(
        "WorkflowTask",
        "审批任务",
        "menu",
        parent_key="SystemManagement",
        path="/system/workflow-task/index",
        component="system/workflow-task/index",
        icon="ri:inbox-line",
        permission_key="workflow_task:list",
        sort_no=11,
    ),
]


# 独立业务页签改为二级目录下的三级页面，保留旧入口路径与授权记录。
_source_menu = next(menu for menu in MENUS if menu.key == 'WorkflowTask')
MENUS = [replace(menu, menu_type_code="directory", component=None, previous_components=('system/workflow-task/index',), flex_form={"route": {"redirect": '/system/workflow-task/approval'}}) if menu.key == 'WorkflowTask' else menu for menu in MENUS]
MENUS.append(MenuDef('WorkflowApprovals', '待我审批', "menu", parent_key='WorkflowTask', path='/system/workflow-task/approval', component='system/workflow-task/index', icon=_source_menu.icon, permission_key='workflow_task:list', sort_no=1, flex_form={"route": {"meta": {'menuView': 'approval', 'menuGroup': 'WorkflowTask'}}}))
MENUS.append(MenuDef('WorkflowCopies', '抄送我的', "menu", parent_key='WorkflowTask', path='/system/workflow-task/cc', component='system/workflow-task/index', icon=_source_menu.icon, permission_key='workflow_task:list', sort_no=2, flex_form={"route": {"meta": {'menuView': 'cc', 'menuGroup': 'WorkflowTask'}}}))
