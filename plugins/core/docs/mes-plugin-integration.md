# MES 制造套件：使用步骤

MES 是 L3 业务插件，依赖 inv，版本约束以 `plugins/mes/plugin.toml` 为准。suite.toml 将 MES 和库存统一交付。以下命令在仓库根目录运行；Linux 将 python 换为 python3。

## 当前目录已经有源码

```text
python scripts/erp.py use mes
```

命令自动补齐库存依赖并检查源码。只选择制造套件及依赖时使用 `python scripts/erp.py use mes --replace`。

## 数据库准备

新库先 init。已有底座按[数据库维护](database-workflow.md)执行 `db revision --plugin mes --schema t_actual`，审核后 `db upgrade --plugin mes --schema t_actual`，再启动并启用套件；inv 自动包含。

## 收到制造套件 ZIP

```text
python scripts/erp.py install dist/suites/实际制造包.zip
```

命令导入 MES 和 inv 源码、选择部署并执行检查。

## 安装 MES 后端依赖

完成底座依赖安装后，在仓库根目录用同一个后端虚拟环境安装 MES 清单。源码已存在和通过 ZIP 导入的环境都执行此步。

```powershell
& './plugins/core/backend/.venv/Scripts/python.exe' -m pip install -r plugins/mes/requirements.txt -c plugins/core/backend/requirements.txt
```

Linux/macOS 将解释器换成 `./plugins/core/backend/.venv/bin/python`。清单包含自动排程引擎和 AI 报价的本地解析、导出库。报价所需的模型和 OCR 参数见[插件运行配置](plugin-configuration.md)。

## 初始化、启动与开通

新库先 `python scripts/erp.py init` 并核对目标；已初始化的底座库跳过。重启前后端，以目标租户管理员进入 **系统管理 → 应用管理 → MES 制造套件 → 启用整套**。

程序先处理 inv，再处理 mes 的迁移、菜单和必需配置，无须逐个点击；该操作会写数据库。普通成员需分配权限，空库列表为空正常。教育和 MES 同时启用时共享一份 inv；停用任一套件会保留另一方需要的库存。

## 更新、交付与 Harness

- 交付：`python scripts/erp.py pack mes`，一条命令打包并校验包含库存的套件。
- 更新：install 新包、按模型生成并审核本环境差异、迁移后重启/构建，再点击升级整套。
- 检索：`python scripts/erp.py ai sync --schema <实际租户> --index`，先核对确认目标，见[Harness 同步](harness-sync.md)。


## 业务使用

MES 支持从询价报价、客户订单审核到生产工单、排程、报工和出货。手动报工在管理端办理，扫码报工从小程序扫描工单卡进入。管理端支持检验放行、异常处理、生产领退料、成品入库和出货单据。

安装套件后，操作与设计说明位于 `plugins/mes/docs/README.md`。验证时使用独立租户和合成业务数据，检查审批权限、排程资源、报工与出货数量。
