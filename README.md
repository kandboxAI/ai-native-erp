# AI Native ERP（MIT）

行业无关的 ERP 底座，可组合库存（inv）、制造（MES）等业务插件，并与配套 DeepSeek Harness（DSH）组成桌面客户端。管理端基于 vue-pure-admin，保留 [MIT 声明](plugins/core/web/LICENSE)；本项目授权范围见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)。

本文命令适用于下列 `plugins/core/` 源码布局。纯底座导出器仍输出旧布局，发布前需适配并单独验收，见[开源发布](plugins/core/docs/open-source-release.md#1-生成候选发行物)。

## 从哪里开始

| 目标 | 操作入口 |
| --- | --- |
| 浏览器运行 ERP | 按本文第 1～4 节操作 |
| ERP＋DSH 桌面联调 | ERP 运行后，继续第 5 节 |
| 打包 ERP＋DSH 安装包 | 第 6 节及[完整桌面指南](plugins/core/docs/desktop-packaging.md) |
| 维护数据库、接入业务插件 | [数据库维护](plugins/core/docs/database-workflow.md)、[插件接入](plugins/core/docs/business-plugin-integration.md) |
| 小程序开发、服务端智能体等扩展 | [开发上手](plugins/core/docs/developer-quickstart.md)、[AI 元数据与网关](plugins/core/docs/harness-sync.md) |

core 隐式必装，`deployment.json` 只声明业务插件。纯底座发行物与含 MES 的组合源码范围不同，以收到的插件目录及清单为准。桌面安装包包含 ERP 管理端和本地 DSH 运行时；ERP 后端、PostgreSQL、Redis 仍需单独运行。

```text
ai-native-erp/
  scripts/                       ERP 启动、插件管理和客户端打包入口
  plugins/core/backend/          后端、.venv、.env、数据库迁移
  plugins/core/web/              管理端、公共组件与统一前端依赖
  plugins/core/miniprogram/      移动端外壳
  plugins/core/docs/             规范和操作文档
  plugins/inv/                   库存插件（组合源码或另行安装）
  plugins/mes/                   MES 插件（组合源码或另行安装）
  deployment.json               业务部署组合，不保存凭据
```

## 1. 取得源码和准备工具

取得 ERP 源码。使用桌面功能时，同时准备与 ERP 发行版本配套的 Harness 源码。可将两个项目放在同一个父目录。

```text
C:/workspace/ai-native-erp
C:/workspace/harness-opensource
```

ERP 与 Harness 的配套版本以发行说明列出的标签或提交为准。

| 工具 | 要求 |
| --- | --- |
| Python | 3.12 或更高版本，用于 ERP 后端；按发行版本的验证记录选择 |
| Node.js | ERP＋DSH 统一使用 24.9.0 或更高版本；仅 ERP 的最低声明为 22.22.1 |
| pnpm | 使用配套 Harness 的 `packageManager` 所声明的版本 |
| 数据库、缓存 | PostgreSQL 18+，服务器安装 pgvector；Redis |
| Docker | 可选，用于运行仓库提供的 PostgreSQL/Redis |
| 桌面打包工具 | Windows/macOS 各自准备，见[桌面指南](plugins/core/docs/desktop-packaging.md#3-windows-未签名安装包) |

下文主要使用 Windows PowerShell，明确标注每个命令的工作目录。Linux/macOS 的 ERP 环境准备见[统一命令](plugins/core/docs/plugin-commands.md)；Linux 不构建 Windows/macOS 桌面安装包。先检查版本，将装依赖命令中的 `<配套版本>` 换为实际版本号（PowerShell 中先替换占位符，再运行）：

```powershell
node --version
python --version
npm install -g pnpm@<配套版本>
pnpm --version
```

DSH 首次安装及运行环境准备需要访问 npm、Electron/GitHub release、nodejs.org 和 Python 依赖下载地址。使用正常 registry/代理配置解决网络问题；后续可复用已校验的本机缓存。公开使用流程

## 2. 准备 ERP 环境

### 2.1 安装后端依赖并复制模板

在 **ERP 仓库根目录**运行：

```powershell
python -m venv plugins/core/backend/.venv
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/core/backend/requirements.txt
if (-not (Test-Path plugins/core/backend/.env)) {
  Copy-Item plugins/core/backend/.env.example plugins/core/backend/.env
}
```

配置 `plugins/core/backend/.env`，保留已有文件。至少填写：

| 配置 | 含义 |
| --- | --- |
| `DATABASE_URL` | 目标 PostgreSQL 连接；库需事先创建，URL 中的密码按 URL 规则编码 |
| `REDIS_URL` | Redis 连接 |
| `JWT_SECRET` | 自行生成的随机长密钥 |
| `DEFAULT_TENANT_NO` | 默认租户编号，例如 `default`，对应 `t_default` |
| `INIT_ADMIN_EMAIL`、`INIT_ADMIN_PASSWORD` | 首次开通管理员的登录邮箱、密码，自行设置并替换模板占位值 |

### 2.2 启动数据库和 Redis

已有服务时直接使用实际连接。没有服务时，可以在 **ERP 根目录**使用 Docker：

```powershell
$env:POSTGRES_PASSWORD = Read-Host '设置本地 PostgreSQL 密码，并保存到自己的连接配置'
docker compose up -d postgres redis
docker compose ps
```

Compose 默认创建 `erp_foundation` 数据库，用户为 `erp`，本机端口为 5432/6379；`DATABASE_URL` 中的密码须与上述输入一致。需要改库名、用户名或端口时使用 Compose 中的 `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PORT`、`REDIS_PORT`，并同步后端配置。已有数据卷保留原有账号密码，修改环境变量不会重置它。

PostgreSQL 镜像已携带 pgvector；自有 PostgreSQL 需先安装扩展文件。底座初始化负责在目标库启用 `btree_gist` 和 `vector`，不创建数据库本身。权限、扩展检查见[底座说明](plugins/core/docs/core-open-source.md#postgresql-扩展检查)。

### 2.3 选择一组业务

在 **ERP 根目录**选择下表中的一条命令。`use` 选择已安装的源码，不从网络下载插件。

| 组合 | 命令 |
| --- | --- |
| 纯底座 | `python scripts/erp.py use core --replace` |
| MES＋库存（需已有源码） | `python scripts/erp.py use mes --replace` |
| 收到 MES 套件 ZIP | `python scripts/erp.py install "C:/downloads/实际套件文件.zip"` |

MES 套件会解析 inv 依赖。安装单个 MES 插件包时，缺少 inv 会停止；应取得完整套件或先安装对应依赖。源码安装、数据库迁移、租户开通是独立步骤。

### 2.4 安装 MES 后端依赖

选择了 MES 的环境，在源码就位后、初始化或启动后端前，从 **ERP 根目录**执行。纯底座使用第 2.1 节的依赖即可。

```powershell
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/mes/requirements.txt -c plugins/core/backend/requirements.txt
```

Linux/macOS 将解释器换成 `./plugins/core/backend/.venv/bin/python`。若虚拟环境由 uv 创建且没有 pip，可运行：

```powershell
uv pip install --python plugins/core/backend/.venv/Scripts/python.exe -r plugins/mes/requirements.txt -c plugins/core/backend/requirements.txt
```

MES 清单同时安装 OR-Tools 排程引擎，以及 AI 报价所需的 PDF/STEP 图纸解析和报价导出库。安装套件 ZIP 会导入源码和清单，第三方 Python 包由上面的命令安装到 ERP 后端虚拟环境。

使用 AI 报价时，参考 `plugins/mes/config/.env.example` 配置宿主的 `plugins/core/backend/config/plugin/mes.env`，填写所用模型和 PDF 云解析服务的凭据，再启动或重启后端。前端图纸预览依赖随第 4 节的 `pnpm install --frozen-lockfile` 安装。详见 [MES 插件说明](plugins/mes/README.md)和[插件运行配置](plugins/core/docs/plugin-configuration.md)。

## 3. 初始化并对齐数据库

以下命令均在 **ERP 根目录**运行。示例使用 `DEFAULT_TENANT_NO=default`，对应 `t_default`；使用其他编号时替换后面的 schema。

**仅全新空库**先执行初始化；已有库跳过，先备份并核对目标连接：

```powershell
python scripts/erp.py init
```

按提示确认目标，看到 `bootstrap complete` 后继续。`init` 建立 public/core 基线和管理员，不加载业务插件或演示数据。固定基线与当前模型可能存在差异，因此新库也必须继续对齐当前模型：

```powershell
python scripts/erp.py db revision --schema t_default
```

**先审核生成文件**中的字段、外键、默认值及数据转换，再执行：

```powershell
python scripts/erp.py db upgrade --schema t_default
python scripts/erp.py dev sync --schema t_default
```

默认按当前部署处理 public、core 及业务插件和依赖；`dev sync` 仅用于 `APP_ENV=development`，补齐底座和已启用插件的必要配置。没有差异时不会生成空迁移。每次命令均核对目标；部分失败先处理错误，不用重跑初始化、删表或 `stamp` 消除差异。环境迁移文件须随数据库备份保存，详见[数据库维护](plugins/core/docs/database-workflow.md)。

## 4. 在浏览器运行 ERP

终端 A，在 **ERP 根目录**启动后端，保持运行：

```powershell
python scripts/erp.py serve --reload
```

也可直接使用 uvicorn，与上面的启动方式二选一。从 **ERP 根目录**进入后端目录，并使用项目虚拟环境运行：

```powershell
cd plugins/core/backend
& './.venv/Scripts/python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

这条命令监听底座 `app/` 的代码变更。需要插件热重载时追加对应路径，例如 `--reload-dir ../../mes/backend --reload-dir ../../inv/backend`；上面的 `serve --reload` 会自动收集已部署插件的监听目录。

终端 B，进入 **ERP 管理端目录**启动前端，保持运行：

```powershell
cd plugins/core/web
pnpm install --frozen-lockfile
pnpm dev
```

打开 [管理端](http://127.0.0.1:8848)，使用自己配置的 `INIT_ADMIN_EMAIL`、`INIT_ADMIN_PASSWORD` 登录。管理员已存在时修改配置或重跑初始化不会重置密码。登录后检查工作台和通知列表。

后端可通过 [存活检查](http://127.0.0.1:8000/healthz) 和 [就绪检查](http://127.0.0.1:8000/readyz) 检查；仅 `/healthz` 成功不代表数据库、Redis 和业务表均就绪。

若选择 MES，管理员进入 **系统管理 → 应用管理 → MES 制造套件 → 启用整套**。等待 inv/MES 就绪后重新登录；普通用户还需分配权限。正常开通不自动生成演示业务数据，空列表是正常状态。

## 5. 运行 ERP＋DSH 桌面

保持 ERP 后端和前端运行；再开终端进入 **Harness 根目录**。以下是首次启动的必要顺序：

```powershell
cd C:/workspace/harness-opensource
pnpm install --frozen-lockfile
pnpm build:artifacts
pnpm dev:desktop:erp
```

路径按自己的源码位置替换。当前启动器在执行自动构建前会加载工作区编译产物，所以干净源码必须先手动执行 `build:artifacts`，否则可能报 `dsh-app-boot/lib/index.js` 不存在。

`dev:desktop:erp` 默认加载 `http://127.0.0.1:8848/`，不会代启 ERP。首次还需准备 Electron 和内置 Node/Python/Office 运行环境；无日志输出不代表已就绪，需等到运行环境检查完成并打开桌面窗口。下载来源、缓存、端口覆盖和跳过重复构建的启动方式见[完整桌面指南](plugins/core/docs/desktop-packaging.md#2-首次构建与桌面联调)。

桌面能显示登录页后，还需配置 AI：

- 对话模型密钥仅写在 ERP 后端的 `LLM_GATEWAY_DEEPSEEK_API_KEY`，模型地址及允许模型见环境模板；修改后重启后端。留空时网关返回 503，普通业务页面仍可使用。
- 数据库迁移或接口变更后，按[Harness 同步](plugins/core/docs/harness-sync.md)更新表/接口目录。向量检索另需配置 embedding 服务，再由操作者确认目标后执行 `python scripts/erp.py ai sync --schema t_default --index`；它会访问数据库、调用向量模型并写索引。
- 核验普通对话、只读业务查询，以及写操作确认和权限拒绝。登录成功不等于 AI 及业务工具已验收。

## 6. 打包桌面安装包

在 **ERP 根目录**使用套件打包入口。例如 MES 的无签名、本机测试包：

```powershell
python scripts/package_erp_client.py --suite mes --version 1.0.0 --harness-root "C:/workspace/harness-opensource" --api-url http://127.0.0.1:8000 --check
```

此 `--check` **仅校验 ERP 发行参数和品牌入口**，不会执行 Harness 工具链预检，也不生成安装包。完成[桌面指南](plugins/core/docs/desktop-packaging.md#3-windows-未签名安装包)中的平台工具、Windows 本地配置和 Harness 预检后，才执行：

```powershell
python scripts/package_erp_client.py --suite mes --version 1.0.0 --harness-root "C:/workspace/harness-opensource" --api-url http://127.0.0.1:8000
```

该命令构建 ERP 管理端，调用 Harness 预检及打包。Windows x64 包输出到 Harness 的 `apps/desktop/.desktop-build/targets/win-x64/unsigned-artifacts/`。在目标机器安装后再检查启动、登录、AI 和业务权限；本机 HTTP 地址仅适合后端也运行在同一台机器的测试包。分发时改用部署好的 HTTPS 后端根地址，不附加 `/api`。

macOS 本地无签名包、正式签名和独立 DSH 打包的区别，见[完整桌面指南](plugins/core/docs/desktop-packaging.md)。打包不包括后端部署，也不上传发布。

## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| `ModuleNotFoundError` | 使用 `plugins/core/backend/.venv` 安装后端依赖；系统 Conda 环境不替代项目虚拟环境 |
| MES 排程引擎执行失败，或 AI 报价提示缺少解析库 | 按[第 2.4 节](#24-安装-mes-后端依赖)将 MES 依赖补装到正在运行的后端虚拟环境 |
| 工作台报数据库列不存在 | 对实际租户生成、审核、执行模型差异；已有库不重新 `init` |
| DSH 报 `dsh-app-boot/lib/index.js` 不存在 | 在 Harness 根目录先执行 `pnpm build:artifacts` |
| 长时间停在 Electron/运行环境准备 | 检查依赖下载网络及进程最终错误；缓存须通过版本及哈希校验 |
| ERP 页无法加载 | 确认 ERP 前后端均在运行、桌面 `ERP_DEV_URL` 与 Vite 端口一致 |
| Windows DevTools 目录 `rename` 报 EPERM | 关闭占用产物的进程，避免并行构建后重试；确认文件占用原因，不把关闭系统保护作为默认安装步骤 |
| AI 网关返回 503 | 检查实际后端的模型密钥及配置，重启后端；不把密钥写入前端或安装包 |

小程序是独立构建目标，在 `plugins/core/miniprogram/` 安装依赖后使用 `pnpm dev:h5` / `pnpm build:mp-weixin`；发布前自行配置 AppID、API 域名和平台合法域名。底座导出及插件交付见[开源发布](plugins/core/docs/open-source-release.md)，架构入口见[设计文档索引](plugins/core/docs/foundation-platform/README.md)。

## 快盒业务插件

仓库另提供可选的 [快盒插件](plugins/sample_app/README.md)，覆盖员工、工资社保、项目资金和员工自助报销。按插件 README 选择部署、审核数据库差异并开通租户。插件目录为 `plugins/sample_app/`，标识 `sample_app`，采用 MIT 许可证。
