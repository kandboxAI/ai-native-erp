import { paginateTodos } from "@/utils/todoPagination";
import { requestApi } from "./client";
import type { MobileNotificationItem } from "./index";
import { getInventoryAlerts, type InventoryAlertItem } from "./inventoryAlerts";
import type { WorkflowTaskRow } from "./workflowTask";
import { listUnifiedTodos } from "./todo";
import { todoEntryTarget } from "@/utils/todoEntry";
import { hasPermission } from "@/utils/permissions";
import { pluginAccess, refreshPluginAccess } from "@/store/pluginAccess";
import { pluginProviders } from "@/config/pluginProviders";
import type { InboxTodoPage, InboxTodoRow } from "@/config/pluginServices";
export type { InboxTodoRow } from "@/config/pluginServices";

export interface InboxPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AnnouncementItem {
  id: string;
  title: string;
  summary: string | null;
  notice_type_code?: "notice" | "announcement" | string;
  publisher_name_snapshot: string | null;
  published_at: string | null;
  created_at: string;
  is_read: boolean;
  is_shown_on_home: boolean;
}

export type NotificationDetail = {
  title: string;
  content: string | null;
  scene_name: string;
  occurred_at: string;
};

export function notificationDetail(recipientId: string) {
  return requestApi<NotificationDetail>({
    path: `/api/notification_center/mine/detail/${encodeURIComponent(recipientId)}`,
  });
}

export type InboxAlertRow = {
  id: string;
  title: string;
  content: string;
  time: string;
  target?: string;
  sourceSystem: string;
};

export function listNotifications(page = 1, unreadOnly = false, pageSize = 20, sceneKey?: string) {
  return requestApi<InboxPage<MobileNotificationItem>>({
    path: "/api/notification_center/mine/list",
    data: {
      page,
      page_size: pageSize,
      status_code: unreadOnly ? "unread" : "all",
      scene_key: sceneKey,
    },
  });
}

export function listAnnouncements(
  page = 1,
  unreadOnly = false,
  page_size = 20,
  homeOnly = false,
) {
  return requestApi<InboxPage<AnnouncementItem>>({
    path: "/api/notice_announcement/mine/list",
    data: {
      page,
      page_size,
      read_status: unreadOnly ? "unread" : "all",
      ...(homeOnly ? { is_shown_on_home: true } : {}),
    },
  });
}

export function notificationUnreadCount() {
  return requestApi<{ unread_count: number }>({
    path: "/api/notification_center/mine/unread-count",
  });
}

export function readNotification(id: string) {
  return requestApi<{ updated: boolean }>({
    path: `/api/notification_center/mine/read/${id}`,
    method: "POST",
  });
}

export function confirmNotification(id: string) {
  return requestApi<{ confirmed: boolean }>({
    path: `/api/notification_center/mine/confirm/${id}`,
    method: "POST",
  });
}

export function readAllNotifications() {
  return requestApi<{ marked_count: number }>({
    path: "/api/notification_center/mine/read-all",
    method: "POST",
  });
}

export function announcementDetail(id: string) {
  return requestApi<AnnouncementItem>({
    path: `/api/notice_announcement/mine/detail/${id}`,
  });
}

export function readAnnouncement(id: string) {
  return requestApi<AnnouncementItem>({
    path: `/api/notice_announcement/read/${id}`,
    method: "POST",
  });
}

export function readAllAnnouncements() {
  return requestApi<{ marked_count: number }>({
    path: "/api/notice_announcement/read-all",
    method: "POST",
  });
}

export async function listTodos(
  page = 1,
  pageSize = 20,
): Promise<InboxTodoPage> {
  const sources: Array<(page: number, size: number) => Promise<InboxTodoPage>> = [
    async (sourcePage, size) => {
      const data = await listUnifiedTodos(sourcePage, size);
      return {
        ...data,
        items: data.items.map(row => ({
          id: `todo:${row.id}`,
          task_name: row.title,
          business_summary: row.summary,
          avatar_url: row.avatar_url,
          arrived_at: row.arrived_at,
          target: todoEntryTarget(row),
          business_display_type: row.type_label,
        })),
      };
    },
  ];
  if (await refreshPluginAccess()) {
    for (const provider of pluginProviders) {
      if (
        pluginAccess.state.enabledPluginKeys.includes(provider.key) &&
        provider.listTodos
      )
        sources.push(provider.listTodos);
    }
  }
  return paginateTodos(sources, page, pageSize);
}

function formatTime(value: string | null | undefined) {
  if (!value) return "";
  return String(value).replace("T", " ").slice(0, 16);
}

async function settled<T>(
  allowed: boolean,
  load: () => Promise<T>,
  fallback: T,
): Promise<T> {
  if (!allowed) return fallback;
  try {
    return await load();
  } catch {
    return fallback;
  }
}

/** 业务预警台账摘要（不读 notification_center）。 */
export async function listAlerts(page = 1): Promise<InboxPage<InboxAlertRow>> {
  const pageSize = 20;
  const ready = await refreshPluginAccess();
  const canRead = (plugin: string, permission: string) =>
    ready &&
    pluginAccess.state.enabledPluginKeys.includes(plugin) &&
    hasPermission(permission);
  const [inventory, education, duty] = await Promise.all([
    settled(
      canRead("inv", "inventory_stock_alert:list"),
      () =>
        getInventoryAlerts({
          page: 1,
          page_size: pageSize,
          status_code: "replenishment",
        }),
      {
        items: [] as InventoryAlertItem[],
        total: 0,
        page: 1,
        page_size: pageSize,
      },
    ),
    settled(
      canRead("edu", "student:list"),
      () =>
        requestApi<{ list?: Array<Record<string, unknown>> }>({
          path: "/api/education/warnings",
          method: "GET",
          data: {},
        }),
      { list: [] as Array<Record<string, unknown>> },
    ),
    settled(
      canRead("edu", "education:duty:list"),
      () =>
        requestApi<InboxPage<Record<string, unknown>>>({
          path: "/api/education/duty/warnings",
          method: "GET",
          data: { page: 1, page_size: pageSize, status_code: "pending" },
        }),
      {
        items: [] as Record<string, unknown>[],
        total: 0,
        page: 1,
        page_size: pageSize,
      },
    ),
  ]);

  const inventoryRows: InboxAlertRow[] = (inventory.items || []).map((row) => ({
    id: `inv:${row.item_id}:${row.warehouse_id}`,
    title: `${row.item_name} · ${row.stock_alert_label}`,
    content: `${row.warehouse_name} · 可用 ${row.available_quantity}`,
    time: formatTime(row.updated_at),
    target: `/pages/inventory-alert-detail/index?item_id=${encodeURIComponent(row.item_id)}&warehouse_id=${encodeURIComponent(row.warehouse_id)}`,
    sourceSystem: "库存预警",
  }));

  const educationRows: InboxAlertRow[] = (education.list || [])
    .filter((row) => String(row.status || "") !== "已解除")
    .map((row) => ({
      id: `edu:${row.name || row.source_no}`,
      title: String(row.rule_title || row.category || "学业预警"),
      content: [
        row.student_name,
        row.student_group,
        (row.ai as { summary?: string } | undefined)?.summary,
      ]
        .filter(Boolean)
        .join(" · "),
      time: formatTime(String(row.trigger_date || "")),
      sourceSystem: "学业预警",
    }));

  const dutyRows: InboxAlertRow[] = (duty.items || []).map((row) => ({
    id: `duty:${row.id}`,
    title: `${row.teacher_name || "教师"} · 坐班预警`,
    content: [row.warning_type_code, row.duty_date, row.evidence]
      .filter(Boolean)
      .join(" · "),
    time: formatTime(String(row.triggered_at || row.duty_date || "")),
    sourceSystem: "坐班预警",
  }));

  const all = [...inventoryRows, ...educationRows, ...dutyRows];
  const start = (page - 1) * pageSize;
  return {
    items: all.slice(start, start + pageSize),
    total: all.length,
    page,
    page_size: pageSize,
  };
}

export type { WorkflowTaskRow };
