import { http } from "@/utils/http";
import { applyLocalListQuery } from "@/utils/listState";
import type { OrganizationTreeNode } from "@/api/organizationStructure";

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

type ResultTable = {
  code: number;
  message: string;
  data?: {
    list: Array<any>;
    total?: number;
    pageSize?: number;
    currentPage?: number;
  };
};

type OperationResult = {
  code: number;
  message: string;
  data?: Record<string, any>;
};

const ok = <T>(
  data: T,
  extra: Partial<OperationResult> = {}
): OperationResult & { data: T } => ({
  code: 0,
  message: "success",
  ...extra,
  data
});

/* ----------------------------- 组织 ----------------------------- */

export const getOrganizationTree = () => {
  return http.request<ApiResponse<OrganizationTreeNode[]>>(
    "get",
    "/api/organization/tree"
  );
};

export type OrganizationPayload = {
  org_no: string;
  org_name: string;
  org_type_code: string;
  parent_id?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  address?: string | null;
  sort_no?: number | null;
  is_active?: boolean;
  remark?: string | null;
};

export type OrganizationDetail = OrganizationPayload & {
  id: string;
  created_at?: string;
  updated_at?: string;
};

export const getOrganization = (id: string) => {
  return http.request<ApiResponse<OrganizationDetail>>(
    "get",
    `/api/organization/detail/${id}`
  );
};

export const createOrganization = (data: OrganizationPayload) => {
  return http.request<ApiResponse<OrganizationDetail>>(
    "post",
    "/api/organization/create",
    { data }
  );
};

export const updateOrganization = (
  id: string,
  data: Partial<OrganizationPayload>
) => {
  return http.request<ApiResponse<OrganizationDetail>>(
    "put",
    `/api/organization/update/${id}`,
    { data }
  );
};

export const deleteOrganization = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/organization/delete/${id}`
  );
};

/* ----------------------------- 部门 ----------------------------- */

export type DepartmentRow = {
  id: string;
  org_id: string;
  department_no: string;
  department_name: string;
  parent_id: string | null;
  manager_user_id: string | null;
  sort_no: number | null;
  is_active: boolean;
  remark: string | null;
  created_at: string;
  created_by?: string | null;
  updated_at: string;
  updated_by?: string | null;
};

export type DepartmentPayload = {
  org_id: string;
  department_no: string;
  department_name: string;
  parent_id?: string | null;
  manager_user_id?: string | null;
  sort_no?: number | null;
  is_active?: boolean;
  remark?: string | null;
};

export type DepartmentListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  org_id?: string;
  is_active?: boolean;
};

export const listDepartments = (params: DepartmentListParams) => {
  return http.request<ApiResponse<PageResult<DepartmentRow>>>(
    "get",
    "/api/department/list",
    { params }
  );
};

/** 拉取全部部门（page_size 最大 100，分页拼接） */
export async function fetchAllDepartments(
  params: Omit<DepartmentListParams, "page" | "page_size"> = {}
): Promise<DepartmentRow[]> {
  const page_size = 100;
  let page = 1;
  const all: DepartmentRow[] = [];
  for (;;) {
    const res = await listDepartments({ ...params, page, page_size });
    const batch = res.data?.items ?? [];
    all.push(...batch);
    if (batch.length < page_size || all.length >= (res.data?.total ?? 0)) {
      break;
    }
    page += 1;
  }
  return all;
}

export const createDepartment = (data: DepartmentPayload) => {
  return http.request<ApiResponse<DepartmentRow>>(
    "post",
    "/api/department/create",
    { data }
  );
};

export const updateDepartment = (
  id: string,
  data: Partial<DepartmentPayload>
) => {
  return http.request<ApiResponse<DepartmentRow>>(
    "put",
    `/api/department/update/${id}`,
    { data }
  );
};

export const deleteDepartment = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/department/delete/${id}`
  );
};

/* ----------------------------- 菜单 ----------------------------- */

export type MenuTypeCode = "directory" | "menu" | "button";
export type OpenTargetCode = "self" | "blank" | "iframe";

export type MenuNode = {
  id: string;
  parent_id: string | null;
  menu_key: string;
  menu_name: string;
  menu_type_code: MenuTypeCode;
  path: string | null;
  component: string | null;
  icon: string | null;
  permission_id: string | null;
  permission_key: string | null;
  is_external: boolean;
  external_url: string | null;
  open_target_code: OpenTargetCode | null;
  sort_no: number | null;
  is_visible: boolean;
  is_active: boolean;
  remark: string | null;
  flex_form: Record<string, any>;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
  children?: MenuNode[];
};

export type MenuPayload = {
  menu_key?: string;
  menu_name: string;
  menu_type_code: MenuTypeCode;
  parent_id: string | null;
  path: string | null;
  component: string | null;
  icon: string | null;
  permission_key: string | null;
  is_external: boolean;
  external_url: string | null;
  open_target_code: OpenTargetCode | null;
  sort_no: number | null;
  is_visible: boolean;
  is_active: boolean;
  remark: string | null;
  flex_form: Record<string, any>;
};

/** 全部未删除菜单树（含停用、隐藏、按钮） */
export const getMenuTree = () => {
  return http.request<ApiResponse<MenuNode[]>>("get", "/api/menu/tree");
};

export const createMenu = (data: MenuPayload & { menu_key: string }) => {
  return http.request<ApiResponse<MenuNode>>("post", "/api/menu/create", {
    data
  });
};

export const updateMenu = (id: string, data: Partial<MenuPayload>) => {
  const { menu_key: _menuKey, ...rest } = data;
  return http.request<ApiResponse<MenuNode>>("put", `/api/menu/update/${id}`, {
    data: rest
  });
};

export const deleteMenu = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/menu/delete/${id}`
  );
};

/* ----------------------------- 系统监控 ----------------------------- */

function parseUserAgent(userAgent?: string | null) {
  const text = userAgent || "";
  const system = /Windows/i.test(text)
    ? "Windows"
    : /Mac OS X|Macintosh/i.test(text)
      ? "macOS"
      : /Android/i.test(text)
        ? "Android"
        : /iPhone|iPad|iOS/i.test(text)
          ? "iOS"
          : /Linux/i.test(text)
            ? "Linux"
            : text
              ? "其他"
              : "—";
  const browser = /Edg\//i.test(text)
    ? "Edge"
    : /MicroMessenger/i.test(text)
      ? "微信"
      : /Chrome\//i.test(text)
        ? "Chrome"
        : /Firefox\//i.test(text)
          ? "Firefox"
          : /Safari\//i.test(text)
            ? "Safari"
            : text
              ? "其他"
              : "—";
  return { system, browser };
}

function parseHttpContent(content?: string | null) {
  const text = (content || "").trim();
  const matched = text.match(/^([A-Z]+)\s+(\S+)(?:\s+->\s+(\d+))?/);
  return {
    method: matched?.[1] || "",
    url: matched?.[2] || text,
    statusCode: matched?.[3] ? Number(matched[3]) : undefined
  };
}

function toBoolStatus(status: unknown): boolean | undefined {
  if (status === 1 || status === "1" || status === true) return true;
  if (status === 0 || status === "0" || status === false) return false;
  return undefined;
}

function toCreatedRange(range: unknown) {
  if (!Array.isArray(range) || range.length < 2 || !range[0] || !range[1]) {
    return {};
  }
  return {
    created_start: String(range[0]),
    created_end: String(range[1])
  };
}

function wrapPageList(
  res: ApiResponse<PageResult<Record<string, any>>>,
  list: Record<string, any>[]
) {
  return {
    code: res.code,
    message: res.message,
    data: {
      list,
      total: res.data?.total ?? list.length,
      pageSize: res.data?.page_size,
      currentPage: res.data?.page
    }
  } satisfies ResultTable;
}

function mapLoginLog(row: Record<string, any>) {
  const ua = parseUserAgent(row.user_agent);
  return {
    id: row.id,
    username: row.display_name || row.login_name || "—",
    loginName: row.login_name || "—",
    ip: row.ip_address || "—",
    address: "—",
    system: ua.system,
    browser: ua.browser,
    status: row.is_success ? 1 : 0,
    behavior: row.message || (row.is_success ? "登录成功" : "登录失败"),
    loginTime: row.created_at
  };
}

function mapOperationLog(row: Record<string, any>) {
  const httpInfo = parseHttpContent(row.content);
  return {
    id: row.id,
    username: row.actor_name || "—",
    module: row.module_code || "—",
    action: row.action_code || "—",
    summary: row.action_code || "—",
    content: row.content || "—",
    ip: row.ip_address || "—",
    address: "—",
    system: "—",
    browser: "—",
    status: httpInfo.statusCode && httpInfo.statusCode >= 400 ? 0 : 1,
    operatingTime: row.created_at
  };
}

function mapSystemLog(row: Record<string, any>) {
  const httpInfo = parseHttpContent(row.content);
  return {
    id: row.id,
    module: row.module_code || "—",
    url: httpInfo.url || "—",
    method: httpInfo.method || row.action_code || "—",
    ip: row.ip_address || "—",
    address: "—",
    system: "—",
    browser: "—",
    takesTime: undefined,
    requestTime: row.created_at,
    content: row.content || "",
    targetType: row.target_type_code || "",
    targetId: row.target_id || "",
    isAgentAction: Boolean(row.is_agent_action),
    username: row.actor_name || "—",
    action: row.action_code || "—"
  };
}

function mapOnlineUser(row: Record<string, any>, index: number) {
  const ua = parseUserAgent(row.user_agent);
  return {
    id: row.auth_user_id || index + 1,
    auth_user_id: row.auth_user_id,
    username: row.display_name || row.email || row.auth_user_id || "—",
    email: row.email || "—",
    roleNos: Array.isArray(row.role_nos) ? row.role_nos.join(", ") : "—",
    ip: row.ip_address || "—",
    address: "—",
    system: ua.system,
    browser: ua.browser,
    loginTime: row.last_seen_at
  };
}

async function fetchOperationLogPage(data?: Record<string, any>) {
  return http.request<ApiResponse<PageResult<Record<string, any>>>>(
    "get",
    "/api/operation_log/list",
    {
      params: {
        page: data?.currentPage || 1,
        page_size: data?.pageSize || 10,
        module_code: data?.module || undefined,
        actor_name: data?.actorName || undefined,
        ip_address: data?.ip || undefined,
        keyword: data?.keyword || undefined,
        ...toCreatedRange(data?.operatingTime || data?.requestTime)
      }
    }
  );
}

/** 获取系统监控-在线用户列表 */
export const getOnlineLogsList = async (data?: Record<string, any>) => {
  const res = await http.request<ApiResponse<Record<string, any>[]>>(
    "get",
    "/api/system/online-users"
  );
  const keyword = String(data?.username || "")
    .trim()
    .toLowerCase();
  const mapped = (res.data ?? []).map(mapOnlineUser);
  const filtered = keyword
    ? mapped.filter(item =>
        [item.username, item.email, item.roleNos]
          .join(" ")
          .toLowerCase()
          .includes(keyword)
      )
    : mapped;
  const page = Number(data?.currentPage) || 1;
  const pageSize = Number(data?.pageSize) || 10;
  const start = (page - 1) * pageSize;
  return {
    code: res.code,
    message: res.message,
    data: {
      list: applyLocalListQuery(
        { method: "get", url: "/api/system/online-users" },
        filtered,
        ["username", "email", "roleNos", "ip", "system", "browser", "loginTime"]
      ).slice(start, start + pageSize),
      total: filtered.length,
      pageSize,
      currentPage: page
    }
  } satisfies ResultTable;
};

export const kickOnlineUser = async (authUserId: string) => {
  const res = await http.request<ApiResponse<{ kicked: boolean }>>(
    "post",
    "/api/system/online-users/kick",
    { data: { auth_user_id: authUserId } }
  );
  return ok(res.data ?? { kicked: true }, {
    code: res.code,
    message: res.message
  });
};

/** 获取系统监控-登录日志列表 */
export const getLoginLogsList = async (data?: Record<string, any>) => {
  const res = await http.request<ApiResponse<PageResult<Record<string, any>>>>(
    "get",
    "/api/login_log/list",
    {
      params: {
        page: data?.currentPage || 1,
        page_size: data?.pageSize || 10,
        login_name: data?.username || undefined,
        ip_address: data?.ip || undefined,
        is_success: toBoolStatus(data?.status),
        ...toCreatedRange(data?.loginTime)
      }
    }
  );
  return wrapPageList(res, (res.data?.items ?? []).map(mapLoginLog));
};

/** 获取系统监控-操作日志列表 */
export const getOperationLogsList = async (data?: Record<string, any>) => {
  const res = await fetchOperationLogPage(data);
  return wrapPageList(res, (res.data?.items ?? []).map(mapOperationLog));
};

/** 获取系统监控-系统日志列表（请求审计，复用操作日志） */
export const getSystemLogsList = async (data?: Record<string, any>) => {
  const res = await fetchOperationLogPage(data);
  return wrapPageList(res, (res.data?.items ?? []).map(mapSystemLog));
};

/** 获取系统监控-系统日志-根据 id 查日志详情 */
export const getSystemLogsDetail = async (data?: { id?: string }) => {
  const res = await http.request<ApiResponse<Record<string, any>>>(
    "get",
    `/api/operation_log/detail/${data?.id}`
  );
  return mapSystemLog(res.data ?? {});
};
