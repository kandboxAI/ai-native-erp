# 底座与插件设计

底座文档描述通用架构、运行契约和数据规范。业务插件在自身目录维护领域设计、配置与升级说明。

| 文档 | 内容 |
| --- | --- |
| [架构边界](core-architecture.md) | 模块归属、依赖方向与扩展点 |
| [职责分层](current-layered-architecture.md) | L1 底座、L2 公共业务与 L3 行业业务 |
| [底座实施说明](current-foundation-platform-design.md) | 身份、组织、菜单、权限与通用能力 |
| [插件契约](current-plugin-architecture.md) | 源码布局、部署装配、租户启用与发布 |
| [数据库命名与建模](database-naming-convention.md) | Schema、对象命名、字段、约束与审计 |
| [目录命名](directory-naming-convention.md) | 目录命名及现有工具约定 |
| [数据库设计](core-database-design.md) | 认证、租户、迁移及业务模型边界 |
| [底座表目录](core-table-catalog.md) | 表用途及 ORM 入口 |
| [底座 ER 图](current-er-diagram.md) | 主要实体与关系 |
| [文件与附件设计](file-attachment-design.md) | 上传、绑定、读取及回收 |

## 插件领域设计

- **inv**：库存、物资申领与资产说明在 `plugins/inv/README.md` 和 `plugins/inv/docs/`。
- **MES**：制造执行、排程、询价报价与出货说明在 `plugins/mes/README.md` 和 `plugins/mes/docs/`。

运行与部署见[开发上手](../developer-quickstart.md)，创建或导入插件见[业务插件接入](../business-plugin-integration.md)。
