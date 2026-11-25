import type { MobileNotificationItem } from "@/api";
import { pluginProviders } from "@/config/pluginProviders";

const MP_ROUTE_MAP: Record<string, string> = {
  "/education/homework-collection": "/pages/homework/index",
  "/education/courseware": "/pages/courseware/index",
  "/education/student-works": "/pages/student-works/index",
  "/education/timetable": "/pages/timetable/index",
  "/education/timetable-query": "/pages/timetable/index",
  "/education/schedule-changes": "/pages/schedule-change/index",
};

function queryValue(url: string | undefined, key: string) {
  const match = url?.match(new RegExp(`[?&]${key}=([^&#]+)`));
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

export function notificationTarget(item: MobileNotificationItem) {
  if (item.targets?.miniapp?.startsWith("/pages/")) return item.targets.miniapp;
  if (item.redirect_url?.startsWith("/pages/")) return item.redirect_url;
  for (const provider of pluginProviders) {
    const target = provider.notificationTarget?.(item);
    if (target) return target;
  }
  if (!item.scene_key?.startsWith("inventory.")) {
    if (!item.redirect_url) return undefined;
    if (item.redirect_url.startsWith("/education/my-asset-handovers")) {
      const id = queryValue(item.redirect_url, "id");
      return id
        ? `/pages/asset-handovers/index?id=${encodeURIComponent(id)}`
        : "/pages/asset-handovers/index";
    }
    return MP_ROUTE_MAP[item.redirect_url];
  }
  const itemId = queryValue(item.redirect_url, "item_id");
  const warehouseId = queryValue(item.redirect_url, "warehouse_id");
  if (itemId && warehouseId) {
    return `/pages/inventory-alert-detail/index?item_id=${encodeURIComponent(itemId)}&warehouse_id=${encodeURIComponent(warehouseId)}`;
  }
  if (item.scene_key === "inventory.low_stock_alert" && itemId) {
    return `/pages/inventory-alerts/index?item_id=${encodeURIComponent(itemId)}`;
  }
  return undefined;
}
