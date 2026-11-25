import { http } from "@/utils/http";
import type { MiniappPortal } from "@/api/miniappMenu";

export type { MiniappPortal } from "@/api/miniappMenu";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type MiniappMenuItem = {
  id: string;
  menu_key: string;
  menu_name: string;
  path: string | null;
};

export type MiniappMenuGroup = {
  group_key: string | null;
  group_name: string | null;
  items: MiniappMenuItem[];
};

export type RoleMiniappMenuCatalog = {
  portals: Partial<Record<MiniappPortal, MiniappMenuGroup[]>>;
};

export type RoleMiniappMenuConfig = {
  role_id: string;
  miniapp_menu_ids: string[];
  menu_keys_by_portal: Partial<Record<MiniappPortal, string[]>>;
};

export type RoleMiniappMenuBatchSyncPayload = {
  role_id: string;
  /** 跨全部门户一次对齐 */
  miniapp_menu_ids: string[];
};

export const getRoleMiniappMenuCatalog = () => {
  return http.request<ApiResponse<RoleMiniappMenuCatalog>>(
    "get",
    "/api/role_miniapp_menu/catalog"
  );
};

export const getRoleMiniappMenuConfig = (roleId: string) => {
  return http.request<ApiResponse<RoleMiniappMenuConfig>>(
    "get",
    `/api/role_miniapp_menu/role/${roleId}`
  );
};

export const batchSyncRoleMiniappMenus = (
  data: RoleMiniappMenuBatchSyncPayload
) => {
  return http.request<
    ApiResponse<{ added: number; removed: number; total: number }>
  >("post", "/api/role_miniapp_menu/batch-sync", { data });
};
