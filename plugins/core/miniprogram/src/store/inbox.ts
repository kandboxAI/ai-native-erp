import { computed, reactive, toRefs, watch } from "vue";
import type { MobileNotificationItem } from "@/api";
import { appStore } from "./app";
import * as api from "@/api/inbox";
import { syncTodoTabBarBadge } from "@/utils/tabbar";
import { notificationTarget } from "@/utils/inventoryNotifications";
import { formatLocalDateTime } from "@/utils/dateTime";

export type InboxKind = "message" | "announcement" | "todo" | "alert";
/** @deprecated 兼容旧入口 notification → message */
export type InboxKindLegacy = InboxKind | "notification";

export interface InboxMessage {
  individualRead?: boolean;
  avatar_url?: string | null;
  id: string;
  rawId: string;
  source: InboxKind;
  title: string;
  content: string;
  category: string;
  time: string;
  read: boolean;
  target?: string;
  sourceSystem: string;
  requiresConfirmation: boolean;
  confirmed: boolean;
}

const counts = reactive({
  notificationUnread: 0,
  announcementUnread: 0,
  todoPending: 0,
  alertOpen: 0,
  countsKnown: false,
  homeAnnouncements: [] as api.AnnouncementItem[],
});
let accountVersion = 0;
let countsVersion = 0;
let countsTask: Promise<void> | undefined;
watch(
  [
    () => appStore.state.loggedIn,
    () => appStore.state.account?.userId,
    () => appStore.state.account?.tenantId,
  ],
  () => {
    accountVersion++;
    countsVersion++;
    countsTask = undefined;
    Object.assign(counts, {
      notificationUnread: 0,
      announcementUnread: 0,
      todoPending: 0,
      alertOpen: 0,
      countsKnown: false,
      homeAnnouncements: [],
    });
    syncTodoTabBarBadge(0);
  },
  { flush: "sync" },
);

/** 公告与消息未读仅在常用页展示，底部角标使用待办数量。 */
const unreadCount = computed(
  () => counts.notificationUnread + counts.announcementUnread,
);

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "消息加载失败，请重试";
}

function normalizeKind(kind: InboxKindLegacy): InboxKind {
  return kind === "notification" ? "message" : kind;
}

function notificationCategory(item: MobileNotificationItem) {
  if (item.scene_key?.startsWith("inventory.")) return "物资";
  if (item.scene_key?.startsWith("education.grade.")) return "成绩";
  return "消息";
}

function announcementCategory(item: api.AnnouncementItem) {
  return item.notice_type_code === "notice" ? "通知" : "公告";
}

function mapNotification(item: MobileNotificationItem): InboxMessage {
  return {
    individualRead: item.requires_individual_read,
    id: `message:${item.recipient_id}`,
    rawId: item.recipient_id,
    source: "message",
    title: item.title,
    content: item.content || "",
    category: notificationCategory(item),
    read: item.status_code !== "unread",
    time: formatLocalDateTime(item.occurred_at || item.created_at),
    target: notificationTarget(item),
    sourceSystem: item.scene_name_snapshot || "系统消息",
    requiresConfirmation: Boolean(item.requires_confirmation),
    confirmed: Boolean(item.confirmed_at),
  };
}

function mapAnnouncement(item: api.AnnouncementItem): InboxMessage {
  return {
    id: `announcement:${item.id}`,
    rawId: item.id,
    source: "announcement",
    title: item.title,
    content: item.summary || "",
    category: announcementCategory(item),
    read: item.is_read,
    time: formatLocalDateTime(item.published_at || item.created_at),
    target: `/pages/notice-detail/index?id=${item.id}`,
    sourceSystem: item.publisher_name_snapshot || "学校公告",
    requiresConfirmation: false,
    confirmed: false,
  };
}

function mapTodo(item: api.InboxTodoRow): InboxMessage {
  return {
    id: `todo:${item.id}`,
    rawId: item.id,
    source: "todo",
    avatar_url: item.avatar_url,
    title: item.task_name || "待办任务",
    content: item.business_summary || "",
    category: "待办",
    read: false,
    time: formatLocalDateTime(item.arrived_at),
    target: item.target,
    sourceSystem: item.business_display_type,
    requiresConfirmation: false,
    confirmed: false,
  };
}

function mapAlert(item: api.InboxAlertRow): InboxMessage {
  return {
    id: `alert:${item.id}`,
    rawId: item.id,
    source: "alert",
    title: item.title,
    content: item.content,
    category: "预警",
    read: true,
    time: item.time,
    target: item.target,
    sourceSystem: item.sourceSystem,
    requiresConfirmation: false,
    confirmed: false,
  };
}

async function refreshCounts(force = false) {
  if (!appStore.state.loggedIn || !appStore.state.account) return;
  if (countsTask && !force) return countsTask;
  const version = accountVersion;
  const request = ++countsVersion;
  countsTask = (async () => {
    // 分源 settled：一边失败不能把另一边的未读清掉。
    const [notifications, announcements, home, todos, alerts] =
      await Promise.allSettled([
        api.notificationUnreadCount(),
        api.listAnnouncements(1, true, 1),
        api.listAnnouncements(1, false, 2, true),
        api.listTodos(1, 1),
        api.listAlerts(1),
      ]);
    if (version !== accountVersion || request !== countsVersion) return;
    let known = false;
    if (notifications.status === "fulfilled") {
      counts.notificationUnread = notifications.value.unread_count || 0;
      known = true;
    }
    if (announcements.status === "fulfilled") {
      counts.announcementUnread = announcements.value.total || 0;
      known = true;
    }
    if (home.status === "fulfilled") {
      counts.homeAnnouncements = home.value.items || [];
    }
    if (todos.status === "fulfilled") {
      counts.todoPending = todos.value.total || 0;
    }
    if (alerts.status === "fulfilled") {
      counts.alertOpen = alerts.value.total || 0;
    }
    counts.countsKnown = known;
    syncTodoTabBarBadge(counts.todoPending);
    countsTask = undefined;
  })();
  return countsTask;
}

/** 每个展示区域独立维护列表，共用账号计数。 */
function createInboxList(initialKind: InboxKind, pageSize = 20) {
  const state = reactive({
    ...toRefs(counts),
    kind: initialKind,
    unreadOnly: false,
    rows: [] as InboxMessage[],
    page: 0,
    total: 0,
    loading: false,
    error: "",
    saving: false,
  });
  let listVersion = 0;
  watch(
    [
      () => appStore.state.loggedIn,
      () => appStore.state.account?.userId,
      () => appStore.state.account?.tenantId,
    ],
    () => {
      listVersion++;
      Object.assign(state, {
        kind: initialKind,
        unreadOnly: false,
        rows: [],
        page: 0,
        total: 0,
        loading: false,
        error: "",
        saving: false,
      });
    },
    { flush: "sync" },
  );

  async function load(more = false) {
    if (!appStore.state.loggedIn || !appStore.state.account) return;
    if (more && (state.loading || state.rows.length >= state.total)) return;
    const version = ++listVersion;
    const account = accountVersion;
    const page = more ? state.page + 1 : 1;
    const kind = state.kind;
    const unreadOnly = state.unreadOnly;
    state.loading = true;
    state.error = "";
    if (!more) {
      state.rows = [];
      state.page = 0;
      state.total = 0;
    }
    try {
      let rows: InboxMessage[] = [];
      let resultPage = page;
      let resultTotal = 0;

      if (kind === "message") {
        const result = await api.listNotifications(page, unreadOnly, pageSize);
        rows = result.items.map(mapNotification);
        resultPage = result.page;
        resultTotal = result.total;
      } else if (kind === "announcement") {
        const result = await api.listAnnouncements(page, unreadOnly, pageSize);
        rows = result.items.map(mapAnnouncement);
        resultPage = result.page;
        resultTotal = result.total;
      } else if (kind === "todo") {
        const result = await api.listTodos(page);
        rows = result.items.map(mapTodo);
        resultPage = result.page;
        resultTotal = result.total;
      } else {
        const result = await api.listAlerts(page);
        rows = result.items.map(mapAlert);
        resultPage = result.page;
        resultTotal = result.total;
      }

      if (version !== listVersion || account !== accountVersion) return;
      const ids = new Set(state.rows.map((row) => row.id));
      state.rows = more
        ? [...state.rows, ...rows.filter((row) => !ids.has(row.id))]
        : rows;
      state.page = resultPage;
      state.total = resultTotal;
      if (kind === "todo") {
        counts.todoPending = resultTotal;
        syncTodoTabBarBadge(resultTotal);
      }
    } catch (error) {
      if (version === listVersion && account === accountVersion) {
        state.error = errorText(error);
      }
    } finally {
      if (version === listVersion && account === accountVersion) {
        state.loading = false;
      }
    }
  }

  function select(kind: InboxKindLegacy, unreadOnly = state.unreadOnly) {
    const next = normalizeKind(kind);
    state.kind = next;
    // 待办/预警无未读筛选
    state.unreadOnly =
      next === "message" || next === "announcement" ? unreadOnly : false;
    return load();
  }

  async function markRead(item: InboxMessage) {
    if (item.source === "todo" || item.source === "alert") return true;
    if (item.read) return true;
    const version = accountVersion;
    try {
      if (item.source === "message") {
        const result = await api.readNotification(item.rawId);
        if (!result.updated) throw new Error("消息已读状态未更新，请重试");
      } else await api.readAnnouncement(item.rawId);
      if (version !== accountVersion) return false;
      item.read = true;
      if (state.kind === item.source && state.unreadOnly) await load();
      await refreshCounts(true);
      return version === accountVersion;
    } catch (error) {
      if (version === accountVersion) {
        uni.showToast({ title: errorText(error), icon: "none" });
      }
      return false;
    }
  }

  async function confirm(item: InboxMessage) {
    if (item.source !== "message") return false;
    const version = accountVersion;
    try {
      const result = await api.confirmNotification(item.rawId);
      if (!result.confirmed) throw new Error("确认没有保存，请重试");
      if (version !== accountVersion) return false;
      item.confirmed = true;
      item.read = true;
      await refreshCounts(true);
      return true;
    } catch (error) {
      if (version === accountVersion) {
        uni.showToast({ title: errorText(error), icon: "none" });
      }
      return false;
    }
  }

  async function markAllRead() {
    if (state.saving) return;
    if (state.kind !== "message" && state.kind !== "announcement") return;
    const version = accountVersion;
    const kind = state.kind;
    state.saving = true;
    try {
      if (kind === "message") await api.readAllNotifications();
      else await api.readAllAnnouncements();
      if (version !== accountVersion) return;
      await Promise.all([load(), refreshCounts(true)]);
    } catch (error) {
      if (version === accountVersion) {
        uni.showToast({ title: errorText(error), icon: "none" });
      }
    } finally {
      if (version === accountVersion) state.saving = false;
    }
  }

  return {
    state,
    unreadCount,
    load,
    select,
    refreshCounts,
    markRead,
    markAllRead,
    confirm,
  };
}

export const inboxStore = createInboxList("announcement");
export const todoInboxStore = createInboxList("todo");

export const messageInboxStore = createInboxList("message");
export const announcementPreviewStore = createInboxList("announcement", 2);
export const messagePreviewStore = createInboxList("message", 2);
export type InboxListStore = ReturnType<typeof createInboxList>;
