import { http } from "@/utils/http";
import type { ApiResponse, MesPage } from "./mes";
import { deliveryParams } from "./mesDelivery";
export type InventoryPosting = {
  id: string;
  org_id: string;
  work_order_id: string;
  work_order_no?: string;
  operation_id?: string;
  posting_type_code: "issue" | "return" | "receipt" | "shipment";
  stock_order_id: string;
  order_no: string;
  status_code: string;
  item_id: string;
  item_no: string;
  item_name: string;
  warehouse_id: string;
  lot_id?: string;
  quantity: string;
  unit_code: string;
  business_date: string;
  note?: string;
};
export type WarehouseOption = { id: string; org_id: string; label: string };
export type ReturnOption = {
  id: string;
  order_no: string;
  item_id: string;
  item_name: string;
  operation_id?: string;
  warehouse_id: string;
  lot_id?: string;
  lot_no?: string;
  available_quantity: string;
  unit_code: string;
};
export type OrderInventoryOptions = {
  org_id: string;
  product_item_id: string;
  product_item_name: string;
  receipt_available_quantity: string;
  operations: { id: string; label: string }[];
  issues: ReturnOption[];
};
export const getInventoryPostings = (params: Record<string, unknown>) =>
  http.request<ApiResponse<MesPage<InventoryPosting>>>(
    "get",
    "/api/mes/inventory-postings",
    { params: deliveryParams(params) },
  );
export const createInventoryPosting = (data: unknown) =>
  http.request<ApiResponse<InventoryPosting>>(
    "post",
    "/api/mes/inventory-postings",
    { data },
  );
export const actInventoryPosting = (
  id: string,
  action: string,
  reason: string,
) =>
  http.request<ApiResponse<InventoryPosting>>(
    "post",
    `/api/mes/inventory-postings/${id}/${action}`,
    { data: { reason } },
  );
export const getInventoryOrderOptions = (keyword = "") =>
  http.request<ApiResponse<MesPage<{ id: string; label: string }>>>(
    "get",
    "/api/mes/inventory-options/orders",
    { params: deliveryParams({ keyword, page_size: 50 }) },
  );
export const getOrderInventoryOptions = (id: string) =>
  http.request<ApiResponse<OrderInventoryOptions>>(
    "get",
    `/api/mes/inventory-options/orders/${id}`,
  );
export const getStockWarehouseOptions = (
  direction: "in" | "out",
  purpose = "issue",
) =>
  http.request<ApiResponse<WarehouseOption[]>>(
    "get",
    "/api/mes/inventory-options/warehouses",
    { params: { direction, purpose } },
  );
export const getInventoryItemOptions = (keyword = "") =>
  http.request<
    ApiResponse<{ id: string; item_no: string; item_name: string }[]>
  >("get", "/api/mes/inventory-options/items", {
    params: deliveryParams({ keyword }),
  });
export const getInventoryLotOptions = (id: string) =>
  http.request<ApiResponse<{ id: string; label: string }[]>>(
    "get",
    `/api/mes/inventory-options/items/${id}/lots`,
  );
