# 不使用 AI：用脚本把旧业务整理成插件包

现有源码只要已有 `plugins/<key>/plugin.toml` 和 `frontend.json`，就可以运行转换脚本；不需要再照着文件清单复制和登记。当前备份中的 inv、MES、edu 都有这两个入口。脚本不要求使用 AI。

## 1. 运行一条转换命令

在 **plugins/core/backend/** 终端运行；`--source` 指向待转换源码的仓库根目录，不是插件子目录。源项目可使用其原有的 `plugins/`、`backend/`、`web/`、`miniprogram/` 布局：

```powershell
# 以 inv 为例，将路径替换为待转换的源码目录
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli convert --plugin inv --source ../../../legacy-project
```

从上述工作目录引用当前仓库根目录使用 `../../..`；待转换源码的布局和支持范围以转换器检查报告为准。仅预览时加 `--dry-run`：只准备隔离底座并分析文件，不复制业务、不执行旧业务 Python，也不修改当前源码或部署。

实际转换会在 `plugins/core/backend/.generated/plugin-conversions/` 创建独立工作目录。输出包含 `workspace`、`report`、`status` 和成功时的 `package` 路径。默认 ZIP 名含本次转换标识，可重复运行；也可用 `--output <新文件名.zip>` 指定路径，已有文件拒绝覆盖。

输出使用 `source_layout = "contained"`，源码和资源在 `plugins/<key>/` 内，见[目录规则](plugin-source-layout.md)。已经使用此布局的插件直接 check/pack，不重复 convert。

## 2. 脚本替你做什么

| 步骤 | 自动处理 |
| --- | --- |
| 准备工作目录 | 导出纯底座，复制清单声明的业务模块、页面、提供器及额外文件；当前工程保持原样 |
| 收集前端依赖 | 跟踪静态本地引用，补齐辅助组件、工具、资源文件；私有辅助代码归入插件页面目录 |
| 整理 API | 业务 API 自动加本插件 key 前缀，修正 import，写入 package_files；认证及请求基础设施复用当前底座 |
| 找回旧菜单 | 当模块 MENUS 为空时，从旧 route_manifest.json 按组件归属提取菜单，保留权限标识，移至本插件顶层；重复组件的旧 URL 作为隐藏别名保留 |
| 转换清单 | 旧 tenant 基线改为 core 独立路径；旧迁移不复制，不改历史数据库升级链 |
| 接齐工程 | 自动登记小程序页面，选择插件及已就绪依赖；依赖从当前底座已导入的源码取得，不联网下载 |
| 检查与出包 | 执行模型、目录、权限、页面、迁移树检查，检查通过后自动打包 |

普通转换会执行隔离目录中可信业务源码的离线检查，不启动应用服务、不连接或升级数据库，不自动安装 Python/pnpm 依赖。请使用可信源码。动态 import/glob、固定租户、旧组合、旧门户和本地模拟 Store 等会进入检查报告。

## 3. 看结果，只处理剩下的具体问题

| status | 你接下来做什么 |
| --- | --- |
| `package_ready` | 已有迁移且离线检查通过，取得 package 路径，按第 4 节导入 |
| `source_only_needs_migration` | 源码检查通过，产出待开发源码包；需要显式生成初始迁移后再正式出包 |
| `needs_code_changes` | 查看 check_error 和 review，在 workspace 中修正具体模型/代码；不生成可安装 ZIP |
| `needs_review` | 框架检查已通过，但 review 列出了需要开发人员判断的文件和位置；不生成可安装 ZIP |
| `preview` | 仅预览转换计划 |

例如，旧 inv 曾把库存写在本地 Store、根据学校角色默认授权，或者模型缺字段注释。这些是业务代码问题，需要普通开发人员修正，脚本不会假装已经转换正确。**文件搬运、依赖归位、清单和目录登记不再需要手工重复做。**

在输出的 workspace 中修正后，使用该目录的 Python 环境执行 `plugin_cli check`，再按[开发维护](plugin-development.md)准备迁移和 pack；不要对已转换的独立目录再次 convert。缺少依赖插件时先导入/转换依赖，如 inv 完成后再处理 MES。

如果是全新插件，尚无迁移分支，并且你允许生成迁移，可在这次命令末尾增加：

```text
--generate-initial
```

此标志只在离线检查和 review 均通过后生成初始迁移文件；不连接或升级数据库。已有 core 分支保留，不会重新生成初始迁移。增量迁移仍使用已升级开发库上的 revision --autogenerate 流程。AI 执行该标志前仍须取得项目规则要求的明确授权。

## 4. 导入包

转换器的 workspace 是用于检查源码的隔离目录，不是已经初始化的运行数据库。**实际使用新库时，先在当前工程按 [接入手册第 0 节](business-plugin-integration.md#0-新库必须先初始化底座) 执行底座初始化**：

```powershell
# plugins/core/backend/；先核对 .env 目标库和管理员配置；此命令会写数据库
& '.\.venv\Scripts\python.exe' scripts/bootstrap.py --profile core --skip-other-tenants
```

看到 `bootstrap complete` 后，再导入包；若只是提前整理源码，也可以先导入，但启动/登录和租户启用前必须完成初始化。

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli install '上一步输出的完整ZIP路径' --deploy
```

随后按 [通用插件集成手册第 2、3 节](business-plugin-integration.md#2-生成审核和执行本环境迁移) 生成、审核并执行迁移，重启/重新构建并为目标租户启用。仅 `source_only` 的开发包不能直接用于租户开通；源码适配完成后，按 [通用手册第 4 节](business-plugin-integration.md#4-开发者把待迁移源码准备为正式包) 的具体命令准备迁移和正式包。

脚本已做后端装配和静态前端依赖检查；**完整 TypeScript/构建测试、目标库迁移及真实业务验收仍需完成**。前端依赖未安装时，不能把源码包检查当成前端构建通过。详见 [接入手册](business-plugin-integration.md)。
