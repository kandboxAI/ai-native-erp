import type { RouteRecordRaw } from "vue-router";
import { buildAsyncRoutes, type AuthMenu } from "@/router/authMenuRoutes";
import { applySidebarLayout, type SidebarLayout } from "@/router/sidebarLayout";
import type { MenuSelectionNode } from "./menuSelection";

export function buildRoleMenuCatalog(menus: AuthMenu[], layouts: SidebarLayout[]) {
  const byKey = new Map<string, AuthMenu>();
  function index(nodes: AuthMenu[]) {
    for (const node of nodes) {
      byKey.set(node.menu_key, node);
      index(node.children ?? []);
    }
  }
  index(menus);

  function visible(nodes: AuthMenu[]): AuthMenu[] {
    return nodes
      .filter(node => node.is_active !== false && node.is_visible !== false && node.menu_type_code !== "button")
      .map(node => ({ ...node, children: visible(node.children ?? []) }))
      .filter(node => node.menu_type_code !== "directory" || node.children.length);
  }

  const shown = new Set<string>();
  function sidebarNodes(routes: RouteRecordRaw[]): MenuSelectionNode[] {
    return routes.map(route => {
      const key = route.meta?.menuKey;
      const menu = typeof key === "string" ? byKey.get(key) : undefined;
      if (menu) shown.add(menu.id);
      return {
        id: menu?.id ?? `group:${route.path}`,
        title: String(route.meta?.title ?? ""),
        menu_type_code: menu?.menu_type_code ?? "directory",
        synthetic: !menu,
        children: sidebarNodes(route.children ?? [])
      };
    });
  }

  function remaining(nodes: AuthMenu[]): MenuSelectionNode[] {
    return nodes.flatMap(node => {
      const children = remaining(node.children ?? []);
      if (shown.has(node.id)) return children;
      const suffix = node.is_active === false ? "（停用）"
        : node.menu_type_code === "button" ? "（按钮）"
        : node.is_visible === false ? "（隐藏路由）" : "";
      return [{
        id: node.id, title: node.menu_name + suffix,
        menu_type_code: node.menu_type_code, children
      }];
    });
  }

  const tree = sidebarNodes(applySidebarLayout(buildAsyncRoutes(visible(menus)), layouts));
  const extra = remaining(menus);
  if (extra.length) {
    tree.push({
      id: "group:other-menu-permissions", title: "其他菜单权限",
      menu_type_code: "directory", synthetic: true, children: extra
    });
  }
  return { tree, menuIds: [...byKey.values()].map(menu => menu.id) };
}
