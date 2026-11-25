# 插件与套件目录

纯底座导出不携带业务插件。已安装源码、部署加载、租户开通和用户权限是不同状态，分别核对对应配置。

## 使用入口

[快速接入](core/docs/business-plugin-integration.md) · [统一命令（Windows/Linux）](core/docs/plugin-commands.md) · [套件说明](core/docs/business-suites.md) · [Harness 同步](core/docs/harness-sync.md)

在仓库根目录用 `python scripts/erp.py use <key>` 选择并检查已有源码；`python scripts/erp.py install <ZIP>` 导入并检查；`python scripts/erp.py pack <key>` 交付。Linux 使用 python3。随后重启前后端，在管理端为租户开通。

## 当前开发目录中的业务

| 插件 | 职责 | 使用说明 |
| --- | --- | --- |
| edu | 教育及 hr/ar/fac/tkt 内部模块，套件仅包含共享 inv | 教育使用（开发仓库/插件中的 `core/docs/edu-plugin-integration.md`，未随纯底座分发）、插件说明（开发仓库/插件中的 `edu/README.md`，未随纯底座分发） |
| mes | 制造执行，套件入口 | [MES 使用](core/docs/mes-plugin-integration.md)、插件说明（开发仓库/插件中的 `mes/README.md`，未随纯底座分发） |
| inv | 物资与库存，教育/MES 共享 | 库存说明（开发仓库/插件中的 `inv/README.md`，未随纯底座分发） |

其他环境可能只有部分源码；实际组成以 plugin.toml、suite.toml、deployment.json 和租户状态为准。

## 开发入口

业务后端、管理端、小程序及其资源统一存放在 `plugins/<key>/`；用法见[插件源码目录](core/docs/plugin-source-layout.md)。迁移目录和主设计文档保留原位置。

[开发与迁移维护](core/docs/plugin-development.md) · [配置参考](core/docs/business-plugin-reference.md) · [脚本转换](core/docs/plugin-script-conversion.md) · [AI 接入任务单](core/docs/plugin-ai-onboarding.md)

原四个插件已归并到 EDU，声明归档在 edu/legacy/；不再独立接入。见归并说明（开发仓库/插件中的 `core/docs/edu-consolidation.md`，未随纯底座分发）。
