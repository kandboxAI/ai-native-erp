import { requestApi } from "./client";

export type InventoryAlertStatus =
  | "out_of_stock"
  | "low_stock"
  | "unconfigured"
  | "normal"
  | "overstock";

export interface InventoryAlertItem {
  item_id: string;
  org_id: string;
  org_name: string;
  warehouse_id: string;
  warehouse_name: string;
  item_no: string;
  item_name: string;
  category_name?: string | null;
  specification?: string | null;
  unit_code: string;
  min_quantity?: string | number | null;
  max_quantity?: string | number | null;
  available_quantity: string | number;
  stock_alert_status: InventoryAlertStatus;
  stock_alert_label: string;
  suggested_replenishment_quantity: string | number;
  updated_at?: string | null;
}

export interface InventoryAlertQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  item_id?: string;
  warehouse_id?: string;
  status_code?:
    | "replenishment"
    | Exclude<InventoryAlertStatus, "normal" | "overstock">;
}

export function getInventoryAlerts(data: InventoryAlertQuery) {
  return requestApi<{
    items: InventoryAlertItem[];
    total: number;
    page: number;
    page_size: number;
  }>({
    path: "/api/inventory_stock_alert/list",
    method: "GET",
    data,
  });
}

export function getInventoryAlertDetail(itemId: string, warehouseId: string) {
  return requestApi<InventoryAlertItem>({
    path: `/api/inventory_stock_alert/${encodeURIComponent(itemId)}/${encodeURIComponent(warehouseId)}`,
    method: "GET",
  });
}

export function getInventoryAlertMeta() {
  return requestApi<Record<string, Array<{ value: string; label: string }>>>({
    path: "/api/inventory_meta/options",
    method: "GET",
  });
}
