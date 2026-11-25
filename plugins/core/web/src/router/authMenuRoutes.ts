/** /api/auth/menus 的菜单节点（字段与 sys_menu 一致） */
export type AuthMenu = {
  id: string;
  parent_id?: string | null;
  menu_key: string;
  menu_name: string;
  menu_type_code: "directory" | "menu" | "button" | string;
  path?: string | null;
  component?: string | null;
  icon?: string | null;
  permission_id?: string | null;
  permission_key?: string | null;
  is_external?: boolean;
  external_url?: string | null;
  open_target_code?: "self" | "blank" | "iframe" | null;
  sort_no?: number | null;
  is_visible?: boolean;
  is_active?: boolean;
  flex_form?: {
    route?: {
      redirect?: string;
      meta?: Record<string, unknown>;
    };
    [key: string]: unknown;
  };
  children?: AuthMenu[];
};

function hasNavigablePath(routes: any[], path: string): boolean {
  return routes.some(
    route =>
      (route.meta?.showLink !== false &&
        !route.path.includes("/:") &&
        route.path === path) ||
      hasNavigablePath(route.children ?? [], path)
  );
}

function toRoute(menu: AuthMenu, inheritedFeedback = false, level = 1): any {
  const businessErrorFeedback =
    inheritedFeedback || ["Education", "Finance"].includes(menu.menu_key);
  const isExternal = menu.is_external && menu.external_url;
  const routeConfig = menu.flex_form?.route ?? {};
  const children = (menu.children ?? [])
    .filter(item => item.is_active !== false)
    .map(child => toRoute(child, businessErrorFeedback, level + 1));
  const firstNavigableChild = children.find(
    child => child.meta.showLink !== false && !child.path.includes("/:")
  );
  const redirect =
    menu.menu_type_code === "directory"
      ? routeConfig.redirect && hasNavigablePath(children, routeConfig.redirect)
        ? routeConfig.redirect
        : firstNavigableChild?.path
      : routeConfig.redirect;

  return {
    path: isExternal
      ? menu.path || `/external/${menu.menu_key}`
      : menu.path || `/${menu.menu_key}`,
    name:
      isExternal && menu.open_target_code === "blank"
        ? menu.external_url
        : menu.menu_key,
    component:
      menu.menu_type_code === "directory"
        ? undefined
        : menu.component || undefined,
    redirect,
    meta: {
      ...(routeConfig.meta ?? {}),
      businessErrorFeedback,
      title: menu.menu_name,
      menuKey: menu.menu_key,
      menuDirectory: menu.menu_type_code === "directory",
      sidebarIcon: menu.icon || undefined,
      // 按授权菜单树的实际层级统一展示，三级及以下菜单使用纯文字。
      icon: level < 3 ? menu.icon || undefined : undefined,
      rank: menu.parent_id ? undefined : (menu.sort_no ?? undefined),
      showLink: menu.is_visible !== false,
      frameSrc:
        isExternal && menu.open_target_code !== "blank"
          ? menu.external_url
          : undefined,
      // 页面注册由角色菜单授权决定；接口权限仍由 auths 和后端鉴权控制。
      permissions: undefined
    },
    children: children.length ? children : undefined
  };
}

/** 将当前用户的后端授权菜单转换成可注册的 Vue Router 路由。 */
export const buildAsyncRoutes = (menus: AuthMenu[]) =>
  menus.filter(item => item.is_active !== false).map(menu => toRoute(menu));
