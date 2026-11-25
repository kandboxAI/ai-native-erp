import { getHttpErrorMessage } from "@/utils/http";

export function isWorkflowActionTimeout(error: unknown): boolean {
  const value = error as { code?: string; message?: string } | null;
  return value?.code === "ECONNABORTED" || value?.code === "ETIMEDOUT" ||
    /timeout.*exceeded|timed?\s*out/i.test(value?.message || "");
}

export function workflowActionErrorMessage(error: unknown): string {
  return isWorkflowActionTimeout(error)
    ? "审批结果暂未确认，后台可能仍在处理。请稍后刷新待办核对结果，确认前不要重复提交"
    : getHttpErrorMessage(error, "审批操作失败");
}
