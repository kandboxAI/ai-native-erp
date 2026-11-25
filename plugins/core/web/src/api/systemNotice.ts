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

/** 字典 ntf_notice_type */
export type NoticeTypeCode = "notice" | "announcement";
/** 字典 ntf_notice_status */
export type NoticeStatusCode = "draft" | "published" | "offline";
export type NoticeTargetScope = "all" | "role" | "user" | "mixed";

/** 公告（ntf_notice） */
export type SystemNoticeRow = {
  id: string;
  org_id: string;
  title: string;
  summary: string | null;
  notice_type_code: NoticeTypeCode;
  /** 是否在首页显示 */
  is_shown_on_home: boolean;
  status_code: NoticeStatusCode;
  target_scope: NoticeTargetScope;
  target_role_ids: string[];
  target_user_ids: string[];
  target_roles: Array<{ id: string; role_no: string; role_name: string }>;
  target_users: Array<{ id: string; display_name: string }>;
  published_by: string | null;
  publisher_name_snapshot: string | null;
  published_at: string | null;
  is_read: boolean;
  read_at: string | null;
  read_count: number;
  unread_count: number;
  created_at: string;
  updated_at: string;
};

export type NoticeReadStatus = "all" | "read" | "unread";

export type NoticeReaderRow = {
  user_id: string;
  display_name: string;
  is_read: boolean;
  read_at: string | null;
};

export type NoticeListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  notice_type_code?: NoticeTypeCode;
  is_shown_on_home?: boolean;
  status_code?: NoticeStatusCode;
  read_status?: NoticeReadStatus;
};

export type NoticePayload = {
  title: string;
  summary?: string | null;
  notice_type_code?: NoticeTypeCode;
  is_shown_on_home?: boolean;
  status_code?: NoticeStatusCode;
  org_id?: string | null;
  target_scope?: NoticeTargetScope;
  target_role_ids?: string[];
  target_user_ids?: string[];
};

const BASE = "/api/notice_announcement";

export const listNotices = (params: NoticeListParams) =>
  http.request<ApiResponse<PageResult<SystemNoticeRow>>>(
    "get",
    `${BASE}/list`,
    { params }
  );

/** 本人可见（已发布且在接收范围内） */
export const listMyNotices = (params: NoticeListParams) =>
  http.request<ApiResponse<PageResult<SystemNoticeRow>>>(
    "get",
    `${BASE}/mine/list`,
    { params }
  );

/** 首页公告：本人可见且在首页显示 */
export const listHomeNotices = (pageSize = 5) =>
  listMyNotices({ page: 1, page_size: pageSize, is_shown_on_home: true });

export const getMyNotice = (id: string) =>
  http.request<ApiResponse<SystemNoticeRow>>(
    "get",
    `${BASE}/mine/detail/${id}`
  );

export const createNotice = (data: NoticePayload) =>
  http.request<ApiResponse<SystemNoticeRow>>("post", `${BASE}/create`, {
    data
  });

export const updateNotice = (id: string, data: Partial<NoticePayload>) =>
  http.request<ApiResponse<SystemNoticeRow>>("put", `${BASE}/update/${id}`, {
    data
  });

export const deleteNotice = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `${BASE}/delete/${id}`
  );

export const markNoticeRead = (id: string) =>
  http.request<ApiResponse<SystemNoticeRow>>("post", `${BASE}/read/${id}`);

export const markAllNoticesRead = () =>
  http.request<ApiResponse<{ marked_count: number }>>(
    "post",
    `${BASE}/read-all`
  );

export const listNoticeReaders = (
  id: string,
  params: { page?: number; page_size?: number; read_status?: NoticeReadStatus }
) =>
  http.request<ApiResponse<PageResult<NoticeReaderRow>>>(
    "get",
    `${BASE}/readers/${id}`,
    { params }
  );

export type NoticeTargetOptions = {
  roles: Array<{ id: string; role_no: string; role_name: string }>;
  users: Array<{ id: string; display_name: string }>;
};

/** 接收范围可选的角色与用户（需公告新增或修改权限） */
export const getNoticeTargetOptions = (keyword?: string) =>
  http.request<ApiResponse<NoticeTargetOptions>>(
    "get",
    `${BASE}/target-options`,
    { params: { keyword: keyword || undefined, limit: 50 } }
  );
