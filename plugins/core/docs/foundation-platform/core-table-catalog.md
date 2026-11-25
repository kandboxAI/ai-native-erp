# 底座表目录（core ORM 快照）

本目录列出底座主要模型及其源码入口。规范见[数据库命名与建模](database-naming-convention.md)，结构边界见[底座数据库设计](core-database-design.md)。

## public 认证与租户目录

| 表 | 一行代表什么 / 职责 | 当前模型 |
| --- | --- | --- |
| `auth_identity` | 外部身份：一行为一个账号绑定的一个外部登录身份。微信、企业微信等外部身份与登录账号的绑定，用于扫码或一键登录。 | [模型](../../backend/app/auth/models.py) |
| `auth_login_log` | 登录日志：一行为一次登录尝试。成功和失败的登录都记录。 | [模型](../../backend/app/auth/models.py) |
| `auth_membership` | 账号可进入的租户：一行为一个账号可以进入的一个租户。登录后供用户选择进入哪个租户。由开通、停用租户内用户的流程同步维护。 | [模型](../../backend/app/auth/models.py) |
| `auth_password_history` | 密码历史：一行为一次密码设置。用于“不得与最近 N 次密码相同”的校验。 | [模型](../../backend/app/auth/models.py) |
| `auth_tenant` | 租户：一行为一个租户。租户目录。每个租户的业务数据在自己的 schema 中（`schema_name`），不同租户互不可见；登录时据此切换 schema。 | [模型](../../backend/app/auth/models.py) |
| `auth_tenant_plugin` | 租户能力包：一行记录一个租户对一个能力包的开通和启停状态。 | [模型](../../backend/app/auth/models.py) |
| `auth_user` | 登录账号：一行为一个可以登录的账号（全局唯一，不属于任何租户）。统一登录的账号。登录成功后，进入哪个租户、看到哪些数据，由该租户 schema 中的租户内用户 `sys_user` 决定。 | [模型](../../backend/app/auth/models.py) |

## 租户 L1 管理底座

`ai_user_preference`（用户回答偏好）和 `ai_prompt_template`（组织岗位提示模板），见 [模型](../../backend/app/modules/ai_assistant/context_models.py)。

`ai_user_template_preference`（一位用户对一份角色模板的个人启停选择，用户与模板唯一，无记录默认启用），见同一[模型](../../backend/app/modules/ai_assistant/context_models.py)。

| 表 | 一行代表什么 / 职责 | 当前模型 |
| --- | --- | --- |
| `ai_resource_active` | AI 资源活动索引：一行为当前租户一个目录命名空间的活动版本指针；发布事务原子切换 | [模型](../../backend/app/modules/harness_discovery/index_models.py) |
| `ai_resource_bundle` | AI 资源索引版本：一行为当前租户一个命名空间的一次元数据索引发布；不包含业务记录 | [模型](../../backend/app/modules/harness_discovery/index_models.py) |
| `ai_resource_document` | AI 资源索引定义：一行为一个版本内的已审核表、接口或指标定义的向量；不包含业务记录 | [模型](../../backend/app/modules/harness_discovery/index_models.py) |
| `audit_operation_log` | 操作日志：一行为一次写操作（含智能体代为操作）。只追加，不可修改、删除。 | [模型](../../backend/app/modules/operation_log/models.py) |
| `file_attachment` | 文件与附件：一行为一个上传的文件。uploading 表示等待客户端直传，pending 表示已上传、待业务绑定，bound 表示已绑定且不可复用。任何接口都不返回上传人。 | [模型](../../backend/app/modules/file/models.py) |
| `int_outbox_event` | 事件出站：一行为一个待发送或已发送的领域事件。事务内写入，再由后台投递；通知、待办、智能体触发都从这里获取事件。 | [模型](../../backend/app/modules/message_bus/models.py) |
| `md_organization` | 外部机构：一行为一个与业务往来的外部机构。生源学校、实习企业、供应商等外部机构；不是本租户的组织架构（那是 `sys_org`）。子类型表，主键为 `party_id`。 | [模型](../../backend/app/modules/masterdata/models.py) |
| `md_party` | 主体：一行为一个参与业务的主体（自然人或机构）。人员和外部机构的共同父表。 | [模型](../../backend/app/modules/masterdata/models.py) |
| `md_person` | 人员：一行为一个人（终身一条）。子类型表，主键为 `party_id`。学生、教师、监护人都通过 `party_id` 关联到这里。 | [模型](../../backend/app/modules/masterdata/models.py) |
| `md_person_contact` | 人员联系方式：一行为一个人的一个联系方式。一人可有多个手机号、住址等；登录手机号在 `public.auth_user`，与这里含义不同。 | [模型](../../backend/app/modules/masterdata/models.py) |
| `md_person_pii` | 人员身份信息：一行为一个人的一种证件（personal identity information）。人员身份信息（personal identity information）：证件类机密信息，单独授权，加密存储。AI 和报表不可读取。 | [模型](../../backend/app/modules/masterdata/models.py) |
| `ntf_channel_binding` | 通知渠道绑定：一行为一个用户在一个外部渠道的绑定。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_delivery_log` | 通知投递日志：一行为一次渠道投递尝试。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_event_log` | 通知事件日志：一行为一次业务事件的处理记录。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_notice` | 公告：一行为一条通知公告。 | [模型](../../backend/app/modules/notice_announcement/models.py) |
| `ntf_notice_read` | 公告阅读记录：一行为一个用户阅读一条公告。 | [模型](../../backend/app/modules/notice_announcement/models.py) |
| `ntf_notice_target` | 公告接收范围：一行为一条公告的一个接收对象。 | [模型](../../backend/app/modules/notice_announcement/models.py) |
| `ntf_notification` | 站内通知：一行为一次业务事件产生的一条通知。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_preference` | 通知偏好：一行为一个用户对一个场景一个渠道的偏好。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_recipient` | 通知接收人：一行为一条通知的一个接收人。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_route` | 通知路由：一行为一个场景的一条接收人规则。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_scene` | 通知场景：一行为一个由业务代码触发的通知场景。`scene_key` 由代码定义，如 leave_approved。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_scene_channel` | 场景渠道：一行为一个通知场景启用的一个渠道。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `ntf_template` | 通知模板：一行为一个场景在一个渠道上的模板。 | [模型](../../backend/app/modules/notification_center/models.py) |
| `sys_department` | 部门：一行为一个部门（如教务科、学生科、教研组）。部门树；负责人引用租户内用户。 | [模型](../../backend/app/modules/department/models.py) |
| `sys_dict` | 字典：一行为一个字典（如“请假类型”）。每个租户 schema 一份完整字典。内置字典由平台定义，开通租户时生成、升级时同步。 | [模型](../../backend/app/modules/dictionary/models.py) |
| `sys_dict_item` | 字典项：一行为字典中的一个取值。业务表 `_code` 字段存的就是 `item_code`。内置项由平台定义，学校自己增加的项 `is_builtin` 为否。 | [模型](../../backend/app/modules/dictionary_item/models.py) |
| `sys_menu` | 菜单：一行为管理端的一个菜单、目录或按钮。菜单每个租户一份，`menu_key` 对应前端页面组件。 | [模型](../../backend/app/modules/menu/models.py) |
| `sys_miniapp_menu` | 小程序菜单：一行为小程序某个门户中的一个菜单项。 | [模型](../../backend/app/modules/miniapp_menu/models.py) |
| `sys_miniapp_banner` | 小程序首页轮播：一行为一个组织的图片配置；当前图片外键引用 `file_attachment.id`，按组织、启停和排序展示。 | [模型](../../backend/app/modules/miniapp_menu/models.py) |
| `sys_org` | 组织：一行为组织树中的一个节点。业务记录通过 `org_id` 归属租户内的组织。 | [模型](../../backend/app/modules/organization/models.py) |
| `sys_permission` | 权限：一行为一个功能权限点。权限由代码定义，开通租户时从模板生成；接口按 `permission_key` 校验。 | [模型](../../backend/app/modules/permission/models.py) |
| `sys_position` | 岗位：一行为部门中的一类岗位，可由多人任职。上级岗位构成汇报线（不能成环）；同一部门最多一个负责人岗位。 | [模型](../../backend/app/modules/position/models.py) |
| `sys_role` | 角色：一行为一个角色。角色是学校配置的权限与数据范围组合。代码不按角色名判断；内置管理员角色以 `is_builtin` 防止删除，数据范围为全部、拥有全部权限。 | [模型](../../backend/app/modules/role/models.py) |
| `sys_role_menu` | 角色菜单：一行为一个角色可见的一个菜单。 | [模型](../../backend/app/modules/role_menu/models.py) |
| `sys_role_miniapp_menu` | 角色小程序菜单：一行为一个角色在小程序中可见的一个菜单。 | [模型](../../backend/app/modules/role_miniapp_menu/models.py) |
| `sys_role_permission` | 角色权限：一行为一个角色拥有的一个权限。 | [模型](../../backend/app/modules/role_permission/models.py) |
| `sys_setting` | 系统参数：一行为一个系统参数。代码读取的系统参数，`setting_key` 由代码定义，创建后不可修改。 | [模型](../../backend/app/modules/system_setting/models.py) |
| `sys_todo` | 通用待办：一行为一个业务对象的一轮办理事项。 | [模型](../../backend/app/modules/todo/models.py) |
| `sys_todo_assignee` | 待办分配：一行为一项待办的一名具体办理人及其处理状态。 | [模型](../../backend/app/modules/todo/models.py) |
| `sys_user` | 租户内用户：一行为一个登录账号在一个租户中的用户身份。用户进入租户后的身份：所属组织、部门、角色都挂在这里。姓名、电话等人员信息在 `md_person`（经 `md_person.user_id` 关联）。 | [模型](../../backend/app/modules/user_profile/models.py) |
| `sys_user_miniapp_favorite` | 用户小程序常用菜单：一行为一个租户用户固定的一个小程序入口；数量不设业务上限，顺序由用户维护。 | [模型](../../backend/app/modules/miniapp_menu/models.py) |
| `sys_user_org` | 用户可访问的组织：一行为一个用户被授权访问的一个组织。用户除主组织外还能访问的组织（例如管理人员访问多个分支机构）。 | [模型](../../backend/app/modules/user_profile/models.py) |
| `sys_user_position` | 账号岗位：一个租户账号直接选择的一个岗位，用于岗位知识资格；不代表雇佣或主岗。 | [模型](../../backend/app/modules/user_profile/models.py) |
| `sys_user_role` | 用户角色：一行为一个用户拥有的一个角色。 | [模型](../../backend/app/modules/user_role/models.py) |
| `wf_cc_record` | 抄送记录：一行为一次抄送给一个人。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_definition` | 流程定义：一行为一个审批流程。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_definition_version` | 流程版本：一行为流程的一个版本。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_instance` | 流程实例：一行为一次审批流程的运行。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_task` | 审批任务：一行为流程中的一个待办审批任务。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_task_action` | 审批记录：一行为一次审批动作。 | [模型](../../backend/app/modules/workflow/models.py) |
| `wf_task_candidate` | 审批候选人：一行为一个审批任务的一个候选处理人。 | [模型](../../backend/app/modules/workflow/models.py) |

## 插件与历史字典

业务表及领域规则见所属插件文档。迁移按已选插件的实际 ORM 结构生成。

新增或修改底座模型后需同步本目录；字段、约束及类型的完整定义以对应模型与正式迁移为准。数据库结构变更不因更新表目录而执行。

### 待办AI分析增量

`wf_instance` 增加 AI 分析状态、参考文本、模型、来源指纹、生成时间、租约开始时间、失败原因7字段；不新增表，不改人工审批意见。字符串字段有数据库默认值，时间字段可空。变更按目标租户的迁移流程应用。
