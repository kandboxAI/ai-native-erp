import { http } from "@/utils/http";
import type { ApiResponse, MesPage } from "./mes";
import { deliveryParams } from "./mesDelivery";

export type CockpitFocus =
  | "outstanding"
  | "all"
  | "overdue"
  | "due_soon"
  | "waiting_quality"
  | "unplanned"
  | "released_output"
  | "delivered"
  | "blocked"
  | "no_due"
  | "exceptions"
  | "overdue_exceptions";
export type CockpitQuery = {
  page?: number;
  page_size?: number;
  keyword?: string;
  customer?: string;
  due_from?: string;
  due_to?: string;
  soon_days?: number;
  focus?: CockpitFocus;
};
export type DeliveryRow = {
  id: string;
  org_id: string;
  work_order_no: string;
  status_code: string;
  priority_code: string;
  product_item_no: string;
  product_item_name: string;
  unit_code: string;
  production_order_no?: string;
  project_name?: string;
  customer_no?: string;
  customer_name?: string;
  due_at?: string;
  planned_quantity: string;
  shipped_quantity: string;
  outstanding_quantity: string;
  released_good_quantity: string;
  operation_count: number;
  completed_operation_count: number;
  waiting_quality_count: number;
  unplanned_count: number;
  pending_change_count: number;
  blocked_operation_count: number;
  open_exception_count: number;
  overdue_exception_count: number;
  latest_planned_end_at?: string;
  current_operation_name?: string;
  current_operation_status?: string;
  current_workstation?: string;
  current_planned_end_at?: string;
  delivery_status: "delivered" | "overdue" | "due_soon" | "no_due" | "on_track";
  risk_flags: string[];
};
export type DeliveryCockpit = MesPage<DeliveryRow> & {
  summary: Record<Exclude<CockpitFocus, "all"> | "total", number>;
  due_buckets: { day: string; order_count: number }[];
  generated_at: string;
  soon_days: number;
};
export const getDeliveryCockpit = (params: CockpitQuery = {}) =>
  http.request<ApiResponse<DeliveryCockpit>>(
    "get",
    "/api/mes/delivery-cockpit",
    { params: deliveryParams(params) },
  );
