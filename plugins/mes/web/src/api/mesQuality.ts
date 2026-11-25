import { http } from "@/utils/http";
import type { MesTask, MesTaskDetail } from "./mes";

export type QualityInspection = {
  inspection_type_code?: string;
  production_phase_id?: string | null;
  id: string;
  operation_id: string;
  execution_id: string;
  operation_version_snapshot: number;
  result_code: "pass" | "fail";
  to_status_code: string;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  unit_name: string;
  note?: string | null;
  created_at: string;
};
export type QualityTask = Pick<
  MesTask,
  | "id"
  | "org_id"
  | "work_order_id"
  | "work_order_no"
  | "work_order_status_code"
  | "product_item_no"
  | "product_item_name"
  | "operation_no"
  | "operation_name"
  | "status_code"
  | "status_label"
  | "planned_quantity"
  | "good_quantity"
  | "scrap_quantity"
  | "rework_quantity"
  | "unit_name"
> & { version_no: number };
export type QualityDetail = QualityTask & {
  inspections: QualityInspection[];
  schedule_context?: MesTaskDetail["schedule_context"];
  rework_options?: Array<{ value: string; label: string }>;
};
export type QualityBody = {
  version_no: number;
  result_code: "pass" | "fail";
  note?: string | null;
  idempotency_key: string;
  production_phase_code?: "first" | "remaining";
  production_person_id?: string;
  rework_operation_id?: string;
};
type Response<T> = { code: number; message: string; data: T };
export const getQualityTasks = (params: {
  page: number;
  page_size: number;
  keyword?: string;
  status_code?: string;
}) =>
  http.request<Response<{ items: QualityTask[]; total: number }>>(
    "get",
    "/api/mes/quality/tasks",
    { params },
  );
export const getQualityTask = (id: string) =>
  http.request<Response<QualityDetail>>("get", `/api/mes/quality/tasks/${id}`);
export const submitQualityInspection = (id: string, data: QualityBody) =>
  http.request<Response<{ task: QualityTask; inspection: QualityInspection }>>(
    "post",
    `/api/mes/quality/tasks/${id}/inspections`,
    { data },
  );
