const compactQuery = (value: Record<string, unknown>) => Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ""));
import { requestApi } from "./client";

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type WorkflowTaskRow = {
  business_avatar_url?: string | null;
  id: string;
  instance_id: string;
  business_type_code: string;
  business_id: string;
  task_key: string;
  task_name: string | null;
  assignee_type_code: string;
  assignee_value: string;
  approval_mode_code: "single" | "any" | "all";
  approved_count: number;
  required_count: number;
  status_code: string;
  arrived_at: string | null;
  instance_status_code: string;
  business_summary: string | null;
  business_display_type?: string | null;
};

export type WorkflowCcRow = {
  id: string;
  instance_id: string;
  task_id: string | null;
  task_key: string | null;
  task_name: string | null;
  business_type_code: string;
  business_id: string;
  business_summary: string | null;
  status_code: "unread" | "read" | string;
  created_at: string | null;
  read_at: string | null;
};

export type WorkflowBusinessDetailField = {
  label: string;
  value: string;
  type?: "text" | "avatar" | "image" | null;
};

export type WorkflowBusinessDetailTable = {
  title: string;
  columns: Array<{ prop: string; label: string }>;
  rows: Record<string, unknown>[];
};

export type WorkflowBusinessDetail = {
  fields: WorkflowBusinessDetailField[];
  tables: WorkflowBusinessDetailTable[];
};

export type WorkflowTimelineItem = {
  occurred_at: string | null;
  action_code: string;
  action_label: string;
  actor_name: string | null;
  comment: string | null;
  task_name: string | null;
  task_key: string | null;
  assignee_label: string | null;
  assignee_names: string[];
  instance_id: string | null;
  instance_status_code: string | null;
};

export type WorkflowTaskDetail = {
  id: string;
  instance_id: string;
  task_key: string;
  task_name: string | null;
  status_code: string;
  comment: string | null;
  can_act?: boolean;
  approval_mode_code: "single" | "any" | "all";
  approved_count: number;
  required_count: number;
  business_type_code: string;
  business_id: string;
  instance_status_code: string;
  business_summary: string | null;
  business_display_type?: string | null;
  business_detail?: WorkflowBusinessDetail;
  timeline?: WorkflowTimelineItem[];
};

export type WorkflowCcDetail = {
  id: string;
  instance_id: string;
  task_id: string | null;
  task_key: string | null;
  task_name: string | null;
  status_code: string;
  business_type_code: string;
  business_id: string;
  instance_status_code: string;
  business_summary: string | null;
  business_display_type?: string | null;
  created_at: string | null;
  read_at: string | null;
  business_detail?: WorkflowBusinessDetail;
  timeline?: WorkflowTimelineItem[];
};

export type WorkflowBusinessTypeOption = {
  value: string;
  label: string;
};

export function taskStatusLabel(status?: string) {
  if (status === "pending") return "待办";
  if (status === "completed") return "已办";
  if (status === "rejected") return "已驳回";
  if (status === "unread") return "未读";
  if (status === "read") return "已读";
  return status || "未知";
}

export function approvalModeLabel(row: {
  approval_mode_code?: string;
  approved_count?: number;
  required_count?: number;
}) {
  if (row.approval_mode_code === "all") {
    return `会签 ${row.approved_count || 0}/${row.required_count || 0}`;
  }
  if (row.approval_mode_code === "any") return "或签";
  return "单人审批";
}

export function formatDt(value?: string | null) {
  if (!value) return "—";
  return String(value).replace("T", " ").slice(0, 19);
}

export const listWorkflowTasks = (params: {
  page?: number;
  page_size?: number;
  status_code?: string;
  business_type_code?: string;
  business_id?: string;
} = {}) =>
  requestApi<PageResult<WorkflowTaskRow>>({
    method: "GET",
    path: "/api/workflow_task/list",
    data: compactQuery(params)
  });

export const listWorkflowCcRecords = (params: {
  page?: number;
  page_size?: number;
  status_code?: string;
  business_type_code?: string;
  business_id?: string;
} = {}) =>
  requestApi<PageResult<WorkflowCcRow>>({
    method: "GET",
    path: "/api/workflow_task/cc/list",
    data: compactQuery(params)
  });

export const getWorkflowTaskDetail = (taskId: string) =>
  requestApi<WorkflowTaskDetail>({
    method: "GET",
    path: `/api/workflow_task/detail/${taskId}`
  });

export const getWorkflowCcDetail = (ccId: string) =>
  requestApi<WorkflowCcDetail>({
    method: "GET",
    path: `/api/workflow_task/cc/detail/${ccId}`
  });

export const markWorkflowCcRead = (ccId: string) =>
  requestApi<{ id: string; status: string }>({
    method: "POST",
    path: `/api/workflow_task/cc/read/${ccId}`
  });

export const completeWorkflowTask = (taskId: string, comment?: string) =>
  requestApi<Record<string, unknown>>({
    method: "POST",
    path: `/api/workflow_task/complete/${taskId}`,
    data: comment ? { comment } : {}
  });

export const rejectWorkflowTask = (taskId: string, comment?: string) =>
  requestApi<Record<string, unknown>>({
    method: "POST",
    path: `/api/workflow_task/reject/${taskId}`,
    data: comment ? { comment } : {}
  });

export const listWorkflowBusinessTypes = () =>
  requestApi<WorkflowBusinessTypeOption[]>({
    method: "GET",
    path: "/api/workflow_definition/business-types"
  });
