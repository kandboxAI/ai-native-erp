# 从零开发插件：最小示例

## 先看你现在处在哪一步

本例用于理解新插件开发，不要求正在安装 inv 的使用者再创建示例。已有插件包请直接按 [主手册](business-plugin-integration.md) 导入。

旧业务需要先适配为包，再导入到其他底座。源码改造可交给 AI 按 [任务单](plugin-ai-onboarding.md) 完成。下面步骤在独立开发副本中练习。

| 你要做什么 | 从哪里开始 |
| --- | --- |
| 先理解怎么接插件，跑通菜单 → 页面 → 接口 | 按本文第 1～7 步做一个最小示例 |
| 把现有业务迁入插件 | 看[旧业务移植操作单](legacy-business-plugin-porting.md)，按实际模块依赖安排迁入顺序 |

最小示例没有业务表，用来验证接入机制；它不等于 MES 已接入。下面命令供你执行，本文更新没有替你修改部署、安装业务或操作数据库。

## 第 1 步：先让纯底座能登录

**已经用新库成功登录，并且能打开“系统管理 → 应用管理”的，跳到第 2 步。**

否则先做三件事：

1. 确认 Python/前端依赖已安装，PostgreSQL 18+、pgvector 和 Redis 已准备好。服务端需已有 pgvector 扩展文件；下面的 bootstrap 会在目标库自动启用扩展。安装与权限检查见[底座运行说明](core-open-source.md#postgresql-扩展检查)。
2. 编辑 `plugins/core/backend/.env`，填写**准备使用的新库**的连接、Redis、JWT、管理员邮箱和密码。以下示例用 `DEFAULT_TENANT_NO=default`，对应 `t_default`；如果你用了其他编号，后面的 schema 一起替换。现有 `.env` 不要用示例文件覆盖。
3. 根目录 `deployment.json` 保持：

```json
{ "format_version": 1, "plugins": [] }
```

在 **`plugins/core/backend/` 终端**执行下面命令（会写入这个新库）：

```powershell
& '.\.venv\Scripts\python.exe' scripts/bootstrap.py --profile core --skip-other-tenants
```

正常启动只用根目录 JSON 选择插件。若终端或调试配置仍设置 `ERP_DEPLOYMENT_PROFILE`、`DEPLOYMENT_PROFILE` 或 `FRONTEND_DEPLOYMENT_FILE`，先移除这些旧覆盖，否则可能仍在运行另一套组合。

然后在 VS Code 运行“**底座：启动前后端**”，打开 `http://localhost:8848`，用 `.env` 配置的管理员登录。

**这一步完成的标志：**应用管理能打开，列表为空。空列表是正常的；底座还没有任何业务插件。初始化报错时先解决报错，不继续安装插件。

## 第 2 步：生成一个最小插件

在 **`plugins/core/backend/` 终端**执行（只生成源码）：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli scaffold --key sample_app --name "示例应用" --layer L3
```

生成后，你会看到这些位置：

```text
plugins/sample_app/
  plugin.toml                         插件登记表
  frontend.json                       页面和入口登记表
  miniprogram/services.ts             小程序入口
  backend/app/modules/sample_app/      后端代码、权限、菜单、字典
  web/src/views/sample-app/index.vue   管理端页面
  web/src/api/sample_app.ts            管理端接口调用
  miniprogram/src/pages/sample-app/index.vue  小程序页面
plugins/core/backend/alembic/versions/plugins/sample_app/   本插件的迁移目录
```

**这些文件都已经由脚手架生成，不用你再照表新建。** 此时不要把示例替换成旧 MES 文件；先保持生成内容原样。

如果报“拒绝覆盖”，说明目标已经存在。检查已有文件，接着做后续步骤即可，不要反复生成或删除已有开发内容。

### 需要显示为“业务套件”时

`scaffold` 默认只创建独立插件，不生成套件声明。若该应用需要作为业务套件统一管理，在 `plugins/sample_app/suite.toml` 新建：

```toml
format_version = 1
key = "sample_app"
name = "示例业务套件"
version = "0.1.0"
plugins = ["sample_app"]
```

key 和 version 与同目录 `plugin.toml` 一致。套件可以只有一个根插件；依赖从 `plugin.toml` 的 requires 自动收集，不需要为了套件再拆分业务模块。

源码已部署、插件已启用时，新增声明后重启后端、刷新应用管理即可归入业务套件，沿用已有安装和启用状态，无需重新迁移或停用再启用。正式交付在仓库根目录用 `python scripts/erp.py pack sample_app`，会自动识别套件并包含依赖；下文第 3 步的底层 `plugin_cli pack` 只生成单插件包。完整操作见[业务套件](business-suites.md)。

## 第 3 步：自动登记页面和部署

在 `plugins/core/backend/` 运行以下命令。当前还没有迁移，因此明确标记为待开发源码包：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli pack --plugin sample_app --source-only --output ../../../dist/plugins/sample-app-dev.zip
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli install ../../../dist/plugins/sample-app-dev.zip --source-only --deploy
```

命令自动将示例选入根 `deployment.json` 并登记小程序页面，保留原组合与其他页面。此时不能给租户开通，先继续生成迁移。源码修改后重新打包请使用新文件名。

## 第 4 步：检查文件是否接齐

在 **`plugins/core/backend/` 终端**执行（不连接数据库）：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli check
```

输出里应包含下面这些值，其余输出不用手动填写：

```json
{
  "migration_base": "core",
  "plugins": ["sample_app"],
  "plugin_heads": { "sample_app": null }
}
```

这里的 `null` 正常，表示还没有生成本插件的迁移文件。报错就按文末对照表修正，**这一条通过后再继续**。

## 第 5 步：为这个空示例生成一个迁移分支

在 **`plugins/core/backend/` 终端**执行：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli revision --plugin sample_app --schema t_default --message "initial sample plugin" --baseline
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli check --require-migrations
```

**--baseline 只用于无业务模型的新插件固定基线**，不读写数据库；日常不带该参数，增量生成到本环境目录。

打开 `plugins/core/backend/alembic/versions/plugins/sample_app/` 下新生成的 `.py`，应看到分支 `sample_app`、依赖 `core_0001`，`upgrade()`/`downgrade()` 为空。检查输出中的 `plugin_heads.sample_app` 应从 `null` 变成版本号。

有真实业务表的插件不能拿空迁移充数；其模型开发和迁移步骤见后面的“加入真实业务”。

## 第 6 步：重启，然后给当前租户启用

1. 停止并重新运行 VS Code 的“**底座：启动前后端**”。插件装配在进程启动时确定。
2. 用当前租户的底座管理员登录，打开“**系统管理 → 应用管理**”。
3. 列表应出现“**示例应用**”，状态为“**待开通**”。点击“**启用**”，确认本次操作。
4. 这次点击检查模型并执行已有本地迁移、同步权限/菜单和基础配置，成功后显示“**已就绪**”并启用。
5. **退出并重新登录一次**，让前端重新取得权限和菜单。

不用再单独运行 `plugin_cli upgrade`；正常首次启用已经包含迁移。后者留给需要先单独检查 DDL 的开发人员。

## 第 7 步：确认接入成功

重新登录后：

- 左侧菜单出现“示例应用”；应用中心也有相应入口。
- 打开页面，显示“**插件入口已接通**”；下方“业务功能待实现”是这个空示例的正常状态。
- 浏览器开发者工具 Network 中，`GET /api/sample_app/status` 返回 HTTP 200，业务 `code` 为 `0`，`data.plugin_key` 为 `sample_app`。
- 停用后退出重登，入口不再出现；旧页面刷新后，对应业务接口也不能继续访问。

**到这里，你已经完成一次“源码登记 → 部署加载 → 迁移分支 → 租户启用 → 页面调用”的完整接入。没有新增业务表。** 小程序是否发布不影响这次管理端验收。

## 下一步：加入真实业务，具体改哪里

不要再生成一次脚手架。在已经跑通的插件中继续开发：

| 要加什么 | 修改哪里 | 什么时候做 |
| --- | --- | --- |
| 业务表 | `backend/app/modules/<模块>/models.py` | 先设计模型，按[数据库规范](foundation-platform/database-naming-convention.md)定义字段、外键、注释和权限范围 |
| 查询、业务动作、接口 | 同目录 `repository.py`、`service.py`、`schemas.py`、`api.py` | 让页面请求真实业务接口 |
| 权限与菜单 | 同目录 `catalog.py`；菜单 key 同步登记在 `plugin.toml` | 增加业务页面时 |
| 页面 | `web/src/views/<目录>/`、`web/src/api/` | 对齐服务端字段和权限 |
| 基础字典/必需配置 | `dictionary_specs.py`、`tenant_setup.py` | 正常开通需要的数据，不放演示记录 |
| 小程序、AI、审批 | [扩展参考](business-plugin-reference.md#11-通用外壳中的业务扩展) | 主业务接通后再按需要扩展 |

业务模型完成后，在仓库根目录按目标库生成差异：

```text
python scripts/erp.py db revision --plugin sample_app --schema t_actual
```

审核输出文件后执行 `python scripts/erp.py db upgrade --plugin sample_app --schema t_actual`。递增插件版本、重启后端，在应用管理点击“升级”；无需反复停用依赖。环境增量不提交、不随包发布，见[数据库维护](database-workflow.md)。

## 报错时先看这一张表

| 现象 | 检查位置 / 下一步 |
| --- | --- |
| 能力包列表没有新插件 | 根 `deployment.json` 是否包含它；后端是否已经重启；清单是否在 `plugins/<key>/plugin.toml` |
| `插件页面未注册` / 小程序页面缺失 | 第 3 步导入是否成功；frontend.json 中页面是否存在 |
| `尚无迁移` | 第 5 步是否成功；迁移应在本插件目录内 |
| `请先为依赖插件 … 创建迁移` | 先完成依赖插件，再生成当前插件迁移 |
| `Target database is not up to date` | 开发库还有未审核/未执行迁移，先完成当前组合的升级，不使用 stamp 绕过 |
| 开通失败 | 查看后端日志；页面只显示错误类型。修好后重试，不代表需要重建数据库 |
| 已启用但没有菜单 | 先退出重登；再核对 `catalog.py`、TOML 的 `menu_keys` 和权限；能力包列表与菜单是两个来源 |
| 改了模型但数据库没有变化 | 保存模型不等于生成迁移；生成迁移也不等于执行迁移；升级已有插件还要更新版本 |

本文的文件装配与检查流程已在隔离临时目录核对；真实新库初始化和租户启用需按上述步骤在你的目标库验收。
