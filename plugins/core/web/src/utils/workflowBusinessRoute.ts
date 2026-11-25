/** 审批待办对应的业务页面（按字典 wf_business_type）。 */
import BUSINESS_ROUTE_NAMES from "virtual:workflow-routes";

export function buildWorkflowBusinessRoute(
  businessType?: string | null,
  businessId?: string | null,
  businessPageQuery?: Record<string, string>
): { name: string; query?: Record<string, string> } | null {
  const name = businessType ? BUSINESS_ROUTE_NAMES[businessType] : undefined;
  if (!name) return null;
  const query = { ...businessPageQuery, ...(businessId ? { id: businessId } : {}) };
  return Object.keys(query).length ? { name, query } : { name };
}
