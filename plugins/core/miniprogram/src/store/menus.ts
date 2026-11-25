import { computed, reactive, watch } from "vue";
import { appStore } from "./app";
import {
  fetchMiniappFavorites,
  fetchMyMenus,
  portalForRole,
  saveMiniappFavorites,
  type MiniappMenu,
} from "@/api/miniappMenu";
import { getServiceDescription, getServiceIcon, getRoleServiceItems } from "@/config/roleServices";
import type { RoleServiceItem } from "@/config/pluginServices";
import { commonServices, normalizeServiceUsage, type ServiceUsage } from "@/utils/common-services";
import { isPageAvailable, pagePath, refreshPluginAccess } from "@/store/pluginAccess";

export interface MiniappServiceItem extends RoleServiceItem {
  id: string;
  url: string;
  groupKey: string | null;
  groupName: string | null;
}

type AuthorizedMenu = MiniappMenu & {
  group_key: string | null;
  group_name: string | null;
};

const state = reactive({
  menus: [] as AuthorizedMenu[],
  favoriteMenuIds: [] as string[],
  loading: false,
  favoritesLoading: false,
  favoritesSaving: false,
  favoritesReady: false,
  error: "",
  favoritesError: "",
});
const usage = reactive({ records: {} as ServiceUsage });

function usageKey() {
  const account = appStore.state.account;
  return appStore.state.loggedIn && account
    ? `erp-service-usage-v1:${account.tenantId || ""}:${account.userId}:${portalForRole(appStore.state.currentRole)}`
    : "";
}

watch(usageKey, key => {
  usage.records = {};
  if (!key) return;
  try { usage.records = normalizeServiceUsage(uni.getStorageSync(key)); } catch { /* 存储不可用时从空记录开始 */ }
}, { immediate: true, flush: "sync" });

let generation = 0;
let pending: Promise<void> | undefined;
let lastLoaded = 0;
watch(
  [
    () => appStore.state.loggedIn,
    () => appStore.state.account?.userId,
    () => appStore.state.account?.tenantId,
    () => appStore.state.currentRole,
  ],
  () => {
    generation++;
    pending = undefined;
    lastLoaded = 0;
    state.menus = [];
    state.favoriteMenuIds = [];
    state.loading = false;
    state.favoritesLoading = false;
    state.favoritesSaving = false;
    state.favoritesReady = false;
    state.error = "";
    state.favoritesError = "";
  },
  { flush: "sync" },
);

async function refresh(force = false) {
  if (!appStore.state.loggedIn || !appStore.state.account) return;
  if (state.favoritesSaving) return;
  if (pending) return pending;
  if (!force && Date.now() - lastLoaded < 1000) return;
  const version = ++generation;
  const portal = portalForRole(appStore.state.currentRole);
  state.loading = true;
  state.favoritesLoading = true;
  state.favoritesReady = false;
  state.error = "";
  state.favoritesError = "";
  state.menus = [];
  pending = (async () => {
    try {
      await refreshPluginAccess();
      if (version !== generation) return;
      const config = await fetchMyMenus(portal);
      if (version !== generation) return;
      state.menus = config.groups.flatMap(group =>
        group.items
          .filter(item => item.path && isPageAvailable(item.path))
          .map(item => ({
            ...item,
            group_key: group.group_key,
            group_name: group.group_name,
          })),
      );
      lastLoaded = Date.now();
      try {
        const favorites = await fetchMiniappFavorites(portal);
        if (version !== generation) return;
        const authorizedIds = new Set(state.menus.map(menu => menu.id));
        state.favoriteMenuIds = favorites.items
          .map(item => item.miniapp_menu_id)
          .filter(id => authorizedIds.has(id));
        state.favoritesReady = true;
      } catch (error) {
        if (version === generation) {
          state.favoriteMenuIds = [];
          state.favoritesError = error instanceof Error ? error.message : "常用菜单加载失败";
        }
      }
    } catch (error) {
      if (version === generation) {
        state.menus = [];
        state.favoriteMenuIds = [];
        state.error = error instanceof Error ? error.message : "菜单加载失败，请重试";
      }
    } finally {
      if (version === generation) {
        state.loading = false;
        state.favoritesLoading = false;
        pending = undefined;
      }
    }
  })();
  return pending;
}

const nativeTabs = __MINIAPP_TAB_PAGES__;
function hasPath(path: string) {
  return isPageAvailable(path) && (
    nativeTabs.includes(pagePath(path)) || state.menus.some(menu => menu.path === path)
  );
}

function open(path: string) {
  if (!hasPath(path)) {
    uni.showToast({ title: "当前入口未授权", icon: "none" });
    return;
  }
  const base = path.split("?")[0]!;
  const key = usageKey();
  const success = () => {
    if (!key || key !== usageKey()) return;
    const previous = usage.records[path];
    usage.records[path] = {
      count: Math.min((previous?.count || 0) + 1, Number.MAX_SAFE_INTEGER),
      last_used_at: Date.now(),
    };
    try { uni.setStorageSync(key, usage.records); } catch { /* 存储失败不影响使用功能 */ }
  };
  if (base === "/pages/todo/index") {
    uni.switchTab({ url: "/pages/messages/index", success });
  } else if (nativeTabs.includes(base)) {
    const tab = path.match(/[?&]tab=([^&]+)/)?.[1];
    if (base === "/pages/messages/index" && ["notice", "announcement", "message", "notification", "alert"].includes(tab || "")) {
      const target = tab === "notice" || tab === "announcement" ? "announcements" : "notifications";
      uni.navigateTo({ url: `/pages/${target}/index`, success });
    } else uni.switchTab({ url: base, success });
  } else {
    uni.navigateTo({ url: path, success });
  }
}

function excludedWorkEntryPaths() {
  const paths = new Set([
    "/pages/home/index",
    "/pages/workspace/index",
    "/pages/xiaohang/index",
    "/pages/messages/index",
    "/pages/profile/index",
  ]);
  return paths;
}

const services = computed<MiniappServiceItem[]>(() => {
  const presentation = getRoleServiceItems({
    role: appStore.state.currentRole,
    department: appStore.state.currentDepartment,
    homeroomTeacher: false,
    permissions: appStore.state.account?.permissions || [],
  });
  const excluded = excludedWorkEntryPaths();
  return state.menus
    .filter(menu => menu.path && !excluded.has(pagePath(menu.path)))
    .map(menu => {
      const exact = presentation.find(item => (item.url || item.tab) === menu.path);
      const entry = exact || presentation.find(item => pagePath(item.url || item.tab || "") === pagePath(menu.path!));
      return {
        ...(entry || { tone: "blue" as const }),
        desc: (menu.path!.includes("?") ? exact?.desc : undefined)
          || getServiceDescription(menu.path!) || entry?.desc || "查看与办理相关事项",
        id: menu.id,
        title: menu.menu_name,
        icon: getServiceIcon(menu.path!),
        url: menu.path!,
        groupKey: menu.group_key,
        groupName: menu.group_name,
      };
    });
});

const rankedServices = computed<MiniappServiceItem[]>(() =>
  commonServices(services.value, usage.records) as MiniappServiceItem[],
);
const favoriteServices = computed<MiniappServiceItem[]>(() => {
  const byId = new Map(services.value.map(item => [item.id, item]));
  return state.favoriteMenuIds
    .map(id => byId.get(id))
    .filter((item): item is MiniappServiceItem => Boolean(item));
});

const serviceGroups = computed(() => {
  const groups: { groupKey: string | null; groupName: string; items: MiniappServiceItem[] }[] = [];
  const byKey = new Map<string, (typeof groups)[number]>();
  for (const item of services.value) {
    const key = item.groupKey || "__other__";
    let group = byKey.get(key);
    if (!group) {
      group = {
        groupKey: item.groupKey,
        groupName: item.groupName || "其他应用",
        items: [],
      };
      byKey.set(key, group);
      groups.push(group);
    }
    group.items.push(item);
  }
  return groups;
});

async function saveFavorites(menuIds: string[]) {
  if (state.favoritesSaving || state.loading || !state.favoritesReady) return false;
  const version = generation;
  const available = new Set(services.value.map(item => item.id));
  const normalized = menuIds.filter(
    (id, index) => available.has(id) && menuIds.indexOf(id) === index,
  );
  state.favoritesSaving = true;
  state.favoritesError = "";
  try {
    const config = await saveMiniappFavorites(
      portalForRole(appStore.state.currentRole),
      normalized,
    );
    if (version !== generation) return false;
    state.favoriteMenuIds = config.items
      .map(item => item.miniapp_menu_id)
      .filter(id => available.has(id));
    return true;
  } catch (error) {
    if (version !== generation) return false;
    state.favoritesError = error instanceof Error ? error.message : "常用菜单保存失败";
    throw error;
  } finally {
    if (version === generation) state.favoritesSaving = false;
  }
}

async function toggleFavorite(menuId: string) {
  if (!services.value.some(item => item.id === menuId)) return false;
  const ids = state.favoriteMenuIds;
  return saveFavorites(ids.includes(menuId)
    ? ids.filter(id => id !== menuId)
    : [...ids, menuId]);
}

export const menuStore = {
  state,
  refresh,
  hasPath,
  open,
  saveFavorites,
  toggleFavorite,
  services,
  serviceGroups,
  rankedServices,
  favoriteServices,
  hasCustomFavorites: computed(() => state.favoriteMenuIds.length > 0),
  commonServices: rankedServices,
};
