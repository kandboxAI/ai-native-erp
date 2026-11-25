import { computed } from "vue";
import { useRoute } from "vue-router";

/** 首页和工作台共用学校品牌页头，其他业务页保持原有导航。 */
export function usePortalHeader() {
  const route = useRoute();
  return computed(() =>
    ["Welcome", "PlatformWorkbench"].includes(String(route.name))
  );
}
