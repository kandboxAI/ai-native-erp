# 开发上手：启动、更新数据库、验证

管理端列表使用共用的 `ListPagination` 组件。

日常开发看这一页即可；首次安装 Python、pnpm、PostgreSQL/pgvector、Redis 和配置 `plugins/core/backend/.env`，先看[环境准备](core-open-source.md)。

首次使用 ERP＋DSH 桌面，先按本文完成 ERP 数据库对齐和浏览器登录，再按[桌面指南](desktop-packaging.md#2-首次构建与桌面联调)安装配套 Harness、显式执行首次 `pnpm build:artifacts` 并启动桌面。安装包使用同一指南的独立打包流程；ERP 参数检查不代替 Harness 工具链预检。

业务源码在 `plugins/<key>/backend/app/modules/`、`plugins/<key>/web/src/` 和 `plugins/<key>/miniprogram/src/`；底座目录保留通用能力。Python 导入名称和菜单路径保持不变。图片、引用规则及旧目录转换见[插件源码目录](plugin-source-layout.md)。

除特别说明外，以下命令在**仓库根目录**执行，示例租户 schema 为 `t_default`，与实际配置不同时统一替换。Windows 使用 `python scripts/erp.py`；也可换成 `.\scripts\erp.ps1`。Linux 换成 `sh scripts/erp.sh`，后面的参数相同，自动使用 `plugins/core/backend/.venv`。

## 1. 选择要运行的插件

已有业务源码时不用重新打包导入；纯底座发行版先按[接入手册](business-plugin-integration.md)导入所需插件。按需选择一行：

| 运行内容 | 命令 |
| --- | --- |
| MES 及库存依赖 | `python scripts/erp.py use mes --replace` |
| 纯底座 | `python scripts/erp.py use core --replace` |

命令更新 `deployment.json` 并检查源码，依赖自动补齐。部署选择和租户启用是两步；改组合后重启前后端。

## 2. 更新自己的数据库

**已有底座库**：停后端、备份数据库，核对 `plugins/core/backend/.env` 的连接和目标 schema。

**全新空库**：先创建数据库、配置连接，再执行一次 `python scripts/erp.py init`，成功后继续下面步骤。已有库不要重复初始化。

先生成差异（只生成文件，不执行业务 DDL）：

```text
python scripts/erp.py db revision --schema t_default
```

打开输出的“待审核”文件，核对删列、类型变化、外键和数据回填。确认后再执行：

```text
python scripts/erp.py db upgrade --schema t_default
```

默认按 **public → core → 选中的业务插件** 的依赖顺序处理。可为两条命令添加 `--plugin mes` 以聚焦制造套件及其依赖。

每条命令都会显示目标并要求确认；失败立即停下。无差异不生成空文件；已有待执行迁移先审核执行。自动比较不能推断字段重命名或旧数据身份映射，不能直接把删列/加列当作重命名执行。

## 3. 启动并开通租户

后端，在仓库根目录：

```text
python scripts/erp.py serve --reload
```

此入口监听底座及所选插件后端源码；VS Code 的“底座：后端 FastAPI”也已监听插件目录。

也可进入 `plugins/core/backend/`，激活该目录下的 `.venv` 后直接启动，与上面的命令二选一：

```text
uvicorn app.main:app --port 8000
```

管理端，另开终端进入 `plugins/core/web/`：

```text
pnpm install --frozen-lockfile
pnpm dev
```

首次或依赖锁文件变化时才需安装依赖。打开 <http://localhost:8848>，管理员进入 **系统管理 → 应用管理**：新安装点“启用整套”，更新版本点“升级整套”；原来停用的需要再启用。普通账号还需分配菜单和权限。

后端启动不自动迁移；应用管理执行已有本地迁移并检查结构、同步目录，不替开发者生成和审核迁移。更新同一开发目录的代码不用重新导入 ZIP。

## 4. 后续开发怎么做

| 改什么 | 改哪里 / 接下来做什么 |
| --- | --- |
| 通用认证、组织、权限、工作流等 | 底座模块；不得反向引用业务插件 |
| 库存、资产管理 / 制造 | 分别改 inv / mes 所属模块 |
| 新模块、接口、菜单、页面 | 同步 `catalog.py`、`plugins/<key>/plugin.toml`、`frontend.json` 中的相应声明；已有登记无需重复添加 |
| 菜单、权限、字典或必需配置 | 声明更新后执行下面的 `dev sync`，无需打包或递增版本 |
| 模型结构 | 同步接口及前端字段，再重复第 2 节；只改页面无需迁移 |
| 表、接口或 AI 定义 | 数据库就绪后按下方命令同步 Harness |

提交源码、清单、必要的数据转换逻辑及测试。日常环境增量在 `plugins/core/backend/.local-migrations/`，**不提交 Git，随数据库备份保存**；仓库已有基线和已发布历史保留。其他开发者拉取代码后，对自己的库重复第 2 节。

本地同步配置（模型有变化时，先完成第 2 节）：

```text
python scripts/erp.py dev sync --schema t_default
```

在 `plugins/core/backend/` 目录执行则用 `python ../../../scripts/erp.py dev sync --schema t_default`。也可加 `--plugin mes`，包含已启用的依赖；Linux 使用 `sh scripts/erp.sh` 入口。

命令先显示目标并确认，仅用于 `APP_ENV=development`；同步底座及当前租户已启用插件的权限、管理端/小程序菜单、字典和必需配置，不自动开通插件、不改安装版本或启停状态、不执行迁移、不加载演示数据、不构建 AI 索引。缺表、缺列或待执行迁移会在配置写入前报错，按第 2 节处理。

成功后重新登录刷新菜单与权限；内置管理员会补齐授权，普通角色按现有目录授权规则补菜单，新业务权限仍需手动分配。已有租户自定义配置按原有幂等规则保留；失败时已完成的配置可能保留，修复后可重试。

## 5. 开发后怎么验证

先运行不访问数据库的源码检查：

```text
python scripts/erp.py check
```

再按改动选验证，不必每次全跑：

| 改动 | 验证 |
| --- | --- |
| 后端业务 | 使用 `plugins/core/backend/.venv` 的 Python 运行所属模块测试；涉及真实服务的集成测试另选专用测试库 |
| 管理端 | 在 `plugins/core/web/` 执行 `pnpm typecheck`；认证/路由改动加 `pnpm test:auth`、`pnpm test:routes` |
| 小程序 | 在 `plugins/core/miniprogram/` 执行 `pnpm typecheck`，再 `pnpm dev:h5` 或 `pnpm dev:mp-weixin` 实测 |
| 数据库 | `db upgrade` 成功并通过模型一致性检查后，启动实测登录、列表和本次修改的业务操作 |

至少用管理员和一个受限账号验证：菜单正确、接口可用、越权被拒；涉及租户开关时，再停用插件检查入口和接口。静态检查通过不等于业务已验收。

首次克隆或安装后使用 Harness，以及后续修改表/接口时，数据库升级后执行：

```text
python scripts/erp.py ai sync --schema t_default --index
```

表/接口快照不提交 Git、不随插件包分发，各环境自行生成。此命令会读取数据库、调用向量模型并写租户索引；需要已配置模型，完成后重启后端以清除缓存。只同步快照去掉 `--index`；离线检查用 `python scripts/erp.py ai check`。未构建索引时不能视为检索已就绪。

更多细节：[数据库维护](database-workflow.md) · [新插件接入](business-plugin-integration.md) · [新插件开发与出包](plugin-development.md) · [Harness 同步](harness-sync.md)
