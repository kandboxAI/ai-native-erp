# 插件源码与资源目录

业务代码现在由插件自己保存。INV、EDU、MES 及可选知识库已采用此布局，底座不再保存它们的业务模块和页面。

core 是隐式必装底座，其后端、管理端、小程序和主文档分别位于 `plugins/core/backend/`、`plugins/core/web/`、`plugins/core/miniprogram/`、`plugins/core/docs/`，不写入 `deployment.json`。下方目录树描述业务插件内部结构，路径相对 `plugins/<key>/`；清单中的逻辑路径保持不变。

```text
plugins/<key>/
  plugin.toml                       版本、依赖、模块和路由
  frontend.json                     页面归属和应用入口
  backend/app/modules/<module>/     模型、服务、接口、目录、AI 提供器
  backend/app/integrations/<key>/   可选集成适配
  web/src/views/<root>/             页面及页面专属图片、样式
  web/src/api/                      业务 API
  web/src/assets/                   插件共用图片、字体等
  miniprogram/src/pages/            小程序业务页面
  miniprogram/src/api/              小程序业务 API
  miniprogram/services.ts           移动入口提供器
  docs/                            随包说明
```

## 开发与启动

1. 在对应插件目录修改业务源码；通用认证、组件、工具仍在底座。
2. 用 `python scripts/erp.py use edu --replace` 选择业务，依赖自动补齐。
3. 根目录运行 `python scripts/erp.py serve --reload`；在 `plugins/core/web/` 运行 `pnpm dev`。后端同时监听底座和所选插件目录。
4. 菜单声明变化执行 `python scripts/erp.py dev sync --schema t_default`；模型变化按[开发上手](developer-quickstart.md)生成、审核及执行数据库差异。

改目录本身不改变表、版本记录、租户启停或权限，不需要为此生成迁移。已有数据库仍使用原来的连接及迁移文件。

## 引用与资源规则

- `plugin.toml` 声明 `source_layout = "contained"`；未声明的旧包仍按 `legacy` 读取。
- Python 继续使用 `from app.modules.inventory...` 等稳定名称，由底座加载器映射到所属插件。不要修改 `sys.path` 或把业务再复制回底座。
- Python 模块路径登记会检查本地插件源码布局，业务路由及模型仍按 deployment 选择。已删除包仅剩 `__pycache__/*.pyc` 的目录作为缓存残留忽略，不要求把旧模块重新加入清单；真实源码、未声明包及声明包缺失 `__init__.py` 仍会报错。
- 插件内部优先相对导入；管理端引用底座用 `@/components/...` 等，引用插件源码用 `@plugins/<key>/web/src/...`。跨插件引用必须同时声明依赖。
- 管理端第三方依赖统一声明在 `plugins/core/web/package.json`，提交对应锁文件，在 `plugins/core/web/` 执行 `pnpm install --frozen-lockfile`。Vite 将已部署插件源码的这些 npm 导入解析到宿主依赖，支持包子路径、样式和 worker；无需根目录 `node_modules` 联接，也不用在每个插件重复安装。新增依赖后重启 `pnpm dev`，接收旧版底座时须先更新此解析配置及依赖清单；源码包不自动改写接收方清单。
- 图片、字体、样式放在插件源码旁或 `web/src/assets/`，通过相对 `import`、CSS `url()` 或 `new URL(..., import.meta.url)` 引用。Vite 会生成资源地址；不要写 `/plugins/...` 静态 URL，也不要将插件资源放进底座 `public/`。
- 小程序资源放在自己的 `miniprogram/src/`，按小程序支持的导入方式引用；需要 `/static/...` 的文件放在插件的 `miniprogram/src/static/<key>/`，使用 key 防止重名。
- 小程序底部导航对所有账号固定为“常用、通知、智能助手、应用、我的”，分别对应原首页、消息、助手、工作台和个人页面。业务入口由工作台的服务端授权菜单承载，旧提供器的 `getSecondTab` 不再改变底部导航或排除工作台入口。常规导航使用星标、应用网格、通知铃铛和个人头像图标，由 `plugins/core/miniprogram/scripts/generate-tab-icons.py` 生成默认与选中态 PNG。
- “常用”只展示当前账号已选的应用；在“应用”页点击每行右侧居中的星标加入或取消，直接通过现有常用菜单接口保存，无独立的“全部应用”页面。取消全部星标后展示空状态，不回退到使用频率推荐；常用数量不设上限，顺序按加入先后保留。
- 常用页顶部显示当前账号头像、名称及服务端角色名称，下方图片轮播由“系统管理 → 小程序菜单管理 → 首页轮播图”维护。无启用图片时不显示轮播区，模型、权限、文件绑定与升级步骤见小程序常用页与轮播配置（开发仓库/插件中的 `foundation-platform/miniapp-home-design.md`，未随纯底座分发）。
- 常用页以五列展示收藏，应用页通过吸顶搜索及后台菜单分组筛选；两页共用 `ApplicationIcon` 彩色图标组件，其他业务场景仍可使用 `ServiceIcon`。提供器可导出 `getServiceIcon(path)` 返回本插件的本地 PNG 路径（如 `/static/edu/service-icons/grades.png`），彩色版本为同目录 `grades-tile.png`，缺失时回退原图；展示映射独立于角色权限筛选，不授予菜单访问权，未配置时使用通用应用图标。图标源在 `plugins/core/miniprogram/scripts/generate-service-icons.py`，可用 `plugins/core/backend/.venv` 的 Python（需 Pillow）重新生成。
- 菜单 `component`、小程序路由和清单 `package_files` 仍填写逻辑路径，例如 `inventory/goods/index`、`pages/material/index`、`web/src/api/invGoodsManagement.ts`，不要加物理目录前缀。
- 构建只装配 deployment 中的插件及已声明依赖。租户停用由服务端鉴权，已发布包中的源码不会被远程删除。
- 固定基线及已发布迁移仍在 `plugins/core/backend/alembic/versions/plugins/`；本环境增量仍在忽略的 `plugins/core/backend/.local-migrations/`。设计主文档仍在 `plugins/core/docs/foundation-platform/`。

## 新建、转换与交付

在 `plugins/core/backend/` 使用虚拟环境执行，脚手架默认生成独立目录：

```text
python -m app.framework.plugin_cli scaffold --key sample_app --name "示例应用" --layer L3
```

旧源码转换器 `convert` 也输出独立目录包。已有合法旧清单的开发仓库，可先预览再迁移（根目录）：

```text
python scripts/erp.py relocate sample_app --dry-run
python scripts/erp.py relocate sample_app
```

命令搬迁清单拥有的源码并更新静态导入，拒绝覆盖目标文件；保留本地业务修改，不操作数据库、部署或迁移。先提交或备份自己的源码；动态拼接路径及清单遗漏文件仍需检查。已完成迁移的目录重复执行不会再搬迁。

交付继续用 `python scripts/erp.py pack <key>`，接收方用 `python scripts/erp.py install <ZIP>`。插件目录内的源码和资源随包交付，依赖按套件规则处理。使用旧版底座的接收方须先更新底座，旧布局的安装目录须先完成上述 relocate，再导入新布局的更新包。

验证入口：`python scripts/erp.py check`；管理端在 `plugins/core/web/` 执行 `pnpm typecheck`、`pnpm build`；小程序在 `plugins/core/miniprogram/` 执行 `pnpm build:mp-weixin`。这些检查不替代目标租户的真实业务验收。
