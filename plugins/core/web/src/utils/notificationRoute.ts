import type { RouteLocationRaw, Router } from "vue-router";
import type { NotificationMineRow } from "@/api/notificationCenter";
import { buildWorkflowBusinessRoute } from "@/utils/workflowBusinessRoute";

/** 插件声明业务页面；小程序专用地址不能直接交给管理端路由。 */
export function notificationRoute(
  row: Pick<
    NotificationMineRow,
    "business_type_code" | "business_id" | "redirect_url" | "targets"
  >,
  router: Pick<Router, "hasRoute">
): RouteLocationRaw {
  const webTarget = row.targets?.web;
  if (webTarget?.startsWith("/") && !webTarget.startsWith("//") &&
      !webTarget.split(/[?#]/, 1)[0].startsWith("/pages/")) {
    return webTarget;
  }
  const target = buildWorkflowBusinessRoute(
    row.business_type_code,
    row.business_id
  );
  if (target && router.hasRoute(target.name)) {
    return target;
  }
  if (
    row.redirect_url?.startsWith("/") &&
    !row.redirect_url.startsWith("//") &&
    !row.redirect_url.split(/[?#]/, 1)[0].startsWith("/pages/")
  ) {
    return row.redirect_url;
  }
  return { path: "/welcome", query: { tab: "messages" } };
}
