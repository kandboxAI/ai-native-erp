import type {
  RoleServiceOptions,
  RoleServiceItem,
  PluginSecondTab,
} from "@/config/pluginServices";

export function getRoleServiceItems(
  options: RoleServiceOptions,
): RoleServiceItem[] {
  const items: RoleServiceItem[] = [];
  if (options.permissions?.includes("mes:production_report:create")) {
    items.push({
      title: "扫码报工",
      desc: "扫描工单卡二维码，选择工序报工",
      icon: "/static/mes/service-icons/scan-report.png",
      tone: "blue",
      url: "/pages/production-report/index",
    });
  }
  if (options.permissions?.includes("mes:work_order:list")) {
    items.push({
      title: "加工进度",
      desc: "查看各工单的加工进度与完成情况",
      icon: "/static/mes/service-icons/progress.png",
      tone: "green",
      url: "/pages/production-progress/index",
    });
  }
  return items;
}

export function getSecondTab(
  options: RoleServiceOptions,
): PluginSecondTab | undefined {
  if (!options.permissions?.includes("mes:production_report:create"))
    return undefined;
  return {
    label: "扫码报工",
    path: "/pages/production-report/index",
    kind: "workspace",
  };
}

export function getServiceIcon(path: string): string | undefined {
  if (path === "/pages/production-report/index") return "/static/mes/service-icons/scan-report.png";
  if (path === "/pages/production-progress/index") return "/static/mes/service-icons/progress.png";
}
