import { formatToken, getToken } from "@/utils/auth";
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

/** 数据范围编码（字典 sys_data_scope） */
export type RoleDataScope =
  "all" | "organization" | "department" | "self" | "related";

/** 列表行（后端 RoleListItem） */
export type SystemRoleRow = {
  id: string;
  role_no: string;
  role_name: string;
  description: string | null;
  data_scope_code: RoleDataScope;
  is_builtin: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
  user_count: number;
  permission_count: number;
  menu_count: number;
};

export type RolePermissionItem = {
  id: string;
  permission_key: string;
  permission_name: string;
  module_code: string;
  data_scope_code: RoleDataScope;
  is_scope_overridden: boolean;
};

export type RoleMenuItem = {
  id: string;
  menu_key: string;
  menu_name: string;
  menu_type_code: string;
  path?: string | null;
};

export type SystemRoleDetail = SystemRoleRow & {
  permissions: RolePermissionItem[];
  menus: RoleMenuItem[];
  users: Array<{ id: string; display_name: string; full_name: string | null }>;
  miniapp_menu_ids: string[];
};

/** 权限节点（扁平勾选） */
export type SystemPermission = {
  id: string;
  permission_key: string;
  permission_name: string;
  module_code: string;
};

export type RolePermissionConfigItem = SystemPermission & {
  selected: boolean;
  data_scope_code: RoleDataScope;
};

export type RolePermissionConfig = {
  role: SystemRoleRow;
  permissions: RolePermissionConfigItem[];
};

export type RoleListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  role_no?: string;
  role_name?: string;
  is_active?: boolean;
  sort_by?:
    | "updated_at"
    | "created_at"
    | "role_no"
    | "role_name"
    | "user_count"
    | "permission_count";
  sort_order?: "asc" | "desc";
};

export type RolePayload = {
  role_no: string;
  role_name: string;
  description?: string | null;
  data_scope_code: RoleDataScope;
  is_active?: boolean;
};

export type RolePermissionScopePayload = {
  permission_id: string;
  /** null = 取角色默认数据范围 */
  data_scope_code: RoleDataScope | null;
};

export type RolePermissionBatchSyncPayload = {
  role_id: string;
  permission_ids?: string[];
  permission_scopes?: RolePermissionScopePayload[];
};

export type RoleMenuBatchSyncPayload = {
  role_id: string;
  menu_ids: string[];
};

export type RoleMenuLinkRow = {
  id: string;
  role_id: string;
  menu_id: string;
  role_no: string;
  role_name: string;
  menu_key: string;
  menu_name: string;
  menu_type_code: string;
  created_at: string;
};

export type RolePermissionTemplateImportResult = {
  processed_count: number;
  created_count: number;
  updated_count: number;
  role_menu_total: number;
  role_permission_total: number;
  errors: { row: number; message: string }[];
};

export const listRoles = (params: RoleListParams = {}) => {
  return http.request<ApiResponse<PageResult<SystemRoleRow>>>(
    "get",
    "/api/role/list",
    { params }
  );
};

/** 全部角色（下拉选项用） */
export async function fetchAllRoles(
  params: Omit<RoleListParams, "page" | "page_size"> = {}
): Promise<SystemRoleRow[]> {
  const res = await listRoles({
    ...params,
    page: 1,
    page_size: 500,
    sort_by: "role_no",
    sort_order: "asc"
  });
  return res.data?.items ?? [];
}

export const getRoleDetail = (id: string) => {
  return http.request<ApiResponse<SystemRoleDetail>>(
    "get",
    `/api/role/detail/${id}`
  );
};

export const getRolePermissionConfig = (id: string) => {
  return http.request<ApiResponse<RolePermissionConfig>>(
    "get",
    `/api/role/permission-config/${id}`
  );
};

export const createRole = (data: RolePayload) => {
  return http.request<ApiResponse<SystemRoleDetail>>(
    "post",
    "/api/role/create",
    { data }
  );
};

export const updateRole = (id: string, data: Partial<RolePayload>) => {
  return http.request<ApiResponse<SystemRoleDetail>>(
    "put",
    `/api/role/update/${id}`,
    { data }
  );
};

export const deleteRole = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/role/delete/${id}`
  );
};

export const downloadRolePermissionTemplate = () => {
  return http.request<Blob>("get", "/api/role/permission-template", {
    responseType: "blob"
  });
};

export const exportRolePermissionTemplate = () => {
  return http.request<Blob>("get", "/api/role/permission-template/export", {
    responseType: "blob"
  });
};

export async function importRolePermissionTemplate(
  file: File
): Promise<ApiResponse<RolePermissionTemplateImportResult>> {
  const fd = new FormData();
  fd.append("file", file);
  const tokenInfo = getToken();
  const headers: Record<string, string> = {};
  if (tokenInfo?.accessToken) {
    headers.Authorization = formatToken(tokenInfo.accessToken);
  }
  const res = await fetch("/api/role/permission-template/import", {
    method: "POST",
    headers,
    body: fd,
    credentials: "same-origin"
  });
  const body = (await res
    .json()
    .catch(
      () => null
    )) as ApiResponse<RolePermissionTemplateImportResult> | null;
  if (!res.ok || !body || typeof body !== "object") {
    throw new Error("导入失败");
  }
  if (body.code !== 0) {
    throw new Error(body.message || "导入失败");
  }
  return body;
}

export const batchSyncRolePermissions = (
  data: RolePermissionBatchSyncPayload
) => {
  return http.request<
    ApiResponse<{
      added: number;
      removed: number;
      updated: number;
      total: number;
    }>
  >("post", "/api/role_permission/batch-sync", { data });
};

/** 角色已绑定的菜单 id */
export async function fetchRoleMenuIds(roleId: string): Promise<string[]> {
  const res = await http.request<ApiResponse<PageResult<RoleMenuLinkRow>>>(
    "get",
    "/api/role_menu/list",
    { params: { role_id: roleId, page: 1, page_size: 2000 } }
  );
  return (res.data?.items ?? []).map(item => item.menu_id);
}

export const batchSyncRoleMenus = (data: RoleMenuBatchSyncPayload) => {
  return http.request<
    ApiResponse<{ added: number; removed: number; total: number }>
  >("post", "/api/role_menu/batch-sync", { data });
};

export const DATA_SCOPE_LABELS: Record<RoleDataScope, string> = {
  all: "全部",
  organization: "本组织",
  department: "本部门",
  self: "本人",
  related: "关联关系"
};

export function dataScopeLabel(scope?: string | null): string {
  if (!scope) return "—";
  return DATA_SCOPE_LABELS[scope as RoleDataScope] ?? scope;
}
