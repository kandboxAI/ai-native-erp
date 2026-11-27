# 快盒业务插件

快盒提供内部员工与外包人员、月度考勤、定薪、工资核算、社保缴费、项目合同与回款、资金账户、往来款、费用报销及员工自助门户。插件标识为 `sample_app`，公开版本为 `0.1.2`，依赖 ERP 底座，采用 MIT 许可证。

## 安装和开通

员工端需使用本次发布同时更新的底座，旧版本缺少附件核验和本人改密支持。

以下命令在仓库根目录执行。先完成根 README 中的底座环境准备。新库先执行 `python scripts/erp.py init`，已有库按数据库维护说明备份并升级。

```powershell
python scripts/erp.py use sample_app
python scripts/erp.py check
python scripts/erp.py db revision --plugin sample_app --schema t_default
# 审核目标环境生成的差异后执行
python scripts/erp.py db upgrade --plugin sample_app --schema t_default
```

`t_default` 替换为实际租户 schema。随包保留的 `6d6f916d9fdc` 是原有空基线，业务表由各环境按当前模型生成、审核和升级。初次启用也须完成上述数据库差异流程。已有库保留已执行迁移记录，增量文件随目标数据库备份。

更新后端并在 `plugins/core/web/` 安装依赖、执行 `pnpm build`。启动管理端，在应用管理启用快盒，分配快盒菜单及 `sample_app:access` 权限。历史来源台账另外需要 `sample_app:history`。内部员工的登录账号关联在内部员工页维护，本人报销权限为 `sample_app:reimbursement:self`。

首次使用先维护组织、员工、定薪和缴费基数。租户开通会幂等补齐必要字典和默认计薪参数，演示种子目前为空。发布内容不附带客户账簿或内部人员初始化脚本。

## 员工门户和 AI 连接

员工门户由独立 Python 服务提供页面及接口。组织和人员权限由当前租户、员工绑定与本人权限共同校验。请先完成插件部署与租户开通。

复制公开参数模板到宿主的私有配置位置，已有文件直接编辑。

```powershell
New-Item -ItemType Directory -Force plugins/core/backend/config/plugin | Out-Null
if (Test-Path plugins/core/backend/config/plugin/sample_app.env) { throw "配置文件已存在，请直接编辑" }
Copy-Item plugins/sample_app/config/.env.example plugins/core/backend/config/plugin/sample_app.env -ErrorAction Stop
```

本地默认入口为 `http://127.0.0.1:18990`。远程部署将 PUBLIC_URL 改成实际 HTTPS 源地址，通过反向代理转发独立员工服务。文件存储复用底座配置，直传服务需配置对应页面来源的 CORS。

在 `plugins/core/backend/` 执行

```powershell
& './.venv/Scripts/python.exe' -m app.modules.sample_app.employee_mcp
```

登录员工门户的「AI 连接」页面可复制 HTTP MCP 地址并签发短期凭证。需要访问本机发票的桌面客户端可配置 stdio 本地桥接 `python -m app.modules.sample_app.employee_mcp_local`，工作目录同上。桥接需要明确设置 `KUAIHE_EMPLOYEE_MCP_URL` 和 JSON 数组形式的 `KUAIHE_INVOICE_ROOTS`，例如专用发票目录。桥接仅读取授权目录内的原件。

AI 准备申请并上传原件后返回本人确认链接。本人登录页面核对并提交，管理端随后办理实际付款。软件报销沿其工资归属月份登记。金额、税率、费率和历史工资的完整性需由经办人员核对。

浏览器通过同源 HttpOnly Cookie 恢复固定期限会话，退出会撤销对应刷新令牌。MCP 凭证和浏览器登录凭证分别校验，人工确认使用正常登录。

## 验证和源码包

管理端回归在仓库根目录执行

```powershell
node --test plugins/sample_app/web/tests/organization-context.test.mjs
```

后端测试位于 `plugins/core/backend/tests/test_sample_app_*.py`。配置独立测试环境后，在 `plugins/core/backend/` 运行对应 pytest 文件。测试使用 mock，不以真实客户数据库作为测试库。

```powershell
python scripts/erp.py pack sample_app
```

源码包收集插件、配置模板、许可证及原有迁移。包安装后仍需在目标环境生成并审核数据库差异，再由应用管理开通或升级。AI 表和接口快照通过独立 Harness 同步命令在目标环境生成。

小程序当前只提供插件可访问性检查入口，完整业务操作使用管理端和独立员工门户。
