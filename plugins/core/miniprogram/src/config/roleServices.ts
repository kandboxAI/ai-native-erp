import { pluginProviders } from "./pluginProviders";
import { pluginAccess, isPageAvailable, pagePath } from "@/store/pluginAccess";
export type {
  ServiceTone,
  RoleServiceItem,
  RoleServiceOptions,
} from "./pluginServices";
import type { RoleServiceItem, RoleServiceOptions } from "./pluginServices";
import type { PluginSecondTab } from "./pluginServices";

export function getRoleServiceItems(
  options: RoleServiceOptions,
): RoleServiceItem[] {
  const items: RoleServiceItem[] = [
    {
      title: "统一待办",
      desc: "查看待办与任务进度",
      icon: "/static/service-icons/tasks.png",
      tone: "blue",
      url: "/pages/todo/index",
    },
  ];
  if (pluginAccess.state.ready) {
    for (const provider of pluginProviders) {
      if (!pluginAccess.state.enabledPluginKeys.includes(provider.key))
        continue;
      for (const item of provider.getRoleServiceItems({
        ...options,
        permissions: pluginAccess.state.permissions,
      })) {
        const path = item.url || item.tab;
        if (!path) continue;
        const owner = __MINIAPP_PAGE_OWNERS__[pagePath(path)];
        if (
          (owner === provider.key || owner === "core") &&
          isPageAvailable(path)
        )
          items.push(item);
      }
    }
  }
  const seen = new Set<string>();
  return items.filter((item) => {
    const path = item.url || item.tab;
    if (!path || !isPageAvailable(path) || seen.has(path)) return false;
    seen.add(path);
    return true;
  });
}

/** 图标展示独立于角色和权限筛选，入口授权仍以服务端菜单为准。 */
export function getServiceIcon(url: string): string {
  const path = pagePath(url);
  if (path === "/pages/todo/index") return "/static/service-icons/tasks.png";
  if (pluginAccess.state.ready) {
    for (const provider of pluginProviders) {
      if (
        pluginAccess.state.enabledPluginKeys.includes(provider.key) &&
        __MINIAPP_PAGE_OWNERS__[path] === provider.key
      ) {
        const icon = provider.getServiceIcon?.(path);
        if (icon) return icon;
      }
    }
  }
  return "/static/service-icons/apps.png";
}

/** 服务端已授权菜单按页面读取用途说明，避免展示候选的权限筛选丢失文案。 */
export function getServiceDescription(url: string): string | undefined {
  const path = pagePath(url);
  if (path === "/pages/todo/index") return "查看待办事项，跟进任务处理进度";
  if (pluginAccess.state.ready) {
    for (const provider of pluginProviders) {
      if (
        pluginAccess.state.enabledPluginKeys.includes(provider.key) &&
        __MINIAPP_PAGE_OWNERS__[path] === provider.key
      ) {
        const description = provider.getServiceDescription?.(path);
        if (description) return description;
      }
    }
  }
}

/**
 * 兼容旧插件的业务入口查询；固定底部导航和工作台不再调用此接口。
 *
 * deployment 中依赖插件排在业务插件之前，后声明且仍可访问的业务插件
 * 可以覆盖依赖插件的候选项。例如 EDU + INV 组合优先使用 EDU 的角色入口，
 * 只有没有 EDU 入口时才回退到 INV 的物资入口。
 */
export function getPluginSecondTab(
  options: RoleServiceOptions,
): PluginSecondTab | undefined {
  if (!pluginAccess.state.ready) return undefined;

  let selected: PluginSecondTab | undefined;
  for (const provider of pluginProviders) {
    if (
      !pluginAccess.state.enabledPluginKeys.includes(provider.key) ||
      !provider.getSecondTab
    )
      continue;

    const candidate = provider.getSecondTab({
      ...options,
      permissions: pluginAccess.state.permissions,
    });
    if (!candidate) continue;

    const path = pagePath(candidate.path);
    const owner = __MINIAPP_PAGE_OWNERS__[path];
    if (
      (owner === provider.key || owner === "core") &&
      isPageAvailable(path)
    )
      selected = { ...candidate, path };
  }
  return selected;
}
