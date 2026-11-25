# ERP＋DSH 桌面：开发运行与安装包

本指南区分浏览器 ERP、组合桌面开发、组合安装包和独立 DSH。组合安装包内置 ERP 管理端与本地 DSH，后端、数据库和 Redis 单独部署；开发桌面则加载正在运行的 Vite。

## 1. 源码、版本与环境

准备 ERP 源码和发行说明所列版本的配套 Harness 源码。

示例将两份源码放在 `C:/workspace/ai-native-erp`、`C:/workspace/harness-opensource`；路径均可替换。以下 PowerShell 命令注明了工作目录。

| 部分 | 环境 |
| --- | --- |
| ERP | Python 3.12+、PostgreSQL 18+及 pgvector、Redis |
| 完整 ERP＋DSH 开发 | Node.js 24.9.0+；pnpm 以配套 Harness 的声明为准 |
| Windows 安装包 | 原生 Windows x64、Git、PowerShell 7（`pwsh`）、tar、Python、Visual C++ Build Tools 的 C++工具及 Windows SDK |
| macOS 本地安装包 | 在对应 macOS 构建机准备 Xcode/Command Line Tools；签名发布另准备证书与公证配置 |
| Linux | 可运行 ERP 和 Harness 的适用目标；不能在 Linux 运行本文 Windows/macOS 桌面打包入口 |

Node.js 和 pnpm 版本以配套 Harness 的 `engines` 和 `packageManager` 为准。

依赖安装和首次运行环境准备需要访问 npm、Electron/GitHub release、nodejs.org 和锁文件列出的 Python 解释器/依赖归档地址。下载有问题时配置可用的 registry/代理，保留校验和验证。

## 2. 首次构建与桌面联调

### 2.1 先运行 ERP

按[根 README](../../../README.md#2-准备-erp-环境)准备配置、新库初始化、模型差异和租户开通。保持两个终端运行：

```powershell
# 终端 A，ERP 根目录
python scripts/erp.py serve --reload
```

```powershell
# 终端 B，从 ERP 根目录进入管理端
cd plugins/core/web
pnpm install --frozen-lockfile
pnpm dev
```

先在浏览器打开 `http://127.0.0.1:8848/`，使用自设的管理员邮箱/密码完成登录；确认工作台没有缺表、缺列错误。`/healthz` 是存活检查，`/readyz` 是后端依赖就绪检查。MES 源码部署后还需在应用管理启用套件。

### 2.2 再准备 Harness 并启动桌面

终端 C，在 **Harness 根目录**执行：

```powershell
cd C:/workspace/harness-opensource
pnpm install --frozen-lockfile
pnpm build:artifacts
pnpm dev:desktop:erp
```

当前 `apps/desktop/scripts/dev.ts` 的顶层导入会读取工作区 `lib`，早于其自动构建阶段。因此干净源码先执行一次 `build:artifacts`；直接 `dev:desktop:erp` 可能报 `@deepseek-ai/dsh-app-boot/lib/index.js` 不存在。工作区依赖安装和编译产物是两件事。

`dev:desktop:erp` 会再执行构建并启动一个 Electron 进程，默认 ERP 页面为 `http://127.0.0.1:8848/`，不会代启 ERP 服务。若 Vite 使用其他端口，在同一终端先设置：

```powershell
$env:ERP_DEV_URL = 'http://127.0.0.1:实际前端端口/'
pnpm dev:desktop:erp
```

上例的端口须替换成 Vite 实际端口。后端地址改变时，还要同步 ERP 前端的 API 配置并重启 Vite。

源码和构建配置未变时，可在 **Harness 根目录**复用已有构建产物：

```powershell
$env:ERP_DEV_URL = 'http://127.0.0.1:8848/'
$env:DSH_DESKTOP_OPEN_DEVTOOLS = '0'
pnpm start:desktop
```

`start:desktop` 跳过源码构建，仍准备和检查目标运行环境；改代码后重新运行构建或使用 `dev:desktop:erp`。Linux/macOS 的进程环境变量使用本机 shell 语法，不直接复制 PowerShell 的 `$env:`。

### 2.3 首次运行的下载与缓存

Electron npm 包和 Electron 可执行文件分别准备。首次还会按 `scripts/primary-runtime/lock.json` 下载并校验内置 Node、Python 解释器和依赖，执行依赖完整性及 Office 文档读写冒烟，再启动 Electron。没有完整准备结果时不能把命令视为启动成功。

Harness 的开发状态位于 `apps/desktop/.desktop-build/`，运行环境位于 `targets/<target>/runtime/`；下载归档默认位于其 `downloads/`。可用 `DSH_DESKTOP_PACKAGE_CACHE_DIR` 指定绝对缓存根目录，构建器仍按锁文件校验下载归档。Electron 有独立的包安装/下载缓存，不能只设置这个变量就认为 Electron 已安装。

首次过程可能较长。失败时保留最后一个失败阶段和错误信息；网络超时先排查网络，缺文件先检查依赖和构建。只复用版本与校验值匹配的归档，不复制其他使用者的会话或登录数据。Windows `EPERM rename` 需先检查文件占用、并行构建和权限，不将关闭系统保护作为默认安装步骤。

### 2.4 启用 AI 与 ERP 工具

密钥只存放在 ERP 后端 `plugins/core/backend/.env`：`LLM_GATEWAY_DEEPSEEK_API_KEY`，模型地址与允许模型按[完整环境模板](../backend/.env.core.example)填写。修改后重启后端；留空时网关返回 503，桌面仍可能正常打开登录页。

表/接口元数据和检索索引不随源码包交付。按[Harness 同步说明](harness-sync.md)确认实际租户并同步；带 `--index` 会调用配置的向量模型并写租户索引，需先配置 embedding 服务。普通登录、模型对话、业务查询和确认写入分别验收，不以其中一项代替其他项。

后端的可选服务端智能体 SDK 与本文本地桌面运行时是不同部署方式。普通浏览器 ERP 不要求先安装本地 Harness；本指南不将服务端 SDK 安装当作桌面启动步骤。

## 3. Windows 未签名安装包

### 3.1 准备套件与工具

本文以已安装并选择的 MES 套件为例。在 **ERP 根目录**：

```powershell
python scripts/erp.py use mes --replace
```

套件根插件须有 `suite.toml` 的 `[desktop]`：

```toml
[desktop]
product_name = "MES 智能助手"
app_id = "org.ai-native-erp.mes"
artifact_prefix = "mes-erp"
icon = "desktop/icon.png"
```

`icon` 是所属插件内的 PNG 相对路径，正方形、至少 256 像素；省略时使用 DSH 默认图标。首次公开发布前将应用 ID 改成发布者自己的反向域名，后续保持稳定。助手名由 ERP 品牌合并器提供，标题 `DSH_CLIENT_TITLE` 使用 `product_name`。

套件名称和图标同时用于原生主窗口、聊天侧栏及安装器；本地未签名构建的侧栏默认分支也必须读取这些配置。发布前核对 Harness 构建记录中的 `DSH_CLIENT_TITLE`、`DSH_CLIENT_ERP_BRAND` 和图标摘要 `DSH_CLIENT_BRAND_ICON`，避免仅修改安装器品牌而让页面仍显示旧名称。更新 Harness 源码后重新打包并安装，旧安装包不会自动变化。

平台工具要求见第 1 节。在 **Harness 根目录**检查工具可用：

```powershell
node --version
pnpm --version
git --version
pwsh --version
tar --version
python --version
```

另确认 Visual C++ Build Tools 和 Windows SDK 已安装。工具版本查询成功不代替打包器的完整工具链预检。

### 3.2 创建 Windows 本地配置

在 **Harness 根目录**复制公开模板，保留已有文件：

```powershell
if (-not (Test-Path apps/desktop/.env.windows)) {
  Copy-Item apps/desktop/.env.windows.example apps/desktop/.env.windows
}
```

编辑该文件，参考模板保留应用 ID 和必要构建参数。ERP 套件打包入口会传入套件应用 ID、`ERP_DIST_DIR`、`ERP_API_URL` 和品牌信息，实际应用 ID以套件为准。无签名模式不需要 EV 证书、token PIN 或上传凭据；实际环境文件不提交、不随包分发。

当前 Harness 对**提供有效 ERP 前端与后端地址的组合包**跳过独立 DSH 的强制更新策略校验，因此不要为了本文组合包虚构更新服务 origin。独立 DSH Windows 安装包的要求不同，见第 5 节。若使用 `DSH_PACKAGING_PRESET`，配置来自所选机器 preset；其路径和优先级按 Harness 的 `apps/desktop/packaging/README.zh.md` 操作，不能只修改 `.env.windows` 后假定已生效。

### 3.3 执行资源和工具链预检

另开一个打包终端，避免继承桌面开发的覆盖项。以下路径按实际位置替换：

```powershell
$erpRoot = 'C:/workspace/ai-native-erp'
$harnessRoot = 'C:/workspace/harness-opensource'
Remove-Item Env:ERP_DEV_URL -ErrorAction SilentlyContinue
Push-Location "$erpRoot/plugins/core/web"
pnpm build
Pop-Location

Set-Location $harnessRoot
$env:ERP_DIST_DIR = "$erpRoot/plugins/core/web/dist"
$env:ERP_API_URL = 'http://127.0.0.1:8000'
pnpm run package:desktop:win:x64:unsigned --check
```

这里的 Harness `--check` 才会执行它的配置、平台和工具检查，不构建安装包；先修复报告的缺项。`ERP_API_URL` 为后端根地址，不加 `/api`；本机 HTTP 仅供无签名本机测试。预检使用 ERP 模式，避免误用独立 DSH 的配置要求。

### 3.4 从 ERP 统一入口打包

在上一节的打包终端切回 **ERP 根目录**，先检查发行参数：

```powershell
Set-Location $erpRoot
python scripts/package_erp_client.py --suite mes --version 1.0.0 --harness-root "C:/workspace/harness-opensource" --api-url http://127.0.0.1:8000 --check
```

ERP 的 `--check` 只检查套件、版本、目标平台、地址、品牌入口等发行参数，不构建，也**不调用 Harness 预检**。它不能代替上一节。然后执行实际打包：

```powershell
python scripts/package_erp_client.py --suite mes --version 1.0.0 --harness-root "C:/workspace/harness-opensource" --api-url http://127.0.0.1:8000
```

脚本构建 ERP 管理端，检查 `dist/index.html`，调用 Harness 预检和完整打包，任一步失败立即停止。前端已按当前源码构建时可加 `--skip-web-build`。版本使用语义版本、不含 `+build`；安装包版本独立于业务插件和 Harness 的版本。上一节已清除打包终端的 `ERP_DEV_URL`，使安装包使用内嵌前端。

预期产物目录：Harness 的 `apps/desktop/.desktop-build/targets/win-x64/unsigned-artifacts/`；完整阶段日志位于 `.desktop-build/packaging-runs/`。命令不部署后端、不上传发布；得到文件后仍需进行安装验收。

本机 `127.0.0.1` 地址会指向安装包使用者自己的电脑，只用于同机后端测试。分发给其他使用者时改为已部署的 HTTPS 后端根地址；后端的数据库、Redis、模型凭据和网络可达性由服务部署负责。

## 4. macOS 与正式发布

macOS 安装包在 macOS 上构建；ERP 与 Harness 分别安装该系统的依赖，不复用 Windows 的 `.venv` 或 `node_modules`。先按前文准备 ERP 前端及 Harness 构建环境，再在 **ERP 根目录**执行，例如 Apple Silicon 本地无签名包：

```sh
python3 scripts/package_erp_client.py --suite mes --version 1.0.0 --arch arm64 --harness-root /path/to/harness-opensource --api-url http://127.0.0.1:8000 --check
python3 scripts/package_erp_client.py --suite mes --version 1.0.0 --arch arm64 --harness-root /path/to/harness-opensource --api-url http://127.0.0.1:8000
```

Intel macOS 改为 `--arch x64`。当前 Harness 的 macOS 本地无签名分支不要求 `.env.macos` 或发布证书，具体系统工具和行为见该仓库的 `apps/desktop/packaging/README.zh.md`。输出为对应 `targets/mac-arm64/unsigned-artifacts/` 或 `mac-x64/unsigned-artifacts/`。

正式签名由 ERP 打包命令增加 `--signed`，并使用已部署的 HTTPS 后端。Windows 的 EV/签名工具配置、macOS 的签名证书及公证配置，按 Harness 的平台打包文档准备。签名、上传、更新服务和公开发布分别完成；本文不把本地未签名产物当成正式可分发版本。

## 5. 独立 DSH 与组合包的区别

独立 DSH 在未设置 `ERP_DEV_URL`、`ERP_DIST_DIR`、`ERP_API_URL`、`DSH_ERP_BRANDING` 的新终端运行。仍在 **Harness 根目录**先安装依赖、执行 `pnpm build:artifacts`，然后 `pnpm dev:desktop`；使用自己的模型/身份配置，不加载 ERP 页面。

独立 DSH Windows 未签名打包为 `pnpm run package:desktop:win:x64:unsigned`，但与 ERP 组合模式不同，需按 Harness 的 `.env.windows.example` 和 `apps/desktop/packaging/README.zh.md` 配置真实的强制更新策略服务；先用同一命令加 `--check` 预检。不要拿 ERP 的模型服务地址充当更新策略服务。

ERP 品牌转换脚本 `scripts/erp-branding.mjs` 属于 **Harness 仓库**，由 `apps/desktop/scripts/desktop-erp-branding.mjs` 导出给 ERP 打包入口使用。两边通过 `ERP_DEV_URL`、`ERP_DIST_DIR`、`ERP_API_URL`、`DSH_ERP_BRANDING` 协作；桌面桥为 `window.erpDesktop`，网关请求头为 `x-erp-client-id`，本地链接协议为 `erp-client://`。配套升级后重新构建并安装；已有安装包不会随源码改变。

## 6. 发布前验收

- 填写两个公开源码入口和对应版本；从全新检出、无旧仓库依赖的环境照 README 操作。
- 对专用空库执行初始化、审核和执行模型差异、管理员登录、工作台/通知、插件开通和受限账号验证；已有客户库不用于这项验收。
- 完成配套 Harness 的构建检查、相关测试，以及无缓存依赖下载或明确支持的可校验缓存准备流程。
- 验证模型网关、目录/索引、只读业务查询、明确确认写入、权限拒绝及客户端重启。
- 安装产物并验证内嵌 ERP 页面、后端连接、登录持久性、AI 功能和卸载行为；分开记录 Windows/macOS及签名/未签名结果。
- 核对品牌、协议、公开模板及安装包内容，排除环境文件、会话、凭据与业务数据。
