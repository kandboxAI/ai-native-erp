# 统一命令（Windows / Linux）

在仓库根目录运行。入口自动选择 plugins/core/backend/.venv：Windows 为 Scripts/python.exe，Linux 为 bin/python。命令不依赖 PowerShell、Bash、shell 拼接或虚拟环境激活。

也提供不依赖全局 Python 命令的短入口，参数相同，推荐使用：

```powershell
# Windows / PowerShell
.\scripts\erp.ps1 use mes
```

```sh
# Linux
sh scripts/erp.sh use mes
```

下文 `python scripts/erp.py ...` 均可替换为 Windows 的 `.\scripts\erp.ps1 ...` 或 Linux 的 `sh scripts/erp.sh ...`；避免系统 Python 别名未配置导致启动失败。

```text
# Windows
python scripts/erp.py --help
# Linux
python3 scripts/erp.py --help
```

下表示例使用 python；Linux 换为 python3。各命令均支持 --help。

## 首次准备环境

后端需要 Python 3.12 或更高版本。完整 ERP＋DSH 联调统一使用 Node.js 24.9.0+，pnpm 按配套 Harness 的 `packageManager` 固定（当前为 11.28.5）；仅 ERP 管理端的最低 Node.js 声明为 22.22.1。首次桌面构建、运行环境准备和打包见[桌面指南](desktop-packaging.md)。在仓库根目录创建本机虚拟环境并安装依赖：

```powershell
# Windows / PowerShell
python -m venv plugins/core/backend/.venv
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/core/backend/requirements.txt
```

```bash
# Linux
python3 -m venv plugins/core/backend/.venv
plugins/core/backend/.venv/bin/python -m pip install -r plugins/core/backend/requirements.txt
```

复制 plugins/core/backend/.env.example 为 plugins/core/backend/.env（已有文件保留），填写实际配置。两个系统各自创建环境，不复用另一系统的 .venv。数据库、pgvector 和 Redis 准备见[底座运行说明](core-open-source.md)。

## 常用命令

| 操作 | 命令 |
| --- | --- |
| 初始化默认租户的纯底座 | `python scripts/erp.py init` |
| 合并选择插件或套件并检查 | `python scripts/erp.py use mes` |
| 替换当前组合，仅运行 MES 和依赖 | `python scripts/erp.py use mes --replace` |
| 混合运行 | `python scripts/erp.py use edu mes --replace` |
| 切换纯底座 | `python scripts/erp.py use core --replace` |
| 导入、选入部署并检查 | `python scripts/erp.py install dist/suites/实际文件.zip` |
| 打包并校验成品 | `python scripts/erp.py pack mes` |
| 预览旧布局源码搬迁 | `python scripts/erp.py relocate sample_app --dry-run` |
| 将已有插件源码迁入自己的目录 | `python scripts/erp.py relocate sample_app` |
| 生成本环境差异（待审核） | `python scripts/erp.py db revision --plugin edu --schema t_actual` |
| 执行已审核的本地迁移 | `python scripts/erp.py db upgrade --plugin edu --schema t_actual` |
| 查看本环境版本 | `python scripts/erp.py db current --plugin edu --schema t_actual` |
| 本地补齐菜单、权限和必需配置 | `python scripts/erp.py dev sync --schema t_actual` |
| 检查源码/依赖/迁移 | `python scripts/erp.py check` |
| 检查通用页面实体并列出接口未绑定入口 | `python scripts/erp.py check-pages` |
| 离线检查 AI 元数据 | `python scripts/erp.py ai check` |
| 同步快照 | `python scripts/erp.py ai sync --schema t_default` |
| 同步快照并构建索引 | `python scripts/erp.py ai sync --schema t_default --index` |

## 常用参数

- use：可给多个 key；默认合并，--replace 替换，--dry-run 只显示计划、不写文件或执行源码检查。
- install：自动识别套件/单插件；--dry-run 预检包和文件冲突，不执行源码装配；--source-only 导入待开发源码，允许缺迁移。
- pack：默认按版本和时间戳输出 dist/suites/ 或 dist/plugins/；--output 可指定路径，拒绝覆盖已有文件；--source-only 仅用于待开发包。
- relocate：仅搬迁旧清单拥有的源码并更新静态导入，不操作数据库或迁移；目标存在则拒绝覆盖。详见[源码目录](plugin-source-layout.md)。
- check/use：--source-only 仅检查源码，不要求迁移完整，不能据此开通租户。
- ai sync：默认同步整个部署；--suite mes 或重复 --plugin 限定快照范围。--index 始终为完整部署构建索引，其他插件快照也须齐全。
- 所有文件参数的相对路径以仓库根目录为准，带空格时给路径加引号。
- dev sync：只用于 APP_ENV=development；默认底座和租户已启用插件，--plugin 可限定插件及依赖。先检查模型一致，再补齐配置；不改版本或启停，不执行迁移、演示种子或 AI 同步。完成后重新登录。详见[开发上手](developer-quickstart.md)。

## 数据库与非交互执行

init、db、dev sync 和 ai sync 首先显示不含账号密码的主机、端口、库名和 schema，要求输入 `库名/schema` 确认。连接来自 plugins/core/backend/.env/环境变量；--schema 只选择租户，--database **只校验确认的库名，不切换连接**。

明确核对目标后的自动化可以执行：

```text
python scripts/erp.py ai sync --schema t_default --index --yes --database actual_database
```

--yes 必须同时提供匹配的 --database，否则停止。init 只处理 .env 中默认租户；不自动创建数据库、不启动服务、不安装业务或加载演示数据。需要停服或维护窗口的环境由操作者安排。

## 失败如何处理

失败立即停止，不继续后续命令。use 的源码检查失败会恢复本次部署选择（不覆盖并发修改）；安装包写入沿用安装器回滚保护，但**导入成功后源码检查失败会保留已导入源码**，修复后运行 check。不要删除安装记录、覆盖本地修改或 stamp 绕过失败。

通过静态检查不代表迁移、权限和真实业务已验收。源代码必须来自可信来源，导入后的源码检查会执行业务 Python；哈希只检查损坏，不证明发布者身份。

日常迁移见[数据库维护](database-workflow.md)；新插件基线见[开发维护](plugin-development.md)。
