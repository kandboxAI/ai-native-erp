import { reactive, watch } from "vue";
import { getCurrentAccount } from "@/api/auth";
import { fetchHomeBanners, type HomeBanner } from "@/api/homeBanner";
import { fileUrl } from "@/api/systemFile";
import { appStore } from "./app";

const state = reactive({ banners: [] as HomeBanner[], loading: false, error: "" });
let generation = 0;
let pending: Promise<void> | undefined;

watch([() => appStore.state.account, () => appStore.state.loggedIn], () => {
  generation++;
  pending = undefined;
  state.banners = [];
  state.loading = false;
  state.error = "";
}, { flush: "sync" });

async function refresh() {
  const account = appStore.state.account;
  if (!account || !appStore.state.loggedIn) return;
  if (pending) return pending;
  const version = generation;
  const avatarRevision = appStore.state.avatarRevision;
  const current = () => version === generation && appStore.state.account === account;
  state.loading = true;
  state.error = "";
  pending = Promise.allSettled([
    getCurrentAccount().then(user => {
      if (!current() || user.user_id !== account.userId || (account.tenantId && user.tenant_id !== account.tenantId)) return;
      appStore.updateAccountProfile({
        displayName: user.display_name || "用户",
        avatarUrl: appStore.state.avatarRevision === avatarRevision
          ? (user.avatar_url ? fileUrl(user.avatar_url) : "")
          : (account.avatarUrl || ""),
        roles: user.role_nos || [],
        roleNames: user.role_names || [],
      });
    }),
    fetchHomeBanners().then(result => {
      if (!current()) return;
      state.banners = result.items
        .filter(item => item.image?.url)
        .map(item => ({ ...item, image: { ...item.image!, url: fileUrl(item.image!.url) } }));
    }).catch(() => {
      if (current()) {
        state.banners = [];
        state.error = "轮播图暂时无法加载，点击重试";
      }
    }),
  ]).then(() => {
    if (current()) { state.loading = false; pending = undefined; }
  });
  return pending;
}

export const homeStore = { state, refresh };
