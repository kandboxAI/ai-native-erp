# 开发与发布验证

在仓库根目录运行 `python scripts/erp.py check` 以核对部署组合、插件声明及源码。准备正式源码包时，按[插件开发](plugin-development.md)检查迁移与包内容。

- **后端**：使用底座虚拟环境运行改动范围内的测试。涉及数据库、Redis、对象存储或模型服务时，使用独立的测试环境和合成数据。
- **管理端**：在 `plugins/core/web/` 运行 `pnpm typecheck` 和 `pnpm build`。认证或路由改动分别运行 `pnpm test:auth` 和 `pnpm test:routes`。
- **小程序**：在 `plugins/core/miniprogram/` 运行 `pnpm typecheck`，以 H5 或微信开发构建验证入口与操作。微信发布前用发布配置构建，并验证目标 AppID 与真机请求。
- **租户**：在隔离环境实际完成数据库迁移、插件启用和业务操作，使用管理员及受限角色核对授权与数据范围。
- **桌面端**：按[打包指南](desktop-packaging.md#6-发布前验收)验证安装、登录和业务联动。

候选发行物的检查范围见[开源发布](open-source-release.md)。
