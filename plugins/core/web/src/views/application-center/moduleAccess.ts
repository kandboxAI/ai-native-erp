/** 应用入口只从后端授权的可见菜单树中选择，避免固定地址指向未授权页面。 */
type MenuNode = {
  name?: string | symbol;
  path: string;
  component?: unknown;
  meta?: { showLink?: boolean };
  children?: MenuNode[];
};

export function resolveModuleEntry(
  menus: MenuNode[],
  rootName: string,
  preferredPath: string
): string | undefined {
  const root = menus.find(menu => menu.name === rootName);
  if (!root || root.meta?.showLink === false) return;
  const paths: string[] = [];
  const visit = (node: MenuNode) => {
    if (node.meta?.showLink === false) return;
    if (node.children?.length) {
      node.children.forEach(visit);
    } else if (
      node.component &&
      node.path.startsWith("/") &&
      !node.path.includes(":")
    ) {
      paths.push(node.path);
    }
  };
  visit(root);
  return paths.includes(preferredPath) ? preferredPath : paths[0];
}
