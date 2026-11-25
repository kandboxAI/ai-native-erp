export const MES_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  released: "已发布",
  pending: "待执行",
  dispatched: "已派工",
  in_progress: "执行中",
  paused: "已暂停",
  waiting_quality: "待检验",
  completed: "已完成",
  cancelled: "已取消",
  posted: "已入账",
  pending_inventory: "待库存处理",
  reversed: "已冲销",
  web: "管理端",
  mini_program: "手机小程序",
  device: "设备采集",
  integration: "接口导入",
};

export const MES_STATUS_TYPES: Record<string, string> = {
  unconfigured: "info",
  ready: "warning",
  ordered: "primary",
  completed: "success",
  posted: "success",
  in_progress: "primary",
  dispatched: "warning",
  paused: "warning",
  waiting_quality: "warning",
  cancelled: "info",
  draft: "info",
};

export type MesTagType = "success" | "warning" | "danger" | "info" | "primary";

const ORDER_STATUS_LABELS: Record<string, string> = {
  unconfigured: "未配置",
  ready: "待下单",
  ordered: "已下单",
  paused: "已暂停",
  completed: "已完结",
  cancelled: "已取消",
};
type OrderStatus = {
  status_code?: string;
  display_status_key?: string;
  operation_count?: number;
};
export function mesWorkOrderStatusKey(order: OrderStatus) {
  if (order.display_status_key) return order.display_status_key;
  if (order.status_code === "draft")
    return order.operation_count ? "ready" : "unconfigured";
  if (["released", "in_progress"].includes(order.status_code)) return "ordered";
  return order.status_code || "unconfigured";
}
export function mesWorkOrderStatusLabel(order: OrderStatus) {
  const key = mesWorkOrderStatusKey(order);
  return ORDER_STATUS_LABELS[key] || key;
}
export function mesProjectOrderStatusKey(project: {
  display_status_key?: string;
  orders: OrderStatus[];
}) {
  if (project.display_status_key) return project.display_status_key;
  const states = new Set(project.orders.map(mesWorkOrderStatusKey));
  return (
    [
      "ordered",
      "paused",
      "unconfigured",
      "ready",
      "completed",
      "cancelled",
    ].find((key) => states.has(key)) || "unconfigured"
  );
}
export function mesProjectOrderStatusLabel(
  project: Parameters<typeof mesProjectOrderStatusKey>[0],
) {
  return ORDER_STATUS_LABELS[mesProjectOrderStatusKey(project)];
}
export function mesPendingProjectOrders(project: {
  orders: Array<OrderStatus & { id: string; version_no: number }>;
}) {
  return project.orders.filter((order) => order.status_code === "draft");
}
export function canPlaceMesProject(
  project: Parameters<typeof mesPendingProjectOrders>[0],
) {
  const pending = mesPendingProjectOrders(project);
  return (
    pending.length > 0 &&
    pending.every((order) => (order.operation_count || 0) > 0)
  );
}

export function mesStatusLabel(code?: string | null) {
  return code ? MES_STATUS_LABELS[code] || code : "—";
}

export function mesStatusType(code?: string | null): MesTagType {
  return (MES_STATUS_TYPES[code || ""] as MesTagType) || "info";
}

export function mesProcessingTypeLabel(code?: string | null) {
  return (
    { in_house: "自制", outsourced: "委外", purchased: "采购" }[code || ""] ||
    code ||
    "—"
  );
}

export function mesDispatchPersonLabel(task: {
  schedule_plan_id?: string | null;
  scheduled_production_person_name?: string | null;
  assigned_production_person_id?: string | null;
  assigned_production_person_name?: string | null;
  assigned_production_person_no?: string | null;
  assigned_user_name?: string | null;
}) {
  if (task.schedule_plan_id) {
    return task.scheduled_production_person_name || "按方案执行";
  }
  if (task.assigned_production_person_id) {
    return [task.assigned_production_person_name, task.assigned_production_person_no]
      .filter(Boolean)
      .join(" · ") || "生产人员档案待核对";
  }
  return task.assigned_user_name ? `${task.assigned_user_name}（原派工账号）` : "未派工";
}

export function formatMesDate(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function mesPercent(completed: number, total: number) {
  return total > 0
    ? Math.min(100, Math.max(0, Math.round((completed / total) * 100)))
    : 0;
}

export function isMesOverdue(
  row: { due_at?: string | null; status_code?: string },
  now = Date.now(),
) {
  return (
    !!row.due_at &&
    !["completed", "cancelled"].includes(row.status_code) &&
    new Date(row.due_at).getTime() < now
  );
}

export function mesReportedQuantity(row: {
  good_quantity?: number;
  scrap_quantity?: number;
  rework_quantity?: number;
}) {
  return (
    (row.good_quantity || 0) +
    (row.scrap_quantity || 0) +
    (row.rework_quantity || 0)
  );
}
