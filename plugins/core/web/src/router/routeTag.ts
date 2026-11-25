import type {
  RouteLocationNormalized,
  RouteRecordNormalized
} from "vue-router";

/** 标签对应已授权的可见菜单；合并入口的内部页面共用入口标签。 */
export function resolveRouteTag(
  route: RouteLocationNormalized,
  routes: RouteRecordNormalized[]
) {
  if (!route.name || route.meta.hiddenTag) return;
  // 已拆为独立可见菜单的页面使用自己的名称；历史归属元数据仅用于隐藏详情页。
  const owner = routes.find(
    item =>
      route.meta.showLink === false &&
      item.meta.showLink !== false &&
      !item.meta.hiddenTag &&
      ((typeof route.meta.embeddedIn === "string" &&
        item.name === route.meta.embeddedIn) ||
        (typeof route.meta.activePath === "string" &&
          item.path === route.meta.activePath))
  );
  const target = owner ?? route;
  if (target.meta.showLink === false || !target.meta.title) return;
  // 待办填写参数只用于打开表单，共用业务菜单标签。
  const todoEntry =
    typeof route.query.todo_id === "string" && route.query.open_create === "1";
  return {
    path: target.path,
    name: target.name,
    meta: target.meta,
    // 合并入口、页内查询视图不携带内部参数，避免生成重复的菜单标签。
    ...(owner
      ? {}
      : {
          query: todoEntry || target.meta.reuseOnQueryChange ? {} : route.query,
          params: route.params
        })
  };
}
