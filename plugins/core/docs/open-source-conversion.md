# 从旧部署迁移到插件化底座

全新部署按[底座运行说明](core-open-source.md)初始化空库，再通过[插件接入手册](business-plugin-integration.md)导入并启用所需插件。

已有部署继续使用与目标数据库配套的应用版本和迁移链。迁移至插件化底座前，备份数据库和对应配置，盘点旧模型、业务数据及依赖，在隔离环境验证数据转换和迁移顺序。旧业务源码的整理步骤见[插件转换](plugin-script-conversion.md)，目标数据库的增量升级见[数据库维护](database-workflow.md)。

对外发行使用[开源发布流程](open-source-release.md)生成并审查候选源码。版本库历史与本地环境配置不属于候选发行物。
