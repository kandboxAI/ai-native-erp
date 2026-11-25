# 项目开发规则

本文件适用于整个 ERP 仓库。Codex 及其他 AI 编码工具生成、修改、重构代码时必须遵守；代码评审也按这些规则检查。

## 1. 规范依据与阅读入口

按任务读取对应文档，不必每次开发都通读整个设计目录。

| 任务 | 必须参考的文档 |
| --- | --- |
| 查找总体设计、业务设计及实现差异 | [设计文档索引](plugins/core/docs/foundation-platform/README.md) |
| 数据库模型、字段、约束、SQL | [数据库命名与建模规范](plugins/core/docs/foundation-platform/database-naming-convention.md) |
| 新增目录、调整源码布局与目录命名 | [目录命名规范](plugins/core/docs/foundation-platform/directory-naming-convention.md) |
| 基础能力、模块归属、插件依赖 | [当前架构边界](plugins/core/docs/foundation-platform/core-architecture.md)、[当前分层](plugins/core/docs/foundation-platform/current-layered-architecture.md)、[当前插件契约](plugins/core/docs/foundation-platform/current-plugin-architecture.md) |
| MES 业务、状态机、生产执行及数据库关系 | [MES 操作与设计索引](plugins/mes/docs/README.md)、[MES 领域模型](plugins/mes/docs/mes-domain-data-model.md)、[MES 数据库与实现说明](plugins/mes/docs/database-design.md) |
| MES 分期与开发顺序 | [MES 开发顺序](plugins/mes/docs/mes-plugin-development-order.md)，结合实际源码核对已完成项 |
| 教育领域模型与子域归属 | 教育领域模型（开发仓库/插件中的 `docs/foundation-platform/education-domain-data-model.md`，未随纯底座分发）、教育表分类（开发仓库/插件中的 `docs/foundation-platform/education-table-classification.md`，未随纯底座分发） |
| 人事、应收公共业务 | 人事设计（开发仓库/插件中的 `docs/foundation-platform/hr-employee-design.md`，未随纯底座分发）、应收与计费设计（开发仓库/插件中的 `docs/foundation-platform/ar-billing-design.md`，未随纯底座分发） |
| 数据字典设计源、生成产物与现有表核对 | 原设计字典说明（开发仓库/插件中的 `docs/foundation-platform/data-dictionary/README.md`，未随纯底座分发）、[当前底座表目录](plugins/core/docs/foundation-platform/core-table-catalog.md)、实际插件模型 |
| 新插件接入、迁移、启用和前端 | [业务插件接入手册](plugins/core/docs/business-plugin-integration.md) |
| 插件专属运行参数、凭据及随包模板 | [插件运行配置](plugins/core/docs/plugin-configuration.md) |
| 日常开发、启动、数据库更新与验证 | [开发上手](plugins/core/docs/developer-quickstart.md) |
| 各环境按模型生成、审核和执行数据库差异 | [数据库维护](plugins/core/docs/database-workflow.md) |
| Windows/Linux 操作命令与插件迁移维护 | [统一命令](plugins/core/docs/plugin-commands.md)、[开发维护](plugins/core/docs/plugin-development.md) |
| Harness 表/接口快照与检索索引同步 | [同步说明](plugins/core/docs/harness-sync.md) |
| 一组插件统一打包、导入、开通与升级 | [业务套件说明](plugins/core/docs/business-suites.md) |
| AI 改造旧业务并产出可导入包 | [AI 插件接入任务单](plugins/core/docs/plugin-ai-onboarding.md) |
| 脚本转换旧业务，不依赖 AI | [脚本转换说明](plugins/core/docs/plugin-script-conversion.md) |
| 底座运行与开源发布 | [底座说明](plugins/core/docs/core-open-source.md)、[旧部署迁移](plugins/core/docs/open-source-conversion.md) |
| 文件与附件 | [文件与附件设计](plugins/core/docs/foundation-platform/file-attachment-design.md) |

底座设计维护在 `plugins/core/docs/foundation-platform/`。业务插件在自身的 `docs/` 下维护领域设计、配置与升级说明。

- 数据库命名、schema、标准字段、敏感分级以 `database-naming-convention.md` 为准。设计文档标为草稿，不降低用户指定规范的约束力。
- 旧文档中的 `public.users`、`organization_id`、“底座表不加前缀”、按角色名判断权限等表述已过时，不得据此生成新代码。
- 规划能力不等于已实现能力。落地前查看当前模型、公开 Service、注册机制与相关测试，不凭设计文档假设接口存在。
- 设计、表目录和数据字典用于说明模型及规划；部署、注册、迁移和开通操作以 `current-*.md`、`core-architecture.md`、接入手册及现行代码为准。历史“无数据、直接删表/重建”文字不是执行授权。统一规范与业务目标同时遵守，发现差异明确记录，不以旧实现放宽规范。
- 数据字典与实际模型有差异时明确说明，按任务同步相关定义；不得通过重建数据库或覆盖全部模型来消除差异。
- 改动限定在任务所需范围，保留用户的其他改动。默认不提交、切换分支、stash 或修改其他仓库。

## 2. 技术栈与目录

- core 为隐式必装底座，源码和主文档位于 `plugins/core/{backend,web,miniprogram,docs}/`；`deployment.json` 只声明业务插件。以下物理路径相对仓库根目录；插件清单中的逻辑路径和 Python `app.modules.*` 导入名称保持不变。
- **新增目录使用英文单数命名，禁止因存放多个文件或对象而使用复数**，例如 `doc`、`script`、`test`、`component`。已有 `plugins/core/docs/`、`scripts/`、`tests/` 等目录及当前插件固定路径契约保留，不批量改名，也不新建同用途的单数镜像目录；新增普通子目录仍遵守单数规则。第三方或工具强制目录按约定保留，新增例外须记录原因。详见[目录命名规范](plugins/core/docs/foundation-platform/directory-naming-convention.md)。
- 后端：Python 3.12、FastAPI、SQLModel / SQLAlchemy、PostgreSQL 18+、Redis、JWT。
- 认证在 `plugins/core/backend/app/auth/`：`public.auth_user`、bcrypt、自签 JWT、Redis refresh token；租户内用户为 `sys_user`。
- 管理端：Vue 3、TypeScript、Element Plus、vue-pure-admin，固定在 `plugins/core/web/`；小程序在 `plugins/core/miniprogram/`。
- 后端优先使用 `plugins/core/backend/.venv`；前端使用 pnpm。
- 管理端本地开发在 `plugins/core/web/` 下运行 `pnpm dev`，后端沿用 `.vscode/launch.json` 或当前项目启动入口。
- 数据库、JWT、通用模型网关等公共配置写在 `plugins/core/backend/.env`；插件专属参数及凭据写在 `plugins/core/backend/config/plugin/<key>.env`，类型、默认值和不含凭据的模板由插件维护，见[插件运行配置](plugins/core/docs/plugin-configuration.md)。实际环境文件不得提交或随包分发，旧插件 `.env` 读取方式保持兼容。不得输出密钥，模型供应商密钥不得进入前端、小程序或 Electron 安装包。
- 部署组合在仓库根目录 `deployment.json` 选择；该文件只声明加载的能力包，不存放密钥或租户启用状态。修改组合后重启后端与管理端。
- 不引入养老业务代码，也不为复用库存设计引入无关 MES 业务。

```text
plugins/core/backend/app/core/                  配置、异常、统一响应
plugins/core/backend/app/auth/                  认证、会话、权限与数据范围基础机制
plugins/core/backend/app/framework/             数据库会话、租户上下文、通用 CRUD、模块注册
plugins/core/backend/app/modules/               底座基础能力及主数据
plugins/<key>/backend/app/modules/ 插件业务模块（导入名仍为 app.modules.*）
plugins/<key>/web/src/             插件管理端页面、API 与资源
plugins/<key>/miniprogram/src/     插件小程序页面、API 与资源
plugins/core/backend/app/integrations/          ERP / Harness 集成与本项目适配
plugins/core/backend/resource_discovery/        通用资源检索协议、索引与检索实现
plugins/core/backend/alembic/versions/public/   认证与租户目录迁移
plugins/core/backend/alembic/versions/core/     租户 L1 独立基线
plugins/core/backend/alembic/versions/plugins/  业务插件独立迁移分支
plugins/core/web/                              管理端前端
plugins/core/miniprogram/                      小程序
plugins/core/docs/foundation-platform/         底座、数据库和领域设计规范
```

## 3. 基础模块与业务模块边界

纯底座导出只含 L1。开发工作目录可安装 inv、edu、mes 等独立业务源码包；实际加载、迁移及租户启用状态分别核对清单、deployment、迁移目录和目标租户，不把某次交付时的状态视为当前事实。操作差异见 edu 接入说明（开发仓库/插件中的 `docs/edu-plugin-integration.md`，未随纯底座分发）、[MES 接入说明](plugins/core/docs/mes-plugin-integration.md)。下表中的其他 L2/L3 路径是职责示例，实际状态以清单、源码和租户状态为准。

先判断能力归属，再决定代码位置。L1 / L2 / L3 是职责层次（[当前分层](plugins/core/docs/foundation-platform/current-layered-architecture.md)，原规划见 ERP 整体分层设计（开发仓库/插件中的 `docs/foundation-platform/erp-layered-architecture.md`，未随纯底座分发）），不要求为本次任务整体搬迁现有目录：L1 管理底座与行业无关；L2 公共管理层各行业通用、可被行业扩展；L3 是行业业务。

职责分层不等于发布单元。hr/ar/fac/tkt 已归入 EDU，统一版本、启停及 `--plugin edu` 新迁移；inv 仍独立。模块边界和已发布迁移保留，旧清单归档于 `plugins/edu/legacy/`。旧租户须显式升级 EDU；详见归并规则（开发仓库/插件中的 `docs/edu-consolidation.md`，未随纯底座分发）、升级步骤（开发仓库/插件中的 `docs/edu-local-upgrade.md`，未随纯底座分发）。

| 层次 | 负责什么 | 当前代码入口示例 |
| --- | --- | --- |
| 技术基础设施 | 配置、异常、会话、租户上下文、通用 CRUD、注册机制 | `core/`、`framework/`；保持通用 |
| L1 管理底座：身份与授权 | 登录、会话、租户成员、用户、组织、部门（含分管领导）、职务与岗位、角色、权限 | `auth/`；`modules/user_profile`、`organization`、`department`、`position`、`role`、`permission`、`user_authorization` 及其关系模块 |
| L1 管理底座：公共管理能力 | 导航、菜单、字典、参数、通知、工作流、文件、集成事件、审计 | `modules/system`、`menu`、`miniapp_menu`、`navigation`、`dictionary`、`dictionary_item`、`system_setting`、`notification_center`、`notice_announcement`、`workflow`、`file`、`message_bus`、`login_log`、`operation_log` |
| L1 管理底座：通用 AI 能力 | 模型网关、受控工具协议、资源检索、字段保护与调用治理 | `modules/llm_gateway`、`modules/harness_discovery`、`resource_discovery/`；行业语义放在适配层 |
| 跨域主数据 | 主体、自然人、外部机构共享对象（L1）；物料、供应商（L2，由物资与库存维护） | `modules/masterdata`（L1）；`supplier`、`supplier_category`（L2）；数据库使用 `md_` 前缀 |
| L2 公共管理层 | 人事（员工、任职）、应收与计费、工单、物资与库存、后勤与设施、财务核算（规划） | `modules/hr`（`hr_`）、`ar`（`ar_`）、`repair_order`（`tkt_`）、`inventory`、`inventory_requisition`（`inv_`）、`canteen`、`patrol`（`fac_`） |
| L3 行业业务：教育公共 | 学年学期、专业、课程、班级、学生、教师、监护关系等共享教育对象 | `modules/education` 中的公共模型与服务（`edu_`，规划拆为能力包 `edu_core`）；教育字典、关系范围提供器、身份标记和技能包 |
| L3 行业业务：教育业务 | 招生、排课、考勤与请假、考试、教学资源、评价、学工、宿舍、安全、离校、学费等具体流程 | `modules/admission`、`student_leave`、`class_log`、`hygiene`、`duty_eight`、`safety_incident`、`anonymous_report`、`holiday_homework`、`canteen_survey`、`leadership_meal` 等；`education` 中的业务流程（含学费扩展 `edu_fee_*`）也按 L3 处理；表名使用 `edu_<子域>_` |
| L3 行业业务：其他行业 | 制造（MES）等 | `modules/mes` 已有部分生产执行能力；继续按[当前插件契约](plugins/core/docs/foundation-platform/current-plugin-architecture.md)和 MES 领域设计演进，不改 L1 |

依赖规则：

- L1、`core`、`framework` 和通用检索库不得新增学生、班级、教师、学期等行业规则或反向依赖业务模块。
- 依赖只能自上而下：L2 可以依赖 L1；L3 可以依赖 L1 / L2。通过公开 Service、事件、已定义的查询契约或扩展点协作，避免循环依赖。L3 扩展 L2 的数据时使用 1:1 扩展表（如 `edu_fee_bill` 扩展 `ar_bill`）。
- 模块拥有自己的数据生命周期。跨模块操作调用所属模块的公开能力，不直接写其他模块的表；跨模块读取、联查必须有明确的数据范围和字段访问契约。
- 通知、审批、文件、权限等公共能力优先复用。业务模块注册场景、模板、来源或处理器，不各自复制一套公共机制。
- `md_person` 保存人员信息，`edu_student` / `edu_teacher` 保存教育身份，`sys_user` 保存租户用户，分别承担明确职责。
- 教育专属语义、指标、关系与字段映射放在所属插件的提供器/适配层，如 `modules/education/ai_catalog.py`；通用检索算法和协议不得硬编码本校表名。
- 现有耦合由相关任务逐步整改，不因为新增一个功能而无关重写整个底座。

### 当前业务插件开发入口

- 底座导出不含业务插件；当前开发目录的 inv 为单独接入的插件，源码已选入部署，数据库开通需显式执行。
- 通过 `app.framework.plugin_cli scaffold` 生成新插件，默认 `source_layout = "contained"`；业务源码与资源位于 `plugins/<key>/backend/app/modules`、`plugins/<key>/web/src`、`plugins/<key>/miniprogram/src`。本文件表格中的 `modules/<name>` 为稳定逻辑模块，实际文件在其拥有者目录。底座不反向依赖插件；导入/资源规则见[插件源码目录](plugins/core/docs/plugin-source-layout.md)。旧 legacy 包通过 relocate 转换，不手动复制回底座。
- 旧业务优先使用 `plugin_cli convert` 自动处理收集、依赖归位、清单转换、目录和页面登记、检查出包；开发人员处理报告中的具体业务问题，AI 为可选协助。转换不修改当前源码/部署，不执行数据库升级。已有包使用 `pack / inspect-package / install --deploy`；不把逐文件手改清单当作交付。
- 空部署为 core，非空为 custom；全部依赖明确写入 deployment，不再隐式加载学校模块。
- 新插件固定初始基线必须依赖 core，目录为 `plugins/core/backend/alembic/versions/plugins/<key>/`；日常增量按目标库生成到 Git 忽略的 `plugins/core/backend/.local-migrations/`，不随源码包发布。已发布的历史迁移链需保留；不得把旧业务 schema 直接切换到新基线。
- 生成或执行迁移仍遵守第 10 节授权规则，普通开发检查不得访问真实业务库或调用外部模型。

## 4. 后端模块分层

每个模块按职责组织以下文件，简单模块可以复用现有通用实现。

| 文件 | 职责 |
| --- | --- |
| `models.py` / `*_models.py` | 数据库表、字段、类型、中文注释、约束与索引 |
| `schemas.py` | 请求 / 响应 Pydantic 模型和协议校验 |
| `repository.py` / `*_repository.py` | SQL / ORM 查询、范围过滤、软删除过滤和持久化 |
| `service.py` | 业务规则、状态流转、调用 Repository / 其他模块公开能力、编排事务 |
| `api.py` | HTTP 参数、依赖注入、鉴权入口、调用 Service、统一响应 |
| `catalog.py` | 本模块的权限、管理端菜单、小程序菜单声明 |
| `tenant_setup.py` | 每个租户需要的基础配置；必须幂等 |
| `demo_seed.py` | 演示数据，与正常开通分离；必须幂等 |

- 只有 Repository 写业务 SQL / ORM；API 和 Service 不写查询、不拼 SQL。
- 常规 CRUD 复用 `framework/crud`，简单完整示例参考 `modules/department`。
- API 前缀使用 `/api/{module}`，统一返回 `{ code, message, data }`。返回用户可理解的中文业务错误，并保留稳定的机器错误码。
- 同一 HTTP 方法与路径不得重复注册；新增路由在 `framework/router.py` 等现有入口注册。
- 事务边界围绕完整业务动作设计，避免业务执行到一半就提交；失败必须回滚。
- 业务接口字段与新模型字段统一使用 `snake_case`。修改字段时同步请求、响应、前端类型、小程序和相关测试，避免残留旧名。

## 5. 数据库强制规范

以下是执行摘要；涉及数据库改动时必须读取原规范的对应章节。

### 5.1 Schema 与身份

- `public` 只存放登录认证与租户目录，新对象使用 `auth_` 前缀；业务表、管理底座、字典和菜单都在租户 schema。
- 租户 schema 为 `t_<租户编号>`；`t_edu` 是本地默认值，不得写死在应用、业务 ORM、迁移、视图、函数或业务语义中。
- 业务 ORM 不指定固定 schema，依靠当前租户的事务级 `search_path`；认证表显式指定 `public`。
- 业务表不加 `tenant_id`，业务唯一键不含 `tenant_id`；学校 / 校区的数据归属用 `org_id`。
- 禁止跨租户外键。`public` 不引用租户表；租户用户的 `auth_user_id` 可以引用 `public.auth_user.id`。
- 已有不符合规范的对象不能成为新代码的模板；相关整改必须说明兼容影响和迁移方式。

### 5.2 名称、类型与标准字段

- 所有数据库对象使用小写 `snake_case`，表名为“业务域前缀 + 单数实体名”，对象名称不超过 63 字节。
- 前缀按层划分（规范 §6）：L1 `auth_`、`sys_`、`wf_`、`ntf_`、`file_`、`doc_`、`kb_`、`ai_`、`int_`、`audit_`；L2 `hr_`、`tkt_`、`ar_`、`fin_`、`inv_`、`pur_`、`asset_`、`fac_`；L3 `edu_`（子域如 `edu_adm_`、`edu_att_`、`edu_fee_`）、`mes_` 等；跨层 `md_`、`rpt_`。`adm_`、`fee_`、`can_`、`patrol_`、`log_` 已停用。新增前缀或子域先确认现有规范不能表达。
- 主键为 UUIDv7，命名 `id`；应用复用 `framework/db/ids.py` 的 `uuid7()`，数据库默认 `uuidv7()`。Party 子类型 `md_person` / `md_organization` 的主键兼外键为 `party_id`；学生、教师等角色表仍有自己的 `id`。
- 标准字段与命名约定复用 `framework/db/models.py` 的字段工厂；不要自行发明另一个基类。
- 普通表包含创建与修改审计字段及 `flex_form`；业务数据包含 `org_id`。日志 / 历史表与只追加事务性流水按规范 §8.3 的不同例外处理，不机械套用全部字段。
- `public` 普通认证表不含 `org_id`，审计动作人引用 `public.auth_user`；租户表的审计动作人引用 `sys_user`。
- 时间点为 `timestamptz`，Python 使用带时区的 datetime 和 `utc_now()` / `local_now()`；纯日期用 `date`。金额用 `numeric(18, 2)`，不使用 float。
- `_code` 仅表示字典值；`_no` 表示实体自身、单据或外部系统的编号；`_key` 表示代码定义且不可修改的稳定程序标识。
- 每个 `_code` 字段写明“字典 <字典编码>”，并使用已存在的字典；字典定义自身的 `dict_code` / `item_code` 按原规范豁免。实体编号有符合业务范围的唯一约束。
- 状态机使用 `status_code`，启停使用 `is_active`；其他布尔字段以 `is_` / `has_` / `can_` 开头。
- 不使用 PostgreSQL ENUM，不用 CHECK 写死字典枚举；CHECK 可约束数值范围、日期先后等稳定规则。
- 用户引用严格区分 `auth_user_id`、`user_id`、`<角色>_user_id`、`<动作>_by`、`party_id` 与 `student_id` / `teacher_id`。
- 外部字符串标识使用 `<系统>_<对象>_no`，不能冒充内部 UUID 外键；不新增 `profile_id`、`operator_id`、`organization_id`、`enabled`、`is_delete` 等旧字段。
- 教育术语使用 `teacher`、`major`、`score`、`grade_level`，分别表示教师、专业、成绩、年级；遵守规范中的中英文术语表。

### 5.3 关系、约束、注释与敏感信息

- 引用内部实体的字段声明外键，包括组织和审计字段。特殊多态、跨库等无法声明的关系必须注明原因并登记到语义模型。
- 约束命名：`pk_<table>`、`fk_<table>_<column>`、`uk_<table>_<columns>`、`idx_<table>_<columns>`、`ck_<table>_<rule>`、`ex_<table>_<rule>`；删除行为显式声明。
- 索引按实际查询设计；审计字段外键默认不建索引，不重复建立已被联合索引前导列覆盖的单列索引。
- 软删除使用成对的 `deleted_at` / `deleted_by`，默认过滤已删除数据；业务唯一性使用适当的部分唯一索引。单据用撤销 / 作废状态，流水、审计日志按留存规则处理。
- 会变化的关系用 `valid_from` / `valid_to`，左闭右开，空结束日期表示持续有效；按业务约束避免重叠，不覆盖历史关系。
- 冗余保存提交时的值使用 `_snapshot` 后缀并保留对应外键，明确“按当时”还是“按当前”的统计口径。
- 每张表、每个字段都有准确的中文 COMMENT；表注释写明一行代表什么，字段说明单位、字典、引用、快照和敏感级别。
- 个人信息默认不进入 AI 上下文；机密信息单独建表、单独授权并加密，使用 `_encrypted` / `_hash` / `_masked` 等明确命名。
- `flex_form` 仅用于已定义、已校验的租户扩展信息；不放核心关联、ID 数组和需统计的明细。关联建关系表，明细建子表；其他 JSONB 字段有明确结构和业务含义。

## 6. 租户、权限与数据范围

- 认证复用 `app/auth`；登录身份是 `public.auth_user`，租户内操作身份是 `sys_user`。会话使用 `auth_user_id`，业务审计使用 `current_user.user_id`。
- 租户来源于已验证的登录身份与成员关系；业务接口不信任客户端传入的 schema 或租户。`org_id` 写入和查询都校验当前用户的数据范围。
- 请求通过 `get_current_user` / `require_permissions` 建立租户上下文；SQLModel 会话在每个事务开始时切换 schema。
- 后台任务、事件、中间件、初始化脚本显式使用 `use_tenant_schema(schema)`；原生 asyncpg 业务访问使用 `tenant_connection()`，不直接调用 `get_pool().fetch(...)`。
- 接口使用 `require_permissions` / `require_any_permissions`；Repository 复用 `scope_filters` 的范围条件和 `alive_condition`。聚合、联查、导出也必须过滤范围和软删除记录。
- `role_nos` 仅用于展示与角色分配。权限不能通过 `admin`、`teacher` 等角色名旁路；内置管理员通过真实授权拥有权限。
- `related` 范围由业务模块注册关系提供器，按任课、任职、监护等关系过滤；通用底座不写行业角色判断。没有关系规则时拒绝放行。
- 保护现有固定期限登录会话、刷新令牌轮换和租户绑定，不因业务改造降低认证约束。

## 7. 新模块的注册与基础数据

- 在模块 `catalog.py` 中声明 `PERMISSIONS`、`MENUS`、`MINIAPP_MENUS`，复用 `framework/catalog.py` 的声明类型；标识唯一并能解析引用。
- `module_code` 引用已有 `sys_module` 字典。权限沿用已有稳定 `permission_key`，新增标识遵循模块内现有约定，不无关改名。
- 每个租户必需的字典、通知场景、单据类型等放在 `tenant_setup.py`，幂等补齐，不覆盖客户已修改的业务配置。
- 演示账号与业务数据只放在 `demo_seed.py`，通过显式 `--with-demo` 加载；生产环境不使用演示数据。
- 开通账号复用现有用户开通能力，如 `modules/user_profile/provisioning.py`，完整建立认证账号、租户成员、租户用户与人员关系，避免只插一张用户表。
- 注册新模型、路由或目录时检查现有收集机制，避免漏注册、重复注册或依赖导入顺序。

## 8. 管理端与小程序

- 管理端查询列表遵循列表页面规范（开发仓库/插件中的 `docs/frontend-list-standard.md`，未随纯底座分发）：查询项和操作按钮统一对齐，新分页复用 `plugins/core/web/src/components/ListPagination/index.vue`；不再逐页定义分页外观，固定页容量及业务事件保持明确。
- 工具栏新增、数据导入、附件上传、下载/导出复用 `plugins/core/web/src/components/ActionButton/index.vue`，按 `create/import/upload/download` 选择统一填充色，详见同一规范；不逐页硬编码按钮颜色，取消与返回保持中性样式。
- 表单保存、提交、审核等操作统一置于内容末尾右下角，复用 `.erp-form-actions` 及其主/辅助操作组，主要确认按钮在最右；窄屏换行后仍保持右对齐，见同一规范。
- 查询区与表格、同容器内的表格/表单与底部操作区统一保留 20px 留白，分别复用 `.erp-query-form`、`.erp-form-actions` 的公共间距；不得让按钮或查询控件紧贴表格边缘，不在页面重复叠加间距。
- 登录、菜单、权限和已落地业务使用真实后端；只有尚未落地的功能可以保留明确的 mock，不以静态数据伪装真实查询结果。
- 前端 API 类型、请求与响应适配真实后端字段。更新表或接口字段时同步相关页面、mock 和小程序调用。
- 页面组件映射与路由在 `plugins/core/web/src/router/modules/` 等现有入口维护；可见菜单以 `/api/auth/menus` 下发的授权目录为准。
- 路由权限使用 `meta.permissions`，不新增 `meta.roles` 或前端硬编码角色权限；服务端仍负责最终鉴权。
- 小程序复用服务端菜单与门户契约，教育页面属于业务层，不在通用登录与导航外壳新增教育角色映射。

## 9. Harness / AI 数据访问

- FastAPI 是权限、范围、字段过滤和模型出口保护的执行边界；提示词不能代替服务端校验。
- AI 不能获得数据库任意 SQL 执行权限，不能绕过用户权限读取全量表或接口。查询计划只使用服务端校验过的表、字段、关系与数量限制。
- 给模型的业务结果经过统一字段与值过滤；凭据、姓名、证件、联系方式、银行信息及未确认安全的自由文本按现有保护策略处理。
- 检索只发布元数据及允许的定义，按用户权限查找相关资源；不能将全量表结构、接口文档或业务记录直接塞进模型上下文。
- 表快照、接口快照与检索索引通过现有独立 CLI 生成、检查和重建，不耦合到 `upgrade head` 或服务启动。生成 JSON 不手写、不提交 Git、不随底座或业务源码包分发，也不登记在 `package_files`；目标环境迁移后显式同步，生成依据和权限策略仍须提交。
- 人工策略、字段白名单与敏感分级的调整限定在任务范围内，不因接口新增而自动放宽保护；写操作继续使用明确确认机制。
- 数据库改动后说明目录与索引需要更新的步骤；未建检索表、未配置向量模型或未重建索引时明确交付状态。

## 10. 数据库变更与验证

- 默认由用户生成与执行 Alembic 迁移：AI 修改模型及必要的业务定义，交付所需命令；任务明确授权生成或执行迁移时再操作。
- 日常使用 `scripts/erp.py db revision / db upgrade`：各环境对照模型生成、审核和执行，不维护统一的开发增量链。环境文件须随目标库备份保留；已发布基线、旧版本记录不改写，不用 `stamp head` 代替真实升级。
- `public` 和 `tenant` 分别管理迁移；租户迁移逐个 schema 执行。不能再使用不指定范围的旧 `alembic upgrade head` 命令。
- `bootstrap.py` 用于执行迁移和开通数据，不负责把旧结构数据自动转换到新结构。不得将历史文档中的“无历史数据、重建旧表”视为持续授权删库。
- 执行初始化、升级、种子或目录生成前确认目标连接与任务授权；不写死本机数据库名称、容器名称或端口到通用代码。
- 数据字典有设计源与生成产物。涉及原字典范围的结构修改时检查 `plugins/core/docs/foundation-platform/data-dictionary/tools/dd_spec.py` 及对应模型；原混合字典不覆盖全部当前插件，不把其中的历史验证记录视为当前数据库已通过。只运行与任务相关的生成器，不用全量模型生成覆盖手工业务代码。
- 验证选择与改动风险匹配的检查：数据库对象命名和注释、租户隔离、范围过滤、敏感结果保护、接口契约和必要回归测试。
- 交付说明写清改动、验证结果、迁移 / 重建命令和未完成条件，不将未运行的测试或未执行的数据库升级写成通过。

常用验证命令（PowerShell，按任务选用）：

```powershell
# 在 plugins/core/backend/ 下：导入应用、运行相关模块测试
& '.\.venv\Scripts\python.exe' -c "import app.main"
& '.\.venv\Scripts\python.exe' -m pytest tests/test_相关模块.py -q

# 在 plugins/core/web/ 下：类型检查；认证或路由改动时运行对应测试
pnpm typecheck
pnpm test:auth
pnpm test:routes
```

`test_相关模块.py` 是占位名称，替换为实际测试文件。数据库升级、演示数据加载、外部模型调用和索引构建不属于普通检查，按已授权任务执行。
