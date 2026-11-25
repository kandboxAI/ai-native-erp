import { toRaw } from "vue";
import { sidebarIcons } from "virtual:sidebar-layouts";
import type { menuType } from "@/layout/types";

export function sidebarMenuIcon(
  item: menuType,
  level = item.pathList?.length ?? 1
) {
  if (level > 2) return undefined;

  const icon = toRaw(item.meta?.sidebarIcon || item.meta?.icon);
  return typeof icon === "string" ? sidebarIcons[icon] ?? icon : icon;
}
