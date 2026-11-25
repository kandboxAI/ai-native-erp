import { http } from "@/utils/http";
import type { ApiResponse } from "./mes";

export type ManufacturingWarehouse = {
  id: string;
  org_id: string;
  warehouse_no: string;
  warehouse_name: string;
  warehouse_type_code: string;
  is_active: boolean;
  can_manage: boolean;
};
export type WarehouseConfiguration = {
  items: ManufacturingWarehouse[];
  types: Record<string, string>;
  organizations: { id: string; org_name: string }[];
};
export const getManufacturingWarehouses = () =>
  http.request<ApiResponse<WarehouseConfiguration>>(
    "get",
    "/api/mes/warehouses",
  );
export const saveManufacturingWarehouse = (
  id: string | undefined,
  data: unknown,
) =>
  http.request<ApiResponse<ManufacturingWarehouse>>(
    id ? "patch" : "post",
    id ? `/api/mes/warehouses/${id}` : "/api/mes/warehouses",
    { data },
  );
