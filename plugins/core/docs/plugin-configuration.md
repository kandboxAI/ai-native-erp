# 插件运行配置

底座 `.env` 维护数据库、认证和通用 AI 等公共配置；插件定义自己的参数类型、默认值、变量前缀及公开模板。实际环境配置存放在宿主后端，不随插件源码包发布，不按租户启停拆分。租户各自的费率、报价规则等业务配置仍由所属插件存数据库。

## 发布配置与部署配置

| 内容 | 配置位置 |
| --- | --- |
| 通用桌面产品名称、应用标识、安装包前缀和图标 | 所属套件 `suite.toml` 的 `[desktop]` |
| 管理端、小程序通用产品名称、图标及登录文案 | 所属插件 `frontend.json` 的 `branding` |
| 单独部署的展示品牌 | Git 忽略的 `branding/profiles/<名称>.json`，通过进程环境变量 `ERP_BRANDING_PROFILE` 选择 |
| 微信小程序发布 AppID 与 API 地址 | 小程序目录的 `.env.production` 或进程环境变量 `WEIXIN_APPID`、`VITE_API_BASE_URL` |
| 微信服务号二维码和服务端凭据 | 后端 `.env` 的 `WECHAT_OFFICIAL_QR_CODE_URL` 和对应微信凭据配置 |
| 加工报价材料、价格和工序费率 | 由授权人员在 MES 报价规则中按组织维护 |

微信小程序开发构建可将 `WEIXIN_APPID` 放在小程序目录的 `.env.local` 中。未配置时使用测试号 `touristappid`，用于本地模拟器。发布构建要求填写实际 AppID。使用微信登录时，后端还需配置对应的 `WECHAT_MINIAPP_APPID` 和 `WECHAT_MINIAPP_SECRET`。

## 使用者：配置 MES

| 文件 | 用途 |
| --- | --- |
| `plugins/mes/config/.env.example` | 随 MES 包交付的完整参数模板，凭据留空 |
| `plugins/core/backend/config/plugin/mes.env` | 当前环境参数和凭据，Git 忽略，不打包 |
| `plugins/core/backend/.env` | 公共配置；兼容已有的 `MES_CNC_*` 参数 |

收到新版底座和 MES 包后，在仓库根目录首次创建独立配置文件。已有文件直接编辑，不重复复制：

```powershell
# Windows / PowerShell
New-Item -ItemType Directory -Force plugins/core/backend/config/plugin | Out-Null
if (Test-Path plugins/core/backend/config/plugin/mes.env) { throw "配置文件已存在，请直接编辑" }
Copy-Item plugins/mes/config/.env.example plugins/core/backend/config/plugin/mes.env -ErrorAction Stop
```

```sh
# Linux
mkdir -p plugins/core/backend/config/plugin
cp -n plugins/mes/config/.env.example plugins/core/backend/config/plugin/mes.env
```

填写实际模型及 OCR 参数，再重启后端。`MES_CNC_AI_API_KEY` 留空时沿用公共 `LLM_GATEWAY_DEEPSEEK_API_KEY`；MES 的模型地址、模型名和超时使用自己的配置。`MES_CNC_MAX_CONCURRENT_JOBS` 为每个后端进程的并发通道数，默认 1，允许 1～16。

优先级为：**进程环境变量 → 独立插件配置文件 → 原 `plugins/core/backend/.env` → 配置类型默认值**。新文件中已填写的变量（包括空值）会覆盖旧文件同名项；从旧配置迁移时，先保留原有的专用凭据、并发值等。未创建独立文件时，原配置继续有效。安装和升级只更新公开模板，不创建或覆盖实际环境文件，不自动搬运或删除凭据。

本次不涉及数据库结构；更新底座与插件源码、检查配置后重启即可。无需为此次配置改造生成迁移或重新启用套件。旧版底座不识别新的清单声明，需要先更新底座再安装新版插件。

## 开发者：声明与读取

新插件脚手架自动生成 `config/.env.example`、业务模块内的 `config.py` 和以下清单段。已有插件按需添加，例如 MES 的 `plugin.toml`：

```toml
[configuration]
env_prefix = "MES_"
template = "config/.env.example"
secret_keys = ["MES_CNC_AI_API_KEY", "MES_CNC_PADDLEOCR_ACCESS_TOKEN"]
```

`env_prefix` 必须是插件 key 的大写形式加 `_`，模板固定为本插件的 `config/.env.example`；变量名不得越过所属前缀。`secret_keys` 列出完整凭据变量名，模板必须包含它们且值为空；名称以 `_KEY`、`_TOKEN`、`_SECRET`、`_PASSWORD` 结尾的变量也必须留空。模板不执行环境变量插值，不能利用宿主环境注入真实密钥。

类型和默认值在插件自己的 Pydantic `BaseSettings` 中定义，`model_config` 设置 `env_prefix`、`extra="ignore"`，不自行读取其他插件的配置。通过 `app.framework.plugin_settings.load_plugin_settings("mes", Settings)` 加载，可用插件前缀下的子前缀，例如 `MES_CNC_`。调用方用 `lru_cache` 缓存，参数调整后重启后端。实现参考插件源码中的 `backend/app/modules/mes/cnc/config.py`。

加载器只为当前部署插件读取环境文件，不修改 `os.environ`。未部署插件的离线参数构造不读取这些文件；进程环境变量仍按其类型前缀生效。没有 `configuration` 声明的旧插件保持原读取机制。配置校验错误不回显变量值，业务密钥使用 `SecretStr`。

打包器只允许声明过的 `.env.example` 随包交付，跳过真实 `.env`、`.env.*` 和 `*.env`，导入器也拒绝这些环境文件。配置模板或声明有误时拒绝打包/导入，安装操作不执行插件配置代码。新增字段时同步类型、模板、凭据声明及相关测试。
