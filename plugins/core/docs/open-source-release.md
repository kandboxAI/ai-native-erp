# 底座与 MES 开源发布

公开范围为 MIT 底座、inv、MES。EDU、客户资料、真实图纸及原开发仓库历史不在发行范围内。授权边界见 [LICENSE_SCOPE](../../../LICENSE_SCOPE.md)。

发行说明列出 ERP 源码和配套 Harness 源码的获取入口及版本。安装使用见[根 README](../../../README.md)，桌面安装包验收见[桌面指南](desktop-packaging.md#6-发布前验收)。

## 1. 生成候选发行物

当前仓库 README 面向 `plugins/core/` 布局的完整源码快照。下列 `export_core.py` 仍生成根级 `backend/web/miniprogram/docs` 布局，README 复制与链接改写也沿用旧规则，尚未适配当前文档和根级脚本。**纯底座导出流程暂不能作为已可用的公开获取入口**；发布前须完成布局适配和干净环境验收。以下保留维护者的候选生成命令，不表示导出物已可直接运行。

先整理本次发布代码，核对 `plugin.toml` 与 `suite.toml` 版本。在仓库根目录执行：

```powershell
python scripts/erp.py check
python scripts/erp.py pack mes --output dist/suites/mes-open-source.zip
& ./plugins/core/backend/.venv/Scripts/python.exe plugins/core/backend/scripts/export_core.py --output dist/core-open-source
```

Linux 前两条使用 `python3`；导出命令为 `plugins/core/backend/.venv/bin/python plugins/core/backend/scripts/export_core.py --output dist/core-open-source`。已有输出拒绝覆盖，重新发布使用新的输出路径。

MES 套件自动包含 inv；各插件携带自己的 MIT `LICENSE`。不用 `--source-only` 绕过正式包检查。以上步骤不访问数据库、不生成或执行迁移、不上传外部仓库。

从曾捆绑初始材料价表的旧 MES 套件升级时，如果导入器提示新版本删减了安装文件，先在接收环境备份并移出旧的 `plugins/mes/backend/app/modules/mes/cnc/data/cost_reference_v1.json`，再导入。数据库中已保存的材料规则和报价快照由各租户继续管理。

## 2. 发行物边界

- 底座业务模块由 `plugins/core/backend/app/framework/core_manifest.json` 决定，管理端页面按底座入口依赖闭包收集。
- 插件使用、但底座页面未直接引用的公共前端入口登记在同一白名单的 `web_shared_entries`，导出时包含其依赖闭包；不能只依据纯底座能否启动判断插件依赖完整。
- 测试、管理端静态资源、样式与构建辅助文件、小程序图标及构建脚本使用 `plugins/core/backend/scripts/core_source_allowlist.json` 的逐文件白名单。新增文件须审核后登记；被引用但未登记的资源会使导出失败。
- 不整体复制开发测试目录、静态资源目录或 `.vscode`。不复制本地环境文件、存储附件、私有备份、环境增量迁移、生成快照、依赖或 Git 历史。
- 在仓库根目录的 `release-markers.local.txt` 配置需排除的名称、域名和旧品牌标识，每行一项。也可通过 `ERP_RELEASE_MARKERS_FILE` 指定本地清单。纯底座导出会在生成文件清单前检查这些文本，命中时仅报告文件路径。清单不随源码发行，套件 ZIP 和二进制资源仍须单独审查。
- `source-manifest.json` 记录导出文件 SHA-256 和白名单摘要；导出失败不会留下一个貌似完整的最终目录。哈希用于核对文件完整性，不代替内容审核。

不要把导出目录复制回原开发仓库，也不要直接将原开发仓库设为公开。

## 3. 在干净环境验收

底座按 [运行说明](core-open-source.md) 安装依赖；在 `plugins/core/web/` 执行 `pnpm install --frozen-lockfile`、`pnpm test:auth`、`pnpm test:routes`、`pnpm build`。后端在 `plugins/core/backend/` 执行 `python -m pytest -q`；发行版只携带已选的离线测试。

再按 [MES 接入](mes-plugin-integration.md) 导入套件，在独立测试数据库验证初始化、按模型生成并审核差异、迁移、租户开通和主要业务流程。源码检查与前端构建不代表真实数据库已验收。

## 4. 公开发布

审核候选目录及套件 ZIP 的源码、文档、图标、示例和许可证，确认没有客户数据及环境配置后，为干净底座目录新建 Git 仓库，首次提交不带原仓库历史。MES 套件源码 ZIP 可作为版本附件发布；也可在干净底座内安装套件后建立包含 core、inv、MES 的公开仓库。

组合仓库安装插件后须重新记录最终文件清单，原 `source-manifest.json` 仅描述安装前的底座目录。版本附件保留各自包清单、许可证和校验摘要。此流程不自动创建远程仓库、提交或推送。
