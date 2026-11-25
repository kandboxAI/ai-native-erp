import { isNavigationFailure, type Router } from "vue-router";

/** Handle only Electron main's validated ERP route commands. */
export function installDesktopNavigation(router: Router): () => void {
  if (!window.erpDesktop) return () => undefined;
  return window.erpDesktop.onNavigate(command => {
    if (command === null || typeof command !== "object") return;
    const row = command as Record<string, unknown>;
    if (typeof row.requestId !== "string" || typeof row.path !== "string")
      return;
    const ack = (ok: boolean, error?: string) => {
      void window.erpDesktop?.acknowledgeNavigation({
        requestId: row.requestId,
        ok,
        actualPath: router.currentRoute.value.fullPath,
        ...(error ? { error } : {})
      });
    };
    const path = row.path;
    if (
      !path.startsWith("/") ||
      path.startsWith("//") ||
      path.length > 2048 ||
      /[\\?#\u0000-\u001f\u007f]/u.test(path) ||
      row.query === null ||
      typeof row.query !== "object" ||
      Array.isArray(row.query)
    ) {
      ack(false, "ERP 页面路径无效");
      return;
    }
    const query: Record<string, string | number | null> = {};
    for (const [key, value] of Object.entries(row.query)) {
      if (
        key.length > 64 ||
        (value !== null &&
          typeof value !== "string" &&
          typeof value !== "number" &&
          typeof value !== "boolean")
      ) {
        ack(false, "ERP 页面查询参数无效");
        return;
      }
      query[key] =
        typeof value === "boolean"
          ? String(value)
          : (value as string | number | null);
    }
    void (
      row.replace === true
        ? router.replace({ path, query })
        : router.push({ path, query })
    )
      .then(failure => {
        const actual = router.currentRoute.value.path;
        const blocked =
          isNavigationFailure(failure) ||
          actual === "/login" ||
          actual.startsWith("/error/");
        ack(
          !blocked,
          blocked ? `ERP 路由守卫阻止了跳转：${actual}` : undefined
        );
      })
      .catch(error => {
        ack(false, error instanceof Error ? error.message : String(error));
      });
  });
}
