# 业务插件配置与扩展参考

操作主线见 [从这里开始](business-plugin-integration.md)，旧业务移植见 [移植操作单](legacy-business-plugin-porting.md)。本文件用于按需查配置、迁移和扩展约定。

更新：2026-10-22。本文对应已经实现的清单加载器与 `app.framework.plugin_cli`，不是架构草案。通用操作命令以 [插件集成与租户开通手册](business-plugin-integration.md) 为准。

部署清单决定加载的插件，租户启用记录决定可用范围。已有环境的升级见[旧部署迁移](open-source-conversion.md)。

## 1. 先分清三件事

| 操作 | 作用 | 是否操作数据库 |
| --- | --- | --- |
| 放入代码和 `plugin.toml` | 安装源码到工程，声明依赖与归属 | 否 |
| 编辑根目录 `deployment.json` 并重启/重新构建 | 把插件装入本次部署 | 否；启动不自动迁移 |
| 当前租户启用插件 | 检查依赖，升级该分支，执行开通配置，成功后标记 ready/启用 | 是 |

表留在当前租户 `t_<编号>` schema，按前缀区分领域，不另建一个 MES schema。停用只禁止入口和访问，不删除表和数据。插件不是运行时下载的远程页面；新代码进入部署仍需重新构建。

新插件使用 `source_layout = "contained"`：后端、管理端和小程序源码分别放在 `plugins/<key>/backend/app/modules/`、`plugins/<key>/web/src/`、`plugins/<key>/miniprogram/src/`。底座加载器保留 `app.modules.*` 导入名称，构建器保留菜单组件和移动路由的逻辑路径。下文未加插件前缀的源码路径是逻辑路径；旧 `legacy` 包仍兼容。完整规则见[插件源码目录](plugin-source-layout.md)。没有 `PluginContext.apply()` 接口。

## 2. 初始化一个纯底座新库

以下是供你执行的命令；不要在旧业务库执行纯底座初始化。

1. 编辑 `plugins/core/backend/.env`，设置实际新库的 `DATABASE_URL`、Redis、JWT、`DEFAULT_TENANT_NO`、`DEFAULT_TENANT_NAME`、`INIT_ADMIN_EMAIL`、`INIT_ADMIN_PASSWORD`。已有 `.env` 不要用示例覆盖。示例在完整仓库为 `.env.core.example`，底座源码包中为 `.env.example`。
2. PostgreSQL 使用 18+，服务端安装 pgvector。`public` 迁移会创建 vector 扩展，需要相应建扩展权限。
3. 根目录 `deployment.json` 改为：

```json
{ "format_version": 1, "plugins": [] }
```

4. 移除终端和启动配置中旧的部署覆盖。正常开发只以 JSON 为准：

```powershell
Remove-Item Env:ERP_DEPLOYMENT_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:DEPLOYMENT_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:FRONTEND_DEPLOYMENT_FILE -ErrorAction SilentlyContinue
```

还要检查 VS Code 的 `launch.json` / `envFile` 是否注入这些覆盖；仅清终端不影响调试器的独立环境。

5. 在 `plugins/core/backend/` 执行：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli check
& '.\.venv\Scripts\python.exe' scripts/bootstrap.py --skip-other-tenants
```

第一次检查应显示 `plugins: []`、`migration_base: core`。bootstrap 会升级 public、创建默认租户 schema、执行 `core_0001` 并开通管理员，不加载演示数据。若是刚导出的源码，请先按根 README 安装 Python/前端依赖。

后续示例以 **`t_default`** 为租户 schema：如果 `DEFAULT_TENANT_NO` 不是 `default`，把所有命令中的 `t_default` 替换成实际编号。确认登录和系统管理正常后，再开始业务接入。

## 3. 一个插件需要哪些内容

| 内容 | 实际位置 / 注册方式 |
| --- | --- |
| 版本、依赖、模块、路由、表前缀、目录归属 | `plugins/<key>/plugin.toml` |
| ORM | `backend/app/modules/<模块>/models.py` 或 `*_models.py`，使用 `SQLModel(..., table=True)` |
| SQL / 业务 / 协议 / API | 所属模块 `repository.py`、`service.py`、`schemas.py`、`api.py` |
| 权限和管理端、小程序菜单 | 所属模块 `catalog.py` 的 `PERMISSIONS`、`MENUS`、`MINIAPP_MENUS` |
| 字典定义和对公共字典的扩展值 | 所属模块 `dictionary_specs.py` 的 `DICTIONARIES`、`DICT_ITEMS`；模块编码须登记到 `sys_module` |
| 幂等必需配置 | `tenant_setup.py` 的 `async def setup_tenant(session, ctx)` |
| 演示数据 | `demo_seed.py` 的 `async def seed_demo(session, ctx)`；正常启用不调用它 |
| 固定初始基线 | `plugins/core/backend/alembic/versions/plugins/<key>/`，在 TOML 声明 |
| 前端范围、应用卡片、可选工作台 | `plugins/<key>/frontend.json` |
| 小程序入口提供器 | `plugins/<key>/miniprogram/services.ts`，返回当前权限可用的入口 |
| AI 查询和语义 | `ai_catalog.py`、`ai_semantics.json`，在 TOML 的 `ai_providers` 声明 |
| 定时任务、审批适配、身份及关联范围 | 沿用模块的现有注册机制，见 `foundation-platform/core-architecture.md` 和实际模块注册接口；入口执行时仍需检查租户启用 |

`module_names` 是拥有的 Python 模块目录名，`module_codes` 是拥有的权限模块字典值，两者不是必须相同。例如库存插件 key 是 `inv`，现有权限模块编码是 `inventory`。不要为了接入重命名已有稳定权限。

业务小程序入口应在 `MiniappMenuDef.permission_key` 声明进入页面所需的最小权限。服务端下发角色菜单和常用入口时会再次核对当前用户权限；登录、首页、消息等不需要业务权限的公共外壳可以不声明。页面接口仍必须使用 `require_permissions` 做最终鉴权，菜单过滤不能代替接口权限。

一个模块、一个表、一个菜单标识、一个前端目录只能有一个所有者。`md_` 不是“全部属于底座”：`md_party`/`md_person` 属于底座，物料/供应商属于库存。工具依据 ORM 类所在模块确定表归属，再检查前缀和外键，不能只按 `md_` 裁剪。

`replaces` 是可选的旧插件归并声明，不是依赖或隐式授权。新插件需显式登记接管模块；打包包含旧分支原文件，安装器排除旧声明的活动归属并保护本地修改。后续只为新插件生成迁移和发版，旧记录及迁移仍保留。多个 AI 提供器可归属同一个插件，HTTP 策略按提供器的 `http_modules` 应用；默认绑定提供器所在模块，显式声明只能引用本插件模块，不能以合并为由扩大字段或接口访问。

## 4. 新插件脚手架（可选练习，不必在正式库安装示例）

在 `plugins/core/backend/`：

```powershell
& '.\.venv\Scripts\python.exe' -m app.framework.plugin_cli scaffold --key sample_app --name "示例应用" --layer L3
# 有依赖时可重复传入 --requires，例如 --requires 'sample_base>=0.1'
```

脚手架生成清单、分层文件、权限/菜单/字典、带权限保护的真实 `/api/sample_app/status` 接口、管理端占位页、小程序占位页及独立空迁移目录。页面明确标记业务功能待实现，不提供虚假业务数据。它**不修改 deployment.json、不生成迁移、不写数据库、不覆盖已有目录**。

使用 `pack --source-only` 和 `install --source-only --deploy` 自动登记页面与部署，然后运行 `plugin_cli check`，完整练习见 [插件开发示例](business-plugin-development-example.md)。没有业务模型可生成空迁移分支，仅验收入口装配；正式接入须完成真实模型及迁移。

脚手架对已有目录拒绝覆盖。旧业务优先按 [脚本转换说明](plugin-script-conversion.md) 完成机械适配，不要把空脚手架误认为已有业务实现。

## 5. 将现有 inv / mes / edu 改成新插件

### 5.1 依赖顺序

推荐先完成 `inv`，再完成 `mes`；教育另外盘点其 L2 依赖后接入。每次先接通一个完整插件，再追加下一个。新插件基线离线生成；日常增量按[数据库维护](database-workflow.md)对照目标库生成，不要求追共享链最新 heads。

| 插件 | 必须核对的现有入口 | 接入要点 |
| --- | --- | --- |
| inv | `inventory`、`inventory_requisition`、`supplier`、`supplier_category`；现有 `plugins/inv/` | `inv_*` 和库存所属 `md_*` 单独建新分支，不创建教育/MES 表 |
| mes | `modules/mes`、`web/src/views/mes`、`web/src/api/mes.ts`、小程序生产报工页 | `requires` 包含新 inv；外键依赖库存的实际新迁移 head；业务操作仍调用库存公开 Service |
| edu | 现有 `plugins/edu/plugin.toml` 所列教育模块、导航及业务页面 | EDU 统一拥有 hr、ar、fac、tkt 内部模块，仅依赖 inv；保留模块边界，不再独立安装四个组件，也不并入底座 |

教育内部 HR/AR 等模块由 EDU 统一登记；只有独立发布的真实依赖（如 inv）才另设插件清单。不仅检查外键，还要检查业务 Service 的导入和调用。未选择的模块不会因为 profile 仍叫 `edu` 而自动加载。

### 5.2 每个插件的修改顺序

1. 先盘点源项目拥有的业务源码与迁移依赖。旧部署继续使用原迁移链，不改其 revision/down_revision。新接入时只恢复该插件拥有的模块、页面、API 和清单，参照下列步骤逐项改造。
2. 新建 `plugins/core/backend/alembic/versions/plugins/<key>/`，例如 `plugins/inv`、`plugins/mes` 的新迁移分别放在这个新目录下。
3. 新增或调整 `plugins/<key>/plugin.toml`：

```toml
# 以下是需要修改的迁移字段，不是可覆盖整个清单的完整示例
migration_base = "core"
migration_location = "alembic/versions/plugins/mes"
```

库存对应 `plugins/inv`，教育对应 `plugins/edu`。其他既有版本、路由、权限和菜单标识按实际模块核对保留。新分支初次建议仍由当前 `version` 表示首次发行；以后改代码和迁移要递增版本。

4. 核对 `module_names`：包括全部拥有的模块，排除底座和依赖插件模块；共享模块不能同时被两个清单拥有。核对 `table_prefixes`、`module_codes`，补齐现有权限对应模块编码，不能仅照抄旧清单中的不完整值。
5. 清理模块对未声明插件的导入和外键；直接依赖写入 `requires`（例如 `"inv>=0.1"`）。L2 不能依赖 L3。需要跨插件写入时使用公开 Service。
6. 补齐 `catalog.py` 和字典；所有业务菜单标识登记到 TOML。模块级必需配置迁到 `tenant_setup.py`，避免从旧全量初始化脚本取数据。不要在新迁移中复制全量字典、账号和演示数据。
7. 核对 `frontend.json` 的页面根目录、卡片及小程序提供器；小程序页面既要在该清单归属，也要在 `src/pages.json` 登记。管理端菜单的 `component` 必须存在并位于本插件声明的根目录中。
8. 新插件使用通用管理端/小程序外壳。旧业务页面如果依赖旧学校 `appStore` 字段、静态 mock 或通用层中的教育分支，应在业务插件内适配；不能把这些规则重新塞回底座。库存、MES 的管理端/小程序页面也按真实接口和当前会话权限验收。
9. 在部署 JSON 只选择本次接入的 core 插件及依赖，执行下面的检查和迁移生成。

**不能只把 migration_base 改为 core，再把历史 `0001_tenant_baseline` / MES 旧分支复制进来。** 新初始迁移只建本插件拥有的表，底座表来自 `core_0001`；历史 MES 分支依赖旧主干，也不能作为新分支。

当前开源底座只接受 core 基线。不要把原 `migration_base = "tenant"` 清单原样放回 `plugins/`；需要先完成新分支和代码边界改造。旧部署使用保留的原发布代码和原迁移链。

## 6. 检查与生成迁移

开发命令、按依赖顺序准备分支和正式出包步骤，统一见 [开发维护：准备正式包](plugin-development.md#准备正式包)；已有版本增量迁移见 [开发维护：日常开发与部署](plugin-development.md#日常开发与部署)。

迁移机制：

- 当前组合的版本树为 core + 所选插件独立目录，共用该租户的 `alembic_version`。
- 初始分支的 `down_revision=None`、`branch_labels=(plugin_key,)`，`depends_on` 包含 `core_0001` 及声明依赖的当前 head；依赖分支必须先存在。
- 有模型的新插件可以使用 `revision --from-models` 离线生成初始迁移，不读取或升级数据库。视图、触发器和存量转换需要单独设计。
- 已有分支使用 `revision --autogenerate` 对照已升级开发 schema 追加；读取数据库前确认目标与授权。它只比较本插件拥有的表，保留外键目标元数据。
- 不带这两个选项的 `revision` 用于明确无表的插件建立空分支，不能用于掩盖模型漏注册。
- `revision` 不执行 upgrade。autogenerate 要求开发 schema 与选定组合的版本树一致；不能用 stamp 绕过未处理的迁移。
- 普通 `alembic -n tenant revision --autogenerate` 没有本插件的归属过滤，应使用插件 CLI。

迁移审核覆盖表归属、组织与审计外键、约束、注释、索引、业务数据兼容及回退顺序；自动生成不能替代审核。`check --require-migrations` 要求所有已选插件有合法迁移头，但不证明全部手写 SQL、业务流程或页面行为正确。

## 7. 在租户中真正安装 / 启用

管理端开通流程见 [通用手册第 3 节](business-plugin-integration.md#3-为目标租户真正开通)。

当前实现的接口：

```text
GET  /api/plugins
POST /api/plugins/<plugin_key>/enable
POST /api/plugins/<plugin_key>/disable
```

接口要求目标租户的有效登录会话及 `plugin:manage` 权限。先启用依赖，再启用使用方；停用顺序相反。首次 enable 执行已审核的本地迁移并检查模型，再同步目录和开通配置，全部成功才写 ready 并开放入口。

`scripts/erp.py db upgrade --plugin <key> --schema <实际租户schema>` 用于执行本环境已审核文件及检查模型，不替代 enable。当前不存在 `plugin_cli enable` 命令；不要通过修改 public 状态表假装完成开通。

代码、迁移、部署和租户状态分别由各自阶段处理：API 不安装源码或第三方依赖、不生成迁移、不重新构建前端，也不创建新数据库。底座新库初始化使用通用手册第 0 节；旧业务库沿用原迁移链并单独设计升级。

部署组合包含全部直接和间接依赖，非空合法组合的 profile 均为 `custom`，不会因某个行业插件名称而隐式加载其他模块。组合显示名称与权限和安装状态分别管理。

## 8. 前端与小程序验证

在 `plugins/core/web/`：

```powershell
pnpm typecheck
pnpm dev
pnpm exec vite build
```

新 core 组合只导入底座页面和所选插件声明的目录，不会因仓库仍有旧教育页面而把它们收入包。菜单以 `/api/auth/menus` 为准，应用卡片还会检查该用户是否有可进入的授权菜单。

在 `plugins/core/miniprogram/`：

```powershell
node scripts/run-deployment.mjs --prepare-only
```

输出会显示本次 profile（空插件为 core，非空组合为 custom）。用对应目录进行组合类型检查：

```powershell
# 把 custom 替换成刚输出的实际 profile
pnpm exec vue-tsc --noEmit -p .deployment-input/custom/tsconfig.json
pnpm build:h5
pnpm build:mp-weixin
```

所有 core 基线组合均采用 `plugins/core/miniprogram/core` 通用外壳，再装入选中的业务页与提供器。不要把 `core` 这个 profile 名称误当成唯一能使用通用外壳的组合。小程序发布还需配置自己的 AppID、API 域名和平台合法域名；租户停用不能从已经发布的包中删除代码，服务端必须拒绝访问。

## 9. AI 查询、接口、页面跳转和技能

- 使用底座已有的通用 ERP 查询/接口/页面跳转协议。每增加业务插件无需再写一套 Harness 宿主插件。
- 新插件在 `ai_catalog.py` 声明受控表、允许字段、权限与接口，行业语义保存在本插件的语义文件。不要仅把数据库所有列直接开放给模型。
- 小程序和管理端页面来自授权菜单。新增页面必须同时登记目录与组件；AI 不拥有独立权限旁路。
- `ai_skill_keys` 只声明该业务可用技能的稳定标识，技能文件本身仍需按 Harness 的实际技能打包机制交付；接入 CLI 不会自动上传技能或修改 Harness。

结构已迁移后，在 `plugins/core/backend/` 显式同步（数据库命令先确认连接及 schema）：

```powershell
# 默认处理 core 和所有当前装载插件；首次接入先补齐所有分组，避免遗漏快照
& '.\.venv\Scripts\python.exe' -m app.integrations.harness_catalog_cli sync --schema t_default
& '.\.venv\Scripts\python.exe' -m app.integrations.harness_http_cli sync
& '.\.venv\Scripts\python.exe' -m app.integrations.harness_metadata_cli check

# 配置向量模型、索引表已迁移后才执行；会调用模型并写入该租户索引
& '.\.venv\Scripts\python.exe' -m app.modules.harness_discovery.cli build-index --schema t_default
```

表快照、接口快照、检索索引分别维护。每次变更模型、白名单、接口或组合后检查差异，不能把 JSON 生成视为授权审核。运行时仍按租户启用、用户权限、数据范围和字段保护过滤。

## 10. 完成接入的验收条件

- 新库只装底座时无 edu/mes/inv/hr/ar 业务表；安装 inv 后只新增它拥有的表，安装 mes/edu 后按依赖新增相应业务表。
- `check --require-migrations` 通过；迁移分支只依赖 core 和所需插件的新分支，未指向旧主干。实际新库升级及模块回归通过。
- 目标租户 GET `/api/plugins` 显示正确版本、ready、is_active；未安装或停用的租户无法调用对应 API；缺少权限的用户也无法调用。
- 管理端菜单顶层归属、应用中心、详情路由可用；组合构建无不相关业务页面。
- 小程序入口和接口真实可用；停用后前后台入口与访问都失效；另一个租户不受影响。
- AI 资源只发布审核过的定义，敏感字段保护与写操作确认仍生效；未建索引时明确未就绪。
- 不通过改写旧版本、删库、stamp、角色名放行或关闭权限检查来“完成”接入。

当前源码与布局状态见[源码目录](plugin-source-layout.md)及各插件说明；离线迁移编译和构建不代替真实新库安装验收。

## 11. 通用外壳中的业务扩展

- **组织**：`sys_org_type` 底座预置 `group` / `organization`。插件通过 `dictionary_specs.py` 的 `DICT_ITEMS` 追加类别；常规组织 CRUD 在 Repository 校验有效字典项。底座组织导入模板只支持集团、组织和部门；行业组织导入需插件自行适配。原 `ensure_campus_org` 和 CRUD 默认校区限制已移出底座，旧教育插件需在自己的 Repository 实现其校区规则。通用写入只要求组织存在、启用并通过数据范围校验。
- **审批默认模板**：在所属模块 `workflow_defaults.py` 声明 `DEFAULT_DESIGNS = {business_type_code: 零参数模板工厂}` 和 `BUILTIN_DEFINITIONS`（每项包含 `definition_no`、`definition_name`、`business_type_code`、`description`）。工厂返回 `FlowDesignV3`；同时向 `wf_business_type` 注册字典值并登记业务适配器。底座没有预置教育流程。首次安装插件时可在插件 `tenant_setup.setup_tenant(session, ctx)` 中显式调用 `await workflow.tenant_setup.setup_tenant(session, ctx, only={"本插件模块名"})`；only 包含本插件的模板模块，防止提前初始化部署中尚未启用的其他插件。函数按已有流程编号幂等跳过，不覆盖租户配置。
- **审批页面跳转**：`frontend.json` 可增加 `"workflow_routes": {"request_review": "SampleAppRoot"}`，值是该插件已授权菜单的路由名。只构建当前部署的映射；真正导航仍经过授权路由。业务详情字段和值由服务端业务适配器格式化，外壳不再猜测行业状态字典。
- **移动门户**：默认 `standard`。额外门户应由插件扩展 `sys_miniapp_portal`、登录/身份提供器和菜单声明。仅增加门户字典不等于完成业务身份验证。
- **特殊动态列表 API**：底座不再内置 `/api/education/list` 的实体目录生成逻辑。优先使用标准接口契约及受控资源；旧教育动态接口需要在教育适配层提供元数据/投影，不要恢复框架中的路径特判。
- **品牌**：桌面产品和图标使用套件的 `suite.toml [desktop]`。管理端和小程序的公开默认值来自插件 `frontend.json.branding`，部署特有的品牌放在 Git 忽略的 `branding/profiles/<名称>.json`，通过进程环境变量 `ERP_BRANDING_PROFILE` 选择。配置仅对绑定插件生效。完整配置见[插件运行配置](plugin-configuration.md)。
- **品牌资源与登录**：Web 的 `logo`、`favicon` 和 `login.background` 支持本站静态资源路径或 HTTPS 地址；小程序使用单独的 `miniapp_logo`、`miniapp_assistant_avatar`，需准备实际小程序静态路径或平台允许的 HTTPS 图片。空图片值表示使用文字标记 / 默认图标或不显示背景。`login` 可配置 `school_name`、`english_name`、`welcome_title`、`subtitle`、`tagline`、`background`、`background_alt`、`ai_note`、`help_lines` 和 `steps`（每项为 `title`、`lines`）。登录页已不再读取旧的 `plugins/core/web/public/login-page.json`；客户值迁入 profile。现有第三方 Web Widget 内部品牌尚未接入此配置，不能认为其 bundle 中的名称和头像已经一并覆盖。

- **登录步骤图标**：`login.steps` 每项除 `title`、`lines` 外，可直接配置 Remix Icon 的 Iconify 名称，如 `"icon": "ri:sparkling-2-line"`（闪光星）、`ri:brain-line`（大脑）、`ri:file-list-3-line`（任务清单）、`ri:loop-right-line`（循环箭头）。支持项目已安装版本中的 Remix 图标；省略时沿用默认图标，不存在的名称在前端启动或构建时报错。只打包配置用到的图标，无需运行时联网；修改配置后重启前端开发服务或重新构建。
- **首页与工作台页头**：可配置 `branding.header_logo` 为含校徽、校名的横版图片，路径规则与 `logo` 相同；页头右侧系统名称使用 `login.subtitle`。未配置横版图或加载失败时，回退为 `logo`、`login.school_name` 和 `login.english_name`；`logo` 失效后尝试公共品牌图，仍失败则只显示文字。该配置不改变登录页和侧边栏的 Logo。

这些适配点是旧 edu/MES 迁入前必须检查的变化，不能仅复制清单和迁移目录后就认为业务已接入。

## 12. 源码包与额外文件

`plugin_cli pack --plugin <key> --output <zip>` 收集清单的后端模块、独立迁移目录、插件目录、管理端页面根和小程序页面目录。目录外的私有源码使用可选 TOML 数组 `package_files` 声明，目前允许：

contained 布局直接收集 `plugins/<key>/` 内的源码、图片和样式，无需逐项登记资源；下列额外文件声明仍用逻辑路径，由解析器映射到插件目录。legacy 包继续按原目录收集。

- `web/src/api/<key>*.ts`、`miniprogram/src/api/<key>*.ts`。
- `backend/app/integrations/<key>/` 内的 Python 集成模块（逻辑路径，contained 布局映射到 `plugins/<key>/backend/app/integrations/<key>/`）。

Harness 表/接口 `*.generated.json` 不提交、不打包、不登记在 `package_files`；目标环境迁移后按[同步说明](harness-sync.md)生成。旧快照声明仅保留读取兼容，出包和导入会剔除。

同名共享辅助代码应放入插件拥有的目录或所属依赖插件，不允许通过此字段覆盖底座 API、组件和框架文件。脚手架会自动声明它生成的管理端 API。

包头 `erp-plugin-package.json` 包含版本、文件 SHA-256 和小程序页面注册信息。导入前校验路径、归属、哈希及单头独立迁移分支，导入过程中不执行包内 Python。迁移存在不代表数据库已经执行，也不代表 SQL 语义已被自动审核。

`install <zip> --deploy --dry-run` 预览；不带 dry-run 才写源码、页面登记、部署组合和 `.plugin-lock.json`。没有迁移的开发包需要 pack/install 两端明确 `--source-only`。源码文件本地已修改时拒绝覆盖；新增依赖包应先导入，移除旧文件需先明确处理，不会自动删除。
