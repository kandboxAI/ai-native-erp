import { http } from "@/utils/http";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type WorkflowDefinitionRow = {
  id: string;
  definition_no: string;
  definition_name: string;
  business_type_code: string;
  org_id: string;
  org_name?: string | null;
  description: string | null;
  is_active: boolean;
  is_default: boolean;
  current_version_id: string | null;
  current_version_no: number | null;
  created_at: string;
  updated_at: string;
};

/** 字典 wf_definition_version_status */
export type WorkflowVersionStatus = "draft" | "published" | "offline";

export type WorkflowDefinitionVersionRow = {
  id: string;
  definition_id: string;
  version_no: number;
  bpmn_process_no: string;
  status_code: WorkflowVersionStatus;
  published_at: string | null;
  remark: string | null;
  created_at: string;
  created_by?: string | null;
  source?: string | null;
  design?: FlowDesignV3 | null;
  is_current?: boolean | null;
};

export type WorkflowDefinitionDetail = WorkflowDefinitionRow & {
  versions: WorkflowDefinitionVersionRow[];
};

export type DefinitionListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  business_type_code?: string;
  org_id?: string;
  is_active?: boolean;
};

export type DefinitionCreatePayload = {
  definition_no: string;
  definition_name: string;
  business_type_code: string;
  org_id?: string | null;
  description?: string | null;
  is_active?: boolean;
  is_default?: boolean;
};

export type DefinitionUpdatePayload = Partial<
  Omit<DefinitionCreatePayload, "definition_no">
>;

/** 与床位设置 buildAutoCode 一致：{前缀}-{YYYYMMDDHHmmss}-{随机4位} */
export function generateWorkflowDefinitionCode(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `WF-${ts}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

export const listWorkflowDefinitions = (params: DefinitionListParams) => {
  return http.request<ApiResponse<PageResult<WorkflowDefinitionRow>>>(
    "get",
    "/api/workflow_definition/list",
    { params }
  );
};

export const getWorkflowDefinitionDetail = (id: string) => {
  return http.request<ApiResponse<WorkflowDefinitionDetail>>(
    "get",
    `/api/workflow_definition/detail/${id}`
  );
};

export const createWorkflowDefinition = (data: DefinitionCreatePayload) => {
  return http.request<ApiResponse<WorkflowDefinitionRow>>(
    "post",
    "/api/workflow_definition/create",
    { data }
  );
};

export const updateWorkflowDefinition = (
  id: string,
  data: DefinitionUpdatePayload
) => {
  return http.request<ApiResponse<WorkflowDefinitionRow>>(
    "put",
    `/api/workflow_definition/update/${id}`,
    { data }
  );
};

export const deleteWorkflowDefinition = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/workflow_definition/delete/${id}`
  );
};

export const uploadBpmnVersion = (data: {
  definition_id: string;
  bpmn_xml: string;
  bpmn_process_no?: string;
  remark?: string;
}) => {
  return http.request<ApiResponse<WorkflowDefinitionVersionRow>>(
    "post",
    "/api/workflow_definition/version/upload",
    { data }
  );
};

export const uploadBpmnVersionFile = (formData: FormData) => {
  return http.request<ApiResponse<WorkflowDefinitionVersionRow>>(
    "post",
    "/api/workflow_definition/version/upload-file",
    { data: formData },
    { headers: { "Content-Type": "multipart/form-data" } }
  );
};

export const publishBpmnVersion = (versionId: string, remark?: string) => {
  return http.request<ApiResponse<WorkflowDefinitionRow>>(
    "post",
    `/api/workflow_definition/version/publish/${versionId}`,
    { data: remark ? { remark } : {} }
  );
};

/**
 * 审批人类型（字典 wf_assignee_type）。不按角色指定审批人：
 * permission=拥有某权限的用户（如 leave:approve 学生科）；business_owner=业务关系人（如 class_head_teacher 班主任）
 */
export type AssigneeType =
  | "user"
  | "permission"
  | "business_owner"
  | "department_manager"
  | "initiator_leader"
  | "starter"
  | "starter_select";

export type AssigneeConfig = {
  type: AssigneeType;
  value?: string | null;
};

export type AssigneePreviewResult = {
  org_id: string | null;
  candidate_count: number;
  candidates: Array<{ user_id: string; name: string }>;
  groups: Array<{
    type: AssigneeConfig["type"];
    value?: string | null;
    dynamic: boolean;
    members: Array<{ user_id: string; name: string; actionable: boolean }>;
  }>;
  has_dynamic_assignees: boolean;
};

export const previewWorkflowAssignees = (
  definitionId: string,
  assignees: AssigneeConfig[]
) =>
  http.request<ApiResponse<AssigneePreviewResult>>(
    "post",
    "/api/workflow_definition/assignee/preview",
    { data: { definition_id: definitionId, assignees } }
  );

export type ApprovalNode = {
  type: "approval";
  id: string;
  name: string;
  assignee: AssigneeConfig;
  approval_mode: "single" | "any" | "all";
  assignees: AssigneeConfig[];
};

export type CcNode = {
  type: "cc";
  id: string;
  name: string;
  recipients: AssigneeConfig[];
};

export type FlowNode = ApprovalNode | CcNode;

export type ConditionOperator = "eq" | "ne" | "gt" | "gte" | "lt" | "lte";

export type ConditionExpression = {
  field: string;
  operator: ConditionOperator;
  value: string | number | boolean;
};

export type ConditionBranch = {
  id: string;
  name: string;
  condition: ConditionExpression | null;
  nodes: FlowNodeV3[];
};

export type ExclusiveGatewayNode = {
  type: "exclusive_gateway";
  id: string;
  name: string;
  default_branch_id: string;
  branches: ConditionBranch[];
};

export type FlowDesignV2 = {
  schema_version: 2;
  process_name: string;
  process_id?: string | null;
  mode: "serial" | "conditional";
  nodes: FlowNode[];
  gateway?: {
    default_branch_id: string;
    branches: ConditionBranch[];
  } | null;
};

export type ParallelGatewayNode = {
  type: "parallel_gateway";
  id: string;
  name: string;
  branches: ConditionBranch[];
};

export type FlowGatewayNode = ExclusiveGatewayNode | ParallelGatewayNode;
export type FlowNodeV3 = ApprovalNode | CcNode | FlowGatewayNode;

export type FlowDesignV3 = {
  schema_version: 3;
  process_name: string;
  process_id?: string | null;
  nodes: FlowNodeV3[];
};

export type AssigneePermissionOption = {
  permission_key: string;
  permission_name: string;
  module_code: string;
};

export type AssigneeOptions = {
  assignee_types: Array<{ value: AssigneeType; label: string }>;
  permissions: AssigneePermissionOption[];
  business_owners: Array<{ value: string; label: string }>;
};

export type AssigneeUserOption = {
  id: string;
  display_name: string | null;
};

/** 设计器可选的审批对象：审批人类型、权限清单、该业务类型登记的业务负责人 */
export const getAssigneeOptions = (business_type_code?: string | null) => {
  return http.request<ApiResponse<AssigneeOptions>>(
    "get",
    "/api/workflow_definition/assignee/options",
    { params: { business_type_code: business_type_code || undefined } }
  );
};

export const searchAssigneeUsers = (keyword?: string, limit = 50) => {
  return http.request<ApiResponse<AssigneeUserOption[]>>(
    "get",
    "/api/workflow_definition/assignee/users",
    { params: { keyword, limit } }
  );
};

export type WorkflowBusinessTypeOption = {
  value: string;
  label: string;
};

export const listWorkflowBusinessTypes = () => {
  return http.request<ApiResponse<WorkflowBusinessTypeOption[]>>(
    "get",
    "/api/workflow_definition/business-types"
  );
};

export const getDesignTemplate = (business_type_code: string) => {
  return http.request<ApiResponse<FlowDesignV3>>(
    "get",
    "/api/workflow_definition/design/template",
    { params: { business_type_code } }
  );
};

export const getLatestDesign = (definition_id: string) => {
  return http.request<ApiResponse<FlowDesignV3 | null>>(
    "get",
    "/api/workflow_definition/design/latest",
    { params: { definition_id } }
  );
};

export const saveFlowDesign = (data: {
  definition_id: string;
  design: FlowDesignV3;
  remark?: string;
}) => {
  return http.request<ApiResponse<WorkflowDefinitionVersionRow>>(
    "post",
    "/api/workflow_definition/design/save",
    { data }
  );
};

export type BpmnUserTaskMeta = {
  task_key: string;
  task_name: string | null;
  assignee_type_code: string;
  assignee_value: string;
};

export const previewFlowDesign = (
  design: FlowDesignV3,
  business_type_code: string
) => {
  return http.request<
    ApiResponse<{
      bpmn_process_no: string;
      bpmn_xml: string;
      user_tasks: BpmnUserTaskMeta[];
    }>
  >("post", "/api/workflow_definition/design/preview", {
    data: { design, business_type_code }
  });
};

export type WorkflowConditionField = {
  key: string;
  label: string;
  field_type: "number" | "string" | "boolean";
  operators: ConditionOperator[];
};

export const listWorkflowConditionFields = (business_type_code: string) => {
  return http.request<ApiResponse<WorkflowConditionField[]>>(
    "get",
    "/api/workflow_definition/design/condition-fields",
    { params: { business_type_code } }
  );
};

export const validateBpmn = (bpmn_xml: string, bpmn_process_no?: string) => {
  return http.request<
    ApiResponse<{ bpmn_process_no: string; user_tasks: BpmnUserTaskMeta[] }>
  >("post", "/api/workflow_definition/bpmn/validate", {
    data: { bpmn_xml, bpmn_process_no }
  });
};
