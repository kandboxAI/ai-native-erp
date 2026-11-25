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

export type OrgAccessModeCode = "primary_only" | "assigned" | "all";

export type UserProfileRoleItem = {
  id: string;
  role_no: string;
  role_name: string;
};

export type UserProfileRow = {
  id: string;
  auth_user_id: string;
  party_id?: string | null;
  display_name: string;
  full_name: string | null;
  email: string | null;
  mobile: string | null;
  avatar_url: string | null;
  org_id: string;
  org_name?: string | null;
  org_access_mode_code: OrgAccessModeCode;
  org_ids: string[];
  department_id?: string | null;
  department_name?: string | null;
  is_active: boolean;
  account_is_active: boolean;
  roles: UserProfileRoleItem[];
  position_ids: string[];
  role_count: number;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
};

export type UserProfileDetail = UserProfileRow & {
  permissions: Array<{
    id: string;
    permission_key: string;
    permission_name: string;
    module_code: string;
  }>;
};

export type UserProfileListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  full_name?: string;
  email?: string;
  mobile?: string;
  org_id?: string;
  department_id?: string;
  role_id?: string;
  role_no?: string;
  is_active?: boolean;
  sort_by?:
    "updated_at" | "created_at" | "display_name" | "email" | "role_count";
  sort_order?: "asc" | "desc";
};

/** 新增用户：邮箱、手机号至少一个 */
export type UserProfileCreatePayload = {
  email?: string | null;
  mobile?: string | null;
  password: string;
  full_name: string;
  display_name?: string | null;
  org_id: string;
  org_access_mode_code?: OrgAccessModeCode;
  org_ids?: string[];
  department_id?: string | null;
  role_ids?: string[];
  position_ids?: string[];
  is_active?: boolean;
};

/** 修改用户：邮箱和手机号均不可改 */
export type UserProfileUpdatePayload = {
  full_name?: string;
  display_name?: string | null;
  avatar_url?: string | null;
  org_id?: string;
  org_access_mode_code?: OrgAccessModeCode;
  org_ids?: string[];
  department_id?: string | null;
  role_ids?: string[];
  position_ids?: string[];
  is_active?: boolean;
};

export type UserOrgOption = {
  id: string;
  org_name: string;
  org_type_code: string | null;
};

export const listUserProfiles = (params: UserProfileListParams) => {
  return http.request<ApiResponse<PageResult<UserProfileRow>>>(
    "get",
    "/api/user_profile/list",
    { params }
  );
};

export const getUserProfileDetail = (id: string) => {
  return http.request<ApiResponse<UserProfileDetail>>(
    "get",
    `/api/user_profile/detail/${id}`
  );
};

export const createUserProfile = (data: UserProfileCreatePayload) => {
  return http.request<ApiResponse<UserProfileDetail>>(
    "post",
    "/api/user_profile/create",
    { data }
  );
};

export const updateUserProfile = (
  id: string,
  data: UserProfileUpdatePayload
) => {
  return http.request<ApiResponse<UserProfileDetail>>(
    "put",
    `/api/user_profile/update/${id}`,
    { data }
  );
};

export const deleteUserProfile = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean; deactivated?: boolean }>>(
    "delete",
    `/api/user_profile/delete/${id}`
  );
};

export const updateUserProfileStatus = (id: string, is_active: boolean) => {
  return http.request<ApiResponse<{ updated: boolean; is_active: boolean }>>(
    "put",
    `/api/user_profile/status/${id}`,
    { data: { is_active } }
  );
};

/** 重置登录密码（需 user_profile:reset_password） */
export const resetUserProfilePassword = (
  id: string,
  password: string,
  is_password_change_required = false
) => {
  return http.request<ApiResponse<{ updated: boolean }>>(
    "post",
    `/api/user_profile/reset_password/${id}`,
    { data: { password, is_password_change_required } }
  );
};

/** 用户表单可选组织 */
export const listUserOrgOptions = () => {
  return http.request<ApiResponse<UserOrgOption[]>>(
    "get",
    "/api/user_profile/org_options"
  );
};

/** 拉取用户（下拉选择用，page_size 100 分页拼接） */
export async function fetchAllUserProfiles(
  params: Omit<UserProfileListParams, "page" | "page_size"> = {}
): Promise<UserProfileRow[]> {
  const page_size = 100;
  let page = 1;
  const all: UserProfileRow[] = [];
  for (;;) {
    const res = await listUserProfiles({ ...params, page, page_size });
    if (res.code !== 0) throw new Error(res.message);
    const batch = res.data?.items ?? [];
    all.push(...batch);
    if (batch.length < page_size || all.length >= (res.data?.total ?? 0)) {
      break;
    }
    page += 1;
  }
  return all;
}

export type UserPositionOption = {
  id: string;
  org_id: string;
  name: string;
  department_name: string;
  is_active: boolean;
};
export const getUserPositionOptions = (org_id: string) =>
  http.request<ApiResponse<UserPositionOption[]>>(
    "get",
    "/api/user_profile/position_options",
    { params: { org_id } }
  );
