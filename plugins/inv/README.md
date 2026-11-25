# 物资与库存插件 inv

本插件使用 [MIT 许可证](LICENSE)。当前版本以 `plugin.toml` 为准；开源发行步骤见 [发布说明](../core/docs/open-source-release.md)。业务仓库用途可由所属插件扩展。

后端、管理端和小程序源码在本目录的 `backend/`、`web/`、`miniprogram/src/`；独立目录与资源规则见[源码目录](../core/docs/plugin-source-layout.md)。

> 使用入口：[快速接入](../core/docs/business-plugin-integration.md) · [统一命令（Windows/Linux）](../core/docs/plugin-commands.md) · [套件](../core/docs/business-suites.md) · [Harness 同步](../core/docs/harness-sync.md)。


用于全新 core 基线租户。拥有库存、物资领用、物料及供应商模块；不依赖教育或 MES。已声明的 Python/pnpm 依赖由当前底座依赖清单提供，本版本不要求额外安装包。

## 导入和启用

在 ERP 根目录执行 `python scripts/erp.py install <包路径>`，然后重启/重新构建前后端，在目标租户的“系统管理 → 应用管理”启用。

导入只写源码与配置；首次启用才执行独立 inv 分支迁移和必需配置。迁移初始版本为 `2c3a70a76b0a`，依赖 `core_0001`，创建 16 张本插件表。不要将此新基线直接用于已有旧业务 schema。

## 当前范围

安全库存按物料与仓库配置下限及补货目标。首次入库前可先设置阈值，保存后按当前库存余额计算预警。物资申请按组织权限审批与发放，申请人可在管理端和小程序查看进度。

- 管理端：库存查询、物料及基础资料、入库、出库、调拨、借出归还、报损；使用真实服务端接口。
- 单据列表及导出按明细配对展示物料、数量和单位；列表固定显示前两行，通过“查看明细”浮层查看全部，避免撑高表格行，不再展示跨单位合计数量。列表接口新增 `item_summaries`（`line_no`、`item_name`、`quantity`、`unit_code`），旧摘要字段仅为兼容保留，无数据库结构变更。
- 小程序：物资领用、申请表单、申请详情、真实库存查询，共 5 个页面。物资配置页明确提示使用管理端，目前不提供移动维护。
- 正常开通幂等补齐字典、库存单据类型等配置；不自动加载演示数据。
- 通过底座角色与菜单管理授权，按组织范围查看仓库和单据。
- Harness 同步使用已审查的接口范围，见[同步说明](../core/docs/harness-sync.md)。

源码包包含 `plugin.toml`、`frontend.json`、后端、前端、小程序、独立迁移和额外 API 文件。源码接入与构建检查不能替代目标库上的业务验收；请验证权限、数据范围、领用及单据记账流程。


## 库存升级

按[数据库维护](../core/docs/database-workflow.md)对目标库生成并应用 inv 差异。升级早期库位结构时，核对历史库位与仓库的唯一有效映射，避免将跨组织或无法确认的记录自动回填。旧库重新增加必填的 `warehouse_type_code` 时，迁移应设置 `general` 默认值用于补齐已有行，并保留仓库 ID、编号与库存关系。

领用签收、位置和资产边界见[领用签收](docs/requisition-receipt.md)、[位置管理](docs/location-master-design.md)及[资产流转](docs/inventory-asset-lifecycle.md)。

仓库删除需要 `inventory_warehouse:delete` 权限，并按对应组织范围校验。删除前须结清引用该仓库的在途业务，逐条核对库存和预留均为零。删除后历史单据与记账流水继续保留。
