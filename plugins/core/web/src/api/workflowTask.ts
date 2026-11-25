import { http } from "@/utils/http";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type WorkflowTaskBusinessTypeOption = { value: string; label: string };
export const listWorkflowTaskBusinessTypes = () =>
  http.request<ApiResponse<WorkflowTaskBusinessTypeOption[]>>(
    "get",
    "/api/workflow_task/business-types"
  );

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/** 待办（wf_task）；候选人来自 wf_task_candidate */
export type WorkflowTaskRow = {
  business_avatar_url?: string | null;
  id: string;
  instance_id: string;
  business_type_code: string;
  business_id: string;
  task_key: string;
  task_name: string;
  assignee_type_code: string;
  assignee_value: string | null;
  approval_mode_code: "single" | "any" | "all";
  approved_count: number;
  required_count: number;
  /** 字典 wf_task_status：pending / completed / cancelled */
  status_code: string;
  /** 字典 wf_task_outcome：approved / rejected / returned */
  outcome_code?: string | null;
  arrived_at: string | null;
  completed_at?: string | null;
  instance_status_code: string;
  business_summary: string | null;
  candidate_names?: string[];
  ai_analysis?: string | null;
  ai_analysis_status_code?: string;
  ai_analysis_generated_at?: string | null;
  can_direct_approve?: boolean;
};

export type WorkflowTaskListParams = {
  page?: number;
  page_size?: number;
  /** pending=待我办理，completed=我已办理，空=全部 */
  status_code?: string;
  business_type_code?: string;
  business_id?: string;
};

export type WorkflowCcRow = {
  id: string;
  instance_id: string;
  task_id: string | null;
  task_key: string | null;
  task_name: string | null;
  cc_type_code?: string;
  business_type_code: string;
  business_id: string;
  business_summary: string | null;
  /** 字典 wf_read_status */
  status_code: "unread" | "read" | string;
  created_at: string | null;
  read_at: string | null;
};

export type WorkflowCcListParams = {
  page?: number;
  page_size?: number;
  status_code?: string;
  business_type_code?: string;
  business_id?: string;
};

export type WorkflowBusinessDetailField = {
  label: string;
  value: string | null;
  file_id?: string | null;
  type?: "text" | "avatar" | "image" | "markdown" | "markdown_diff" | null;
  /** markdown_diff 的旧正文；null 表示缺失，空字符串表示明确的新建文档。 */
  old_value?: string | null;
  old_label?: string;
  unavailable_reason?: string;
};

export type WorkflowBusinessDetailColumn = {
  prop: string;
  label: string;
};

export type WorkflowBusinessDetailTable = {
  title: string;
  columns: WorkflowBusinessDetailColumn[];
  rows: Record<string, unknown>[];
};

export type WorkflowBusinessContractPreview = {
  title?: string;
  contract_type?: string;
  mode?: "pdf" | "file" | "external" | "none";
  preview_url?: string | null;
  open_url?: string | null;
  attachments?: { name: string; url: string }[];
};

export type WorkflowBusinessDetail = {
  business_page_query?: Record<string, string>;
  fields: WorkflowBusinessDetailField[];
  tables: WorkflowBusinessDetailTable[];
  contract?: WorkflowBusinessContractPreview | null;
};

export type WorkflowTaskDetail = WorkflowTaskRow & {
  comment: string | null;
  can_act: boolean;
  business_detail?: WorkflowBusinessDetail;
  timeline?: WorkflowTimelineItem[];
};

export type WorkflowCcDetail = WorkflowCcRow & {
  instance_status_code: string;
  business_detail?: WorkflowBusinessDetail;
  timeline?: WorkflowTimelineItem[];
};

export const getWorkflowTaskDetail = (taskId: string) => {
  return http.request<ApiResponse<WorkflowTaskDetail>>(
    "get",
    `/api/workflow_task/detail/${taskId}`
  );
};

export type WorkflowTimelineItem = {
  occurred_at: string | null;
  /** submit / resubmit / approved / rejected / pending / cancelled / not_started / comment / withdraw */
  action_code: string;
  action_label: string;
  actor_name: string | null;
  comment: string | null;
  task_name: string | null;
  task_key: string | null;
  assignee_label: string | null;
  assignee_names: string[];
  approval_mode_code?: "single" | "any" | "all";
  approved_count?: number;
  required_count?: number;
  instance_id: string | null;
  instance_status_code: string | null;
};

export type WorkflowTimelineResult = {
  business_type_code: string;
  business_id: string;
  items: WorkflowTimelineItem[];
  latest_instance_status_code?: string | null;
  org_id?: string | null;
  can_comment?: boolean;
  can_resubmit?: boolean;
  requires_edit_before_resubmit?: boolean;
  edit_saved_after_rejection?: boolean;
};

export const getWorkflowTimeline = (businessType: string, businessId: string) =>
  http.request<ApiResponse<WorkflowTimelineResult>>(
    "get",
    "/api/workflow_task/timeline",
    {
      params: { business_type_code: businessType, business_id: businessId }
    }
  );

export const addWorkflowComment = (
  businessType: string,
  businessId: string,
  comment: string
) =>
  http.request<ApiResponse<WorkflowTimelineResult>>(
    "post",
    `/api/workflow_task/business/${encodeURIComponent(businessType)}/${encodeURIComponent(businessId)}/comments`,
    { data: { comment } }
  );

export const resubmitWorkflow = (
  businessType: string,
  businessId: string,
  comment: string,
  starterChoices?: Record<string, string[]>
) =>
  http.request<ApiResponse<WorkflowTimelineResult>>(
    "post",
    `/api/workflow_task/business/${encodeURIComponent(businessType)}/${encodeURIComponent(businessId)}/resubmit`,
    { data: { comment, starter_choices: starterChoices } }
  );

export const getWorkflowCcDetail = (ccId: string) => {
  return http.request<ApiResponse<WorkflowCcDetail>>(
    "get",
    `/api/workflow_task/cc/detail/${ccId}`
  );
};

export const listWorkflowTasks = (params: WorkflowTaskListParams) => {
  return http.request<ApiResponse<PageResult<WorkflowTaskRow>>>(
    "get",
    "/api/workflow_task/list",
    { params }
  );
};

export const listWorkflowCcRecords = (params: WorkflowCcListParams) => {
  return http.request<ApiResponse<PageResult<WorkflowCcRow>>>(
    "get",
    "/api/workflow_task/cc/list",
    { params }
  );
};

export const markWorkflowCcRead = (ccId: string) => {
  return http.request<ApiResponse<{ id: string; status_code: string }>>(
    "post",
    `/api/workflow_task/cc/read/${ccId}`
  );
};

export const getPendingTaskForBusiness = (
  business_type_code: string,
  business_id: string
) => {
  return http.request<ApiResponse<WorkflowTaskRow | null>>(
    "get",
    "/api/workflow_task/pending_for_business",
    { params: { business_type_code, business_id } }
  );
};

export type WorkflowSupervisionRow = {
  instance_id: string;
  business_type_code: string;
  business_id: string;
  org_id: string;
  instance_status_code: string;
  task_name: string | null;
  task_key: string | null;
  approver_names: string[];
  business_summary: string | null;
  started_at: string | null;
};

/** 查看全部审批（需要 workflow_task:supervise） */
export const listWorkflowSupervision = (params: {
  page?: number;
  page_size?: number;
  status_code?: string;
  business_type_code?: string;
}) =>
  http.request<ApiResponse<PageResult<WorkflowSupervisionRow>>>(
    "get",
    "/api/workflow_task/supervision/list",
    { params }
  );

export const completeWorkflowTask = (taskId: string, comment?: string) => {
  return http.request<ApiResponse<Record<string, unknown>>>(
    "post",
    `/api/workflow_task/complete/${taskId}`,
    { data: comment ? { comment } : {}, timeout: 120000 }
  );
};

export const rejectWorkflowTask = (taskId: string, comment?: string) => {
  return http.request<ApiResponse<Record<string, unknown>>>(
    "post",
    `/api/workflow_task/reject/${taskId}`,
    { data: comment ? { comment } : {}, timeout: 120000 }
  );
};
