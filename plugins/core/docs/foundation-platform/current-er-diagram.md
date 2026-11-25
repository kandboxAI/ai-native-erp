# 当前项目 ER 图

核对日期：2026-11-11。图以当前源码模型和根目录 `deployment.json` 为准：当前部署组合为 core，包含 `public` 认证/租户目录与租户 schema 的 L1 管理底座，共 63 张 ORM 表。未连接数据库核对实际已迁移结构；`plugins` 为空，因此未纳入未部署的 L2/L3 业务表。

图中展示表的主键及业务外键。为便于阅读，公共 `org_id`、`created_by`、`updated_by`、`deleted_by` 外键不在每张表重复展开；租户表的 `org_id` 由公共字段工厂声明并引用 `sys_org.id`，租户审计用户字段引用 `sys_user.id`，`public` 认证表的审计用户字段引用 `public.auth_user.id`。代码标识 `_code` 通常是逻辑字典引用，并非数据库外键。`sys_todo.source_id`、`int_outbox_event` 等多态/事件来源也不是统一外键。

## 登录、租户与用户身份

`auth_*` 表位于 `public` schema；`sys_user` 位于当前租户 schema。认证账号与租户内用户之间通过 `sys_user.auth_user_id` 关联。租户成员关系由开通/停用流程维护，不从 `public` 外键到租户表。

```mermaid
erDiagram
    auth_user {
        uuid id PK
    }
    auth_identity {
        uuid id PK
        uuid auth_user_id FK
    }
    auth_password_history {
        uuid id PK
        uuid auth_user_id FK
    }
    auth_tenant {
        uuid id PK
    }
    auth_tenant_plugin {
        uuid id PK
        uuid tenant_id FK
    }
    auth_membership {
        uuid id PK
        uuid auth_user_id FK
        uuid tenant_id FK
    }
    auth_login_log {
        uuid id PK
        uuid auth_user_id FK
    }
    sys_user {
        uuid id PK
        uuid auth_user_id FK
    }

    auth_user ||--o{ auth_identity : auth_user_id
    auth_user ||--o{ auth_password_history : auth_user_id
    auth_user ||--o{ auth_membership : auth_user_id
    auth_user o|--o{ auth_login_log : auth_user_id
    auth_tenant ||--o{ auth_tenant_plugin : tenant_id
    auth_tenant ||--o{ auth_membership : tenant_id
    auth_user ||--o{ sys_user : auth_user_id
```

## 组织、人事主数据与文件

```mermaid
erDiagram
    sys_org {
        uuid id PK
        uuid parent_id FK
    }
    sys_department {
        uuid id PK
        uuid parent_id FK
        uuid manager_user_id FK
        uuid supervisor_party_id FK
    }
    sys_job {
        uuid id PK
    }
    sys_position {
        uuid id PK
        uuid department_id FK
        uuid job_id FK
        uuid parent_position_id FK
    }
    sys_user {
        uuid id PK
        uuid department_id FK
    }
    sys_user_org {
        uuid id PK
        uuid user_id FK
    }
    md_party {
        uuid id PK
    }
    md_person {
        uuid party_id PK
        uuid user_id FK
        uuid photo_file_id FK
    }
    md_person_pii {
        uuid id PK
        uuid party_id FK
    }
    md_person_contact {
        uuid id PK
        uuid party_id FK
    }
    md_organization {
        uuid party_id PK
    }
    file_attachment {
        uuid id PK
        uuid uploader_user_id FK
    }

    sys_org ||--o{ sys_org : parent_id
    sys_department ||--o{ sys_department : parent_id
    sys_user o|--o{ sys_department : manager_user_id
    md_person ||--o{ sys_department : supervisor_party_id
    sys_department ||--o{ sys_position : department_id
    sys_job o|--o{ sys_position : job_id
    sys_position o|--o{ sys_position : parent_position_id
    sys_department o|--o{ sys_user : department_id
    sys_user ||--o{ sys_user_org : user_id
    md_party ||--o| md_person : party_id
    md_party ||--o| md_organization : party_id
    sys_user o|--o| md_person : user_id
    file_attachment o|--o{ md_person : photo_file_id
    md_person ||--o{ md_person_pii : party_id
    md_person ||--o{ md_person_contact : party_id
    sys_user ||--o{ file_attachment : uploader_user_id
```

`md_person` 与 `md_organization` 是 `md_party` 的 1:1 子类型。`md_person.user_id` 在模型上唯一；有租户账号的人可关联一条人员记录。

## 角色、权限、菜单与字典

```mermaid
erDiagram
    sys_user {
        uuid id PK
    }
    sys_role {
        uuid id PK
    }
    sys_permission {
        uuid id PK
    }
    sys_user_role {
        uuid id PK
        uuid user_id FK
        uuid role_id FK
    }
    sys_role_permission {
        uuid id PK
        uuid role_id FK
        uuid permission_id FK
    }
    sys_menu {
        uuid id PK
        uuid parent_id FK
        uuid permission_id FK
    }
    sys_role_menu {
        uuid id PK
        uuid role_id FK
        uuid menu_id FK
    }
    sys_user_favorite {
        uuid id PK
        uuid user_id FK
        uuid menu_id FK
    }
    sys_miniapp_menu {
        uuid id PK
    }
    sys_role_miniapp_menu {
        uuid id PK
        uuid role_id FK
        uuid miniapp_menu_id FK
    }
    sys_user_miniapp_favorite {
        uuid id PK
        uuid user_id FK
        uuid miniapp_menu_id FK
    }
    sys_miniapp_banner {
        uuid id PK
        uuid image_file_id FK
    }
    file_attachment {
        uuid id PK
    }
    sys_dict {
        uuid id PK
    }
    sys_dict_item {
        uuid id PK
        uuid dict_id FK
    }
    sys_setting {
        uuid id PK
    }

    sys_user ||--o{ sys_user_role : user_id
    sys_role ||--o{ sys_user_role : role_id
    sys_role ||--o{ sys_role_permission : role_id
    sys_permission ||--o{ sys_role_permission : permission_id
    sys_menu o|--o{ sys_menu : parent_id
    sys_permission o|--o{ sys_menu : permission_id
    sys_role ||--o{ sys_role_menu : role_id
    sys_menu ||--o{ sys_role_menu : menu_id
    sys_user ||--o{ sys_user_favorite : user_id
    sys_menu ||--o{ sys_user_favorite : menu_id
    sys_role ||--o{ sys_role_miniapp_menu : role_id
    sys_miniapp_menu ||--o{ sys_role_miniapp_menu : miniapp_menu_id
    sys_user ||--o{ sys_user_miniapp_favorite : user_id
    sys_miniapp_menu ||--o{ sys_user_miniapp_favorite : miniapp_menu_id
    file_attachment ||--o{ sys_miniapp_banner : image_file_id
    sys_dict ||--o{ sys_dict_item : dict_id
```

`sys_setting`、`sys_miniapp_menu` 本身没有数据库外键。页面、权限和小程序菜单目录的业务标识由目录声明与代码契约关联；所有 `_code` 到字典项的引用属于逻辑引用，不在本图中画成外键。

## 通知与公告

```mermaid
erDiagram
    sys_user {
        uuid id PK
    }
    sys_role {
        uuid id PK
    }
    sys_permission {
        uuid id PK
    }
    ntf_scene {
        uuid id PK
    }
    ntf_scene_channel {
        uuid id PK
        uuid scene_id FK
    }
    ntf_template {
        uuid id PK
        uuid scene_id FK
    }
    ntf_route {
        uuid id PK
        uuid scene_id FK
        uuid role_id FK
        uuid user_id FK
        uuid permission_id FK
    }
    ntf_notification {
        uuid id PK
        uuid scene_id FK
    }
    ntf_recipient {
        uuid id PK
        uuid notification_id FK
        uuid user_id FK
    }
    ntf_preference {
        uuid id PK
        uuid user_id FK
        uuid scene_id FK
    }
    ntf_channel_binding {
        uuid id PK
        uuid user_id FK
    }
    ntf_delivery_log {
        uuid id PK
        uuid recipient_id FK
    }
    ntf_event_log {
        uuid id PK
        uuid scene_id FK
    }
    ntf_notice {
        uuid id PK
        uuid published_by FK
    }
    ntf_notice_target {
        uuid id PK
        uuid notice_id FK
        uuid role_id FK
        uuid user_id FK
    }
    ntf_notice_read {
        uuid id PK
        uuid notice_id FK
        uuid user_id FK
    }

    ntf_scene ||--o{ ntf_scene_channel : scene_id
    ntf_scene ||--o{ ntf_template : scene_id
    ntf_scene ||--o{ ntf_route : scene_id
    ntf_scene ||--o{ ntf_notification : scene_id
    ntf_scene ||--o{ ntf_preference : scene_id
    ntf_scene o|--o{ ntf_event_log : scene_id
    sys_role o|--o{ ntf_route : role_id
    sys_user o|--o{ ntf_route : user_id
    sys_permission o|--o{ ntf_route : permission_id
    ntf_notification ||--o{ ntf_recipient : notification_id
    sys_user ||--o{ ntf_recipient : user_id
    sys_user ||--o{ ntf_preference : user_id
    sys_user ||--o{ ntf_channel_binding : user_id
    ntf_recipient ||--o{ ntf_delivery_log : recipient_id
    sys_user o|--o{ ntf_notice : published_by
    ntf_notice ||--o{ ntf_notice_target : notice_id
    sys_role o|--o{ ntf_notice_target : role_id
    sys_user o|--o{ ntf_notice_target : user_id
    ntf_notice ||--o{ ntf_notice_read : notice_id
    sys_user ||--o{ ntf_notice_read : user_id
```

## 工作流与审批

```mermaid
erDiagram
    sys_user {
        uuid id PK
    }
    wf_definition {
        uuid id PK
        uuid current_version_id FK
    }
    wf_definition_version {
        uuid id PK
        uuid definition_id FK
    }
    wf_instance {
        uuid id PK
        uuid definition_id FK
        uuid version_id FK
        uuid started_by FK
    }
    wf_task {
        uuid id PK
        uuid instance_id FK
        uuid assignee_user_id FK
        uuid completed_by FK
    }
    wf_task_candidate {
        uuid id PK
        uuid task_id FK
        uuid user_id FK
    }
    wf_task_action {
        uuid id PK
        uuid instance_id FK
        uuid task_id FK
        uuid actor_user_id FK
    }
    wf_cc_record {
        uuid id PK
        uuid instance_id FK
        uuid task_id FK
        uuid recipient_user_id FK
    }

    wf_definition_version o|--o{ wf_definition : current_version_id
    wf_definition ||--o{ wf_definition_version : definition_id
    wf_definition ||--o{ wf_instance : definition_id
    wf_definition_version ||--o{ wf_instance : version_id
    sys_user ||--o{ wf_instance : started_by
    wf_instance ||--o{ wf_task : instance_id
    sys_user o|--o{ wf_task : assignee_user_id
    sys_user o|--o{ wf_task : completed_by
    wf_task ||--o{ wf_task_candidate : task_id
    sys_user ||--o{ wf_task_candidate : user_id
    wf_instance ||--o{ wf_task_action : instance_id
    wf_task o|--o{ wf_task_action : task_id
    sys_user ||--o{ wf_task_action : actor_user_id
    wf_instance ||--o{ wf_cc_record : instance_id
    wf_task o|--o{ wf_cc_record : task_id
    sys_user ||--o{ wf_cc_record : recipient_user_id
```

## AI 上下文、资源索引、待办与系统事件

```mermaid
erDiagram
    sys_user {
        uuid id PK
    }
    sys_role {
        uuid id PK
    }
    sys_position {
        uuid id PK
    }
    ai_user_preference {
        uuid id PK
        uuid user_id FK
    }
    ai_prompt_template {
        uuid id PK
        uuid role_id FK
        uuid position_id FK
    }
    ai_user_template_preference {
        uuid id PK
        uuid user_id FK
        uuid template_id FK
    }
    ai_resource_bundle {
        uuid id PK
    }
    ai_resource_document {
        uuid id PK
        uuid bundle_id FK
    }
    ai_resource_active {
        uuid id PK
        uuid bundle_id FK
    }
    sys_todo {
        uuid id PK
    }
    sys_todo_assignee {
        uuid id PK
        uuid todo_id FK
        uuid user_id FK
    }
    audit_operation_log {
        uuid id PK
        uuid actor_user_id FK
    }
    int_outbox_event {
        uuid id PK
    }

    sys_user ||--o{ ai_user_preference : user_id
    sys_role o|--o{ ai_prompt_template : role_id
    sys_position o|--o{ ai_prompt_template : position_id
    sys_user ||--o{ ai_user_template_preference : user_id
    ai_prompt_template ||--o{ ai_user_template_preference : template_id
    ai_resource_bundle ||--o{ ai_resource_document : bundle_id
    ai_resource_bundle ||--o{ ai_resource_active : bundle_id
    sys_todo ||--o{ sys_todo_assignee : todo_id
    sys_user ||--o{ sys_todo_assignee : user_id
    sys_user o|--o{ audit_operation_log : actor_user_id
```

`sys_todo.source_id` 是由 `todo_type_key` 对应处理器解释的多态来源 ID；`int_outbox_event` 按事件契约保存来源信息，因此这两类来源关系没有统一数据库外键。
