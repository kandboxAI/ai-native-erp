import type { InjectionKey, Ref } from "vue";
import type { AssigneeOptions } from "@/api/workflowDefinition";

/** 审批对象候选（权限、业务负责人等），由流程设计页统一加载：GET /api/workflow_definition/assignee/options */
export const workflowAssigneeOptionsKey: InjectionKey<Ref<AssigneeOptions>> =
  Symbol("workflowAssigneeOptions");
export const workflowAssigneeOptionsLoadingKey: InjectionKey<Ref<boolean>> =
  Symbol("workflowAssigneeOptionsLoading");

export function emptyAssigneeOptions(): AssigneeOptions {
  return { assignee_types: [], permissions: [], business_owners: [] };
}
