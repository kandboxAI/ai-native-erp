# 业务套件：统一交付相关插件

套件是插件及依赖的交付组合，内部仍保留模块、数据、版本、迁移和租户状态。底座只提供通用机制；套件声明在拥有插件的 `plugins/<key>/suite.toml`。

| 套件 | 根插件 | 自动包含 |
| --- | --- | --- |
| 教育 | edu（含 hr/ar/fac/tkt 内部模块） | inv |
| MES 制造 | mes | inv >= 0.1.2 |

教育的四个内部模块不再分别安装、启停或发版；旧历史随 EDU 保留，见归并说明（开发仓库/插件中的 `edu-consolidation.md`，未随纯底座分发）。

inv 是共享插件。同租户的教育和 MES 共用一份库存记录及数据表；停用一方，另一方仍需要的 inv 会保留。

## 日常使用

所有命令在仓库根目录执行。Windows 使用 python，Linux 使用 python3。

| 操作 | 命令 |
| --- | --- |
| 选择教育并检查 | `python scripts/erp.py use edu` |
| 切换到仅 MES 并检查 | `python scripts/erp.py use mes --replace` |
| 选择教育和 MES 并检查 | `python scripts/erp.py use edu mes --replace` |
| 导入套件并检查 | `python scripts/erp.py install <套件ZIP>` |
| 打包套件及依赖 | `python scripts/erp.py pack mes` |

use 默认合并保留已有部署；--replace 才替换。deployment.json 仍是最终部署清单，程序写入完整依赖；修改后重启/重新构建。

## 3. 新库先初始化底座，再开通套件

新库按[底座运行说明](core-open-source.md)准备数据库、pgvector、Redis 和 plugins/core/backend/.env，执行 `python scripts/erp.py init` 并核对确认目标。已有初始化的库跳过。

初始化后按[数据库维护](database-workflow.md)为该套件生成、审核并执行本环境差异，再重启前后端，在 **系统管理 → 应用管理 → 业务套件** 点击启用整套。开通会写数据库，执行已有本地文件、检查模型并同步必需配置；无须分别点击每个依赖。

## 升级、停用与重试

- 新版本：install 新 ZIP，生成并审核目标库差异、执行迁移，重启/构建，再点击升级整套；仅升级有新版本的组件，保留原启停状态，不支持降级。
- 停用：按反向依赖顺序处理，其他启用业务仍依赖的组件保留；没有使用者的套件组件会停用，包括曾单独启用的组件。数据不删除。
- 失败：展示失败组件和已完成组件，修复后重试。各组件迁移独立提交，不伪装为整套 DDL 已回滚；套件与单组件操作共享租户锁。

## 5. Harness 元数据统一维护

在仓库根目录执行 `python scripts/erp.py ai sync --schema <实际租户> --index`，一次同步快照并构建完整部署索引。可去掉 --index 只同步，具体目标确认、范围和模型配置见[Harness 同步说明](harness-sync.md)。套件不会自动扩大字段白名单。

## 新套件声明（开发者）

在拥有插件目录增加 suite.toml：

```toml
format_version = 1
key = "sample_app"
name = "示例套件"
version = "0.1.0"
plugins = ["sample_app"]
```

key/版本与同目录 plugin.toml 一致，plugins 为根插件，requires 递归依赖由程序收集。正式套件要求所有组件迁移完整；开发源码包使用 --source-only。底座导出不携带行业套件。

[简明接入手册](business-plugin-integration.md) · [统一命令](plugin-commands.md) · 教育（开发仓库/插件中的 `edu-plugin-integration.md`，未随纯底座分发） · [MES](mes-plugin-integration.md)
