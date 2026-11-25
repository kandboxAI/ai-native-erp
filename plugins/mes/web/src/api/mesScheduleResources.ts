import { http } from "@/utils/http/index";
import type { ApiResponse, MesPage, MesOption } from "./mes";
export type ResourceRow = {
  id: string;
  org_id: string;
  version_no: number;
  is_active: boolean;
  person_no?: string;
  full_name?: string;
  job_title_snapshot?: string | null;
  production_person_id?: string | null;
  equipment_id?: string | null;
  calendar_name?: string;
  timezone_name?: string;
  valid_from?: string;
  valid_to?: string | null;
  qualifications?: Qualification[];
  periods?: CalendarPeriod[];
  exceptions?: CalendarException[];
};
export type Qualification = {
  id: string;
  version_no: number;
  process_id: string;
  process_name: string;
  valid_from: string;
  valid_to: string | null;
  is_active: boolean;
};
export type CalendarPeriod = {
  weekday_no: number;
  period_type_code: "work" | "lunch";
  start_minute_of_day: number;
  end_minute_of_day: number;
};
export type CalendarException = {
  id: string;
  version_no: number;
  start_at: string;
  end_at: string;
  exception_type_code: "extra_available" | "unavailable";
  reason: string;
  is_active: boolean;
};
export type ResourceOptions = {
  people: Array<{ id: string; label: string }>;
  equipment: Array<{ id: string; label: string }>;
};
const base = "/api/mes/schedule-resources";
export async function resourceOrganizations(
  keyword = "",
): Promise<MesOption[]> {
  const r = await http.request<
    ApiResponse<Array<{ id: string; org_name: string }>>
  >("get", `${base}/organizations`, { params: { keyword } });
  return r.data.map((row) => ({ value: row.id, label: row.org_name }));
}
export async function resourceProcesses(
  orgId: string,
  keyword = "",
): Promise<MesOption[]> {
  return (
    await http.request<ApiResponse<MesOption[]>>("get", `${base}/processes`, {
      params: { org_id: orgId, keyword },
    })
  ).data;
}
export async function resourceOptions(orgId: string): Promise<ResourceOptions> {
  return (
    await http.request<ApiResponse<ResourceOptions>>("get", `${base}/options`, {
      params: { org_id: orgId },
    })
  ).data;
}
export async function resourcePage(
  kind: "people" | "calendars",
  params: Record<string, unknown>,
) {
  return (
    await http.request<ApiResponse<MesPage<ResourceRow>>>(
      "get",
      `${base}/${kind}`,
      { params },
    )
  ).data;
}
export async function resourceDetail(kind: "people" | "calendars", id: string) {
  return (
    await http.request<ApiResponse<ResourceRow>>("get", `${base}/${kind}/${id}`)
  ).data;
}
export async function saveResource(path: string, body: object, update = false) {
  return (
    await http.request<ApiResponse<ResourceRow>>(
      update ? "put" : "post",
      `${base}/${path}`,
      { data: body },
    )
  ).data;
}
