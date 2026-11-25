import { http } from "@/utils/http/index";

export type ApiResponse<T> = { code: number; message: string; data: T };
export type MesPage<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type MesProcessDisposition = "keep" | "reinspect" | "rework";
export type MesProcessChange = {
  id: string;
  status_code: string;
  previous_name_snapshot: string;
  new_name_snapshot: string;
  remaining_quantity_snapshot: string;
  disposition_quantity_snapshot: string;
  disposition_code: MesProcessDisposition;
  reason: string;
  disposition_note?: string;
  repair_order_id?: string;
};
export type MesProcessChangeOverview = {
  org_id: string;
  version_no: number;
  status_code: string;
  is_pending: boolean;
  operations: { id: string; name: string; operation_no: string; remaining: string; good: string }[];
  changes: MesProcessChange[];
};
const processChangeUrl = (id: string) => `/api/mes/work-orders/${id}/process-changes`;
export const getMesProcessChanges = (id: string) =>
  http.request<ApiResponse<MesProcessChangeOverview>>("get", processChangeUrl(id));
export const submitMesProcessChange = (id: string, data: {
  version_no: number;
  operation_id: string;
  new_process_id: string;
  new_equipment_id?: string;
  disposition_code: MesProcessDisposition;
  reason: string;
}) => http.request<ApiResponse<MesProcessChange>>("post", processChangeUrl(id), { data });
export const actMesProcessChange = (
  id: string,
  changeId: string,
  action: "apply" | "pass" | "rework" | "arrange" | "cancel",
  note: string,
) => http.request<ApiResponse<MesProcessChange>>(
  "post", `${processChangeUrl(id)}/${changeId}/${action}`, { data: { note } },
);

export type MesOperationProgress = {
  is_imported_snapshot?: boolean;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
  actual_started_at?: string | null;
  actual_finished_at?: string | null;
  plan_source_key?: string | null;
  standard_minutes_per_unit?: number | null;
  planned_duration_minutes?: number | null;
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
};

export type MesWorkOrder = {
  is_process_change_pending?: boolean;
  display_status_key?: string;
  processing_type_code?: "in_house" | "outsourced" | "purchased";
  material_name_snapshot?: string | null;
  heat_treatment_snapshot?: string | null;
  surface_treatment_snapshot?: string | null;
  process_requirement_snapshot?: string | null;
  outsourced_due_at?: string | null;
  processing_type_label?: string;
  id: string;
  org_id?: string;
  production_order_id?: string;
  production_order_no?: string;
  project_name?: string;
  customer_id?: string | null;
  customer_no?: string;
  customer_name?: string;
  order_type_code?: string;
  source_work_order_id?: string | null;
  version_no: number;
  created_at?: string;
  creator_name?: string;
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
  priority_code: string;
  priority_label: string;
  due_at?: string | null;
  operation_count: number;
  completed_operation_count: number;
  operation_progress?: MesOperationProgress[];
  updated_at?: string | null;
};

export type MesTask = {
  id: string;
  work_order_id: string;
  work_order_status_code?: string;
  org_id: string;
  sequence_no: number;
  assigned_user_id?: string | null;
  assigned_production_person_id?: string | null;
  assigned_production_person_name?: string | null;
  assigned_production_person_no?: string | null;
  schedule_plan_id?: string | null;
  scheduled_production_person_name?: string | null;
  process_id?: string | null;
  equipment_id?: string | null;
  project_name?: string | null;
  assigned_user_name?: string | null;
  actual_started_at?: string | null;
  actual_finished_at?: string | null;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
  work_order_no: string;
  operation_no: string;
  operation_name: string;
  operation_description?: string | null;
  product_item_no: string;
  product_item_name: string;
  work_center_name?: string | null;
  workstation_name?: string | null;
  planned_quantity: number;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  unit_name: string;
  status_code: string;
  status_label: string;
  priority_code?: string | null;
  priority_label?: string | null;
  due_at?: string | null;
  updated_at?: string | null;
  version_no?: number;
};

export type MesTaskDetail = MesTask & {
  schedule_context?: {
    plan_id: string;
    plan_no: string;
    production_phase_id: string;
    production_phase_code: "first" | "remaining";
    phase_status_code: string;
    first_article_status_code: string;
    phase_label: string;
    planned_quantity: number;
    reported_quantity: number;
    remaining_quantity: number;
    production_person_id: string | null;
    production_person_name?: string | null;
    production_person_no: string | null;
    can_start: boolean;
    reason: string;
    missing_readiness: string[];
    is_rework: boolean;
    execution_kind_code: string;
    load_minutes: number;
    unload_minutes: number;
    planned_start_at: string | null;
  } | null;
  version_no: number;
  operation_description?: string | null;
  required_skills: string[];
  is_predecessor_ready: boolean;
  is_quality_required: boolean;
  material_requirements: Array<{
    id: string;
    item_no: string;
    item_name: string;
    required_quantity: number;
    consumed_quantity: number;
    unit_name: string;
    is_lot_controlled: boolean;
    is_serial_controlled: boolean;
  }>;
  current_execution?: {
    production_phase_id?: string | null;
    production_person_id?: string | null;
    production_person_name?: string | null;
    segment_type_code?: string | null;
    id: string;
    tracked_in_at: string;
    worker_name?: string | null;
    workstation_name?: string | null;
    labor_minutes?: number | null;
    machine_minutes?: number | null;
  } | null;
  events: Array<{
    id: string;
    event_type_code: string;
    event_label?: string | null;
    note?: string | null;
    actor_name_snapshot?: string | null;
    created_at: string;
  }>;
  executions: Array<{
    id: string;
    tracked_in_at: string;
    tracked_out_at?: string | null;
    status_code: string;
    worker_name?: string | null;
    production_person_name?: string | null;
    workstation_name?: string | null;
    labor_minutes?: number | null;
    machine_minutes?: number | null;
  }>;
};

export type MesReport = {
  reporter_name?: string | null;
  note?: string | null;
  id: string;
  report_no: string;
  work_order_no: string;
  operation_no: string;
  operation_name: string;
  product_item_no: string;
  product_item_name: string;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  labor_minutes?: number | null;
  machine_minutes?: number | null;
  exception_type_code?: string | null;
  status_code: string;
  reported_at: string;
  source_code: string;
  created_by: string;
  operation_id?: string;
  work_order_id?: string;
};

export type MesReportBody = {
  version_no: number;
  execution_id?: string;
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  labor_minutes?: number;
  machine_minutes?: number;
  exception_type_code?: string;
  note?: string;
  attachment_ids: string[];
  idempotency_key: string;
};
export const getMesReportingTasks = (params: MesListParams = {}) =>
  http.request<ApiResponse<MesPage<MesTask>>>(
    "get",
    "/api/mes/reporting/tasks",
    { params: listQueryParams(params) },
  );
export const getMesReportingTask = (id: string) =>
  http.request<ApiResponse<MesTaskDetail>>(
    "get",
    `/api/mes/reporting/tasks/${id}`,
  );
export const actMesReportingTask = (
  id: string,
  action: "track-in" | "hold" | "release" | "track-out" | "stage",
  data: {
    version_no: number;
    execution_id?: string;
    note?: string;
    production_person_id?: string;
    production_phase_code?: "first" | "remaining";
    segment_type_code?:
      "load" | "run" | "unload" | "manual" | "external_return";
  },
) =>
  http.request<ApiResponse<MesTaskDetail>>(
    "post",
    `/api/mes/reporting/tasks/${id}/${action}`,
    { data },
  );
export const submitMesWebReport = (id: string, data: MesReportBody) =>
  http.request<ApiResponse<MesTaskDetail>>(
    "post",
    `/api/mes/reporting/tasks/${id}/reports/submit`,
    { data },
  );
export type MesReportDetail = Pick<
  MesReport,
  | "id"
  | "report_no"
  | "status_code"
  | "good_quantity"
  | "scrap_quantity"
  | "rework_quantity"
  | "labor_minutes"
  | "machine_minutes"
> & {
  org_id: string;
  work_order_id: string;
  work_order_no: string;
  operation_id: string;
  operation_name: string;
  unit_name: string;
  note?: string;
  attachments: import("@/api/systemFile").FileItem[];
};
export const getMesReportDetail = (id: string) =>
  http.request<ApiResponse<MesReportDetail>>(
    "get",
    `/api/mes/production-reports/${id}`,
  );
export type MesReportChangeBody = {
  change_type_code: "replace" | "reverse";
  good_quantity: number;
  scrap_quantity: number;
  rework_quantity: number;
  labor_minutes?: number | null;
  machine_minutes?: number | null;
  reason: string;
  idempotency_key: string;
  starter_choices?: Record<string, string[]>;
};
export type MesReportChange = Omit<
  MesReportChangeBody,
  "idempotency_key" | "starter_choices"
> & {
  id: string;
  report_id: string;
  report_no: string;
  org_id: string;
  status_code: string;
  replacement_report_id?: string;
  wf_instance_id?: string;
  created_at: string;
  created_by: string;
};
export const createMesReportChange = (id: string, data: MesReportChangeBody) =>
  http.request<ApiResponse<MesReportChange>>(
    "post",
    `/api/mes/production-reports/${id}/changes`,
    { data },
  );
export const getMesReportChanges = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  status_code?: string;
  report_id?: string;
}) =>
  http.request<ApiResponse<MesPage<MesReportChange>>>(
    "get",
    "/api/mes/report-changes",
    { params: listQueryParams(params) },
  );
export const withdrawMesReportChange = (id: string) =>
  http.request<ApiResponse<{ id: string; status_code: string }>>(
    "post",
    `/api/mes/report-changes/${id}/withdraw`,
  );

export type MesListParams = {
  processing_type_code?: string;
  operation_id?: string;
  work_order_id?: string;
  page?: number;
  page_size?: number;
  keyword?: string;
  status_code?: string;
  priority_code?: string;
  overdue_only?: boolean;
  repair_source_only?: boolean;
  production_order_id?: string;
  customer?: string;
  creator?: string;
  order_type_code?: string;
  created_from?: string;
  created_to?: string;
  due_from?: string;
  due_to?: string;
  configuration?: string;
};

function listQueryParams<T extends object>(params: T): Partial<T> {
  // 未选或已清空的筛选项应省略，避免空值触发后端日期、UUID 和枚举校验。
  return Object.fromEntries(
    Object.entries(params).filter(
      ([, value]) =>
        value != null && !(typeof value === "string" && value.trim() === ""),
    ),
  ) as Partial<T>;
}

export function getMesWorkOrders(params: MesListParams = {}) {
  return http.request<ApiResponse<MesPage<MesWorkOrder>>>(
    "get",
    "/api/mes/work-orders",
    { params: listQueryParams(params) },
  );
}

export type MesScheduleParams = MesListParams & {
  group_by_work_order?: boolean;
  work_order_id?: string;
  work_center?: string;
  scheduled?: boolean;
  start_date?: string;
  end_date?: string;
  product_keyword?: string;
  equipment_keyword?: string;
  equipment_id?: string;
  process_id?: string;
  org_id?: string;
  workstation?: string;
  work_center_exact?: string;
  unassigned_only?: boolean;
  unfinished_only?: boolean;
  unstarted_only?: boolean;
  due_from?: string;
  due_to?: string;
  window_start?: string;
  window_end?: string;
};
export const getMesSchedules = (params: MesScheduleParams = {}) =>
  http.request<ApiResponse<MesPage<MesTask>>>("get", "/api/mes/schedules", {
    params: listQueryParams(params),
  });
export type MesScheduleChange = {
  operation_id: string;
  version_no: number;
  planned_start_at: string | null;
  planned_end_at: string | null;
  equipment_id?: string | null;
};
export const updateMesSchedules = (
  operations: MesScheduleChange[],
  note: string,
) =>
  http.request<ApiResponse<{ updated: number }>>("put", "/api/mes/schedules", {
    data: { operations, note },
  });

export type MesScheduleResource = {
  resource_key: string;
  org_id: string;
  equipment_id?: string | null;
  equipment_no: string;
  equipment_name: string;
  process_id?: string | null;
  process_name?: string | null;
  is_active: boolean;
  work_center_name?: string | null;
  workstation_name?: string | null;
  kind: "equipment" | "station" | "unassigned";
  task_count: number;
  scheduled_count: number;
  planned_minutes: number;
  daily_load: { day: string; task_count: number; planned_minutes: number }[];
};
export const getMesScheduleResources = (params: MesScheduleParams = {}) =>
  http.request<
    ApiResponse<
      MesPage<MesScheduleResource> & {
        window_start: string;
        window_end: string;
      }
    >
  >("get", "/api/mes/schedule-resources", { params: listQueryParams(params) });

export type MesProcessTemplate = {
  product_option?: MesOption;
  is_product_active?: boolean;
  id?: string;
  org_id: string;
  template_no: string;
  template_name: string;
  product_item_id?: string | null;
  version_no?: number;
  is_active: boolean;
  operations: MesOrderDefinition["operations"];
};
export const getMesProcessTemplates = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  org_id?: string;
  product_item_id?: string;
  is_active?: boolean;
}) =>
  http.request<ApiResponse<MesPage<MesProcessTemplate>>>(
    "get",
    "/api/mes/process-templates",
    {
      params: listQueryParams(params),
    },
  );
export const saveMesProcessTemplate = (data: MesProcessTemplate) =>
  http.request<ApiResponse<{ id: string; version_no: number }>>(
    data.id ? "put" : "post",
    data.id
      ? `/api/mes/process-templates/${data.id}`
      : "/api/mes/process-templates",
    { data },
  );
export const getMesProcessTemplateOptions = (
  params: Parameters<typeof getMesProcessTemplates>[0] & {
    action?: "create" | "manage";
  },
) =>
  http.request<ApiResponse<MesPage<MesProcessTemplate>>>(
    "get",
    "/api/mes/process-template-options",
    { params: listQueryParams(params) },
  );

export type MesDrawings = {
  version_no: number;
  revision_no: number;
  is_legacy?: boolean;
  revision_label?: string;
  editable: boolean;
  items: import("@/api/systemFile").FileItem[];
};
export const getMesDrawings = (id: string) =>
  http.request<ApiResponse<MesDrawings>>(
    "get",
    `/api/mes/work-orders/${id}/drawings`,
  );
export const saveMesDrawings = (
  id: string,
  data: {
    version_no: number;
    revision_label?: string;
    change_note: string;
    attachment_ids: string[];
  },
) =>
  http.request<ApiResponse<{ id: string; version_no: number }>>(
    "put",
    `/api/mes/work-orders/${id}/drawings`,
    { data },
  );
export type MesDrawingRevision = {
  id: string;
  revision_no: number;
  revision_label?: string;
  change_note: string;
  created_at: string;
  created_by_name: string;
  items: import("@/api/systemFile").FileItem[];
};
export const getMesDrawingHistory = (id: string, page = 1) =>
  http.request<ApiResponse<MesPage<MesDrawingRevision>>>(
    "get",
    `/api/mes/work-orders/${id}/drawings/history`,
    {
      params: { page, page_size: 5 },
    },
  );

export type MesRework = {
  id: string;
  report_no: string;
  work_order_id: string;
  work_order_no: string;
  operation_name: string;
  product_item_name: string;
  rework_quantity: number;
  allocated_quantity: number;
  pending_quantity: number;
  unit_name: string;
  reported_at: string;
  repairs: {
    operation_count?: number;
    id: string;
    work_order_no: string;
    planned_quantity: number;
    good_quantity: number;
    status_code: string;
  }[];
};
export const getMesReworks = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  allocation?: string;
}) =>
  http.request<ApiResponse<MesPage<MesRework>>>("get", "/api/mes/reworks", {
    params: listQueryParams(params),
  });
export async function getMesScheduleOrgOptions(keyword = "") {
  const result = await http.request<
    ApiResponse<{ id: string; org_name: string }[]>
  >("get", "/api/mes/schedule-options/organizations", { params: { keyword } });
  return result.data.map((row) => ({ value: row.id, label: row.org_name }));
}

export type MesProductDrawing = {
  name: string;
  kind: "pdf" | "model";
  size: number;
  raw?: File;
  id?: string;
  pending?: boolean;
};
function withoutDrawingDraft<T extends object>(data: T) {
  if (!("drawing_files" in data)) return data;
  const { drawing_files: _drawingFiles, ...body } = data;
  return body;
}
export function createMesWorkOrder(data: {
  drawing_attachment_ids?: string[];
  drawing_revision_label?: string;
  processing_type_code?: "in_house" | "outsourced" | "purchased";
  org_id?: string;
  work_order_no: string;
  product_item_id: string;
  planned_quantity: number;
  priority_code: string;
  due_at?: string | null;
  publish?: boolean;
  source_work_order_id?: string | null;
  rework_report_id?: string;
  process_template_id?: string | null;
  process_template_version_snapshot?: number | null;
  note?: string;
  operations: Array<{
    standard_minutes_per_unit?: number | null;
    operation_no: string;
    operation_name: string;
    process_id?: string | null;
    equipment_id?: string | null;
    requirement_id?: string | null;
    planned_quantity?: number;
    work_center_name?: string;
    workstation_name?: string;
    assigned_user_id?: string;
    assigned_user_name?: string;
    is_quality_required?: boolean;
    operation_description?: string;
  }>;
}) {
  return http.request<ApiResponse<{ id: string; work_order_id: string }>>(
    "post",
    "/api/mes/work-orders",
    {
      data: withoutDrawingDraft(data),
    },
  );
}

export function getMesWorkOrder(id: string) {
  return http.request<
    ApiResponse<
      MesWorkOrder & {
        operations: MesTask[];
        note?: string;
        can_edit_configuration: boolean;
        source_work_order_no?: string;
        events: Array<{
          id: string;
          event_type_code: string;
          from_status_code?: string;
          to_status_code: string;
          note?: string;
          version_no: number;
          created_at: string;
        }>;
      }
    >
  >("get", `/api/mes/work-orders/${id}`);
}

export type MesOrderDefinition = Parameters<typeof createMesWorkOrder>[0] & {
  drawing_files?: MesProductDrawing[];
  id?: string;
  version_no?: number;
  product_label?: string;
  unit_name?: string;
  can_edit_configuration?: boolean;
  status_code?: string;
};
export type MesProductionOrder = {
  source_product_count_snapshot?: number | null;
  is_import_incomplete?: boolean;
  display_status_key?: string;
  status_label?: string;
  id: string;
  org_id: string;
  version_no: number;
  note?: string;
  production_order_no: string;
  project_name: string;
  customer_id?: string | null;
  customer_no?: string;
  customer_name?: string;
  product_count: number;
  configured_count: number;
  released_count: number;
  completed_count: number;
  created_at: string;
  orders: MesWorkOrder[];
};
export function getMesProductionOrders(params: MesListParams) {
  return http.request<ApiResponse<MesPage<MesProductionOrder>>>(
    "get",
    "/api/mes/production-orders",
    { params: listQueryParams(params) },
  );
}
export function createMesProductionOrder(data: {
  org_id: string;
  production_order_no: string;
  project_name: string;
  customer_id?: string | null;
  customer_no?: string;
  customer_name?: string;
  note?: string;
  products: MesOrderDefinition[];
}) {
  return http.request<ApiResponse<{ id: string; work_order_ids: string[] }>>(
    "post",
    "/api/mes/production-orders",
    { data: { ...data, products: data.products.map(withoutDrawingDraft) } },
  );
}
export function getMesOrderDefinition(id: string) {
  return http.request<ApiResponse<MesOrderDefinition>>(
    "get",
    `/api/mes/work-orders/${id}/definition`,
  );
}

export function placeMesProductionOrder(
  id: string,
  data: {
    version_no: number;
    orders: Array<{ id: string; version_no: number }>;
  },
) {
  return http.request<
    ApiResponse<{ id: string; version_no: number; placed_count: number }>
  >("post", `/api/mes/production-orders/${id}/place`, { data });
}

export function updateMesProductionOrder(
  id: string,
  data: Parameters<typeof createMesProductionOrder>[0] & { version_no: number },
) {
  return http.request<ApiResponse<{ id: string }>>(
    "put",
    `/api/mes/production-orders/${id}`,
    { data: { ...data, products: data.products.map(withoutDrawingDraft) } },
  );
}
export function updateMesWorkOrder(id: string, data: MesOrderDefinition) {
  return http.request<ApiResponse<{ work_order_id: string }>>(
    "put",
    `/api/mes/work-orders/${id}`,
    { data: withoutDrawingDraft(data) },
  );
}
export type MesOrderAction =
  | "place"
  | "publish"
  | "withdraw"
  | "pause"
  | "resume"
  | "complete"
  | "cancel"
  | "delete";
export function commandMesWorkOrder(
  id: string,
  action: MesOrderAction,
  version_no: number,
  note?: string,
) {
  return http.request<
    ApiResponse<{ id: string; version_no: number; status_code: string }>
  >("post", `/api/mes/work-orders/${id}/actions/${action}`, {
    data: { version_no, note },
  });
}

export function getMesTasks(params: MesListParams = {}) {
  return http.request<ApiResponse<MesPage<MesTask>>>(
    "get",
    "/api/mes/operation-tasks",
    { params: listQueryParams(params) },
  );
}

export function getMesTask(id: string) {
  return http.request<ApiResponse<MesTaskDetail>>(
    "get",
    `/api/mes/operation-tasks/${id}`,
  );
}

export function dispatchMesTask(
  id: string,
  data: { version_no: number; production_person_id: string; note?: string },
) {
  return http.request<ApiResponse<MesTaskDetail>>(
    "post",
    `/api/mes/operation-tasks/${id}/dispatch`,
    { data },
  );
}

export function getMesReports(params: MesListParams = {}) {
  return http.request<ApiResponse<MesPage<MesReport>>>(
    "get",
    "/api/mes/production-reports",
    { params: listQueryParams(params) },
  );
}

export type MesOption = { value: string; label: string; unit?: string };

export async function getMesDispatchPeople(
  taskId: string,
  keyword = "",
): Promise<MesOption[]> {
  const res = await http.request<
    ApiResponse<{ id: string; person_no: string; full_name: string; has_account: boolean }[]>
  >("get", `/api/mes/operation-tasks/${taskId}/assignees`, { params: { keyword } });
  return res.data.map((person) => ({
    value: person.id,
    label: `${person.full_name} · ${person.person_no} · ${person.has_account ? "已关联账号" : "需代报工"}`,
  }));
}

export async function getMesProductOptions(
  keyword = "",
  forTemplate = false,
): Promise<MesOption[]> {
  const res = await http.request<
    ApiResponse<
      Array<{
        id: string;
        item_no: string;
        item_name: string;
        unit_code: string;
        specification?: string;
      }>
    >
  >(
    "get",
    forTemplate
      ? "/api/mes/process-template-options/products"
      : "/api/mes/work-order-options/products",
    { params: { keyword } },
  );
  return res.data.map((item) => ({
    value: item.id,
    label: `${item.item_no} · ${item.item_name}${item.specification ? ` / ${item.specification}` : ""}`,
    unit: item.unit_code,
  }));
}

export async function getMesOrgOptions(
  keyword = "",
  forTemplate = false,
): Promise<MesOption[]> {
  const res = await http.request<
    ApiResponse<Array<{ id: string; org_name: string }>>
  >(
    "get",
    forTemplate
      ? "/api/mes/process-template-options/organizations"
      : "/api/mes/work-order-options/organizations",
    {
      params: { keyword },
    },
  );
  return res.data.map((item) => ({ value: item.id, label: item.org_name }));
}

export async function getMesAssigneeOptions(
  keyword = "",
  orgId?: string,
  forEdit = false,
): Promise<MesOption[]> {
  const res = await http.request<
    ApiResponse<Array<{ id: string; display_name: string }>>
  >(
    "get",
    "/api/mes/work-order-options/assignees",
    {
      params: {
        keyword,
        org_id: orgId,
        for_edit: forEdit,
      },
    },
  );
  return res.data.map((item) => ({ value: item.id, label: item.display_name }));
}
