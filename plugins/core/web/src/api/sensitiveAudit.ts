import { http } from "@/utils/http";

type Result<T> = { code: number; message: string; data: T };
export type SensitiveAuditItem = {
  id: string;
  actor_user_id?: string;
  actor_name?: string;
  module_code: string;
  action_code: string;
  target_type_code?: string;
  target_id?: string;
  request_id?: string;
  request_method?: string;
  request_path?: string;
  http_status?: number;
  created_at: string;
  ip_address?: string;
};
export const getAuditOptions = () =>
  http.request<Result<{ targets: { value: string; label: string }[] }>>(
    "get",
    "/api/operation_log/options"
  );
export const getSensitiveAudits = (params: Record<string, unknown>) =>
  http.request<Result<{ items: SensitiveAuditItem[]; total: number }>>(
    "get",
    "/api/operation_log/list",
    { params: { ...params, sensitive_only: true } }
  );
export const getAuditDetail = (id: string) =>
  http.request<Result<SensitiveAuditItem>>(
    "get",
    `/api/operation_log/detail/${id}`
  );
