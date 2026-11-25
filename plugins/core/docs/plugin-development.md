# 插件开发与迁移维护（开发者）

日常开发、启动和测试先看[开发上手](developer-quickstart.md)。本页补充新插件基线与打包细节。

日常安装与交付用[统一命令](plugin-commands.md)，不必执行下列底层步骤。本页用于新插件开发、初始/增量迁移及明确需要的单分支维护。生成和执行迁移分别取得授权；普通检查不访问真实业务库或模型。

## 准备正式包

### 准备源码

- 新业务用 plugin_cli scaffold，旧业务优先[脚本转换](plugin-script-conversion.md)，需 AI 协助时用[任务单](plugin-ai-onboarding.md)。
- 模型、权限、数据范围、目录、初始化、前端和 AI 定义按[配置参考](business-plugin-reference.md)准备。
- 专属运行参数使用脚手架生成的配置类型、清单声明和模板，见[插件运行配置](plugin-configuration.md)；不继续往公共 `.env.example` 添加业务插件变量。
- 源码已在当前目录，用根目录 `python scripts/erp.py use <key> --source-only` 选择并检查；--source-only 不要求迁移，不代表可以为租户开通。

以下底层开发命令在 **plugins/core/backend/** 执行，先激活该环境，之后 Windows/Linux 共用 python 参数：

```powershell
# Windows / PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / Bash
source .venv/bin/activate
```

例如生成新插件源码（不选择部署、不生成迁移）：

```text
python -m app.framework.plugin_cli scaffold --key sample_app --name "示例应用" --layer L3
```

默认生成 `source_layout = "contained"`，后端、管理端、小程序源码均在 `plugins/sample_app/` 下。资源、导入规则和旧源码搬迁见[插件源码目录](plugin-source-layout.md)。

脚手架默认生成独立插件。需要业务套件管理时，在同目录增加 `suite.toml`，见[最小示例中的套件步骤](business-plugin-development-example.md#需要显示为业务套件时)；套件可只有一个根插件，依赖自动收集。

### 新插件初始迁移

**仅用于尚无迁移分支的新插件，需明确授权生成。** schema 是离线命名占位，不连接数据库。依赖先于目标插件生成，保留已有分支：

```text
python -m app.framework.plugin_cli revision --plugin sample_app --schema t_plugin_build --message "initial sample_app" --from-models
```

审核只包含所属插件的对象，包含 core/实际依赖锚点、约束、索引、注释和可用降级顺序。无表插件使用 revision --baseline 建立固定空分支，不为掩盖漏注册而生成空迁移。已有分支不能再次生成初始迁移。

### 检查与出包

回到仓库根目录（Linux 使用 python3）：

```text
python scripts/erp.py check
```

```text
python scripts/erp.py pack sample_app
```

迁移不齐时只允许 pack --source-only。成品不覆盖已有输出，套件自动收集全部依赖；哈希校验不证明源码可信，也不代替业务测试。

### 当前目录与其他环境导入

当前开发目录已有源码、迁移时直接 use，不必逐文件复制或重新转换。另一个环境使用 `python scripts/erp.py install <ZIP>`，随后按[使用手册](business-plugin-integration.md)初始化新库（如需要），生成并审核目标库差异、执行后再启动开通。

遇到本地修改冲突，先保留并合并，不删除安装记录绕过检查。安装器不会自动移除旧版本删除的文件。

## 日常开发与部署

增量按目标库生成，文件仅保存在本环境。统一命令、审核和执行见[数据库维护](database-workflow.md)。模型与必要的数据转换逻辑随插件提交，环境增量不提交、不打包。

发布时递增真正变更的插件版本；套件拥有插件变版本时同步 suite.toml。打包、导入后，目标环境自行生成并审核差异，再迁移并在应用管理升级。

EDU 内部 hr/ar/fac/tkt 统一使用 --plugin edu；core、inv 仍按归属分别维护。插件移出 deployment 不会删除数据，新流程也不需要解析未加载插件的旧版本。

## 旧链兼容

共享基线和已经发布的历史不得删除或改写。tenant / tenant_core 及显式 --legacy-history 仅用于原版本链维护，不作为日常生成入口。当前未提交旧增量保存在 plugins/core/backend/.local-migrations/legacy/；缺文件先恢复，不能 stamp 或删除版本记录。

[架构边界](foundation-platform/core-architecture.md) · [数据库规范](foundation-platform/database-naming-convention.md) · [Harness 同步](harness-sync.md)
