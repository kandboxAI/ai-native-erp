## 菜单管理

菜单每个租户一份（表 `sys_menu`），字段与接口一致：

| 字段                                                | 说明                                                                     |
| --------------------------------------------------- | ------------------------------------------------------------------------ |
| `menu_key`                                          | 菜单标识，对应前端路由名称；创建后不可修改                               |
| `menu_name`                                         | 菜单名称                                                                 |
| `menu_type_code`                                    | 菜单类型：`directory` 目录 / `menu` 菜单 / `button` 按钮                 |
| `parent_id`                                         | 上级菜单                                                                 |
| `path` / `component` / `icon`                       | 路由路径、页面组件、图标                                                 |
| `flex_form.route.redirect`                          | 路由重定向                                                               |
| `flex_form.route.meta`                              | 页面参数，如 `entity`、`portal`、`tool`、`report`、`activePath`、`auths` |
| `permission_key`                                    | 所需权限（提交时按权限标识，后端换成 `permission_id`）                   |
| `is_external` / `external_url` / `open_target_code` | 外链与打开方式（`self` / `blank` / `iframe`）                            |
| `sort_no`                                           | 排序                                                                     |
| `is_visible` / `is_active`                          | 是否显示 / 是否启用                                                      |

`/api/auth/menus` 返回当前用户角色已授权（`sys_role_menu`）且启用的菜单路由树，前端据此生成动态路由。`is_visible=false` 的详情页仍会下发并注册，但不会出现在左侧导航。

业务页面（含隐藏详情页、流程页和兼容跳转页）的组件、重定向及页面参数都写入
`sys_menu`，运行时以菜单接口为准。源码路由通过 `web/scripts/export-menu-route-manifest.mjs`
生成后端清单，用于初始化和补齐租户数据。首页、登录和错误页仍是应用固定路由。
