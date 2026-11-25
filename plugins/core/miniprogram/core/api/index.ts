import { requestApi } from "./client";
export interface MobileNotificationItem {
  targets?: { web?: string; miniapp?: string };
  recipient_id: string;
  scene_key?: string;
  requires_confirmation?: boolean;
  confirmed_at?: string | null;
  confirm_due_at?: string | null;
  title: string;
  content?: string | null;
  status_code: string;
  created_at: string;
  redirect_url?: string;
}
export function getMyNotifications() {
  return requestApi<{ items: MobileNotificationItem[]; total: number }>({ path: "/api/notification_center/mine/list", data: { page: 1, page_size: 100, status: "all" } });
}
export function markMyNotificationRead(id: string) { return requestApi({ path: `/api/notification_center/mine/read/${id}`, method: "POST" }); }
export function markAllMyNotificationsRead() { return requestApi({ path: "/api/notification_center/mine/read-all", method: "POST" }); }
