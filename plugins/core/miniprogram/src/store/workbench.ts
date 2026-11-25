import { listTodos } from "@/api/inbox";
import { computed, ref } from "vue";
import { appStore, bootstrapStore } from "@/store/app";
import { getMyNotifications, markMyNotificationRead, type MobileNotificationItem } from "@/api";
import { inboxStore } from "@/store/inbox";
const workflowPendingCount = ref(0);
const notifications = ref<MobileNotificationItem[]>([]);
let pending: Promise<void> | undefined;
let listening = false;
async function refreshNotifications() {
  if (!appStore.state.loggedIn) { notifications.value = []; return; }
  if (pending) return pending;
  const account = appStore.state.account;
  const task = getMyNotifications().then(result => { if (account === appStore.state.account) notifications.value = result.items; });
  pending = task;
  try { await task; } finally { if (pending === task) pending = undefined; }
}
export function bootstrapWorkbench() {
  bootstrapStore();
  if (listening) return;
  listening = true;
  uni.$on("miniapp-session-changed", () => {
    workflowPendingCount.value = 0;
    notifications.value = [];
    pending = undefined;
  });
}
export const workbenchStore = {
  notifications,
  pendingCount: computed(() => workflowPendingCount.value),
  async refreshPendingCount() {
    const account = appStore.state.account;
    if (!account) { workflowPendingCount.value = 0; return 0; }
    const data = await listTodos(1, 1);
    if (account === appStore.state.account) workflowPendingCount.value = data.total || 0;
    return workflowPendingCount.value;
  },
  unreadCount: computed(() => notifications.value.filter(item => item.status_code === "unread").length),
  refreshNotifications,
  refreshNotificationUnreadCount: refreshNotifications,
  // 兼容原调用入口，导航角标统一刷新为待办数量。
  syncUnreadBadge() { void inboxStore.refreshCounts(); },
  async markRead(item: MobileNotificationItem) { await markMyNotificationRead(item.recipient_id); item.status_code = "read"; this.syncUnreadBadge(); }
};
