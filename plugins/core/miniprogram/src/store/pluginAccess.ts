import { reactive } from "vue";
import { requestApi } from "@/api/client";
import { appStore } from "@/store/app";

interface CapabilityResponse {
  protocol_version: number;
  deployed_plugin_keys: string[];
  enabled_plugin_keys: string[];
  permissions: string[];
  page_owners: Record<string, string>;
}
const state = reactive({
  identity: "",
  ready: false,
  refreshedAt: 0,
  enabledPluginKeys: [] as string[],
  permissions: [] as string[],
  pageOwners: {} as Record<string, string>,
});
let pending: { identity: string; task: Promise<boolean> } | undefined;
const refreshMs = 15000;
let sessionEpoch = 0;

function identity() {
  const account = appStore.state.account;
  return appStore.state.loggedIn && account
    ? `${account.tenantId || ""}:${account.userId}:${sessionEpoch}`
    : "";
}
export function resetPluginAccess() {
  Object.assign(state, {
    identity: "",
    ready: false,
    refreshedAt: 0,
    enabledPluginKeys: [],
    permissions: [],
    pageOwners: {},
  });
}
export function pagePath(url: string) {
  const path = url.split(/[?#]/, 1)[0] || "";
  return path.startsWith("/") ? path : `/${path}`;
}
export function isPageAvailable(url: string) {
  const path = pagePath(url);
  const owner = __MINIAPP_PAGE_OWNERS__[path];
  if (!owner) return false;
  if (owner === "core") return true;
  return (
    state.ready &&
    state.identity === identity() &&
    state.pageOwners[path] === owner &&
    state.enabledPluginKeys.includes(owner)
  );
}
export async function refreshPluginAccess(force = false): Promise<boolean> {
  const actor = identity();
  if (!actor) {
    resetPluginAccess();
    return false;
  }
  if (state.identity !== actor) {
    resetPluginAccess();
    state.identity = actor;
  }
  if (pending?.identity === actor) return pending.task;
  if (!force && state.ready && Date.now() - state.refreshedAt < refreshMs)
    return true;
  const task = (async () => {
    try {
      const data = await requestApi<CapabilityResponse>({
        path: "/api/plugins/miniapp",
        timeout: 8000,
      });
      if (identity() !== actor) return false;
      if (
        data.protocol_version !== 1 ||
        !Array.isArray(data.enabled_plugin_keys) ||
        data.enabled_plugin_keys.some((key) => typeof key !== "string") ||
        !Array.isArray(data.permissions) ||
        data.permissions.some((key) => typeof key !== "string") ||
        !data.page_owners ||
        Array.isArray(data.page_owners) ||
        typeof data.page_owners !== "object" ||
        Object.entries(data.page_owners).some(
          ([path, owner]) =>
            !/^pages\/[a-z][a-z0-9-]*\/[a-z][a-z0-9-]*$/.test(path) ||
            typeof owner !== "string",
        )
      )
        throw new Error("移动能力协议无效");
      const owners = Object.fromEntries(
        Object.entries(data.page_owners).map(([path, owner]) => [
          `/${path}`,
          owner,
        ]),
      );
      Object.assign(state, {
        identity: actor,
        ready: true,
        refreshedAt: Date.now(),
        enabledPluginKeys: data.enabled_plugin_keys,
        permissions: data.permissions,
        pageOwners: owners,
      });
      appStore.updateAccountPermissions(data.permissions);
      return true;
    } catch {
      if (identity() === actor) resetPluginAccess();
      return false;
    }
  })();
  const slot = { identity: actor, task };
  pending = slot;
  try {
    return await task;
  } finally {
    if (pending === slot) pending = undefined;
  }
}

export const pluginAccess = {
  state,
  isPageAvailable,
  refresh: refreshPluginAccess,
  reset: resetPluginAccess,
};

export function enforceCurrentPage() {
  if (!identity()) return;
  const pages = getCurrentPages();
  const route = pages[pages.length - 1]?.route;
  if (route && !isPageAvailable(route)) {
    uni.showToast({ title: "当前功能不可用，已返回首页", icon: "none" });
    uni.reLaunch({ url: "/pages/home/index" });
  }
}

let installed = false;
let timer: ReturnType<typeof setInterval> | undefined;
let replay: { method: string; url: string; actor: string } | undefined;
export function installPluginNavigation() {
  if (installed) return;
  installed = true;
  for (const method of [
    "navigateTo",
    "redirectTo",
    "reLaunch",
    "switchTab",
  ] as const) {
    uni.addInterceptor(method, {
      invoke(options: {
        url?: string;
        fail?: (result: { errMsg: string }) => void;
        complete?: (result: { errMsg: string }) => void;
      }) {
        const url = options.url;
        if (!url || __MINIAPP_PAGE_OWNERS__[pagePath(url)] === "core")
          return options;
        if (
          replay?.method === method &&
          replay.url === url &&
          replay.actor === identity() &&
          isPageAvailable(url)
        ) {
          replay = undefined;
          return options;
        }
        void refreshPluginAccess(true).then((ok) => {
          if (ok && isPageAvailable(url)) {
            replay = { method, url, actor: identity() };
            try {
              // H5 编译器按静态 uni API 调用收集实现，动态 uni[method] 会丢失导航方法。
              const next = { ...options, url };
              if (method === "navigateTo") uni.navigateTo(next);
              else if (method === "redirectTo") uni.redirectTo(next);
              else if (method === "reLaunch") uni.reLaunch(next);
              else uni.switchTab(next);
            } finally {
              replay = undefined;
            }
          } else {
            uni.showToast({ title: "功能未启用或当前无权访问", icon: "none" });
            const result = {
              errMsg: `${method}:fail 功能未启用或当前无权访问`,
            };
            options.fail?.(result);
            options.complete?.(result);
          }
        });
        return false;
      },
    });
  }
  uni.$on(
    "miniapp-access-refresh",
    () => void refreshPluginAccess(true).then(enforceCurrentPage),
  );
  uni.$on("miniapp-session-changed", () => {
    sessionEpoch++;
    resetPluginAccess();
    void refreshPluginAccess(true).then(enforceCurrentPage);
  });
}
export function resumePluginAccess() {
  pausePluginAccess();
  void refreshPluginAccess(true).then(enforceCurrentPage);
  timer = setInterval(
    () => void refreshPluginAccess(true).then(enforceCurrentPage),
    refreshMs,
  );
}
export function pausePluginAccess() {
  if (timer) clearInterval(timer);
  timer = undefined;
}
