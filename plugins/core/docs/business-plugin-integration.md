# 插件接入：使用者快速上手

所有命令在**仓库根目录**执行。Windows 用 `python scripts/erp.py`；Linux 用 `python3 scripts/erp.py`，其余参数完全相同。入口自动使用 plugins/core/backend/.venv。先按[底座运行说明](core-open-source.md)安装环境、准备 PostgreSQL/pgvector、Redis 并配置 plugins/core/backend/.env。

## 选一条路线

| 你现在有什么 | 一条命令 | 接下来 |
| --- | --- | --- |
| 当前目录已有业务源码 | `python scripts/erp.py use mes` | 按第 2 节准备数据库，再启动开通 |
| 收到插件或套件 ZIP | `python scripts/erp.py install dist/suites/实际文件.zip` | 按第 2 节准备数据库，再启动开通 |
| 需要交付当前业务 | `python scripts/erp.py pack mes` | 把输出的 ZIP 交给安装者 |

edu、mes、inv 等都能使用同一入口。程序自动识别套件/单插件；套件包含依赖，单插件 ZIP 则要求依赖源码已存在。use/install 均完成依赖校验、部署选择和源码/迁移检查，中途失败立即停止。

新插件包把业务源码和资源放在 `plugins/<key>/` 内，安装、启动命令不变。开发位置及旧布局更新步骤见[插件源码目录](plugin-source-layout.md)。

插件自己的运行参数和密钥按[插件运行配置](plugin-configuration.md)准备：模板随包交付，实际配置放在 `plugins/core/backend/config/plugin/<key>.env`，安装升级不覆盖。更新含 `configuration` 声明的插件前，先更新底座加载器。

## 0. 新库必须先初始化底座

**新库在启动和开通前执行一次**；已经初始化并能正常登录的底座库跳过。

```text
python scripts/erp.py init
```

命令显示主机、库名、默认租户 schema，输入提示的 `库名/schema` 确认后才执行。会创建认证、默认租户 L1 表与管理员；不创建数据库本身，不开通业务、不加载演示数据。服务器须先具备 pgvector 文件，public 初始化负责在目标库启用扩展。

## 1. 导入正式插件包并选择部署

收到 ZIP 时执行：

```text
python scripts/erp.py install dist/suites/实际文件.zip
```

自动预检所有包、保护本地文件、导入源码/页面、补齐部署依赖并检查。加 `--dry-run` 仅预览；未准备迁移的开发包加 `--source-only`，不能直接开通。相对 ZIP 路径一律以仓库根目录为准。

当前目录已有源码时直接执行 `python scripts/erp.py use mes`，无须重新导入自己的包。默认保留原组合；**只运行 MES**用 `python scripts/erp.py use mes --replace`；混合运行用 `python scripts/erp.py use edu mes --replace`。依赖由程序补齐。

## 2. 生成、审核和执行本环境迁移

在根目录执行（示例为教育；也可替换成 mes 或 inv）：

```text
python scripts/erp.py db revision --plugin edu --schema t_actual
```

审核生成文件，再执行 `python scripts/erp.py db upgrade --plugin edu --schema t_actual`。依赖自动包含，增量不随插件包分发；详情见[数据库维护](database-workflow.md)。

### 启动开发环境或构建部署

重启后端（沿用 VS Code 启动项），管理端在 plugins/core/web/ 执行 `pnpm dev`；生产环境重新构建并部署前后端，小程序按自己的平台构建。源码命令不会启动服务或发布小程序。

## 3. 为目标租户真正开通

目标租户管理员登录 **系统管理 → 应用管理**：

- 套件点击 **启用整套**，程序依次开通依赖和业务插件。
- 单插件在组件列表启用；有缺失依赖时先处理依赖，成套交付优先用套件。
- 开通会执行已有本地迁移并检查模型，随后同步权限菜单和必需配置；普通成员仍要分配权限。

成功后检查“已就绪/启用”和真实空列表/业务操作。源码检查通过不等于数据库或业务验收通过。

通用页面应由所属插件声明实体契约；源码校验拒绝未知实体，并列出接口未绑定的入口。该结果只说明当前组件的接口绑定情况，不判定整个业务是否实现。插件化先复用已有实现；确实缺失的业务代码只记录，不在接入时补写。教育页面的核对结果见页面绑定范围（开发仓库/插件中的 `education-page-status.md`，未随纯底座分发）。

## 4. 开发者：把待迁移源码准备为正式包

已有正式包的使用者跳过。新业务开发、旧业务适配、迁移生成和审核分别见[开发维护](plugin-development.md)、[脚本转换](plugin-script-conversion.md)、[AI 接入任务单](plugin-ai-onboarding.md)。不要自动生成空迁移或重建数据库绕过失败。

源码和迁移准备好后，交付只需 `python scripts/erp.py pack mes`；自动识别套件并收集依赖、校验成品，输出唯一时间戳文件名。支持 `--output <路径>`；正式包要求迁移齐全，开发包才使用 `--source-only`。不会执行数据库升级。

## 5. Harness 检索同步

迁移完成、确认目标库后，一条命令同步表/接口快照并构建索引：

```text
python scripts/erp.py ai sync --schema t_default --index
```

源码包不含表/接口快照，各环境迁移后自行生成，不提交 Git。`t_default` 换成实际租户。会先显示目标并确认，随后读取数据库、调用向量模型并写入该租户索引。仅同步快照去掉 `--index`。详见[Harness 同步说明](harness-sync.md)。

## 6. 已有插件的版本升级

拿到新 ZIP 后再次 `python scripts/erp.py install <ZIP>`，按第 2 节生成、审核并执行目标库差异，再重启/构建，在页面点击 **升级整套** 或单组件的升级按钮。升级保留原启停状态；失败保留已完成组件并报告失败位置，修复后重试。

停用保留数据，仍被其他业务使用的共享组件会保留。安装器拒绝覆盖本地修改，不删除安装记录绕过冲突。模型/接口变更后另行同步 Harness。

## 文档入口

[统一命令与 Linux 用法](plugin-commands.md) · [套件及共享依赖](business-suites.md) · 教育（开发仓库/插件中的 `edu-plugin-integration.md`，未随纯底座分发） · [MES](mes-plugin-integration.md) · [开发配置参考](business-plugin-reference.md)
