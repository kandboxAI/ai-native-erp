# Harness 检索同步

## 网关失败排查

后端以 WARNING 输出 `Harness API failure`，可在后端启动终端或部署环境收集的标准日志中检索。日志记录租户、用户、组织 ID、入口、目标路由模板、HTTP 状态和审计关联 `request_id`，不记录请求体、查询参数、令牌或异常原文。网关本身不新增日志文件。

`stage` 区分 `route`（路由或租户开通）、`policy`（只读客户端、写接口未开放或静态目录过期）、`permission`（功能权限）、`approval`（写入确认失效）、`business`（业务接口返回失败）及 `response`（响应契约不符）。`reason` 提供固定原因标识；权限失败附带要求的权限组与未持有的权限项，`any` 组只需满足其中一项。业务接口的具体错误正文仍不复制到日志。预期的“等待用户确认”409 不作为失败输出。需要重启后端后复现，历史失败不会补记；本日志改动无需迁移或重建索引。

EDU 统一包将 hr/ar/fac/tkt 提供器及受控表、接口归入 edu，保留原领域名称。当前教育部署的快照分组为 core、inv、edu，不再按四个内部模块分别维护。已安装实例需完成 EDU 升级并重新同步/发布索引；旧索引不代表新的归属已就绪。详见归并说明（开发仓库/插件中的 `edu-consolidation.md`，未随纯底座分发）。

已有分片仅因归属变化需调整时，可在 plugins/core/backend/ 离线执行 `python -m app.integrations.harness_catalog_cli repartition --plugin <新key>`。它只重新分配已有结构证据，缺字段或证据冲突则拒绝生成，不代替数据库同步；接口快照用原 `harness_http_cli sync`。

## 检索范围

插件通过 ai_catalog.py 和语义定义登记表、权限、关联与指标；已登记表的可查询字段来自实际 ORM 模型，不再使用额外的隐私字段白名单或敏感注释拦截。接口快照发布允许的 API 及参数，页面跳转读取授权菜单。范围仍受部署组合、租户启停、权限和数据范围限制，不自动登记全部数据库表，不开放任意 SQL。

设计文档不自动进入检索。修改模型/接口、更新插件、切换部署或更改审核定义后，需要同步；启动和迁移不会自动调用模型。

## 一条命令完成同步和建索引

确认目标租户的 core/插件迁移已完成，pgvector 和 embedding 配置已准备好，在仓库根目录执行：

```text
# Windows
python scripts/erp.py ai sync --schema t_default --index
# Linux
python3 scripts/erp.py ai sync --schema t_default --index
```

只运行适合自己系统的一行，租户替换为实际值。程序先显示目标库和 schema，请输入提示的 `库名/schema` 确认，再依次：

1. 读取目标库，按插件写入表结构快照。
2. 从路由/策略生成接口快照，检查字段、语义及关联。
3. 调用向量模型，向该租户发布当前完整部署组合的索引。

任何一步失败立即停止。仅同步快照时去掉 --index，不调用向量模型；离线检查用 `python scripts/erp.py ai check`，不连接数据库。

## 本地招生地区缴费演示

仅在本机 development 数据库已有教育演示学生时，在仓库根目录运行：

```powershell
& 'plugins/core/backend/.venv/Scripts/python.exe' 'plugins/core/backend/scripts/seed_admissions_region_demo.py' --schema t_default
& 'plugins/core/backend/.venv/Scripts/python.exe' 'plugins/core/backend/scripts/seed_admissions_region_demo.py' --schema t_default --apply
```

脚本只接受当前组织全部学生均为 `STU2025xxxx` 的演示库，重复执行不会重复收款或覆盖已有学生的招生老师绑定。它生成单省负责的招生老师并绑定学生，沿用现有学费演示出账与收款能力。演示统计口径是 `ar_payment.status_code=succeeded`、金额大于零的**去重学生人数**。老师的负责区域只是生源地的代理：老师负责多个地区或需要真实生源地时，应在学生来源数据中单独维护标准省份，不能把负责区域直接当成学生籍贯。

更改 AI 审核语义后按上文同步并发布索引，重启后端。DSH 查询需要 `student:list`、`admission_teacher:list`、`ar_payment:list` 权限及相应数据范围。招生老师仅开放标准单省名称，不开放人员姓名或自由区域描述。

## 业务字段与模型出口

AI 以当前 ERP 用户身份调用业务 API，沿用原接口的权限、租户、组织、班级等数据范围和业务字段控制。公共输出处理、用户问题、历史消息、工具参数与结果、知识正文及模型网关不再进行隐私扫描或脱敏；姓名、联系方式、证件号码和业务正文均按授权结果原样传递。认证凭据接口继续隔离，服务端模型密钥仍不交给客户端。

网页搜索不再按隐私规则拒绝关键词或隐藏网页中的联系方式、网址参数。来源 URL 仍校验为有效 HTTP(S) 地址，继续限制请求与返回容量，不向客户端返回供应商原始诊断。网页/小程序回答按片段发布，不再等待隐私识别完成。

数据库结构化查询不经过业务 API，继续使用已登记资源、模型字段、关系和范围校验；敏感注释不再决定字段是否可查询。未登记资源、认证表和固定 schema 模型仍不可查询。知识检索仍先执行 ERP 文档授权，写操作继续要求用户确认。

接口结果不再附加 `privacy` 脱敏说明，模型请求不再添加 `x-llm-redacted-values`。保留旧插件调用函数作为原样返回的兼容入口。结果容量、分页和 JSON 数值格式校验仍生效；历史会话、旧快照或已保存摘要中已有的脱敏占位符无法恢复原文，需要重新读取业务数据或按原业务流程更新摘要，不能将占位符写回业务字段。

取消保护后，授权取得的个人信息可能发送至配置的外部模型或搜索服务。升级无需数据库迁移；须重启后端，并按上文对目标租户同步表/接口快照及检索索引，使新增可查询字段出现在发现结果中。同步和索引发布须单独确认目标环境，代码更新不会自动执行。

## POST 查询的读写分类

手写 POST 查询由所属插件在 `AiProvider.read_routes` 中显式登记；即使 `inherit_http_policy=True`，该声明也会生效，并沿用实际接口的权限、范围与返回容量校验。EDU 已登记考试、成绩单（含移动端）、排考、听课评价任务、薪酬单、题库、调课、教师请假的 9 个只读列表。已有人工接口配置优先，`deny` 不会被覆盖；未声明的 POST 继续按写入处理。不得按 `/list` 后缀推断只读，例如满意度列表会关闭过期问卷，仍须写入确认。

接口目录的动作和确认要求以实际分类为准，不再把缺少 CRUD 标记的写接口标为“读取”。部署此改动后，在 `plugins/core/backend/` 执行 `python -m app.integrations.harness_http_cli sync` 更新接口快照并重启后端；该同步不访问业务库或模型。启用检索索引的环境另按目标租户发布索引，旧接口契约不能代替当前分类。

## 学生成绩查询的接口发现

考试与成绩沿用现有业务 API，不要求将成绩表另行登记为结构化查询资源。接口元数据包含中文名称和查询步骤：先用 `POST /api/education/grades/sheets/list` 按学期、班级、课程或考试分页查询成绩单，再用 `GET /api/education/grades/sheets/{sheet_id}` 读取学生姓名、学号、分数与排名。列表的 `keyword` 不匹配学生姓名；按姓名查询时须在有权读取的明细中核对，重名结合班级、学号确认。

升级后在 `plugins/core/backend/` 执行 `python -m app.integrations.harness_http_cli sync`，再按目标租户执行 `python -m app.modules.harness_discovery.cli build-index --schema <实际租户schema>`，最后重启后端。前者离线生成接口快照，后者访问目标库和向量模型，须先确认目标环境。无需数据库迁移，也不新增权限授权。

目录中没有成绩表不代表业务成绩接口不可用；搜索时应包含 `operation`，按发现结果的 method、path 和参数执行，不从页面路由猜接口。`route_not_found` 只说明该方法和路径未注册，不能据此认定用户缺少成绩权限；索引返回 `catalog_changed` 时应重新同步并发布索引。

## 结构化查询的文本筛选

单资源查询和关联查询的 `like` / `ilike` 支持 SQLAlchemy 原生文本类型及底层为文本的装饰类型（如 SQLModel `AutoString`）。数字字段仍不允许模糊匹配，筛选值继续参数化并执行原有权限和数据范围。仅更新这一类型识别逻辑时，重启 ERP 后端即可，无需数据库迁移、目录同步或索引重建。

## 同步范围与模型配置

默认处理当前部署全部插件，教育 + MES 混合部署直接使用上述命令。仅同步制造相关快照可加 --suite mes，仅同步指定组件可用 --plugin inv；索引仍覆盖完整部署，其他组件快照缺失会阻止发布。

在实际运行 ERP 后端的 `plugins/core/backend/.env` 中配置以下内容；完整模板见 [`plugins/core/backend/.env.core.example`](../backend/.env.core.example)，当前环境配置写入 `plugins/core/backend/.env`：

底座模板列出当前全部 `HARNESS_*` 配置：查询、embedding、检索及可选 rerank。`HARNESS_QUERY_MAX_JOINS` 默认 8，限制受控查询的关联数量（不含主表）；修改后重新同步索引并重启后端。`HARNESS_QUERY_KEY` 是保留项，当前未用于鉴权，保持为空，接口仍使用用户登录身份、权限及数据范围。全部列出不表示必须启用可选服务；`HARNESS_RERANK_INSTRUCT` 以注释示例提供，需要时填写非空指令，未启用时保持注释。

```dotenv
# 将示例地址、密钥和模型名替换为实际向量服务的配置
HARNESS_EMBEDDING_URL=https://embedding.example.com/v1/embeddings
HARNESS_EMBEDDING_API_KEY=替换为向量服务密钥
HARNESS_EMBEDDING_MODEL=替换为实际向量模型名
HARNESS_EMBEDDING_DIMENSIONS=1024
HARNESS_EMBEDDING_BATCH_SIZE=16
HARNESS_EMBEDDING_SEND_DIMENSIONS=true
```

`HARNESS_EMBEDDING_URL` 是完整的 OpenAI 兼容 embeddings 端点，代码直接请求该地址，不自动追加路径；它与 `LLM_GATEWAY_*` 对话服务独立，不自动复用密钥。`DIMENSIONS` 必须等于实际返回的向量维度；服务不接受 `dimensions` 参数时将 `SEND_DIMENSIONS` 设为 `false`，仍需核对返回维度。本地无需鉴权的向量服务可不填 API Key。更换向量模型或维度后重新构建索引，避免新旧向量混用。

检索默认超时 10 秒，可通过 `HARNESS_DISCOVERY_TIMEOUT_SECONDS` 调整（1～60 秒）；批量大小由 `HARNESS_EMBEDDING_BATCH_SIZE` 控制。rerank 是可选的查询重排序步骤，不是建索引的前提；需要时按模板配置 `HARNESS_RERANK_*`，不需要时保持 URL 和模型为空。

索引发布的是已审核的表、字段、关系和接口资源定义，不是全量业务数据。密钥仅放后端，不写入命令、Git、前端或插件包。检索表由 core 迁移创建，pgvector 扩展及目标租户结构须先就绪，sync 不代替迁移；生成后重启后端以清除缓存。

## 产物和更新规则

- 表快照：plugins/core/backend/app/integrations/harness_schema/<owner>.generated.json。
- 接口快照：plugins/core/backend/app/integrations/harness_http/<owner>.generated.json。
- 索引：目标租户的 ai_resource_* 表，按当前部署组合分命名空间。

这两类 `*.generated.json` 是环境产物：**不提交 Git，不随底座或业务插件源码包分发，也不在 `package_files` 登记**。本地生成后文件会保留，但 Git 忽略其变化；模型、接口、提供器、语义和访问策略仍须提交。旧包导入时忽略其快照，旧安装记录移除快照不会删除目标文件。

新克隆、安装或升级完成数据库迁移后，在目标环境执行上面的 `ai sync --schema t_default --index`；已有环境仅在结构、接口、语义或部署组合变化后重新同步。去掉 `--index` 只生成快照，不发布索引。生成后重启后端以清除进程内缓存。

未同步时，`ai check` 会报告缺少快照并失败，相关普通 HTTP 工具不会开放；缺少表结构证据的关联不可据此执行。未构建索引时检索尚未就绪。正常登录与业务接口不依赖这些生成物；启动和数据库升级不会自动生成它们。

生成文件不手写。结构化数据库查询的新增模型字段直接随已登记资源开放，再同步快照与索引；业务 API 字段随原接口授权返回，无需另增 AI 字段白名单。重建索引不会增加用户的业务权限或数据范围。

[插件接入](business-plugin-integration.md) · [套件说明](business-suites.md) · [完整命令与非交互参数](plugin-commands.md)

接口策略更新后在 `plugins/core/backend/` 离线执行 `python -m app.integrations.harness_http_cli sync` 并重启 ERP 后端；该命令不访问数据库或外部模型。启用的向量索引按本文流程在确认目标租户后重新发布，历史会话中已删除的字段不会自动恢复。
