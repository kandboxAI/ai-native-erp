# 数据库命名与建模规范

| 项目 | 内容 |
|---|---|
| 文档版本 | v2.1（v2.0 由《数据库命名方案》修订拆分） |
| 状态 | 草稿，待评审 |
| 日期 | 2026-10-11（v2.0：2026-10-05） |
| 适用范围 | 基于 PostgreSQL 18 及以上版本的教育 AI 管理系统、MES 等产品；所有新增和修改的数据库对象 |
| 配套文档 | [文档归属与领域设计入口](README.md)、[底座数据库设计](core-database-design.md)、[底座表目录](core-table-catalog.md)、[ERP 整体分层设计](current-layered-architecture.md) |

> v2.0 变更：修正 schema、租户、唯一键、审计字段等前后矛盾；主键改为 UUID；组织字段统一为 `org_id`；审计字段拆分为创建人和修改人；状态机使用 `status_code` 并引用字典，启停统一使用 `is_active`；`_code` 只用于字典值，实体自身编号统一用 `_no`，代码定义的程序标识用 `_key`；新增用户引用命名、外部系统标识、枚举不用 CHECK、关系不放 JSON、软删除统一为 `deleted_at` + `deleted_by` 等规则；成绩统一为 `score`；新增注释必填、字典引用、外键声明、快照与有效期、敏感字段、`flex_form` 扩展字段、schema 划分、中英文术语表、迁移策略；原 MES/库存等领域设计随业务插件维护，位置见[文档索引](README.md#插件领域设计)。`public` 只存放登录认证表与租户目录；**每个租户一个独立的业务 schema**（`t_<租户编号>`），管理底座与行业业务都在租户 schema 中，业务表不含 `tenant_id`，租户内组织按 `org_id` 区分；字典每个租户一份；`flex_form` 覆盖除日志表外的所有表，事务表和事务性流水都包含。

> v2.1 变更（2026-10-11）：业务域前缀按 **L1 管理底座 / L2 公共管理层 / L3 行业业务** 三层重新划分（§6）；新增 L2 前缀 `ar_`（应收与计费，取代 `fee_`）、`fac_`（后勤与设施）；工单 `tkt_` 由 L1 移到 L2；停用 `adm_`（并入 `edu_adm_`）、`fee_`，以及 `can_`、`canteen_`、`log_`、`patrol_`、`leadership_meal_` 等不规范前缀（§6.6）；新增二级子域命名规则与教育的 11 个子域（§5.1、§6.5）；`file_` 的表改为 `file_attachment`（不拆 `file_object`）；新增事件名规则（§6.8）；示例表名按新名称更新。当前[底座表目录](core-table-catalog.md)仅包含 L1。

---

## 1. 目标

- 通过 schema 和表前缀快速识别模块与业务域；
- 表、字段、索引、约束命名一致，同一概念全库只有一个名字；
- **让人和 AI 都能读懂数据库**：每个对象都有中文注释，取值有字典，关系有声明，口径有说明；
- 支持多租户（每个租户一个 schema）、多组织（`org_id`）的数据隔离；
- 保护个人信息，特别是未成年学生的信息；
- 降低跨模块开发、数据分析和系统维护成本。

---

## 2. 总体原则

1. 数据库对象统一使用未加引号的小写 `snake_case`。
2. 两类 schema：`public` 只存放登录认证与租户目录；每个租户一个业务 schema，管理底座和行业业务都在其中（§3、§9）。
3. 表名为“**业务域前缀 + 单数实体名**”。
4. 主键统一为 UUID，命名为 `id`；外键为 `<实体名>_id`。
5. 每张表都包含统一的标准字段：组织、审计；除日志表外都包含 `flex_form`（§8）。租户由 schema 区分，业务表不含 `tenant_id`。
6. 每张表、每个字段都必须有中文注释（§10）。
7. 编码类字段引用数据字典；不使用数据库枚举类型和无含义的数字码（§11）。
8. 引用其他表的 `_id` 字段必须声明外键约束；无法声明的必须登记在语义模型中（§12）。
9. 字段名使用完整英文单词，名称尽量简短；同一概念全库只用一个名称，以术语表为准（§17）。
10. 不使用数据库保留字、拼音缩写、技术前缀。

---

## 3. Schema 划分

### 3.1 两类 schema

| schema | 存放内容 | 例子 |
|---|---|---|
| `public` | **只存放登录认证与租户目录**：登录账号、外部身份绑定、登录日志、密码历史、租户目录、账号可进入的租户 | `public.auth_user`、`public.auth_identity`、`public.auth_tenant`、`public.auth_membership` |
| 租户 schema（业务 schema） | **每个租户一个**，存放该租户登录之后的一切：管理底座（L1：用户、角色、权限、菜单、字典、组织、部门、职务与岗位、通知、工作流、文件、审计日志、知识库、文档中心、AI 能力）+ 公共管理（L2：人事、工单、应收与计费、财务、物资与库存、后勤与设施）+ 行业业务（L3：教育、制造、养老等），以及跨层的主数据 | 示例租户 `t_demo`：`t_demo.sys_user`、`t_demo.sys_org`、`t_demo.wf_instance`、`t_demo.md_party`、`t_demo.edu_student`、`t_demo.ar_bill` |

**为什么这样划分**：
- **统一登录**：登录账号在 `public` 中全局唯一，一个账号可以进入多个租户；
- **租户之间物理隔离**：每个租户的数据在自己的 schema 中，查询漏写条件也不会读到其他租户的数据；可以单独备份、恢复、迁出、删除一个租户；
- **业务表更简单**：业务表不含 `tenant_id`，唯一键也不含它；集团内多所学校、多个校区用 `org_id` 区分（§9）。

规则：

- **命名**：租户 schema 为 `t_<租户编号>`，租户编号为小写字母、数字、下划线，如 `t_demo`。schema 名记录在 `public.auth_tenant.schema_name`，创建后不修改。
- **不得写死 schema 名称**：应用代码、ORM 模型、迁移脚本、视图、函数、语义模型只写表名，依赖 `search_path` 定位到当前租户的 schema；`public` 的名称固定。本文和各领域模型中的 `t_demo.` 前缀表示“当前租户的 schema”。
- **按请求切换**：应用在每个请求的事务内设置 `set local search_path = <租户 schema>, public`，事务结束后自动恢复，连接池中的连接不会带着上一个租户的设置（§9）。
- 租户 schema 内包含管理底座和多个业务域，用表前缀区分，如 `t_demo.sys_user`、`t_demo.edu_student`。
- 不同产品（如 MES）各自有自己的租户 schema，表前缀区分业务域。

### 3.2 登录流程与 schema 的衔接

```text
① 认证（public）：账号 + 密码 / 微信 / 统一身份认证 → 得到 auth_user
② 选择租户（public）：从 auth_membership 列出该账号可进入的租户（auth_tenant），取得租户 schema 名
③ 进入租户（租户 schema）：切换 search_path，按 auth_user_id 找到租户内用户 sys_user
   → 加载角色、权限、组织、数据范围 → 签发包含租户编号与 sys_user_id 的访问令牌
④ 之后每个请求按令牌中的租户切换到对应 schema
```

### 3.3 引用方向

- **租户 schema 可以引用 `public`**：只有租户内用户引用登录账号，即 `sys_user.auth_user_id` 引用 `public.auth_user.id`。
- **`public` 不得引用租户 schema**：认证不依赖任何租户。`auth_membership` 引用同在 `public` 的 `auth_tenant`；租户 schema 中的用户与 `auth_membership` 由开通、停用用户的流程同步维护。
- **租户 schema 之间不得互相引用**。
- 租户 schema 内部的引用（如 `edu_student.org_id` 引用 `sys_org.id`、`created_by` 引用 `sys_user.id`）都在同一 schema 内，正常声明外键。

### 3.4 隔离方式

| 需求 | 做法 |
|---|---|
| 认证数据 | `public` 只授予认证服务所用的数据库角色；业务服务只能读取登录账号的必要字段 |
| 租户隔离 | 每个租户一个 schema；应用按请求切换 `search_path`（§9） |
| 租户内的学校、校区 | `org_id` + 数据范围（§9） |
| 审计日志只追加 | `audit_` 表只授予插入和查询权限，不授予更新和删除 |
| 知识库原始层会话 | 原文存放在对象存储的独立空间；数据库中只存元数据，表级单独授权 |
| AI 只读访问 | AI 使用专用数据库角色，只能访问 `ai_v_` 前缀的受控视图（§14） |
| 报表 | `rpt_` 前缀的视图或物化视图，单独授权 |

---

## 4. PostgreSQL 专项规则

- **数据库版本**：PostgreSQL 18 及以上。开发、测试、生产使用同一主版本；需要向量检索时使用带 pgvector 扩展的同版本镜像（如 `pgvector/pgvector:pg18`）。
- 对象名不超过 63 字节（PostgreSQL 标识符上限）。
- 主键类型为 `uuid`，**统一使用 UUIDv7**（前 48 位为毫秒时间戳，按时间有序），不使用随机的 UUIDv4（`gen_random_uuid()`）。原因：新记录按时间顺序追加到主键索引末尾，减少页分裂和索引膨胀；按 `id` 排序大致等于按创建时间排序。
- **生成方式**：应用写入时生成 UUIDv7；数据库默认值使用 PostgreSQL 18 内置的 `uuidv7()` 兜底（`id uuid primary key default uuidv7()`）。不自定义同名函数，`public` 中只存放认证表与租户目录。
- 时间点使用 `timestamptz`，纯日期使用 `date`。
- 金额使用 `numeric(18, 2)`，单价、汇率等使用项目约定的精度；不使用浮点类型保存金额。
- 不使用 PostgreSQL 枚举类型（`create type ... as enum`），编码统一使用 `varchar` 并引用字典。
- 不使用带双引号的驼峰名称。

---

## 5. 表名

### 5.1 格式

```text
<业务域前缀>_<单数实体名>                  例：sys_user、ar_bill、inv_stock_order
<业务域前缀>_<子域>_<单数实体名>           业务域内表较多时使用，例：edu_adm_lead、fac_patrol_point
```

- **子域**：一个业务域的表超过约 20 张、或包含多块相对独立的业务时，划分二级子域。子域编码是该业务域内的**保留词**，登记在 §6.5；新增子域需评审。
- **子域主表**：子域的主表实体名与子域同名时，直接用 `<业务域前缀>_<子域>`，如 `edu_exam`（考试）。
- **去掉重复的词**：`edu_sched_plan`，而不是 `edu_sched_schedule_plan`。
- **基础子域可以不加子域段**：被几乎所有其他子域引用的基础表可以直接用 `<业务域前缀>_<实体名>`，如教育基础的 `edu_student`、`edu_class`；前提是实体名不以本业务域的任何子域编码开头。

### 5.2 要求

- 全部小写，单词之间用下划线；
- 使用单数实体名：`edu_student`，不用 `edu_students`；
- 表达业务对象，而不是页面、接口或程序名称；
- 不使用 `table`、`data`、`info`、`record` 等没有业务含义的名称（明细行使用 `_line`，流水使用 `_transaction`，日志使用 `_log`）；
- 不使用保留字（`order`、`user`、`group`、`index` 等）作为完整表名；带前缀后（`sal_order`、`sys_user`）可以使用；
- **关联表同样要有前缀**：`sys_user_role`、`sys_role_permission`、`edu_student_guardian`。

### 5.3 后缀约定

| 后缀 | 含义 | 例子 |
|---|---|---|
| `_line` | 单据明细行 | `ar_bill_line` |
| `_transaction` | 不可修改的业务流水 | `inv_stock_transaction` |
| `_balance` | 当前余额 | `inv_stock_balance` |
| `_snapshot` | 某一时刻的快照 | `edu_class_snapshot` |
| `_history` | 业务对象的历史版本（有效期建模之外的完整历史） | `edu_exam_score_history` |
| `_log` | 操作或系统日志 | `audit_operation_log` |
| `_version` | 定义类对象的版本（流程定义、表单定义） | `wf_definition_version` |

---

## 6. 业务域前缀

业务域按层划分（见 [ERP 整体分层设计](current-layered-architecture.md)）：**L1 管理底座**与行业无关；**L2 公共管理层**各行业通用，可以被行业扩展；**L3 行业业务**是某个行业专属的业务。依赖只能自上而下（L3 → L2 → L1），L3 扩展 L2 的表时使用 1:1 扩展表（如 `edu_fee_bill` 扩展 `ar_bill`）。**所有表都必须带业务域前缀**，L1 的表也不例外。

### 6.1 `public`（登录认证）

| 前缀 | 英文 | 业务域 | 例子 |
|---|---|---|---|
| `auth_` | Authentication | 登录认证（`public`）：账号、外部身份、登录日志、密码历史、租户目录、账号可进入的租户 | `auth_user`、`auth_identity`、`auth_login_log`、`auth_password_history`、`auth_tenant`、`auth_membership` |

### 6.2 业务 schema：L1 管理底座

| 前缀 | 英文 | 业务域 | 例子 |
|---|---|---|---|
| `sys_` | System | 系统：用户、角色、权限、菜单、字典、参数、组织、部门、职务、岗位、业务单元 | `sys_user`、`sys_org`、`sys_dict_item`、`sys_job`、`sys_position` |
| `wf_` | Workflow | 工作流与审批 | `wf_definition`、`wf_task` |
| `ntf_` | Notification | 通知与公告 | `ntf_notification`、`ntf_notice` |
| `file_` | File | 文件与附件（所有模块的附件、课件统一使用） | `file_attachment`、`file_import_task`、`file_export_task` |
| `doc_` | Document | 文档中心 | `doc_document`、`doc_version` |
| `kb_` | Knowledge Base | 知识库 | `kb_entry`、`kb_passage` |
| `ai_` | AI | AI 能力：技能、调用记录、语义模型业务层 | `ai_skill`、`ai_invocation` |
| `int_` | Integration | 集成：外部系统、事件出站、Webhook | `int_outbox_event`、`int_connector` |
| `audit_` | Audit | 审计日志（登录日志在 `public.auth_login_log`） | `audit_operation_log`、`audit_data_access_log` |

### 6.3 业务 schema：L2 公共管理层

| 前缀 | 英文 | 业务域 | 例子 |
|---|---|---|---|
| `hr_` | Human Resources | 人力资源：员工、任职（员工 × 部门 × 岗位/职务）、合同、资格证书 | `hr_employee`、`hr_position_assignment` |
| `tkt_` | Ticket | 工单（含报修） | `tkt_ticket`、`tkt_repair_order` |
| `ar_` | Accounts Receivable | 应收与计费：收费账户、收费项目与标准、计费明细、账单、收款、退费 | `ar_account`、`ar_bill`、`ar_payment` |
| `fin_` | Finance | 财务核算 | `fin_voucher` |
| `inv_` | Inventory | 库存与仓储（教育物资、MES 库存）、物资领用 | `inv_warehouse`、`inv_stock_order` |
| `pur_` | Purchase | 采购 | `pur_order` |
| `asset_` | Asset | 固定资产与设备 | `asset_register` |
| `fac_` | Facility (Management) | 后勤与设施：食堂菜谱与采购、巡查，以及场地、能耗、保洁等 | `fac_canteen_recipe`、`fac_patrol_point` |

应付以后如需建设，新增 `ap_`（Accounts Payable），结构与 `ar_` 对称。

### 6.4 业务 schema：L3 行业业务

| 前缀 | 英文 | 业务域 | 适用产品 | 例子 |
|---|---|---|---|---|
| `edu_` | Education | 教育：学年学期、专业、班级、学生、学籍、教师、监护，以及招生、排课、考勤、考试、教学资源、评价、学生事务、宿舍、安全、离校就业、学费（子域见 §6.5） | 教育 | `edu_student`、`edu_adm_lead`、`edu_exam_score` |
| `mes_` | Manufacturing Execution | 制造执行 | MES | `mes_work_order` |
| `qa_` | Quality Assurance | 质量管理 | MES | `qa_inspection` |
| `sal_` | Sales | 销售 | MES | `sal_order` |

其他行业（如养老）的前缀在建表前评审确定。

### 6.5 子域

**教育 `edu_` 的子域**：

| 子域编码 | 英文 | 子域 | 例子 |
|---|---|---|---|
| （无） | — | 教育基础：学年学期、节次、教室、专业、课程、班级、学生与学籍、教师、监护人 | `edu_student`、`edu_class`、`edu_teacher` |
| `adm` | Admission | 招生 | `edu_adm_lead`、`edu_adm_application` |
| `sched` | Scheduling | 开课与排课 | `edu_sched_course_offering`、`edu_sched_plan` |
| `att` | Attendance | 考勤与请假 | `edu_att_session`、`edu_att_leave_request` |
| `exam` | Examination | 考试与成绩 | `edu_exam`、`edu_exam_score` |
| `res` | Resource | 教学资源与作业 | `edu_res_courseware`、`edu_res_question` |
| `eval` | Evaluation | 教学评价 | `edu_eval_survey`、`edu_eval_canteen_survey` |
| `stu` | Student Affairs | 学生事务 | `edu_stu_insurance`、`edu_stu_class_log` |
| `dorm` | Dormitory | 宿舍 | `edu_dorm_room`、`edu_dorm_bed` |
| `safe` | Safety | 安全与常规 | `edu_safe_incident`、`edu_safe_leadership_meal` |
| `grad` | Graduation | 离校与就业 | `edu_grad_exit`、`edu_grad_employment` |
| `fee` | Fee | 学费（L2 `ar_` 的教育扩展） | `edu_fee_account`、`edu_fee_bill` |

**后勤与设施 `fac_` 的子域**：`canteen`（Canteen，食堂菜谱与采购，如 `fac_canteen_recipe`）、`patrol`（Patrol，巡查，如 `fac_patrol_point`）。

**财务 `fin_` 的子域**：`demo`（Demo，独立财务演示台账，如 `fin_demo_budget`、`fin_demo_supplier`）。按明确的演示隔离需求登记，随 EDU 发布，不复用正式应收、库存、采购、人事或资产表；仅组织与审计身份引用 L1。它不是正式核算模型，后续保留或移除独立评估，见 财务演示台账（开发仓库/插件中的 `finance-demo-design.md`，未随纯底座分发）。

### 6.6 跨层前缀与已停用的前缀

| 前缀 | 说明 |
|---|---|
| `md_`（Master Data） | 主数据，跨层共享：主体与人员（`md_party`、`md_person`）属于 L1；物料与供应商（`md_item`、`md_supplier`）属于 L2，由物资与库存维护 |
| `rpt_`（Report） | 报表视图，跨层（§14） |

以下前缀**停用**，不得用于新表；已有表的兼容改名方案由所属插件审核并以增量迁移实施：

| 停用的前缀 | 改为 |
|---|---|
| `adm_` | `edu_adm_` |
| `fee_` | L2 `ar_`；教育专有部分为 `edu_fee_` |
| `can_` | `fac_canteen_` |
| `canteen_`（菜品口味调研） | `edu_eval_canteen_` |
| `patrol_` | `fac_patrol_` |
| `log_`（如 `log_repair_order`） | `tkt_`（`tkt_repair_order`） |
| `leadership_meal_` | `edu_safe_leadership_meal` |
| `sys_attachment` 中的 `sys_` 用法 | `file_attachment` |

### 6.7 前缀使用规则

- 一个表只使用一个前缀；
- 业务域归属不明确时，归入拥有该数据生命周期的模块；
- 跨域共享的主数据统一放在 `md_`，不要在每个模块重复建立同义表；
- 新增前缀或子域需评审，确认现有前缀和子域无法表达；
- 字典编码、权限编码、通知场景、事件名使用同一个业务域前缀（§11、§6.8）。

### 6.8 事件名

领域事件（写入 `int_outbox_event`）的名称**全局统一**为：

```text
<业务域前缀>.<实体>.<动作>          例：ar.bill.issued、hr.employee.left、tkt.ticket.assigned、file.attachment.bound
```

- 业务域前缀与表前缀一致（去掉下划线），实体为单数，动作用过去式；
- 事件名中不出现层级名或平台名（如 `foundation`、`l1`）。
- 存储：事件名写在 `int_outbox_event.routing_key`；`event_type_code` 引用字典 `int_event_type`，取值为事件名把点换成下划线（如 `hr_employee_left`），符合字典项 snake_case 规则；
- 进程内事件（如审批流的监听事件）同样使用这一格式，如 `wf.task.completed`、`wf.instance.approved`。

---

## 7. 字段命名

### 7.1 主键与外键

- 主键统一为 `id`，类型 `uuid`。
- 外键为 `<被引用实体名>_id`，不用 `fk_id`、`ref_id` 等无含义名称。
- 一张表多次引用同一实体时，用角色区分：`head_teacher_id`、`approver_id`，并在注释中写明引用的表。
- 只有 Party 的**子类型表**（`md_person`、`md_organization`）以 `party_id` 作为主键兼外键；学生、教师等**角色表**使用自己的 `id` 作为主键，以 `party_id` 外键关联人员（§13.1）。
- **`_id` 只用于本系统内部实体的 UUID 外键。** 外部系统的字符串标识（微信模板 ID、BPMN 节点 ID、第三方商户号、外部用户 ID）**不使用 `_id` 后缀**，统一为 `<系统>_<对象>_no`，例如 `wechat_template_no`、`bpmn_activity_no`、`spiff_task_no`、`pooul_merchant_no`、`external_user_no`。这样，所有以 `_id` 结尾的字段都必须是 UUID 并声明外键，可以由 CI 统一检查。
- 用户与人员的引用见 §7.8。

### 7.2 编码、编号、名称、说明

> **规则（必需）：`_code` 只给字典值用，实体自己的业务编码一律改用 `_no`。**

| 后缀 | 含义 | 例子 | 强制要求 |
|---|---|---|---|
| `_code` | **字典值**：状态、类型、分类、方式等由字典定义的取值 | `status_code`、`leave_type_code`、`pay_method_code`、`currency_code`、`unit_code` | 必须引用字典，注释写明字典编码（§11） |
| `_no` | **编号**：实体自身的业务编号、单据编号、流水号、人员编号、外部标准编号 | `class_no`、`course_no`、`item_no`、`warehouse_no`、`bill_no`、`student_no`、`registration_no`、`role_no` | 实体自身的编号必须有唯一约束（在租户 schema 内唯一，需要时加 `org_id`）；可由编码规则生成（管理底座 6.3） |
| `_key` | **程序标识**：由代码定义、被代码引用的稳定标识 | `permission_key`、`scene_key`、`setting_key`、`menu_key`、`task_key`、`event_key` | 创建后不可修改；由代码或种子数据维护，管理界面只读；见下方“程序标识 `_key`” |
| `_name` | 展示名称 | `class_name` | |
| `description` | 较长的文字说明 | | |
| `remark` | 备注 | | |

**如何判断用 `_code` 还是 `_no`**

| 情况 | 处理 |
|---|---|
| 取值来自一张有限的列表，由管理员在字典中维护 | `_code`，引用字典 |
| 标识某一个具体对象（某个班级、某份单据、某种物料） | `_no` |
| 只是一组枚举值的“类型表”（只有编码、名称、排序、是否内置） | **改为字典，不建表**，引用处用 `_code` |
| 有自身属性、被其他表以 `_id` 引用的实体（如收费项目、物料） | 建表，自身编号用 `_no` |
| 外部标准的编号（统一社会信用代码、学籍号、行政区划代码） | `_no`，如 `credit_no`、`registration_no` |
| 外部标准的枚举（币种、计量单位、性别） | 导入字典，用 `_code`，如 `currency_code`、`unit_code`、`gender_code` |
| 由代码定义、代码中会写这个值（权限、通知场景、系统参数、菜单与页面组件的对应、流程节点、幂等键） | `_key` |
| 学校可以自己增删改的数据（如角色） | **不能用 `_key`**，代码也不得写死它；用 `_no` |

这样只看字段名后缀，就能确定它是字典值、编号还是程序标识，CI 可以据此自动检查（§11）。

**一句话判断**：代码里会写这个值，用 `_key`；用户从列表里选这个值，用 `_code`；用户用这个值找到某个具体对象，用 `_no`。

**程序标识 `_key`**

| 规则 | 说明 |
|---|---|
| 定义 | 由代码定义、被代码引用的稳定标识；去掉代码，这个值就没有意义 |
| 适用 | 权限 `permission_key`（如 `leave:approve`）、通知场景 `scene_key`（如 `leave_approved`）、系统参数 `setting_key`（如 `password_min_length`）、菜单 `menu_key`（对应前端页面组件）、流程节点 `task_key`、幂等键 `event_key` |
| 不适用 | **角色**、组织、部门、岗位等学校可以自己配置的数据。代码不得按角色名判断，只能判断权限和关系（数据范围），角色标识用 `role_no` |
| 格式 | 小写字母、数字、下划线；权限允许用冒号分段（`module:action`） |
| 不可修改 | 创建后不得修改，只能停用（`is_active = false`）；应用在更新时校验 |
| 维护 | 由代码或种子数据创建；管理界面只显示，不提供编辑 |
| 唯一性 | 权限、菜单等**每个租户 schema 各一份**，`<对象>_key` 在 schema 内唯一；同一个 key 在各租户中取值相同，开通租户时由代码模板生成 |
| 显示 | 界面显示对应的 `_name`，`_key` 只给开发和配置使用 |
| 字典 | `_key` 不引用字典，不受 §11 “`_code` 必须写字典编码”的约束 |

### 7.3 状态与启停

| 场景 | 字段 | 规则 |
|---|---|---|
| **状态机**（有流转的业务状态） | `status_code`；需要区分时用 `<语义>_status_code`，如 `pay_status_code` | 类型 `varchar`，**必须引用字典**，取值在字典中定义 |
| **启停**（只有启用和停用两种状态） | `is_active` | 类型 `boolean`，`not null default true` |
| 类型、分类 | `type_code`、`category_code` 或 `<语义>_type_code` | 引用字典 |

不要用 `status` 同时表示启停和业务状态。

### 7.4 金额、数量、比例

| 后缀 | 例子 | 说明 |
|---|---|---|
| `_amount` | `total_amount`、`paid_amount` | 配套 `currency_code`，不把币种写进字段名 |
| `quantity` / `_quantity` | `quantity`、`reserved_quantity` | |
| `_price` | `unit_price` | |
| `_rate` | `tax_rate`、`discount_rate` | 小数还是百分比，必须在注释中写明 |
| `_count` | `student_count` | 冗余计数，需写明维护方式 |

### 7.5 日期与时间

| 后缀 | 类型 | 例子 |
|---|---|---|
| `_date` | `date` | `admission_date`、`bill_date` |
| `_at` | `timestamptz` | `submitted_at`、`approved_at` |
| `valid_from` / `valid_to` | `date` 或 `timestamptz` | 有效期（§13.3） |

不使用 `time`、`datetime` 作为字段名。

### 7.6 布尔字段

- 统一使用 `is_`、`has_`、`can_` 开头，如 `is_default`、`is_primary`、`has_children`、`can_pickup`；
- 启停统一使用 `is_active`，没有例外；
- 不使用 `flag`、`yn`、`enabled`、`enabled_status` 等写法。

### 7.7 快照字段

保存提交当时的冗余值时，必须使用 `_snapshot` 后缀，并同时保存对应的外键：

| 字段 | 含义 |
|---|---|
| `class_id` | 提交时所在班级（外键） |
| `class_name_snapshot` | 提交时的班级名称（快照，不随班级改名而变化） |

注释中写明“快照：提交时的值”。没有 `_snapshot` 后缀的冗余字段视为不规范。

### 7.8 用户与人员的引用

同一个“人”在系统中有三个层次，引用时必须用对应的字段名：

| 引用对象 | 表 | 字段命名 | 例子 |
|---|---|---|---|
| 登录账号 | `public.auth_user` | `auth_user_id` | **只有** `sys_user.auth_user_id` 和 `public` 中的认证表使用 |
| 租户内用户 | `sys_user` | `user_id`；同一张表有多个用户角色时用 `<角色>_user_id` | `user_id`、`assignee_user_id`、`recipient_user_id`、`applicant_user_id`、`evaluator_user_id` |
| 动作人 | `sys_user` | `<动作>_by` | `created_by`、`updated_by`、`deleted_by`、`approved_by`、`published_by`、`reviewed_by` |
| 人员（与学校、账号无关的关系） | `md_person` | `party_id`；需要区分角色时用 `<角色>_party_id` | `student_party_id`（监护关系中的被监护学生） |
| 业务角色 | `edu_student`、`edu_teacher` 等 | `<角色>_id` | `student_id`、`teacher_id`、`head_teacher_id` |

规则：

- 不使用 `profile_id`、`user_profile_id`、`*_profile_id`、`*_by_id`、`*_by_user_id` 等写法。
- 日志表中记录动作人时使用 `actor_user_id`，需要保留当时姓名时加 `actor_name_snapshot`。
- 一张表只用一种方式引用同一个人，不同时保存 `user_id` 和 `profile_id`。

---

## 8. 标准字段

### 8.1 所有表都包含（日志表的例外见 §8.3）

租户由 schema 区分（§9），业务表**不包含 `tenant_id`**。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `id` | `uuid` | 是 | 主键（仅 Party 子类型表 `md_person`、`md_organization` 为 `party_id`） |
| `created_at` | `timestamptz` | 是 | 创建时间，默认 `now()` |
| `created_by` | `uuid` | 否 | 创建人，引用 `sys_user.id`（租户内用户）；系统任务创建时为空 |
| `updated_at` | `timestamptz` | 是 | 最后修改时间 |
| `updated_by` | `uuid` | 否 | 最后修改人 |
| `flex_form` | `jsonb` | 是 | 自定义扩展字段，默认 `'{}'`（§15）；**日志表不包含** |

### 8.2 按需包含

| 字段 | 类型 | 适用 | 含义 |
|---|---|---|---|
| `org_id` | `uuid` | **所有业务数据表必需**；平台配置表按需 | 所属组织（学校、校区、工厂），引用 `sys_org.id`，数据范围按它过滤 |
| `deleted_at` | `timestamptz` | 使用软删除的表；**与 `deleted_by` 同时出现** | 软删除时间；有效数据为 `deleted_at is null`（§8.4） |
| `deleted_by` | `uuid` | 使用软删除的表；**与 `deleted_at` 同时出现** | 删除人，引用 `sys_user.id`（§8.4） |
| `version_no` | `integer` | 存在并发修改的表 | 乐观锁版本号，每次更新加一 |
| `is_active` | `boolean` | 可启停的主数据和配置 | 启停，`not null default true` |
| `sort_no` | `integer` | 需要人工排序的表 | 排序号 |

### 8.3 例外

- **日志表**：`audit_` 前缀的表、`_log` 后缀的表，以及记录修改前后值的 `_history` 表。它们只追加，不需要 `updated_at`、`updated_by`、`deleted_at`，**也不包含 `flex_form`**。
- **事务表与事务性流水**：单据及其明细、收款、退费、减免、库存流水等记录业务事实的表，**都包含 `flex_form`**，用于记录额外的业务信息，例如学校在收款记录上自定义的“收据抬头”“经办窗口”。其中只追加的流水不需要 `updated_at`、`updated_by`、`deleted_at`。
- **判断标准**：记录的是业务事实（交易、单据、业务事件）的，按事务表处理；记录的是系统或操作行为（谁在何时做了什么、请求记录、修改留痕）的，按日志表处理。
- **`public` 的认证表与租户目录**：不属于任何租户，**不包含 `org_id`，其余标准字段都包含**（`id`、`created_at`、`created_by`、`updated_at`、`updated_by`、`flex_form`）。注意：
  - `created_by`、`updated_by` 引用 **`public.auth_user.id`**（执行操作的登录账号），不引用业务 schema 的 `sys_user`，因为 `public` 不得引用业务 schema（§3.3）；系统任务写入时为空。
  - `public` 中的 `flex_form` 存放**与租户无关**的账号级扩展信息；学校自定义的用户字段仍放在租户 schema 的 `sys_user.flex_form`。
  - 日志类认证表（`auth_login_log`、`auth_password_history`）按日志表规则：只追加，不包含 `updated_at`、`updated_by`、`flex_form`。
- **没有跨租户共享的业务数据**：字典（§11）、菜单、权限、角色都在每个租户 schema 中各一份，开通租户时从代码模板生成。

### 8.4 软删除

| 规则 | 说明 |
|---|---|
| **禁止布尔标志** | 不使用 `is_delete`、`is_deleted`、`del_flag`、`deleted` 等布尔字段表示删除 |
| **必须成对出现** | 需要软删除的表**同时**增加 `deleted_at`（`timestamptz`）和 `deleted_by`（`uuid`，引用 `sys_user`）；删除时两者一起写入，恢复时一起清空 |
| 有效数据 | `deleted_at is null` |
| 默认过滤 | ORM 基类对软删除表自动加上 `deleted_at is null` 条件；需要查已删除数据（回收站、审计）时显式声明 |
| 唯一约束 | 使用带 `where deleted_at is null` 条件的部分唯一索引，删除后可以重新使用同一编号 |
| 恢复与清理 | 删除后保留期限内可在回收站恢复；超过期限的记录按留存策略物理清理。期限在系统参数中配置 |
| 下游同步 | 知识库、检索索引、缓存、小程序本地数据等按 `deleted_at` 增量识别“自上次同步以来被删除的记录” |

**为什么不用布尔标志**：布尔值只能说明“已删除”，无法回答谁删的、什么时候删的、能否恢复、何时清理，下游也无法增量同步删除；而且容易与“停用”混用。

**停用与删除的区别**：

| | 停用 | 删除 |
|---|---|---|
| 字段 | `is_active = false` | `deleted_at` 有值 |
| 含义 | 暂时不用，以后可能启用 | 录错或不再需要，不应再出现 |
| 管理界面 | 仍显示，标为“已停用” | 不显示（回收站除外） |
| 新数据能否选择 | 不能 | 不能 |
| 历史数据的引用 | 保留 | 保留 |

**哪些表使用软删除**：

| 表的类型 | 做法 |
|---|---|
| 主数据、配置（班级、课程、菜单、供应商、物料） | 软删除 |
| 业务单据（请假单、账单、入库单） | **一般不删除**，用状态表示“已撤销”“已作废”；只有草稿允许删除 |
| 流水、日志 | **永不删除**，只按留存期限清理 |

---

## 9. 多租户

### 9.1 模型：每个租户一个 schema

```text
public.auth_user              登录账号（全局，不属于任何租户）
public.auth_tenant            租户目录：租户编号、名称、schema 名、是否启用
public.auth_membership        账号可进入的租户（auth_user × auth_tenant）

t_<租户编号>                   租户 schema（每个租户一个）
  ├─ sys_user                 租户内用户：一个登录账号在每个租户中各有一条
  └─ sys_org                  组织树：集团 → 学校 → 校区（或工厂 → 车间）
       └─ 业务数据（org_id）
```

| 层级 | 标识 | 作用 |
|---|---|---|
| 登录账号 | `auth_user_id` | 认证身份；同一账号可以进入多个租户 |
| 租户 | schema（`auth_tenant.schema_name`） | 数据隔离的边界；不同租户的数据在不同 schema 中，互不可见 |
| 组织 | `org_id` | 租户内部的数据范围：集团内的学校、校区；用户按组织授权 |

### 9.2 规则

1. **一个租户一个 schema**，命名 `t_<租户编号>`；租户目录在 `public.auth_tenant`。开通租户时创建 schema、建表到最新版本、生成菜单权限角色与字典；停用租户时 `auth_tenant.is_active = false`。
2. **业务表不含 `tenant_id`**；业务唯一键在 schema 内定义，需要在学校或校区内唯一的加 `org_id`，如学号唯一为 `(org_id, student_no)`。
3. **按请求切换 schema**：应用根据访问令牌中的租户，在每个请求的事务内执行 `set local search_path = <租户 schema>, public`；不使用会话级 `set`，避免连接池中的连接串租户。
4. **迁移逐个租户执行**：Alembic 对每个租户 schema 依次升级，版本表在各自 schema 中；新租户开通时直接升级到最新版本。
5. **跨租户运维和统计**：只能通过专用数据库角色逐个 schema 执行，并记录审计。
6. 租户只从登录身份中解析，不接受接口参数传入；`org_id` 按用户的组织授权校验。
7. 租户内用户 `sys_user` 在 schema 内按 `auth_user_id` 唯一：一个登录账号在一个租户中只有一个用户。
8. **规模**：每个租户约 120 张表。几百到一两千个租户可直接使用；更多租户时按数据库集群拆分，由 `auth_tenant` 记录租户所在的集群。

---

## 10. 注释（必填）

### 10.1 要求

- **每张表、每个字段都必须有中文注释**，由迁移脚本一起创建；没有注释的迁移不得合并（CI 校验）。
- 注释是 AI 和语义模型理解数据库的第一来源，必须准确，不得残留其他业务的内容。

### 10.2 表注释格式

```text
<中文名>：<一行代表什么（粒度）>。<补充说明>
```

例：`学生请假：一行为一条请假申请。审批通过后才计入考勤。`

### 10.3 字段注释格式

```text
<中文名>[（单位）][；字典 <dict_code>][；快照：<说明>][；敏感：<级别>][；<补充说明>]
```

| 例子 | 注释 |
|---|---|
| `leave_days` | `请假天数（天）；按工作日计算` |
| `leave_type_code` | `请假类型；字典 edu_leave_type` |
| `class_name_snapshot` | `班级名称；快照：提交时的班级名称` |
| `full_name` | `姓名；敏感：个人` |
| `discount_rate` | `优惠比例；小数，0.1 表示 10%` |

---

## 11. 字典引用

- **规则（必需）：所有以 `_code` 结尾的字段都必须引用数据字典（`sys_dict` / `sys_dict_item`），并在注释中写明字典编码。** `_code` 只用于字典值，实体自身的业务编号使用 `_no`（§7.2）。
- `_key`（程序标识）和 `_no`（编号）都不引用字典，不受本规则约束（§7.2）。
- **唯一豁免**：字典表自身的 `sys_dict.dict_code`（字典编码）和 `sys_dict_item.item_code`（字典项值）是字典的定义，不再引用其他字典。
- **CI 检查**：以 `_code` 结尾的字段，注释中必须含有“字典 <字典编码>”且该字典存在；实体自身的 `_no` 字段必须有唯一约束。任一项不满足即阻止合并。
- 字典编码命名：`<业务域前缀>_<含义>`，如 `edu_leave_type`、`ar_pay_method`。
- 字典项的值使用小写英文 `snake_case`，如 `sick_leave`、`approved`，**不使用数字码**。
- 系统内置字典项不可删除，只能停用（`is_active = false`）。
- **字典每个租户一份**：每个租户 schema 中都有完整的字典。
  - **内置字典项**（`is_builtin = true`）由平台在代码中定义，开通租户时生成；平台新增内置项后，升级时同步到各租户。内置项不可删除，只能停用。
  - **学校自己的字典项**：允许扩展的字典（`is_tenant_extensible = true`），学校可以增加本租户的字典项。
  - 字典按租户缓存。
- 状态机字典需要在语义模型中登记允许的状态流转。
- 不建立“字段 → 字典项”的数据库外键（字段保存的是编码值）；由应用校验，语义模型编译时检查注释中的字典编码存在。
- **不用 CHECK 约束写死枚举值**：字典是取值的唯一来源，管理员可以按租户扩展；如果数据库里再用 CHECK 写死取值，每增加一个取值都要改表结构，两边会长期不一致。CHECK 约束只用于数值范围、日期先后等不随配置变化的规则（如 `0 <= score_value <= full_score`、`valid_to > valid_from`）。

---

## 12. 外键声明

1. 引用其他表的 `_id` 字段**必须声明外键约束**，包括标准字段 `org_id`、`created_by`、`updated_by`，以及跨 schema 引用 `public.auth_user` 的 `auth_user_id`。
2. 无法声明外键的关系（文本匹配、日期范围、多态引用、跨库引用）必须在语义模型中登记，并在字段注释中写明。
3. **多态引用**（`source_doc_type` + `source_doc_id`）只用于流水、日志、附件这类通用记录，并在注释中列出可能的类型。
4. 外键的删除行为显式声明：主从明细使用级联删除；其余默认禁止删除被引用的记录。
5. **外键索引**：
   - 业务外键（如 `student_id`、`class_id`、`org_id`）建立索引；如果已有以该字段开头的唯一索引或联合索引，不再单独建单列索引（例如 `org_id` 常是业务唯一键的第一列）。
   - **审计字段外键（`created_by`、`updated_by`、`deleted_by`）只声明外键约束，默认不建索引**。用户只做软删除，不会因为删除用户而检查引用；这三个字段很少作为单独的查询条件，单列索引用不上；`updated_by` 每次更新都可能变化，被索引后 PostgreSQL 无法原地更新（HOT 更新），每次更新都要写所有索引。
   - 确有按创建人查询的场景（如“我提交的申请”），按查询建立联合索引，如 `idx_edu_att_leave_request_created_by_created_at (created_by, created_at desc)`，软删除表可加 `where deleted_at is null`。

外键是语义模型自动内省关系的基础。当前元数据与业务模型的边界见[底座数据库设计](core-database-design.md#4-业务设计与-ai-元数据)。

---

## 13. 建模规则

### 13.1 Party 主体模型

参与业务的主体统一称为 Party，可以是自然人，也可以是机构：

```text
md_party                主体共有信息：类型、显示名称、状态
├── md_person           自然人：姓名、性别、出生日期；可关联登录账号 user_id
└── md_organization     外部机构：法定名称、统一社会信用代码、机构类型
```

- `md_person.party_id`、`md_organization.party_id` 同时作为主键和外键，引用 `md_party.id`。
- `md_party.party_type_code` 与子表的一致性由应用服务或触发器保证。
- **子类型与角色要区分**：

  | 类型 | 含义 | 与人员的关系 | 例子 | 主键 |
  |---|---|---|---|---|
  | 子类型 | 主体**是什么**（自然人或机构） | 严格一对一，终身不变 | `md_person`、`md_organization` | `party_id`（兼外键） |
  | 角色 | 人在**某个组织、某段时间**里的身份 | 一对多：可以在多所学校、多个时期各有一个身份 | `edu_student`、`edu_teacher`、`edu_guardian`、`hr_employee` | 自己的 `id`；`party_id` 为外键 |

- **角色表一律以 `id` 为主键**，通过 `party_id` 外键关联 `md_person.party_id`，并按业务含义声明唯一约束。例如学生的在校身份按学校区分：同一人在集团的小学和中学各有一行，学号分别在各自学校内唯一。
- 一个人可以同时有多个角色，例如既是教师又是家长；跨角色、跨学校汇总一个人的经历时，通过 `party_id` 关联。
- **与“人”有关、与“在哪所学校”无关的关系**（如监护关系）关联到人员的 `party_id`，而不是某个角色记录，避免升学、转学后关系失效。
- **账号、用户与人员的关系**：登录账号 `public.auth_user` → 租户内用户 `sys_user`（`auth_user_id`）→ 人员 `md_person`（`user_id` 可空，引用 `sys_user.id`，租户内唯一）。学生可以没有账号；家长和教师通常有账号。
- **`md_organization` 与 `sys_org` 的区别**：`sys_org` 是本租户内部的组织架构（学校、校区、部门的上级）；`md_organization` 是与业务往来的外部机构（生源学校、实习企业、供应商）。

### 13.2 单据主表与明细

- 主表保存单据整体信息，明细表名为 `<主表名>_line`，以 `<主表实体名>_id` 关联主表。
- 明细行号统一为 `line_no`。
- 单据编号 `_no` 由编码规则生成（管理底座 6.3），在租户 schema 内唯一。

### 13.3 有效期

会随时间变化的关系和属性（班级归属、监护关系、任职、学籍状态、收费标准）使用有效期建模：

| 规则 | 说明 |
|---|---|
| 字段名 | `valid_from`、`valid_to` |
| 类型 | 业务日期用 `date`；需要精确到时刻的用 `timestamptz` |
| 区间含义 | **左闭右开**：`valid_from` 当天生效，`valid_to` 当天起失效 |
| 至今有效 | `valid_to` 为空 |
| 不重叠 | 同一对象的有效区间不得重叠，用排除约束保证，命名为 `ex_<table>_<rule>` |
| 当前记录 | `valid_from <= 当前日期` 且（`valid_to` 为空或 `valid_to > 当前日期`） |
| 修改方式 | 不覆盖旧记录：关闭旧记录（写入 `valid_to`），再插入新记录 |

### 13.4 快照

- 单据保存提交时的关键冗余信息（班级名称、收费标准金额、单价）时，使用 `_snapshot` 字段，并同时保存外键（§7.7）。
- 统计时“按当时”还是“按当前”是业务口径问题，必须在语义模型中登记口径规则。

### 13.5 历史与审计

| 需求 | 做法 |
|---|---|
| 关系或属性随时间变化 | 有效期（§13.3） |
| 单据审批流转 | 工作流记录（`wf_` 前缀） |
| 需要完整保留每次修改的业务对象（如成绩） | `<表名>_history`：每次修改插入一行旧值、修改人、修改原因 |
| 谁在什么时候做了什么 | 操作日志（`audit_operation_log`） |

### 13.6 敏感字段

| 敏感级别 | 例子 | 存储要求 |
|---|---|---|
| 公开 | 学校名称、课程名称 | 无 |
| 内部 | 学号、班级、成绩 | 按权限访问 |
| 个人 | 姓名、手机号、出生日期、家庭住址 | 按权限访问；默认不进入 AI 上下文 |
| 机密 | 身份证号、健康信息、家庭经济状况、银行卡号 | **单独建表、单独授权**；加密存储 |

- 机密字段放在独立的表中，如人员身份信息表 `md_person_pii`（表注释写明“personal identity information”），不放在主表。
- 加密存储的字段命名：`<字段>_encrypted` 存密文，`<字段>_hash` 存用于精确查找的哈希，`<字段>_masked` 存脱敏后的展示值（如 `3501**********1234`）。
- 字段注释中注明敏感级别（§10.3），语义模型据此生成 AI 字段白名单。
- 未成年学生的个人和机密信息，其访问一律记入数据访问审计。

---

## 14. 视图、函数与触发器

| 对象 | 命名 | 例子 |
|---|---|---|
| 普通视图 | `v_<名称>` | `v_edu_current_class_member` |
| 物化视图 | `mv_<名称>` | `mv_rpt_attendance_daily` |
| AI 受控视图 | `ai_v_<名称>` | `ai_v_edu_att_leave_request` |
| 报表视图 | `rpt_<名称>` | `rpt_ar_collection_summary` |
| 函数 | `fn_<动词>_<对象>` | `fn_calc_leave_days` |
| 触发器 | `trg_<table>_<时机>_<用途>` | `trg_edu_exam_score_before_update_history` |

AI 受控视图只暴露语义模型中允许 AI 读取的字段，由 AI 专用数据库角色访问。

---

## 15. JSONB 与 `flex_form`

### 15.1 `flex_form`：扩展字段

| 规则 | 说明 |
|---|---|
| 定义 | `flex_form jsonb not null default '{}'`；除日志表外的所有表都有，事务表和事务性流水也包含（§8.3） |
| 用途 | 存放租户自定义的扩展字段值。例如某学校想给请假单增加“是否离校”“陪同人” |
| 结构 | 一层键值对，键使用小写 `snake_case`；值为字符串、数字、布尔、日期字符串或简单数组 |
| 字段定义 | 每个键的中文名、类型、是否必填、字典、敏感级别，登记在管理底座的动态表单定义中（每个租户 schema 中按表名登记），而不是写在代码里 |
| 校验 | 保存时按表单定义校验 |
| AI 与语义模型 | 语义模型编译时读取表单定义，把扩展字段作为该实体的字段登记；未登记的键不会出现在 AI 上下文中 |
| 敏感数据 | 默认不允许在扩展字段中存放机密级数据；个人级字段必须在表单定义中标注 |
| 索引 | 默认不建索引；确有查询需求时建立 GIN 索引 `idx_<table>_flex_form`，或对单个键建立表达式索引 |
| 升级为正式列 | 某个扩展键被多个租户普遍使用、或需要参与关联和统计时，应升级为正式列，并迁移数据 |

### 15.2 其他 JSONB 字段

| 规则 | 说明 |
|---|---|
| 命名 | 使用有含义的后缀：`_config`（配置）、`_payload`（报文）、`_snapshot`（快照）、`_meta`（元数据） |
| 禁止 | 不把需要关联、筛选、统计的核心业务字段放进 JSONB；不用 JSONB 表达表之间的关系 |
| **关系不放 JSON** | ID 数组（如审批候选人列表）必须拆为关联子表（如 `wf_task_candidate`）；需要统计或筛选的明细（如听评课各维度评分）必须拆为明细子表（如 `edu_eval_lesson_score`），不放在 JSONB 数组中 |
| 结构说明 | 在字段注释中写明结构，或在语义模型中登记 |

---

## 16. 索引、约束与序列命名

```text
pk_<table>                         主键
fk_<table>_<column>                外键
uk_<table>_<column_or_columns>     唯一约束
idx_<table>_<column_or_columns>    普通索引
ck_<table>_<rule>                  检查约束
ex_<table>_<rule>                  排除约束（有效期不重叠等）
seq_<table>_<column>               序列（仅用于编号生成，主键不使用序列）
```

示例：

```text
pk_edu_student
fk_edu_student_org_id
uk_edu_student_org_id_student_no
idx_edu_att_leave_request_student_id
ck_ar_bill_total_amount_nonnegative
ex_edu_class_member_student_period
```

规则：

- 业务唯一键在租户 schema 内定义，不含 `tenant_id`；需要在学校或校区内唯一的加 `org_id`；
- 业务外键、单据编号、`org_id` 按查询场景建立索引；审计字段外键默认不建索引（§12）；
- 已被唯一索引或联合索引的前导列覆盖的字段，不再单独建单列索引；
- 软删除表的唯一约束使用带 `where deleted_at is null` 条件的部分唯一索引；
- 联合索引的字段顺序按查询条件和选择性确定，不为每个字段机械建索引；
- 名称超过 63 字节时缩写列名部分，并在注释中说明。

---

## 17. 中英文术语表

同一概念全库只使用一个英文名称。新增术语需评审后加入本表。

### 17.1 通用

| 中文 | 英文 | 说明 |
|---|---|---|
| 租户 | tenant | |
| 组织 | org | 字段统一为 `org_id`，表为 `sys_org` |
| 部门 | department | |
| 岗位 | position | |
| 登录账号 | auth_user | 表 `public.auth_user`；字段 `auth_user_id` |
| 用户（租户内用户） | user | 表 `sys_user`；字段 `user_id`、`created_by` 等 |
| 主体 | party | |
| 人员 | person | |
| 人员身份信息 | pii | personal identity information，指证件类机密信息；**允许的缩写**，仅用于 `md_person_pii` |
| 外部机构 | organization | 仅用于 `md_organization`，不要与 `org` 混用 |
| 业务单元 | business_unit | |
| 字典 / 字典项 | dict / dict_item | |
| 单据编号 | `_no` | |
| 启用 / 停用 | is_active | 不使用 enabled |
| 审批 | approval | |
| 附件 | attachment | |

### 17.2 教育

| 中文 | 英文 | 说明 |
|---|---|---|
| 学校 | school | 组织类型之一 |
| 校区 | campus | 组织类型之一 |
| 学年 | academic_year | 如 2026-2027 |
| 学期 | term | |
| 教学周 | teaching_week | |
| 年级 | grade_level | **只表示年级** |
| 届（入学年份） | cohort | 如 2024 级 |
| 专业 | major | |
| 班级 | class | 表 `edu_class` |
| 班级成员 | class_member | |
| 班主任 | head_teacher | |
| 学生 | student | |
| 学号 | student_no | 校内编号 |
| 学籍 | registration | |
| 学籍号 | registration_no | 教育主管部门编号 |
| 学籍异动 | registration_change | 休学、复学、转学、退学等 |
| 监护人 | guardian | |
| 监护关系 | student_guardian | |
| 教师 | teacher | |
| 课程 | course | |
| 开课计划 | course_offering | 某学期某班某课程 |
| 任课 | offering_teacher | |
| 教室 | room | |
| 节次 | time_slot | |
| 课表 | schedule_entry | |
| 调代课 | schedule_change | |
| 考勤 | attendance | |
| 点名（考勤场次） | attendance_session | |
| 请假 | leave_request | |
| 考试 | exam | |
| **成绩** | **score** | **不使用 grade** |
| 成绩登记单 | score_sheet | |
| 评教 | lesson_evaluation | |
| 满意度调查 | survey | |
| 招生 | admission | 教育子域 `edu_adm_` |
| 招生计划 | campaign | |
| 招生线索 | lead | |
| 报名 | application | |
| 录取 | offer | |
| 收费项目 | fee_item | 表 `ar_fee_item` |
| 收费标准 | fee_standard | 表 `ar_fee_standard` |
| 收费账户（户号） | account | 表 `ar_account` |
| 计费明细 | charge | 表 `ar_charge` |
| 账单 / 应收 | bill | 表 `ar_bill` |
| 收款 | payment | |
| 退费 | refund | |
| 减免 | waiver | |

### 17.3 制造与库存

| 中文 | 英文 |
|---|---|
| 物料 | item |
| 仓库 / 库位 | warehouse / location |
| 批次 / 序列号 | lot / serial |
| 库存余额 / 库存流水 | stock_balance / stock_transaction |
| 生产工单 | work_order |
| 领料 / 完工入库 | material_issue / production_receipt |
| 质量检验 | inspection |

---

## 18. 推荐示例

```sql
create table t_demo.edu_student (
    id               uuid        not null,
    party_id         uuid        not null,
    org_id           uuid        not null,
    student_no       varchar(32) not null,
    admission_date   date,
    status_code      varchar(32) not null default 'enrolled',
    created_at       timestamptz not null default now(),
    created_by       uuid,
    updated_at       timestamptz not null default now(),
    updated_by       uuid,
    flex_form        jsonb       not null default '{}',

    constraint pk_edu_student primary key (id),
    constraint fk_edu_student_party_id foreign key (party_id) references t_demo.md_person (party_id),
    constraint fk_edu_student_org_id foreign key (org_id) references t_demo.sys_org (id),
    constraint uk_edu_student_org_id_student_no unique (org_id, student_no),
    constraint uk_edu_student_party_id_org_id unique (party_id, org_id)
);

comment on table  t_demo.edu_student                is '学生：一行为一个人在一所学校的在校身份。同一人在集团内不同学校各有一行；人员基本信息见 md_person。';
comment on column t_demo.edu_student.id             is '主键ID';
comment on column t_demo.edu_student.party_id       is '人员ID；引用 md_person.party_id';
comment on column t_demo.edu_student.org_id         is '所在学校ID';
comment on column t_demo.edu_student.student_no     is '学号（本校编号，学校内唯一）；敏感：内部';
comment on column t_demo.edu_student.admission_date is '入学日期';
comment on column t_demo.edu_student.status_code    is '学生状态；字典 edu_student_status';
comment on column t_demo.edu_student.flex_form      is '自定义扩展字段；结构见动态表单定义';
```

说明：表在当前租户的 schema 中（例中为示例租户 `t_demo`），迁移脚本只写表名，不写 schema；学生是角色表，主键为自己的 `id`（UUIDv7：应用生成，正式建表时数据库默认值为 `uuidv7()` 兜底），以 `party_id` 关联人员；学号在学校内唯一，同一人在同一学校只有一个在校身份；业务唯一键在 schema 内定义，不含 `tenant_id`；所有外键显式声明；每个字段都有注释；状态引用字典。

---

## 19. 迁移策略

### 19.1 原则

> **当前结构变更规则**：保留已执行迁移和业务数据，以审核后的增量迁移升级。core 独立基线仅用于全新底座 schema，不能直接替换旧业务库的版本链。原整改文档“无历史数据、重建旧表”的假设只属于历史阶段，不构成删表、重建或执行种子的持续授权。迁移归属见[底座数据库设计](core-database-design.md#3-迁移所有权)，生成和执行分别遵守 AGENTS.md 的授权规则。

- **新表立即执行本规范。**
- 旧表按模块分批整改，每批与该模块的功能迭代一起进行。
- 采用“先扩展、后收缩”的两步迁移：先增加新字段或新表并双写，确认无误后再删除旧字段，避免一次性破坏接口。
- 每次迁移在同一个变更中同步更新：ORM 模型、Alembic 迁移、表和字段注释、语义模型、AI 字段白名单、接口文档。

### 19.2 现状与差距

| 项目 | 现状（当前数据库快照） | 目标 |
|---|---|---|
| schema | 全部在 `public` | 登录认证表与租户目录留在 `public`，其余（含管理底座）全部迁入租户 schema |
| 表名 | 90 张表中 88 张为复数；系统表无前缀；库存用 `inventory_` | 单数 + 前缀 |
| 主键 | UUID（89 张表） | 保持 UUID |
| 租户 | 无租户概念 | 每个租户一个 schema；业务表不加 `tenant_id` |
| 组织字段 | `organization_id`（44 张表） | `org_id` |
| 审计字段 | `operator_id`（88 张表） | `created_by` + `updated_by` |
| 编码字段 | 业务编号也用 `_code`（如 `class_code`、`course_code`、`program_code`） | 实体编号改为 `_no`；`_code` 只保留字典值 |
| 状态与启停 | `status`（40 张表，部分为布尔）、`enabled`（15 张表） | 状态机为 `status_code`，启停为 `is_active`（现有 `enabled` 一并改名） |
| 扩展字段 | 无 | 除日志表外全部增加 `flex_form` |
| 注释 | 1113 个字段中 142 个无注释；部分注释残留养老业务内容 | 全部补齐并校正 |

### 19.3 迁移步骤

| 步骤 | 内容 | 影响 |
|---|---|---|
| 1 | 在 `public` 新建租户目录 `auth_tenant`，为现有数据登记默认租户 | 无 |
| 2 | 所有表增加 `created_by`、`updated_by`；除日志表外增加 `flex_form`；`created_by` 和 `updated_by` 由 `operator_id` 回填 | 只增不删 |
| 3 | 补齐和校正注释；为 `_id` 字段补外键约束 | 无接口变化 |
| 4 | `organization_id` 改名为 `org_id`；`status` 拆分为 `status_code`（引用字典）或 `is_active`；现有 `enabled` 改名为 `is_active`；接口层同步调整 | 需前后端同步发布 |
| 5 | 表改名（单数 + 前缀）；除登录认证表外，全部迁入默认租户的 schema；旧表名保留兼容视图一个版本周期 | 需全量回归 |
| 6 | 删除 `operator_id`、兼容视图等旧对象 | 收缩完成 |

### 19.4 平台表改名对照

| 现有表 | 新表 |
|---|---|
| `users` | `public.auth_user`（只保留登录凭据与账号状态） |
| `user_profiles` | 用户资料迁入 `t_demo.sys_user`（以 `auth_user_id` 关联登录账号，现有字段名一致）；人员信息迁入 `t_demo.md_person`（见教育领域数据模型）；银行卡等机密信息移出 |
| `user_profile_organizations` | `t_demo.sys_user_org` |
| `roles` / `user_roles` | `t_demo.sys_role` / `t_demo.sys_user_role` |
| `permissions` / `role_permissions` | `t_demo.sys_permission` / `t_demo.sys_role_permission` |
| `system_menus` / `role_menus` | `t_demo.sys_menu` / `t_demo.sys_role_menu` |
| `miniapp_menus` / `role_miniapp_menus` | `t_demo.sys_miniapp_menu` / `t_demo.sys_role_miniapp_menu` |
| `dictionaries` / `dictionary_items` | `t_demo.sys_dict` / `t_demo.sys_dict_item` |
| `organizations` / `departments` | `t_demo.sys_org` / `t_demo.sys_department` |
| `system_settings` | `t_demo.sys_setting` |
| `workflow_definitions` 等 6 张 | `t_demo.wf_definition`、`wf_definition_version`、`wf_instance`、`wf_task`、`wf_task_action`、`wf_cc_record` |
| `notifications` 等 9 张、`notice_announcements` 等 3 张 | `t_demo.ntf_*`，如 `ntf_notification`、`ntf_template`、`ntf_notice`、`ntf_notice_read` |
| `login_logs` | `public.auth_login_log` |
| `operation_logs` | `t_demo.audit_operation_log` |
| `message_outbox_events` | `t_demo.int_outbox_event` |
| `suppliers` / `supplier_categories` | `t_demo.md_supplier` / `t_demo.md_supplier_category` |
| `inventory_*`（14 张） | 按 MES 领域数据模型的统一库存模型重构：入库、出库、调拨、借出、报损 5 组单据合并为 `t_demo.inv_stock_order` / `inv_stock_order_line`（类型配置 `inv_stock_order_type`）；库存为 `inv_stock_balance` + `inv_stock_transaction`；主数据为 `md_item`（见整改方案 §3.4） |
| `edu_*`、`student_leaves` | 现有结构由所属插件通过增量迁移演进 |
| （新建） | `public.auth_identity`、`public.auth_password_history`、`public.auth_membership` |

---

## 20. 禁止的命名

| 禁止 | 原因 | 改为 |
|---|---|---|
| `User`、`"EduTeacher"` | 大写、带引号 | `sys_user`、`edu_teacher` |
| `order`（完整表名） | 保留字 | `sal_order` |
| `tbl_employee` | 技术前缀 | `hr_employee` |
| `employee_info` | 语义不明确 | `hr_employee_profile` |
| `emp`、`amt` | 非必要缩写 | `employee`、`amount` |
| `xh`、`bjmc` | 拼音缩写 | `student_no`、`class_name` |
| `createdTime` | 驼峰 | `created_at` |
| `status1` | 无业务含义 | `pay_status_code` |
| `class_code`、`course_code`、`item_code`、`warehouse_code`（表示实体自身编号） | `_code` 只用于字典值 | `class_no`、`course_no`、`item_no`、`warehouse_no` |
| `role_key`、代码中按角色名判断（如 `"admin" in roles`） | 角色是学校配置的数据，不是程序标识 | `role_no`；代码改为判断权限和关系数据范围 |
| `edu_exam_type` 这类纯枚举的类型表 | 只有编码和名称的枚举应放字典 | 字典 `edu_exam_type`，引用处为 `exam_type_code` |
| `data` | 过于泛化 | 具体业务名 |
| `organization_id` | 冗长，与术语表不一致 | `org_id` |
| `can_`、`log_`、`patrol_` 等停用前缀；不带前缀的表名 | 不在业务域前缀表中，看不出业务域和层级 | 见 §6.6 |
| `ticket_categories`、`ai_skills` 等复数表名 | 表名必须是单数 | `tkt_category`、`ai_skill` |
| `foundation.ticket.assigned` 这类带层级名的事件名 | 事件名按业务域前缀统一 | `tkt.ticket.assigned`（§6.8） |
| `operator_id` | 无法区分创建与修改 | `created_by`、`updated_by` |
| `edu_grade`（表示成绩） | 与年级混淆 | `edu_exam_score` |
| `class_name`（作为快照冗余） | 看不出是快照 | `class_name_snapshot` |
| `lot_control_flag` | 布尔字段使用 flag | `is_lot_controlled` |
| `enabled`（表示启停） | 布尔字段统一使用 `is_` 开头 | `is_active` |
| `is_delete`、`is_deleted`、`del_flag` | 布尔软删除无法记录删除人和时间，且易与停用混淆 | `deleted_at` + `deleted_by` |
| `profile_id`、`user_profile_id`、`assignee_profile_id`、`created_by_id`、`reviewed_by_user_id` | 用户引用写法不统一 | `user_id`、`assignee_user_id`、`created_by`、`reviewed_by`（§7.8） |
| `wechat_template_id`、`spiff_task_id`（外部字符串标识） | `_id` 只用于内部 UUID 外键 | `wechat_template_no`、`spiff_task_no` |
| `candidate_profile_ids jsonb` | 用 JSON 表达关系 | 子表 `wf_task_candidate` |
| `check (status in ('draft', 'approved', ...))` | 用 CHECK 写死枚举 | `status_code` 引用字典 |

---

## 21. 检查清单

新增或修改表、字段时，提交前检查：

- [ ] 表在正确的 schema（只有登录认证表与租户目录在 `public`，其余都在租户 schema）；
- [ ] 小写 `snake_case`，前缀正确（§6，不使用停用前缀），需要时带子域（§6.5），单数实体名；
- [ ] 主键为 UUID，名为 `id`（仅 Party 子类型表 `md_person`、`md_organization` 为 `party_id`）；
- [ ] 学生、教师等角色表以 `id` 为主键、`party_id` 为外键，并按业务含义声明唯一约束；
- [ ] 包含 `created_at`、`created_by`、`updated_at`、`updated_by`，不含 `tenant_id`；除日志表外包含 `flex_form`；业务表包含 `org_id`；
- [ ] `public` 认证表不含 `org_id`，其余标准字段齐全，`created_by` / `updated_by` 引用 `public.auth_user`；
- [ ] 代码和迁移中没有写死租户 schema 名称；
- [ ] 业务唯一键在 schema 内定义，需要时包含 `org_id`；
- [ ] 所有 `_id` 字段声明了外键，或已在语义模型中登记；
- [ ] 每张表、每个字段都有中文注释，表注释写明粒度；
- [ ] 所有 `_code` 字段都引用字典，注释写明字典编码（字典表自身除外）；
- [ ] 实体自身的业务编号使用 `_no`，并有唯一约束；
- [ ] `_key` 只用于由代码定义、代码引用的标识，且创建后不可修改；角色等可配置数据没有使用 `_key`，代码中没有按角色名判断；
- [ ] 状态机使用 `status_code`，启停使用 `is_active`；
- [ ] 软删除表同时有 `deleted_at` 和 `deleted_by`，没有 `is_delete` 等布尔删除标志；
- [ ] 用户与人员的引用符合 §7.8；
- [ ] 外部系统的字符串标识使用 `<系统>_<对象>_no`，没有使用 `_id`；
- [ ] 没有用 CHECK 约束写死枚举值；
- [ ] ID 数组、需统计的明细没有放在 JSONB 中；
- [ ] 随时间变化的关系使用 `valid_from` / `valid_to`，并有不重叠约束；
- [ ] 快照字段使用 `_snapshot` 后缀，并保存对应外键；
- [ ] 敏感字段标注级别；机密字段单独建表并加密；
- [ ] JSONB 字段命名有含义，未存放核心业务字段；
- [ ] 术语与术语表一致；
- [ ] 索引和约束命名符合 §16；审计字段外键没有默认建索引，单列索引没有被已有联合索引的前导列重复覆盖；
- [ ] 语义模型与 AI 字段白名单已同步更新。
