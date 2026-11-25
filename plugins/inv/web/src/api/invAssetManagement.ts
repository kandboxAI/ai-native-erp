import { http } from "@/utils/http";

type ApiResponse<T> = { code: number; message: string; data: T };
export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Option = { value: string; label: string };
export type EntityOption = { id: string; [key: string]: string | null };

export type AssetItemOption = {
  id: string;
  item_no: string;
  item_name: string;
  specification: string | null;
  unit_code: string;
  unit_price: string | number | null;
  category_name: string | null;
  default_asset_type_code: string | null;
  default_asset_management_mode_code: "individual" | "batch" | null;
};

export const listAssetItemOptions = (params: {
  org_id: string;
  keyword?: string;
  page: number;
  page_size: number;
  permission_key?: "asset_register:list" | "asset_register:create";
}) =>
  http.request<ApiResponse<PageResult<AssetItemOption>>>(
    "get",
    "/api/asset/item-options",
    { params },
  );

export type AssetRegistrationBody = {
  org_id: string;
  asset_no?: string | null;
  item_id: string;
  quantity: number;
  warehouse_id?: string | null;
  department_id?: string | null;
  custodian_user_id?: string | null;
  location_id?: string | null;
  original_amount?: number | null;
  acquired_date?: string | null;
  status_code: "idle" | "in_use";
  remark?: string | null;
};
export type AssetRegistrationOptions = Omit<AssetOptions, "departments" | "users"> & {
  departments: { value: string; label: string; org_id: string }[];
  users: { value: string; label: string; org_id: string }[];
  warehouses: import("./inventoryManagement").WarehouseOption[];
};
export const getAssetRegistrationOptions = (org_id?: string) =>
  http.request<ApiResponse<AssetRegistrationOptions>>("get", "/api/asset/registration-options", { params: { org_id } });
export const registerAssets = (data: AssetRegistrationBody) =>
  http.request<ApiResponse<{ registered_quantity: number; stock_order_id: string | null }>>("post", "/api/asset/registrations", { data, timeout: 120000 });

export type AssetOptions = {
  org_id: string;
  organizations: Array<{
    id: string;
    org_no: string;
    org_name: string;
    active_location_count: number;
  }>;
  items: AssetItemOption[];
  locations: Array<{
    id: string;
    physical_location_id?: string;
    asset_location_ids?: string[];
    location_no: string | null;
    location_name: string;
  }>;
  departments: Array<{
    id: string;
    org_id: string;
    org_name: string;
    department_no: string;
    department_name: string;
  }>;
  users: Array<{ id: string; display_name: string }>;
  asset_type: Option[];
  asset_status: Option[];
  asset_location_type: Option[];
  asset_change_event_type: Option[];
  md_unit: Option[];
};

export type AssetSummary = {
  location_asset_quantity: string;
  registered_asset_count: number;
  active_location_count: number;
  maintenance_asset_count: number;
  pending_registration_count: number;
};

export type AssetRegistrationStatus =
  "pending_confirmation" | "confirmed" | "voided";

export type AssetLocation = {
  id: string;
  physical_location_id: string | null;
  org_id: string;
  location_no: string;
  location_name: string;
  location_type_code: string;
  parent_id: string | null;
  /** 历史只读值，当前资产登记不使用位置默认责任信息。 */
  default_department_id: string | null;
  default_custodian_user_id: string | null;
  is_active: boolean;
  version_no: number;
  remark: string | null;
};

export type LocationAsset = {
  id: string;
  org_id: string;
  location_id: string | null;
  is_personal_custody?: boolean;
  custody_location_note?: string | null;
  location_no: string | null;
  location_name: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification: string | null;
  asset_type_code: string;
  quantity: string;
  unit_code: string;
  department_id: string | null;
  department_name: string | null;
  custodian_user_id: string | null;
  custodian_name: string | null;
  status_code: string;
  registration_status_code: AssetRegistrationStatus;
  registered_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  version_no: number;
  remark: string | null;
};

export type AssetRegister = {
  id: string;
  org_id: string;
  asset_no: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification: string | null;
  asset_type_code: string;
  serial_no: string | null;
  location_id: string | null;
  is_personal_custody?: boolean;
  custody_location_note?: string | null;
  location_no: string | null;
  location_name: string;
  department_id: string | null;
  department_name: string | null;
  custodian_user_id: string | null;
  custodian_name: string | null;
  status_code: string;
  registration_status_code: AssetRegistrationStatus;
  registered_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  acquired_date: string | null;
  original_amount: string | null;
  version_no: number;
  remark: string | null;
};

export type AssetLedger = {
  acquisition_source_code: string;
  is_asset_managed: boolean;
  management_mode: "batch" | "individual";
  id: string;
  org_id: string;
  asset_no: string | null;
  item_id: string;
  item_no: string;
  item_name: string;
  specification: string | null;
  asset_type_code: string;
  serial_no: string | null;
  location_id: string | null;
  is_personal_custody?: boolean;
  custody_location_note?: string | null;
  location_no: string | null;
  location_name: string;
  quantity: string;
  unit_code: string;
  department_id: string | null;
  department_name: string | null;
  custodian_user_id: string | null;
  custodian_name: string | null;
  status_code: string;
  registration_status_code: AssetRegistrationStatus;
  registered_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  acquired_date: string | null;
  original_amount: string | null;
  version_no: number;
  remark: string | null;
  created_at: string;
  updated_at: string;
};

export type AssetEvent = {
  id: string;
  event_type_code: string;
  quantity_before: string | null;
  quantity_after: string | null;
  from_location_id: string | null;
  to_location_id: string | null;
  from_department_id: string | null;
  to_department_id: string | null;
  from_custodian_user_id: string | null;
  to_custodian_user_id: string | null;
  from_status_code: string | null;
  to_status_code: string | null;
  source_type_code: string;
  source_id: string | null;
  note: string;
  operator_name_snapshot: string;
  created_at: string;
};

export const getAssetOptions = (
  org_id?: string,
  scope: "ledger" = "ledger",
) =>
  http.request<ApiResponse<AssetOptions>>("get", "/api/asset/options", {
    params: { org_id, scope },
  });

export const getAssetSummary = () =>
  http.request<ApiResponse<AssetSummary>>("get", "/api/asset/summary");

export const listAssetLedger = (params: Record<string, any>) =>
  http.request<ApiResponse<PageResult<AssetLedger>>>(
    "get",
    "/api/asset/ledger",
    { params },
  );

export const listLocationAssets = (params: Record<string, any>) =>
  http.request<ApiResponse<PageResult<LocationAsset>>>(
    "get",
    "/api/asset/location-items",
    { params },
  );

export const updateLocationAsset = (id: string, data: Record<string, any>) =>
  http.request<ApiResponse<LocationAsset>>(
    "put",
    `/api/asset/location-items/${id}`,
    { data },
  );

export const adjustLocationAsset = (id: string, data: Record<string, any>) =>
  http.request<ApiResponse<{ removed: boolean; item: LocationAsset | null }>>(
    "post",
    `/api/asset/location-items/${id}/adjust`,
    { data },
  );

export const transferLocationAsset = (id: string, data: Record<string, any>) =>
  http.request<ApiResponse<{ source_removed: boolean; target: LocationAsset }>>(
    "post",
    `/api/asset/location-items/${id}/transfer`,
    { data },
  );

export const listAssetRegisters = (params: Record<string, any>) =>
  http.request<ApiResponse<PageResult<AssetRegister>>>(
    "get",
    "/api/asset/registers",
    { params },
  );

export const createAssetRegister = (data: Record<string, any>) =>
  http.request<ApiResponse<AssetRegister>>("post", "/api/asset/registers", {
    data,
  });

export const updateAssetRegister = (id: string, data: Record<string, any>) =>
  http.request<ApiResponse<AssetRegister>>(
    "put",
    `/api/asset/registers/${id}`,
    { data },
  );

export const transferAssetRegister = (id: string, data: Record<string, any>) =>
  http.request<ApiResponse<AssetRegister>>(
    "post",
    `/api/asset/registers/${id}/transfer`,
    { data },
  );

export const listAssetEvents = (params: Record<string, any>) =>
  http.request<ApiResponse<PageResult<AssetEvent>>>(
    "get",
    "/api/asset/events",
    { params },
  );

export const confirmAssetRegistration = (
  managementMode: "batch" | "individual",
  id: string,
  expected_version: number,
) =>
  http.request<ApiResponse<LocationAsset | AssetRegister>>(
    "post",
    `/api/asset/${managementMode}/${id}/registration/confirm`,
    { data: { expected_version } },
  );

export const voidAssetRegistration = (
  managementMode: "batch" | "individual",
  id: string,
  data: { expected_version: number; reason: string },
) =>
  http.request<ApiResponse<LocationAsset | AssetRegister>>(
    "post",
    `/api/asset/${managementMode}/${id}/registration/void`,
    { data },
  );

export type StockAssetChoice = {
  asset_label?: string;
  binding_id: string;
  quantity: string | number;
  target_location_id?: string | null;
  department_id?: string | null;
  custodian_user_id?: string | null;
};
export type StockAssetTracking = {
  selections: StockAssetChoice[];
  registration?: { department_id: string | null; custodian_user_id?: string | null; asset_no?: string | null;
    acquired_date?: string | null; original_amount?: string | number | null } | null;
};
export type StockAssetBinding = {
  id: string;
  quantity: string;
  asset_no: string | null;
  serial_no?: string | null;
  management_mode: "individual" | "batch";
  stock_status_code: string;
  registration_status_code: string;
  status_code: string;
};
export const listStockAssetBindings = (params: Record<string, unknown>) =>
  http.request<ApiResponse<PageResult<StockAssetBinding>>>("get", "/api/asset/stock-bindings", { params });
export const getStockAssetTargetOptions = (org_id?: string) =>
  http.request<ApiResponse<AssetOptions>>("get", "/api/asset/stock-target-options", { params: { org_id } });
