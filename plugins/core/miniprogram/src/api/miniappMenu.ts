import { requestApi } from "./client";
export type MiniappPortal = "standard";
export interface MiniappMenu { id: string; menu_key: string; menu_name: string; path: string | null }
export interface MiniappMenuConfig {
  portal_code: MiniappPortal;
  menu_keys: string[];
  groups: { group_key: string | null; group_name: string | null; items: MiniappMenu[] }[];
}
export interface MiniappFavoriteItem {
  miniapp_menu_id: string;
  menu_key: string;
  menu_name: string;
  path: string;
  group_key: string | null;
  group_name: string | null;
}
export interface MiniappFavoriteConfig {
  items: MiniappFavoriteItem[];
  candidates: MiniappFavoriteItem[];
}
// 统一门户；业务身份与入口授权由服务端权限和插件声明决定。
export function portalForRole(_role?: string): MiniappPortal { return "standard"; }
export function fetchMyMenus(portal_code: MiniappPortal) {
  return requestApi<MiniappMenuConfig>({ path: "/api/role_miniapp_menu/my", data: { portal_code } });
}
export function fetchMiniappFavorites(portal_code: MiniappPortal) {
  return requestApi<MiniappFavoriteConfig>({ path: "/api/miniapp_menu/favorites", data: { portal_code } });
}
export function saveMiniappFavorites(portal_code: MiniappPortal, menu_ids: string[]) {
  return requestApi<MiniappFavoriteConfig>({
    method: "PUT",
    path: `/api/miniapp_menu/favorites?portal_code=${encodeURIComponent(portal_code)}`,
    data: { menu_ids },
  });
}
