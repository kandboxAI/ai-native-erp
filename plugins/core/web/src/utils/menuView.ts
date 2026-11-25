import { computed, ref } from "vue";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";

/** 只在当前账号已经注册的同组菜单之间跳转，携带显式业务上下文。 */
export function useMenuNavigation() {
  const route = useRoute();
  const router = useRouter();
  const group = route.meta.menuGroup;
  const sourcePath = route.fullPath;
  return (view: string, query?: LocationQueryRaw, subView?: string) => {
    if (typeof group !== "string") return false;
    // 缓存页面的异步保存完成时，不把用户从后来打开的其他页面带走。
    if (route.fullPath !== sourcePath) return true;
    const target = router
      .getRoutes()
      .find(
        item =>
          item.meta.menuGroup === group &&
          item.meta.menuView === view &&
          (subView == null || item.meta.menuSubView === subView)
      );
    if (!target) throw new Error("当前账号没有该功能的菜单入口，请联系管理员");
    void router.push({ path: target.path, query: query ?? route.query });
    return true;
  };
}

export function useMenuView<T extends string>(
  fallback: T,
  supported: readonly T[],
  metadataKey = "menuView"
) {
  const route = useRoute();
  const configured = route.meta[metadataKey];
  if (
    configured != null &&
    (typeof configured !== "string" || !supported.includes(configured as T))
  )
    throw new Error("当前菜单的页面配置无效，请联系管理员");
  // 管理端按 fullPath 缓存页面，各独立菜单分别初始化、分别保留查询状态。
  const current = ref((configured ?? fallback) as T);
  if (configured == null || typeof route.meta.menuGroup !== "string")
    return current;
  const navigate = useMenuNavigation();
  return computed({
    get: () => current.value as T,
    set: (value: T) => {
      if (value === configured) return;
      if (!supported.includes(value))
        throw new Error("当前菜单的页面配置无效，请联系管理员");
      navigate(
        metadataKey === "menuSubView" ? String(route.meta.menuView) : value,
        undefined,
        metadataKey === "menuSubView" ? value : undefined
      );
    }
  });
}
