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

/** 权限由代码定义：只读，只允许改名与启停 */
export type SystemPermissionListRow = {
  id: string;
  permission_key: string;
  permission_name: string;
  module_code: string;
  is_active: boolean;
  role_count: number;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
};

export type PermissionRoleItem = {
  id: string;
  role_no: string;
  role_name: string;
};

export type SystemPermissionDetail = SystemPermissionListRow & {
  roles: PermissionRoleItem[];
};

export type PermissionListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  permission_key?: string;
  permission_name?: string;
  module_code?: string;
  is_active?: boolean;
  sort_by?:
    | "permission_key"
    | "module_code"
    | "role_count"
    | "updated_at"
    | "created_at";
  sort_order?: "asc" | "desc";
};

export type PermissionUpdatePayload = {
  permission_name?: string;
  is_active?: boolean;
};

export const listPermissions = (params: PermissionListParams) => {
  return http.request<ApiResponse<PageResult<SystemPermissionListRow>>>(
    "get",
    "/api/permission/list",
    { params }
  );
};

export const getPermissionDetail = (id: string) => {
  return http.request<ApiResponse<SystemPermissionDetail>>(
    "get",
    `/api/permission/detail/${id}`
  );
};

export const updatePermission = (id: string, data: PermissionUpdatePayload) => {
  return http.request<ApiResponse<SystemPermissionDetail>>(
    "put",
    `/api/permission/update/${id}`,
    { data }
  );
};

/** 拉取全部权限（page_size 最大 1000） */
export async function fetchAllPermissionOptions(
  params: Omit<PermissionListParams, "page" | "page_size"> = {}
): Promise<SystemPermissionListRow[]> {
  const page_size = 1000;
  let page = 1;
  const all: SystemPermissionListRow[] = [];
  for (;;) {
    const res = await listPermissions({ ...params, page, page_size });
    const batch = res.data?.items ?? [];
    all.push(...batch);
    if (batch.length < page_size || all.length >= (res.data?.total ?? 0)) {
      break;
    }
    page += 1;
  }
  return all;
}
