import type {
  RoleServiceOptions,
  RoleServiceItem,
  PluginSecondTab,
} from "@/config/pluginServices";

const materialDescription = "申请领用物资，查看审批与发放进度";
const handoverDescription = "核对交接清单，确认接收资产";
const descriptions: Record<string, string> = {
  "/pages/material/index": materialDescription,
  "/pages/asset-handovers/index": handoverDescription,
  "/pages/inventory-alerts/index": "查看库存不足物资与补货预警",
};

export function getRoleServiceItems(
  options: RoleServiceOptions,
): RoleServiceItem[] {
  const permissions = options.permissions ?? [];
  const items: RoleServiceItem[] = [];
  if (
    permissions.some((key) =>
      ["inventory_requisition:create", "inventory_requisition:list"].includes(
        key,
      ),
    )
  ) {
    items.push({
      title: "物资中心",
      desc: materialDescription,
      icon: "/static/inv/service-icons/material.png",
      tone: "green",
      url: "/pages/material/index",
    });
  }
  if (permissions.includes("asset_handover:mine")) {
    items.push({
      title: "我的资产交接",
      desc: handoverDescription,
      icon: "/static/inv/service-icons/handover.png",
      tone: "blue",
      url: "/pages/asset-handovers/index",
    });
  }
  return items;
}

export function getSecondTab(
  options: RoleServiceOptions,
): PluginSecondTab | undefined {
  if (
    options.permissions?.some((key) =>
      ["inventory_requisition:create", "inventory_requisition:list"].includes(
        key,
      ),
    )
  )
    return { label: "物资", path: "/pages/material/index", kind: "material" };
}

export function getServiceIcon(path: string): string | undefined {
  if (path === "/pages/material/index") return "/static/inv/service-icons/material.png";
  if (path === "/pages/asset-handovers/index") return "/static/inv/service-icons/handover.png";
}

export function getServiceDescription(path: string): string | undefined {
  return descriptions[path];
}
