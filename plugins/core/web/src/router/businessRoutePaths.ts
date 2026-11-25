import roots from "virtual:business-route-roots";

// Route authorization and parameters always come from server menus.
export function isBusinessRoutePath(path: string): boolean {
  return roots.some(root => path === root || path.startsWith(`${root}/`));
}
