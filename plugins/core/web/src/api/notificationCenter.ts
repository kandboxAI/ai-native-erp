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

/** 字典 ntf_severity */
export type NotificationSeverity = "normal" | "important" | "urgent";
/** 字典 ntf_channel */
export type NotificationChannel =
  "in_app" | "wechat_service" | "wechat_miniapp_subscribe" | "sms" | "email";
/** 字典 ntf_delivery_status */
export type NotificationDeliveryStatus =
  "pending" | "sent" | "failed" | "skipped";
/** 字典 ntf_target_type */
export type NotificationRouteTargetType =
  "all" | "role" | "user" | "permission" | "actor";
/** 字典 ntf_route_org_scope */
export type NotificationRouteOrgScope = "none" | "event_organization";
/** 字典 ntf_recipient_status */
export type NotificationRecipientStatus = "unread" | "read" | "archived";

export type NotificationSceneRow = {
  id: string;
  scene_key: string;
  scene_name: string;
  module_code: string;
  description: string | null;
  severity_code: NotificationSeverity;
  fallback_policy_code: "none" | "all";
  is_active: boolean;
  channel_codes: NotificationChannel[];
  created_at: string;
  updated_at: string;
};

export type NotificationSceneChannelRow = {
  id?: string;
  channel_code: NotificationChannel;
  is_active: boolean;
};

export type NotificationTemplateRow = {
  id?: string;
  scene_id?: string;
  channel_code: NotificationChannel;
  title_template: string | null;
  content_template: string | null;
  wechat_template_no: string | null;
  data_mapping_config: Record<string, unknown> | null;
  is_active: boolean;
};

export type NotificationRouteRow = {
  id?: string;
  scene_id?: string;
  target_type_code: NotificationRouteTargetType;
  role_id: string | null;
  user_id: string | null;
  permission_id: string | null;
  actor_key: string | null;
  org_scope_code: NotificationRouteOrgScope;
  is_active: boolean;
  role?: { id: string; role_no: string; role_name: string } | null;
  user?: { id: string; display_name: string } | null;
  permission?: {
    id: string;
    permission_key: string;
    permission_name: string;
    module_code: string;
  } | null;
};

export type NotificationSceneConfig = {
  scene: NotificationSceneRow;
  channels: NotificationSceneChannelRow[];
  templates: NotificationTemplateRow[];
  routes: NotificationRouteRow[];
};

export type NotificationScenePayload = {
  scene_key?: string;
  scene_name?: string;
  module_code?: string;
  description?: string | null;
  severity_code?: NotificationSeverity;
  fallback_policy_code?: "none" | "all";
  is_active?: boolean;
  channels?: Array<
    Pick<NotificationSceneChannelRow, "channel_code" | "is_active">
  >;
  templates?: Array<Omit<NotificationTemplateRow, "id" | "scene_id">>;
  routes?: Array<
    Omit<
      NotificationRouteRow,
      "id" | "scene_id" | "role" | "user" | "permission"
    >
  >;
};

export type NotificationRouteOptions = {
  roles: Array<{ id: string; role_no: string; role_name: string }>;
  permissions: Array<{
    id: string;
    permission_key: string;
    permission_name: string;
    module_code: string;
  }>;
};

export type NotificationMineRow = {
  targets?: { web?: string; miniapp?: string };
  recipient_id: string;
  notification_id: string;
  scene_key: string | null;
  scene_name_snapshot: string | null;
  title: string;
  content: string | null;
  severity_code: NotificationSeverity;
  status_code: NotificationRecipientStatus;
  read_at: string | null;
  requires_confirmation: boolean;
  confirmed_at: string | null;
  business_type_code: string | null;
  business_id: string | null;
  redirect_url: string | null;
  occurred_at: string | null;
  created_at: string;
};

export type NotificationHistoryRow = {
  id: string;
  org_id: string;
  scene_id: string;
  scene_key: string | null;
  scene_name_snapshot: string | null;
  title: string;
  content: string | null;
  severity_code: NotificationSeverity;
  status_code: "created" | "cancelled";
  source_module_code: string | null;
  business_type_code: string | null;
  business_id: string | null;
  event_key: string | null;
  redirect_url: string | null;
  recipient_count: number;
  read_count: number;
  unread_count: number;
  /** 渠道 → 投递状态 → 数量 */
  delivery_stats: Record<string, Record<string, number>>;
  occurred_at: string | null;
  created_at: string;
};

export type NotificationRecipientRow = {
  id: string;
  user_id: string;
  display_name: string | null;
  status_code: NotificationRecipientStatus;
  read_at: string | null;
  created_at: string;
};

export type NotificationDeliveryLogRow = {
  id: string;
  recipient_id: string;
  notification_id: string | null;
  scene_key: string | null;
  title: string | null;
  user_id: string | null;
  display_name: string | null;
  channel_code: NotificationChannel;
  provider_code: string | null;
  target_address: string | null;
  status_code: NotificationDeliveryStatus;
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
};

export type NotificationEventLogRow = {
  id: string;
  scene_id: string | null;
  scene_key: string | null;
  business_type_code: string | null;
  business_id: string | null;
  status_code: "processed" | "skipped" | "failed" | string;
  message: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type NotificationDeliveryProcessResult = {
  scanned_count: number;
  sent_count: number;
  failed_count: number;
  skipped_count: number;
};

export type NotificationPreferenceRow = {
  scene_id: string;
  scene_key: string;
  scene_name: string;
  module_code: string;
  channel_code: NotificationChannel;
  is_enabled_by_user: boolean;
};

export type NotificationChannelBindingRow = {
  id: string;
  user_id: string;
  channel_code: NotificationChannel;
  provider_code: string;
  appid: string;
  external_user_no: string;
  unionid: string | null;
  bound_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

const BASE = "/api/notification_center";

// ───────── 场景配置 ─────────
export const listNotificationScenes = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  module_code?: string;
  is_active?: boolean;
}) =>
  http.request<ApiResponse<PageResult<NotificationSceneRow>>>(
    "get",
    `${BASE}/scenes`,
    { params }
  );

export const getNotificationSceneConfig = (sceneId: string) =>
  http.request<ApiResponse<NotificationSceneConfig>>(
    "get",
    `${BASE}/scenes/${sceneId}`
  );

export const createNotificationScene = (data: NotificationScenePayload) =>
  http.request<ApiResponse<NotificationSceneConfig>>("post", `${BASE}/scenes`, {
    data
  });

export const updateNotificationScene = (
  sceneId: string,
  data: NotificationScenePayload
) =>
  http.request<ApiResponse<NotificationSceneConfig>>(
    "put",
    `${BASE}/scenes/${sceneId}`,
    { data }
  );

export const deleteNotificationScene = (sceneId: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `${BASE}/scenes/${sceneId}`
  );

export const getNotificationRouteOptions = () =>
  http.request<ApiResponse<NotificationRouteOptions>>(
    "get",
    `${BASE}/route-options`
  );

export const searchNotificationRouteUsers = (keyword?: string) =>
  http.request<ApiResponse<Array<{ id: string; display_name: string }>>>(
    "get",
    `${BASE}/route-options/users`,
    { params: { keyword, limit: 30 } }
  );

// ───────── 发送与投递 ─────────
export const publishNotification = (data: {
  scene_key: string;
  recipients?: string[];
  actors?: Record<string, string[]>;
  business_type_code?: string | null;
  business_id?: string | null;
  event_key?: string | null;
  redirect_url?: string | null;
  payload?: Record<string, unknown>;
}) =>
  http.request<
    ApiResponse<{
      notification_id: string | null;
      created: boolean;
      recipient_count: number;
      delivery_count: number;
      skipped_reason: string | null;
    }>
  >("post", `${BASE}/publish`, { data });

export const sendPendingDeliveries = (
  params: { channel_code?: NotificationChannel; limit?: number } = {}
) =>
  http.request<ApiResponse<NotificationDeliveryProcessResult>>(
    "post",
    `${BASE}/deliveries/send-pending`,
    { params }
  );

// ───────── 通知历史与日志 ─────────
export const listNotificationHistory = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  scene_id?: string;
  business_type_code?: string;
  severity_code?: NotificationSeverity;
  status_code?: "created" | "cancelled";
  occurred_start?: string;
  occurred_end?: string;
}) =>
  http.request<ApiResponse<PageResult<NotificationHistoryRow>>>(
    "get",
    `${BASE}/notifications`,
    { params }
  );

export const listNotificationRecipients = (
  notificationId: string,
  params: {
    page?: number;
    page_size?: number;
    status_code?: "all" | NotificationRecipientStatus;
  } = {}
) =>
  http.request<ApiResponse<PageResult<NotificationRecipientRow>>>(
    "get",
    `${BASE}/notifications/${notificationId}/recipients`,
    { params }
  );

export const listNotificationDeliveryLogs = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  notification_id?: string;
  scene_id?: string;
  channel_code?: NotificationChannel;
  status_code?: NotificationDeliveryStatus;
  provider_code?: string;
  created_start?: string;
  created_end?: string;
}) =>
  http.request<ApiResponse<PageResult<NotificationDeliveryLogRow>>>(
    "get",
    `${BASE}/delivery-logs`,
    { params }
  );

export const listNotificationEventLogs = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  scene_id?: string;
  business_type_code?: string;
  status_code?: "processed" | "skipped" | "failed";
  created_start?: string;
  created_end?: string;
}) =>
  http.request<ApiResponse<PageResult<NotificationEventLogRow>>>(
    "get",
    `${BASE}/event-logs`,
    { params }
  );

// ───────── 欠费提醒（需 notification_center:fee_remind） ─────────
export type EducationFeeReminderResult = {
  student_count: number;
  delivered_count: number;
  unmatched_names: string[];
  failed_names: string[];
};

export const remindEducationFees = (data: {
  mode: "self" | "all";
  class_name?: string;
  students: Array<{
    /** edu_student.id；非 UUID 时按姓名匹配 */
    student_id: string;
    student_name: string;
    class_name?: string;
    items: Array<{ item_name: string; amount: number }>;
  }>;
}) =>
  http.request<ApiResponse<EducationFeeReminderResult>>(
    "post",
    `${BASE}/fee-reminders`,
    { data }
  );

// ───────── 我的通知 ─────────
export const listMyNotifications = (params: {
  page?: number;
  page_size?: number;
  status_code?: "all" | NotificationRecipientStatus;
  scene_key?: string;
}) =>
  http.request<ApiResponse<PageResult<NotificationMineRow>>>(
    "get",
    `${BASE}/mine/list`,
    { params }
  );

export const getMyUnreadNotificationCount = () =>
  http.request<ApiResponse<{ unread_count: number }>>(
    "get",
    `${BASE}/mine/unread-count`
  );

export const markNotificationRead = (recipientId: string) =>
  http.request<ApiResponse<{ updated: boolean }>>(
    "post",
    `${BASE}/mine/read/${recipientId}`
  );

export const confirmNotification = (recipientId: string) =>
  http.request<ApiResponse<{ updated: boolean }>>(
    "post",
    `${BASE}/mine/confirm/${recipientId}`
  );

export const markAllNotificationsRead = () =>
  http.request<ApiResponse<{ marked_count: number }>>(
    "post",
    `${BASE}/mine/read-all`
  );

export const listMyNotificationPreferences = () =>
  http.request<ApiResponse<NotificationPreferenceRow[]>>(
    "get",
    `${BASE}/mine/preferences`
  );

export const saveMyNotificationPreferences = (
  data: Array<
    Pick<
      NotificationPreferenceRow,
      "scene_id" | "channel_code" | "is_enabled_by_user"
    >
  >
) =>
  http.request<ApiResponse<{ saved_count: number }>>(
    "put",
    `${BASE}/mine/preferences`,
    { data }
  );

export const listMyChannelBindings = () =>
  http.request<ApiResponse<NotificationChannelBindingRow[]>>(
    "get",
    `${BASE}/mine/channel-bindings`
  );

export const deleteMyChannelBinding = (bindingId: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `${BASE}/mine/channel-bindings/${bindingId}`
  );

export interface FamilyReceipt {
  reading_summary?: string;
  has_reading_details?: boolean;
  guardian_count?: number;
  guardian_read_count?: number;
  guardian_no_account_count?: number;
  student_count?: number;
  student_read_count?: number;
  id: string;
  scene_key: string;
  scene_name: string;
  title: string;
  content: string | null;
  occurred_at: string;
  student_name: string;
  class_name: string;
  requires_confirmation: boolean;
  recipient_count: number;
  read_count: number;
  confirmed_count: number;
  delivery: string;
  in_app_sent_count: number;
  external_sent_count: number;
  external_pending_count: number;
  external_failed_count: number;
  task_id: string | null;
  task_status: string | null;
  task_reason: string | null;
  task_result: string | null;
  can_resend: boolean;
  can_close_task: boolean;
}

export const listFamilyReceipts = (params: {
  page?: number;
  page_size?: number;
}) =>
  http.request<ApiResponse<{ items: FamilyReceipt[]; total: number }>>(
    "get",
    "/api/education/family-notices",
    { params }
  );

export const resendFamilyNotice = (id: string) =>
  http.request<ApiResponse<{ added: number; retried: number; bound: number }>>(
    "post",
    `/api/education/family-notices/${id}/resend`
  );

export type ReadingDetails = { title?: string; content?: string; reading_summary: string; reading_details: { context_name: string; recipient_name: string; audience_name: string; status: string; read_at: string | null; needs_followup: boolean }[] };
export const familyReadingDetails = (id: string) => http.request<ApiResponse<ReadingDetails>>("get", `/api/education/family-notices/${id}/reading-details`);

export const closeFamilyContact = (id: string, note: string) =>
  http.request<ApiResponse<{ id: string }>>(
    "post",
    `/api/education/family-notices/tasks/${id}/close`,
    { data: { note } }
  );
