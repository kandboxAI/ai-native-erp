import { inject, onScopeDispose, ref, type InjectionKey } from "vue";
export function createBusinessContext() {
  return {
    organizations: ref<Array<{ id: string; org_name: string }>>([]),
    operationOrg: ref(""),
  };
}
export type BusinessContextState = ReturnType<typeof createBusinessContext>;
export const businessContextKey: InjectionKey<BusinessContextState> =
  Symbol("sample-app-page");
export const useBusinessContext = () => inject(businessContextKey, undefined);
export function useOrganizationLifetime() {
  let active = true;
  onScopeDispose(() => {
    active = false;
  });
  return () => active;
}
