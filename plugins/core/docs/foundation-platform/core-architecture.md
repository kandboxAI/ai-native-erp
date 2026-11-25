# 开源底座与插件边界

底座与业务设计统一见 [文档索引](README.md)。当前分层及插件契约分别见 current-layered-architecture.md、current-plugin-architecture.md；原总体设计保留全文，插件 docs 可保留随包说明。

## 当前实现

- L1 是行业无关的认证、租户、组织、用户、授权、字典、导航、工作流、通知、文件、审计及通用 AI 基础设施。模块范围见 `plugins/core/backend/app/framework/core_manifest.json`。
- L2 公共业务和 L3 行业业务均通过 `plugins/<key>/plugin.toml` 注册，不随纯底座发行。当前没有内置业务插件。
- `deployment.json` 选择本次部署的全部插件及其依赖。空数组为纯底座；非空为自定义组合，不再内置学校、工厂组合名。
- 需要整套交付的业务由插件自身提供 `suite.toml`；套件命令统一解析依赖并写入显式部署配置，管理端支持整套开通、升级和停用。底座只含通用套件机制，见[业务套件说明](../business-suites.md)。
- 源码安装及构建、部署加载、租户安装启用、用户权限是四个不同步骤。前端包包含所选部署插件的代码，租户停用不会删除已发布代码，服务端必须继续拒绝访问。
- 新插件统一使用 `core` 迁移基线，迁移目录必须为 `plugins/core/backend/alembic/versions/plugins/<key>/`；每个租户独立 schema，共用该 schema 的 `alembic_version`。

## 插件目录与扩展点

业务插件可将同一发布周期内的多个模块统一发布。模块应保持各自的 Service 与数据库职责边界，共享能力通过插件依赖接入。

业务后端模型、Service、API 等在 `plugins/<key>/backend/app/modules/<module>/`，导入名称仍为 `app.modules.<module>`；管理端、小程序源码和资源也保存在插件目录。底座自身保留通用模块。`plugin.toml` 声明源码布局、模块归属、路由、依赖、迁移和 AI 提供器；`frontend.json` 声明页面范围和入口。详见[源码目录](../plugin-source-layout.md)。

框架按清单收集目录、字典、租户配置、演示数据、定时任务和字段提示等模块声明。业务模板通过 `workflow_defaults.py` 注册；业务审批状态、摘要、详情及处理人通过现有 `workflow.integration.registry` 注册。L1 不引用具体行业模块。

跨插件写入调用所有者的公开 Service；跨模块读取必须有权限、数据范围及字段契约。L2 不依赖 L3，插件不能拥有底座模块或底座前缀。模型与迁移不得写死租户 schema。

通用组织类型由 `sys_org_type` 字典维护；底座预置集团和组织。业务需要特定组织类别或业务归属限制时，在插件内扩展字典及所属 Repository 的校验，不在通用 CRUD 中添加行业判断。

## 数据与 AI

数据库规范以 [数据库命名与建模规范](database-naming-convention.md) 为准。AI 工具权限、租户启停、数据范围、原业务接口字段控制及写操作确认由 ERP 执行。公共隐私扫描、脱敏和结构化查询的额外字段白名单已取消，已登记查询资源使用实际模型字段；详见[模型出口说明](../harness-sync.md)。元数据和索引使用独立 CLI，不随服务启动或迁移自动构建。

通用受控工具使用 `erp_api`、`erp_discover`、`erp_query` 和 `erp_open_page`。模型网关使用 `x-erp-client-id`，桌面桥使用 `window.erpDesktop`。行业数据由插件的受控资源提供器发布，结构化查询使用已登记资源。

## 交付边界

接入步骤以 [业务插件接入手册](../business-plugin-integration.md) 为准；文档没有假定 `PluginContext`、远程插件仓库或热安装接口已经存在。旧教育/MES 部署继续使用其原代码和迁移树；当前 core 基线只用于新库/新 schema，不能直接覆盖旧库升级。

位置信息作为 inv 内部共享模块提供一个维护菜单，资产、仓库和 EDU 巡查共用；沿用现有 inv 交付及迁移流程。坐标必填及历史位置关联见位置维护说明（开发仓库/插件中的 `location-master-design.md`，未随纯底座分发）。
