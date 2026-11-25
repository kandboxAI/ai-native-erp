import { http } from "@/utils/http";
import type { ApiResponse } from "./workflowDefinition";

export type WorkflowStarterChoices = Record<string, string[]>;

export type WorkflowSelectionNode = {
  key: string;
  name: string;
  kind: "approval" | "cc";
  multiple: boolean;
};

export type WorkflowStartRequirements = {
  definition_id: string;
  version_id: string;
  selection_nodes: WorkflowSelectionNode[];
};

export type WorkflowStarterCandidate = {
  id: string;
  display_name: string | null;
};

export const getWorkflowStartRequirements = (
  business_type_code: string,
  org_id?: string | null
) =>
  http.request<ApiResponse<WorkflowStartRequirements>>(
    "get",
    "/api/workflow_runtime/start-requirements",
    { params: { business_type_code, org_id: org_id || undefined } }
  );

export const searchWorkflowStarterCandidates = (
  business_type_code: string,
  org_id?: string | null,
  keyword?: string,
  limit = 50
) =>
  http.request<ApiResponse<WorkflowStarterCandidate[]>>(
    "get",
    "/api/workflow_runtime/starter-candidates",
    {
      params: {
        business_type_code,
        org_id: org_id || undefined,
        keyword,
        limit
      }
    }
  );
