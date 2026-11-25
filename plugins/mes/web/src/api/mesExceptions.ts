import { http } from "@/utils/http";
import type { ApiResponse, MesPage, MesOption } from "./mes";
import { deliveryParams } from "./mesDelivery";
export type ExceptionStatus =
  "pending" | "in_progress" | "waiting_confirmation" | "closed";
export type ExceptionAction =
  "assign" | "start" | "progress" | "resolve" | "approve" | "reject" | "reopen";
export type ExceptionCase = {
  id: string;
  org_id: string;
  case_no: string;
  work_order_id: string;
  work_order_no: string;
  operation_id?: string;
  operation_name?: string;
  title: string;
  description: string;
  exception_type_code: string;
  status_code: ExceptionStatus;
  assigned_user_id?: string;
  assigned_user_name?: string;
  reporter_name?: string;
  due_at: string;
  resolved_at?: string;
  closed_at?: string;
  created_at: string;
  version_no: number;
  is_overdue: boolean;
  allowed_actions: ExceptionAction[];
  notification_warning?: string;
};
export type ExceptionEvent = {
  id: string;
  action_code: string;
  from_status_code?: string;
  to_status_code: string;
  note: string;
  actor_name?: string;
  assigned_user_id?: string;
  assigned_user_name?: string;
  due_at_snapshot: string;
  created_at: string;
};
export type ExceptionPayload = {
  work_order_id: string;
  operation_id?: string | null;
  title: string;
  description: string;
  exception_type_code: string;
  assigned_user_id?: string | null;
  due_at: string;
  idempotency_key: string;
};
export const exceptionStatusLabels: Record<ExceptionStatus, string> = {
  pending: "待处理",
  in_progress: "处理中",
  waiting_confirmation: "待确认",
  closed: "已关闭",
};
export const exceptionTypeLabels: Record<string, string> = {
  material_shortage: "缺料",
  equipment_failure: "设备故障",
  quality_abnormal: "质量异常",
  changeover: "换型",
  other: "其他",
};
export const exceptionActionLabels: Record<string, string> = {
  created: "登记",
  assign: "指派 / 调整期限",
  start: "开始处理",
  progress: "记录处理进展",
  resolve: "提交处理结果",
  approve: "复核关闭",
  reject: "退回处理",
  reopen: "重开异常",
  reminded: "超时提醒",
};
export const getExceptionCases = (params: Record<string, unknown>) =>
  http.request<ApiResponse<MesPage<ExceptionCase>>>(
    "get",
    "/api/mes/exceptions",
    { params: deliveryParams(params) },
  );
export const getExceptionCase = (id: string) =>
  http.request<ApiResponse<ExceptionCase>>("get", `/api/mes/exceptions/${id}`);
export const getExceptionEvents = (id: string, page = 1) =>
  http.request<ApiResponse<MesPage<ExceptionEvent>>>(
    "get",
    `/api/mes/exceptions/${id}/events`,
    { params: { page, page_size: 20 } },
  );
export const createExceptionCase = (data: ExceptionPayload) =>
  http.request<ApiResponse<ExceptionCase>>("post", "/api/mes/exceptions", {
    data,
  });
export const actOnException = (
  id: string,
  action: ExceptionAction,
  data: {
    version_no: number;
    note: string;
    assigned_user_id?: string;
    due_at?: string;
  },
) =>
  http.request<ApiResponse<ExceptionCase>>(
    "post",
    `/api/mes/exceptions/${id}/actions/${action}`,
    { data },
  );
export async function exceptionOrderOptions(
  keyword = "",
): Promise<MesOption[]> {
  const result = await http.request<
    ApiResponse<{ id: string; label: string }[]>
  >("get", "/api/mes/exception-options/orders", { params: { keyword } });
  return result.data.map((row) => ({ value: row.id, label: row.label }));
}
export async function exceptionSourceOptions(id: string, keyword = "") {
  const result = await http.request<
    ApiResponse<{
      operations: { id: string; label: string }[];
      users: { id: string; display_name: string }[];
    }>
  >("get", `/api/mes/exception-options/orders/${id}`, { params: { keyword } });
  return {
    operations: result.data.operations.map((row) => ({
      value: row.id,
      label: row.label,
    })),
    users: result.data.users.map((row) => ({
      value: row.id,
      label: row.display_name,
    })),
  };
}
export async function exceptionAssignees(
  id: string,
  keyword = "",
): Promise<MesOption[]> {
  const result = await http.request<
    ApiResponse<{ id: string; display_name: string }[]>
  >("get", `/api/mes/exceptions/${id}/assignees`, { params: { keyword } });
  return result.data.map((row) => ({ value: row.id, label: row.display_name }));
}
