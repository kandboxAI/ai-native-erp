import type { RouteLocationNormalized } from "vue-router";

/** 页内查询视图复用实例；普通业务页与 iframe 保留各自的完整地址。 */
export function resolveRouteViewKey(
  route: RouteLocationNormalized,
  fullPath = route.fullPath
): string {
  return route.meta.reuseOnQueryChange && !route.meta.frameSrc
    ? route.path
    : fullPath;
}
