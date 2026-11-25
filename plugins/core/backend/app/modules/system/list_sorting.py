"""本模块拥有的列表展示排序声明，保留原有查询权限与数据范围。"""
from app.framework.db.list_sorting import DISPLAY_FIELDS, ListSortPolicy

LIST_FIELDS = DISPLAY_FIELDS | frozenset(
    """
    action action_code actor_name arrived_at avatar_url behavior bpmn_process_no browser
    business_summary business_type_code channel_code code component components
    content created_at current_version_no data_scope_code definition_name definition_no delivery
    delivery_stats department_name department_no description dict_code dict_id dict_name
    display_name email error_message external_sent_count full_name group_key group_name
    http_status ids installed_version ip is_active is_builtin is_shown_on_home
    is_tenant_extensible is_visible item_code item_name keyword login_name login_time
    manager_name menu_key menu_name menu_type_code message method module module_code name
    notice_type_code occurred_at operating_time org_id org_name org_no path
    permission_count permission_key permission_name plugin_key portal_code
    provisioning_status_code published_at publisher_name_snapshot read_at read_count redirect
    remark request_method request_path request_time requires requires_confirmation role_count
    role_name role_no role_nos roles route_meta scene_key scene_name scene_name_snapshot
    severity_code sort_no status status_code summary system
    target_id target_role_ids target_scope target_type_code target_user_ids task_name
    task_result title type_code type_label updated_at url user_count username version version_no
    """.split()
)

LIST_SORT_POLICIES = (
    ListSortPolicy('GET', '/api/workflow_definition/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/workflow_task/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/workflow_task/cc/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/dictionary/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/dictionary/entry/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/miniapp_menu/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/notification_center/scenes', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/notification_center/notifications', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/notification_center/delivery-logs', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/notification_center/event-logs', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/notice_announcement/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/login_log/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/operation_log/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/user_profile/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/role/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/permission/list', fields=LIST_FIELDS),
    ListSortPolicy('GET', '/api/role_permission/list', fields=LIST_FIELDS),
)
