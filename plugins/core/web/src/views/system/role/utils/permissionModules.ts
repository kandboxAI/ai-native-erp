import type { SystemPermission } from "@/api/systemRole";

/** 所属模块（字典 sys_module） */
export const PERMISSION_MODULE_LABELS: Record<string, string> = {
  system: "系统管理",
  workflow: "审批",
  notify: "通知"
};

/** 权限标识前缀（资源）→ 中文名。未收录的直接显示前缀。 */
export const PERMISSION_RESOURCE_LABELS: Record<string, string> = {
  organization: "组织",
  department: "部门",
  user_profile: "用户",
  user_role: "用户角色",
  user_authorization: "用户组织授权",
  role: "角色",
  role_permission: "角色权限",
  role_menu: "角色菜单",
  role_miniapp_menu: "角色小程序菜单",
  permission: "权限",
  menu: "菜单",
  miniapp_menu: "小程序菜单",
  dictionary: "字典",
  dictionary_item: "字典项",
  system_setting: "系统参数",
  login_log: "登录日志",
  operation_log: "操作日志",
  online_user: "在线用户",
  scheduled_task: "定时任务",
  workflow_definition: "流程定义",
  workflow_task: "审批任务",
  workflow_runtime: "发起审批流程"
};

export function formatPermissionModuleLabel(
  moduleCode?: string | null,
  labels: Record<string, string> = {}
) {
  const key = (moduleCode || "").trim() || "其他";
  return labels[key] || PERMISSION_MODULE_LABELS[key] || key;
}

export function permissionResource(permissionKey: string) {
  return permissionKey.split(":", 1)[0] || "其他";
}

export function formatPermissionResourceLabel(
  resource: string,
  items: SystemPermission[] = []
) {
  if (PERMISSION_RESOURCE_LABELS[resource])
    return PERMISSION_RESOURCE_LABELS[resource];
  const preferred =
    items.find(item => item.permission_key.endsWith(":list")) ||
    items.find(item => item.permission_key.endsWith(":detail")) ||
    items[0];
  const name = preferred?.permission_name?.trim();
  return name
    ? name.replace(
        /^(查询|查看|新增|创建|修改|删除|导出|导入|维护|管理)/,
        ""
      ) || name
    : resource;
}

export type PermissionGroup = {
  /** 分组键：模块/资源 */
  module: string;
  moduleLabel: string;
  items: SystemPermission[];
};

/** 按“所属模块 / 资源（权限标识前缀）”分组 */
export function buildPermissionGroups(
  catalog: SystemPermission[],
  moduleLabels: Record<string, string> = {}
): PermissionGroup[] {
  const map = new Map<string, SystemPermission[]>();
  for (const item of catalog) {
    const key = `${item.module_code || "其他"}/${permissionResource(item.permission_key)}`;
    const bucket = map.get(key) ?? [];
    bucket.push(item);
    map.set(key, bucket);
  }
  const moduleOrder = Object.keys(PERMISSION_MODULE_LABELS);
  return [...map.entries()]
    .map(([key, items]) => {
      const [moduleCode, resource] = key.split("/");
      return {
        module: key,
        moduleLabel: `${formatPermissionModuleLabel(moduleCode, moduleLabels)} · ${formatPermissionResourceLabel(resource, items)}`,
        items,
        order:
          moduleOrder.indexOf(moduleCode) < 0
            ? 99
            : moduleOrder.indexOf(moduleCode)
      };
    })
    .sort(
      (a, b) =>
        a.order - b.order || a.moduleLabel.localeCompare(b.moduleLabel, "zh-CN")
    )
    .map(({ order: _order, ...group }) => group);
}
