export type MenuRoute = {
  path?: string;
  name?: string | symbol;
  component?: unknown;
  meta?: {
    title?: string;
    icon?: unknown;
    showLink?: boolean;
    showParent?: boolean;
    frameSrc?: string;
  };
  children?: MenuRoute[];
};

export function sidebarModuleLabel(menu: MenuRoute): MenuRoute {
  const children = menu.children?.filter(child => child.meta?.showLink !== false);
  const child = children?.[0];
  if (
    child &&
    children.length === 1 &&
    !child.children?.length &&
    !menu.meta?.showParent &&
    !child.meta?.showParent
  ) {
    return child;
  }
  return menu;
}

/** 从该一级菜单的可见页面中选择应用入口。 */
export function resolveModuleDestination(
  menu: MenuRoute,
  preferredPath?: string
): string | undefined {
  const pages: string[] = [];
  const visit = (items: MenuRoute[]) => {
    for (const item of items) {
      if (item.meta?.showLink === false) continue;
      if (item.children?.length) visit(item.children);
      else if (typeof item.name === "string" && /^https?:\/\//i.test(item.name))
        pages.push(item.name);
      else if (
        (item.component || item.meta?.frameSrc) &&
        item.path?.startsWith("/") &&
        !item.path.includes(":")
      )
        pages.push(item.path);
    }
  };
  visit([menu]);
  return preferredPath && pages.includes(preferredPath) ? preferredPath : pages[0];
}
