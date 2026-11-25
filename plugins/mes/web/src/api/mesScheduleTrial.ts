import { http } from "@/utils/http/index";
import type { ApiResponse } from "./mes";

export type TrialScope = {
  org_id: string;
  work_order_ids: string[];
  start_at: string;
  end_at: string;
};
export type TrialOperation = {
  id: string;
  version_no: number;
  operation_name: string;
  process_id: string | null;
  standard_minutes_per_unit: number | null;
  is_quality_required: boolean;
  status_code: string;
  execution_kind_code?: TrialOperationRule["kind_key"] | null;
  is_equipment_required_snapshot?: boolean | null;
};
export type TrialOrder = {
  id: string;
  version_no: number;
  work_order_no: string;
  quantity: string;
  unit_code: string;
  due_at: string | null;
  operations: TrialOperation[];
  schedule_mode_code?: "full" | "remaining";
  production_order_id?: string | null;
  is_project_complete?: boolean;
};
export type TrialPrepared = {
  snapshot_key: string;
  orders: TrialOrder[];
  processes: Array<{
    id: string;
    process_name: string;
    execution_kind_code?: string | null;
    is_equipment_required?: boolean | null;
  }>;
  issues: string[];
  settings?: Array<{
    operation_id: string;
    source_version_no_snapshot: number;
    execution_kind_code: TrialOperationRule["kind_key"];
    setup_minutes: number;
    load_minutes: number;
    unload_minutes: number;
    can_supervise_two_machines: boolean;
    can_run_during_lunch: boolean;
    is_timing_confirmed: boolean;
    inspection_process_id?: string | null;
    inspection_minutes_per_piece?: number | null;
    is_inspection_equipment_required?: boolean;
    external_first_return_at?: string | null;
    external_remaining_return_at?: string | null;
  }>;
  readiness?: Array<{
    work_order_id: string;
    readiness_kind_code: string;
    expected_at: string;
    confirmed_at?: string | null;
  }>;
  inspection_settings?: Array<{
    inspection_mode_code: "separate" | "last_operation";
    process_id: string | null;
    is_equipment_required: boolean;
    minutes_per_piece: number | null;
  }>;
};
export type TrialOperationRule = {
  operation_id: string;
  version_no: number;
  kind_key:
    "machine" | "manual" | "inspection" | "machine_inspection" | "external";
  setup_minutes: number;
  load_minutes: number;
  unload_minutes: number;
  supervision_key: "exclusive" | "two_machines";
  is_lunch_auto_allowed: boolean;
  is_timing_confirmed: boolean;
  inspection?: {
    process_id: string;
    is_equipment_required: boolean;
    minutes_per_piece: number;
  } | null;
  external_first_return_at?: string | null;
  external_remaining_return_at?: string | null;
};
export type TrialSolve = TrialScope & {
  snapshot_key: string;
  operation_rules: TrialOperationRule[];
  order_rules: Array<{
    work_order_id: string;
    version_no: number;
    ready_at: string;
    is_readiness_confirmed: boolean;
    delivery_mode_key?: "whole_project" | "individual";
    shipping_preparation_minutes?: number | null;
    shipping_windows?: Array<{ start_at: string; end_at: string }>;
  }>;
  inspection: {
    mode_key: "separate" | "last_operation";
    process_id: string | null;
    is_equipment_required: boolean;
    minutes_per_piece: number | null;
  };
  is_regular_calendar_confirmed: boolean;
  time_limit_seconds: number;
};
export type TrialResult = {
  plan_id?: string;
  plan_no?: string;
  plan_version_no?: number;
  status_code: string;
  issues: string[];
  warnings?: string[];
  captured_at?: string;
  segments: Array<{
    order_id: string;
    work_order_no: string;
    operation_id: string;
    operation_name: string;
    batch_key: "first" | "remaining";
    piece_no: number;
    kind_key: string;
    start_at: string;
    end_at: string;
    person_no: string | null;
    equipment_name: string | null;
  }>;
  completions: Array<{
    work_order_id: string;
    work_order_no: string;
    first_article_release_at: string;
    inspection_release_at: string;
    due_at: string;
    shipping_complete?: boolean;
    shipping_release_at?: string | null;
  }>;
};

export async function prepareScheduleTrial(body: TrialScope) {
  const response = await http.request<ApiResponse<TrialPrepared>>(
    "post",
    "/api/mes/schedule-trials/prepare",
    { data: body },
  );
  return response.data;
}
export async function solveScheduleTrial(body: TrialSolve) {
  const response = await http.request<ApiResponse<TrialResult>>(
    "post",
    "/api/mes/schedule-trials/solve",
    { data: body, timeout: 120000 },
  );
  return response.data;
}
