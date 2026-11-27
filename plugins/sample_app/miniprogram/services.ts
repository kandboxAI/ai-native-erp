import type { RoleServiceOptions, RoleServiceItem } from "@/config/pluginServices";
export function getRoleServiceItems(options: RoleServiceOptions): RoleServiceItem[] {
  return options.permissions?.includes("sample_app:access") ? [{ title: "快盒", desc: "业务插件入口", icon: "用", tone: "blue", url: "/pages/sample-app/index" }] : [];
}
