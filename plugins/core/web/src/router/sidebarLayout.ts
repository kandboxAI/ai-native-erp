import type { RouteRecordRaw } from "vue-router";

type SidebarItem = string | {
  title: string;
  menu?: string;
  icon?: string;
  showParent?: boolean;
  children: SidebarItem[];
  trailing?: string[];
};

export type SidebarLayout = { anchors: string[]; items: SidebarItem[] };

/** 仅重排已授权且可见的导航树，页面注册和访问权限由原路由处理。 */
export function applySidebarLayout(
  routes: RouteRecordRaw[],
  layouts: SidebarLayout[]
): RouteRecordRaw[] {
  const byName = new Map<string, RouteRecordRaw>();
  function index(nodes: RouteRecordRaw[]) {
    for (const node of nodes) {
      if (typeof node.name === "string") byName.set(node.name, node);
      if (node.children) index(node.children);
    }
  }
  index(routes);
  function hasAuthorizedEntry(items: SidebarItem[]): boolean {
    return items.some(item => typeof item === "string"
      ? byName.has(item)
      : hasAuthorizedEntry(item.children) || hasAuthorizedEntry(item.trailing ?? []));
  }
  // 受限账号可能没有顶层锚点，仍按已授权的具体入口应用分组。
  const layout = layouts.find(item => item.anchors.some(key => byName.has(key)))
    ?? layouts.find(item => hasAuthorizedEntry(item.items));
  if (!layout) return routes;

  const placed = new Set<RouteRecordRaw>();
  function plan(items: SidebarItem[]) {
    for (const item of items) {
      const key = typeof item === "string" ? item : item.menu;
      const original = key ? byName.get(key) : undefined;
      if (original && (typeof item === "string" || original.children?.length))
        placed.add(original);
      if (typeof item !== "string") {
        plan(item.children);
        plan(item.trailing ?? []);
      }
    }
  }
  plan(layout.items);
  const movedPagePaths = new Set(
    [...placed].filter(node => !node.children?.length && !node.meta?.menuDirectory)
      .map(node => node.path)
  );

  function remaining(nodes: RouteRecordRaw[]): RouteRecordRaw[] {
    return nodes.flatMap(node => placed.has(node) ? [] : copy(node));
  }

  function copy(node: RouteRecordRaw): RouteRecordRaw[] {
    const children = node.children ? remaining(node.children) : [];
    if (children.length) return [{ ...node, children }];
    // 旧租户可能仍把已拆分的目录登记为普通页面，且保留默认跳转。
    const duplicatesMovedPage = !placed.has(node) &&
      typeof node.redirect === "string" && node.redirect !== node.path &&
      movedPagePaths.has(node.redirect);
    if (node.meta?.menuDirectory || duplicatesMovedPage) return [];
    if (!node.children) return [{ ...node }];
    if (!node.component && !node.meta?.frameSrc)
      return [];
    const { children: _children, ...leaf } = node;
    return [leaf as RouteRecordRaw];
  }

  function render(items: SidebarItem[], prefix: string): RouteRecordRaw[] {
    return items.flatMap((item, position) => {
      if (typeof item === "string") {
        const node = byName.get(item);
        return node ? copy(node) : [];
      }
      const slot = `${prefix}/${position}`;
      const original = item.menu ? byName.get(item.menu) : undefined;
      const children = render(item.children, slot);
      if (original?.children) children.push(...remaining(original.children));
      children.push(...render(item.trailing ?? [], slot));
      if (!children.length) return [];
      const sidebarIcon = original?.meta?.sidebarIcon;
      return [{
        path: original?.children ? original.path : slot,
        meta: {
          title: original?.meta?.title ?? item.title,
          menuKey: original && placed.has(original) ? original.meta?.menuKey : undefined,
          icon: typeof sidebarIcon === "string" ? sidebarIcon : original?.meta?.icon ?? item.icon,
          showParent: item.showParent
        },
        children
      }];
    });
  }

  return [...render(layout.items, "/_sidebar"), ...remaining(routes)];
}

export function firstSidebarPath(route: RouteRecordRaw): string {
  const firstChild = route.children?.[0];
  return firstChild ? firstSidebarPath(firstChild) : route.path;
}
