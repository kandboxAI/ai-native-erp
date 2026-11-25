import { requestApi } from "@/api/client";

export type ProductionTaskStatus =
  | "pending"
  | "dispatched"
  | "in_progress"
  | "paused"
  | "waiting_quality"
  | "completed"
  | "cancelled";

export interface ProductionTaskRow {
  id: string;
  process_id?: string | null;
  equipment_id?: string | null;
  work_order_status_code?: string;
  work_order_no: string;
  operation_no: string;
  operation_name: string;
  product_item_no: string;
  product_item_name: string;
  work_center_name?: string | null;
  workstation_name?: string | null;
  planned_quantity: number;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  unit_name: string;
  status_code: ProductionTaskStatus | string;
  status_label?: string;
  priority_code?: string | null;
  priority_label?: string | null;
  due_at?: string | null;
  updated_at?: string | null;
}

export interface ProductionMaterialRequirement {
  id: string;
  item_no: string;
  item_name: string;
  required_quantity: number;
  consumed_quantity: number;
  unit_name: string;
  is_lot_controlled: boolean;
  is_serial_controlled: boolean;
}

export interface ProductionExecution {
  id: string;
  tracked_in_at: string;
  worker_name?: string | null;
  production_person_name?: string | null;
  workstation_name?: string | null;
  labor_minutes?: number | null;
  machine_minutes?: number | null;
}

export interface ProductionExecutionEvent {
  id: string;
  event_type_code: string;
  event_label?: string;
  note?: string | null;
  actor_name_snapshot?: string | null;
  created_at: string;
}

export interface ProductionTaskDetail extends ProductionTaskRow {
  version_no: number;
  operation_description?: string | null;
  required_skills?: string[];
  is_predecessor_ready: boolean;
  is_quality_required: boolean;
  material_requirements: ProductionMaterialRequirement[];
  current_execution?: ProductionExecution | null;
  events: ProductionExecutionEvent[];
}

export interface ProductionTaskPage {
  items: ProductionTaskRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface OperationProgressItem {
  id: string;
  sequence_no: number;
  operation_no: string;
  operation_name: string;
  planned_quantity: number;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  status_code: string;
  status_label: string;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
  actual_started_at?: string | null;
  actual_finished_at?: string | null;
}

export interface WorkOrderProgressRow {
  id: string;
  work_order_no: string;
  product_item_no: string;
  product_item_name: string;
  unit_name: string;
  planned_quantity: number;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  status_code: string;
  status_label: string;
  priority_code?: string | null;
  priority_label?: string | null;
  due_at?: string | null;
  operation_count: number;
  completed_operation_count: number;
  operation_progress: OperationProgressItem[];
  processing_type_label?: string;
  project_name?: string | null;
  customer_name?: string | null;
  updated_at?: string | null;
}

export interface WorkOrderProgressPage {
  items: WorkOrderProgressRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface WorkOrderDrawingFile {
  id: string;
  file_name: string;
  name: string;
  content_type: string;
  file_kind: string;
  file_size: number;
  width?: number | null;
  height?: number | null;
  url: string;
}

export interface WorkOrderDrawing {
  version_no: number;
  revision_label?: string | null;
  revision_no: number;
  is_legacy: boolean;
  editable: boolean;
  items: WorkOrderDrawingFile[];
}

export interface ProductionReportPayload {
  version_no: number;
  execution_id?: string;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  labor_minutes?: number;
  machine_minutes?: number;
  exception_type_code?: string;
  note?: string;
  idempotency_key: string;
}

export interface ProductionActionPayload {
  version_no: number;
  execution_id?: string;
  note?: string;
}

export const productionTaskStatusLabels: Record<string, string> = {
  pending: "待执行",
  dispatched: "已派工",
  in_progress: "执行中",
  paused: "已暂停",
  waiting_quality: "待检验",
  completed: "已完成",
  cancelled: "已取消",
};

export const productionTaskStatusLabel = (value?: string, fallback?: string) =>
  fallback || productionTaskStatusLabels[value || ""] || value || "未知";

const base = "/api/mes/mobile";

export const listMyProductionTasks = (data: Record<string, any> = {}) =>
  requestApi<ProductionTaskPage>({
    path: `${base}/operation-tasks/mine`,
    data,
  });

export const listWorkOrders = (data: Record<string, any> = {}) =>
  requestApi<WorkOrderProgressPage>({
    path: `${base}/work-orders`,
    data,
  });

export const getWorkOrderDrawings = (workOrderId: string) =>
  requestApi<WorkOrderDrawing>({
    path: `${base}/work-orders/${encodeURIComponent(workOrderId)}/drawings`,
  });

export const getProductionTask = (id: string) =>
  requestApi<ProductionTaskDetail>({
    path: `${base}/operation-tasks/${encodeURIComponent(id)}`,
  });

export const trackInProductionTask = (
  id: string,
  data: ProductionActionPayload,
) =>
  requestApi<ProductionTaskDetail>({
    method: "POST",
    path: `${base}/operation-tasks/${encodeURIComponent(id)}/track-in`,
    data,
  });

export const holdProductionTask = (
  id: string,
  data: ProductionActionPayload,
) =>
  requestApi<ProductionTaskDetail>({
    method: "POST",
    path: `${base}/operation-tasks/${encodeURIComponent(id)}/hold`,
    data,
  });

export const releaseProductionTask = (
  id: string,
  data: ProductionActionPayload,
) =>
  requestApi<ProductionTaskDetail>({
    method: "POST",
    path: `${base}/operation-tasks/${encodeURIComponent(id)}/release`,
    data,
  });

export const submitProductionReport = (
  id: string,
  data: ProductionReportPayload,
) =>
  requestApi<ProductionTaskDetail>({
    method: "POST",
    path: `${base}/operation-tasks/${encodeURIComponent(id)}/production-report`,
    data,
  });

export const trackOutProductionTask = (
  id: string,
  data: ProductionActionPayload,
) =>
  requestApi<ProductionTaskDetail>({
    method: "POST",
    path: `${base}/operation-tasks/${encodeURIComponent(id)}/track-out`,
    data,
  });
