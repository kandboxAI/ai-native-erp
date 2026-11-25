import { http } from "@/utils/http/index";
import type { ApiResponse, MesPage } from "./mes";
import type { TrialSolve, TrialResult } from "./mesScheduleTrial";
export type ReadinessInput = {
  work_order_id: string;
  readiness_kind_code: "material" | "drawing" | "program" | "tool";
  expected_at: string;
  is_confirmed: boolean;
};
export type SchedulePlan = {
  id: string;
  org_id: string;
  plan_no: string;
  plan_name: string;
  version_no: number;
  status_code: string;
  solver_result_code?: string;
  window_start_at: string;
  window_end_at: string;
  created_at: string;
  confirmed_at?: string | null;
};
export type PlanSegment = {
  id: string;
  plan_operation_id: string;
  work_order_no: string;
  operation_name: string;
  production_phase_code: string;
  segment_type_code: string;
  planned_start_at: string;
  planned_end_at: string;
  production_person_id: string | null;
  person_no_snapshot: string | null;
  production_person_name?: string | null;
  equipment_id: string | null;
  equipment_name_snapshot: string | null;
  equipment_name?: string | null;
  person_capacity_units_snapshot: number;
  is_independent_inspection: boolean;
};
export type PlanDetail = SchedulePlan & {
  risk_issues?: string[];
  readiness: Array<
    ReadinessInput & {
      id: string;
      version_no: number;
      confirmed_at?: string | null;
    }
  >;
  result: TrialResult;
  operations: Array<{
    id: string;
    work_order_id: string;
    work_order_no: string;
    operation_name: string;
    is_scheduled: boolean;
    planned_start_at: string | null;
    planned_end_at: string | null;
  }>;
  segments: PlanSegment[];
};
const base = "/api/mes/schedule-plans";
export async function createSchedulePlan(
  body: TrialSolve & { plan_name: string; readiness: ReadinessInput[] },
) {
  return (
    await http.request<ApiResponse<TrialResult>>("post", base, {
      data: body,
      timeout: 120000,
    })
  ).data;
}
export async function schedulePlans(params: Record<string, unknown>) {
  return (
    await http.request<ApiResponse<MesPage<SchedulePlan>>>("get", base, {
      params,
    })
  ).data;
}
export async function schedulePlan(id: string) {
  return (await http.request<ApiResponse<PlanDetail>>("get", `${base}/${id}`))
    .data;
}
export async function savePlanReadiness(
  id: string,
  readiness: Array<ReadinessInput & { version_no: number }>,
) {
  return (
    await http.request<ApiResponse<{ updated: number }>>(
      "put",
      `${base}/${id}/readiness`,
      { data: { readiness } },
    )
  ).data;
}
export async function schedulePlanCommand(
  id: string,
  action: "apply" | "cancel",
  version: number,
  note: string,
) {
  return (
    await http.request<ApiResponse<SchedulePlan>>(
      "post",
      `${base}/${id}/${action}`,
      { data: { version_no: version, note } },
    )
  ).data;
}
