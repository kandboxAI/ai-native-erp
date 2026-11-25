import { http } from "@/utils/http";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/** 小程序门户（字典 sys_miniapp_portal） */
export type MiniappPortal = string;

export const MINIAPP_PORTALS = [{ value: "standard", label: "用户" }];

export type MiniappMenuRow = {
  id: string;
  portal_code: MiniappPortal;
  menu_key: string;
  menu_name: string;
  group_key: string | null;
  group_name: string | null;
  path: string | null;
  sort_no: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
};

export type MiniappMenuListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  portal_code?: MiniappPortal;
  group_key?: string;
  is_active?: boolean;
};

export type MiniappMenuPayload = {
  portal_code: MiniappPortal;
  menu_key: string;
  menu_name: string;
  group_key?: string | null;
  group_name?: string | null;
  path?: string | null;
  sort_no?: number | null;
  is_active?: boolean;
};

/** 修改时 portal_code / menu_key 不可改 */
export type MiniappMenuUpdatePayload = Partial<
  Omit<MiniappMenuPayload, "portal_code" | "menu_key">
>;

export const portalLabel = (portal?: string | null) =>
  MINIAPP_PORTALS.find(item => item.value === portal)?.label ?? portal ?? "—";

export const listMiniappMenus = (params: MiniappMenuListParams) => {
  return http.request<ApiResponse<PageResult<MiniappMenuRow>>>(
    "get",
    "/api/miniapp_menu/list",
    { params }
  );
};

export const createMiniappMenu = (data: MiniappMenuPayload) => {
  return http.request<ApiResponse<MiniappMenuRow>>(
    "post",
    "/api/miniapp_menu/create",
    { data }
  );
};

export const updateMiniappMenu = (
  id: string,
  data: MiniappMenuUpdatePayload
) => {
  return http.request<ApiResponse<MiniappMenuRow>>(
    "put",
    `/api/miniapp_menu/update/${id}`,
    { data }
  );
};

export const deleteMiniappMenu = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/miniapp_menu/delete/${id}`
  );
};
