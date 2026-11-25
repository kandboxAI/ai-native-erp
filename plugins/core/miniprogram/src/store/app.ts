import { computed, reactive } from "vue";
import type { AccountSession } from "@/types";

const key = "erp-core-session-v1";
const state = reactive({ bootstrapped: false, loggedIn: false, account: null as AccountSession | null, currentRole: "standard", currentDepartment: "", avatarRevision: 0 });
function persist() { uni.setStorageSync(key, state.account ? { ...state.account } : null); }
export function bootstrapStore() {
  if (state.bootstrapped) return;
  try {
    const cached = uni.getStorageSync(key);
    if (cached && typeof cached === "object" && typeof cached.accessToken === "string" && typeof cached.userId === "string" && Array.isArray(cached.permissions)) {
      state.account = cached;
      state.loggedIn = true;
    }
  } catch { state.account = null; state.loggedIn = false; }
  finally { state.bootstrapped = true; }
}
export const appStore = {
  state,
  currentProfile: computed(() => ({
    name: state.account?.displayName || "用户",
    avatarText: (state.account?.displayName || "用").slice(0, 1),
    avatarUrl: state.account?.avatarUrl || "",
    roleName: (state.account?.roleNames?.length ? state.account.roleNames : state.account?.roles || []).join("、") || "未分配角色",
    subtitle: state.account?.email || "",
  })),
  updateAccountProfile(profile: Pick<AccountSession, "displayName" | "roles" | "roleNames" | "avatarUrl">) {
    if (state.account) { Object.assign(state.account, profile); persist(); }
  },
  updateAccountAvatar(avatarUrl: string) {
    if (state.account) { state.account.avatarUrl = avatarUrl; state.avatarRevision++; persist(); }
  },
  loginAccount(account: AccountSession) { state.account = account; state.loggedIn = true; persist(); uni.$emit("miniapp-session-changed"); },
  logout() { state.account = null; state.loggedIn = false; persist(); uni.$emit("miniapp-session-changed"); },
  updateAccountTokens(tokens: { accessToken: string; refreshToken: string; expiresAt: number }) { if (state.account) { Object.assign(state.account, tokens); persist(); } },
  updateAccountPermissions(permissions: string[]) { if (state.account && JSON.stringify(state.account.permissions) !== JSON.stringify(permissions)) { state.account.permissions = [...permissions]; persist(); } }
};
