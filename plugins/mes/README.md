# MES 业务插件与制造套件

本插件使用 [MIT 许可证](LICENSE)。当前版本以 `plugin.toml`、`suite.toml` 为准，依赖 inv；套件自动包含共享库存插件。开源发行见 [发布步骤](../core/docs/open-source-release.md)。

当前源码包含询价报价、客户订单转生产、工单与工序、手动报工、质量放行、排程及资源配置、出货对账、仓库协同、档案和异常处理。实际开通需完成目标库迁移、目录同步和授权；数据库和完整业务验收另行执行。

## 安装后端依赖

在 ERP 仓库根目录执行。已安装底座依赖的环境只需运行第二条。

```powershell
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/core/backend/requirements.txt
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/mes/requirements.txt -c plugins/core/backend/requirements.txt
```

Linux/macOS 使用 `./plugins/core/backend/.venv/bin/python`。对于没有 pip 的 uv 虚拟环境，使用 `uv pip install --python <后端虚拟环境的解释器路径>`，保留相同的 `-r` 和 `-c` 参数。

统一清单 [requirements.txt](requirements.txt) 引用两份随包清单：

- [自动排程](docs/scheduling-requirements.txt)安装 OR-Tools `9.15.6755`，供自动试排和正式排程使用。
- [AI 报价](docs/cnc-requirements.txt)安装 PDF/STEP 解析和 PDF 导出等库。模型与 OCR 服务参数配置在宿主的 `plugins/core/backend/config/plugin/mes.env`，可参考随包的 [配置模板](config/.env.example)。

安装或升级套件 ZIP 后，按当前清单补装依赖，再启动后端。前端在 `plugins/core/web/` 运行 `pnpm install --frozen-lockfile`。

## 启用与操作

已有源码时在仓库根目录执行 `python scripts/erp.py use mes`。使用套件 ZIP 时执行 `python scripts/erp.py install <ZIP>`。MES 依赖 inv，套件统一选择部署并处理依赖。

新库执行 `python scripts/erp.py init`。已有底座库按[数据库维护](../core/docs/database-workflow.md)审核并应用模型差异。启动前后端后，由租户管理员在「系统管理 → 应用管理」启用制造套件，并给业务人员分配菜单与权限。完整步骤见 [MES 接入](../core/docs/mes-plugin-integration.md)。

- [MES 操作与设计索引](docs/README.md)
- [加工询价配置](docs/cnc-quoting.md)
- [数据库与实现说明](docs/database-design.md)
