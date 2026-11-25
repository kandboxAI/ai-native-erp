/**
 * 物料主数据与供应商接口。
 * - 物料分类 md_item_category：/api/inventory_product_category
 * - 物料 md_item：/api/inventory_product（库存数量不在物料上，见库存查询）
 * - 供应商 md_supplier：/api/supplier；供应商分类：/api/supplier_category
 * - 供应商收款账户（机密，单独授权，只返回脱敏账号）：/api/supplier/{id}/bank_account/...
 */
import { http } from "@/utils/http";
import type {
  ApiResponse,
  Decimalish,
  PageParams,
  PageResult
} from "./inventoryManagement";

// ───────── 物料分类 ─────────
export type ItemCategory = {
  id: string;
  category_name: string;
  parent_id?: string | null;
  description?: string | null;
  created_at: string;
  updated_at: string;
};

export type ItemCategoryBody = {
  category_name: string;
  parent_id?: string | null;
  description?: string | null;
};

export const listItemCategories = (
  params?: PageParams & { parent_id?: string }
) =>
  http.request<ApiResponse<PageResult<ItemCategory>>>(
    "get",
    "/api/inventory_product_category/list",
    { params }
  );

export const listItemCategoryOptions = () =>
  http.request<
    ApiResponse<{
      items: { id: string; category_name: string; parent_id?: string | null }[];
    }>
  >("get", "/api/inventory_product_category/options");

export const createItemCategory = (data: ItemCategoryBody) =>
  http.request<ApiResponse<ItemCategory>>(
    "post",
    "/api/inventory_product_category/create",
    { data }
  );

export const updateItemCategory = (
  id: string,
  data: Partial<ItemCategoryBody>
) =>
  http.request<ApiResponse<ItemCategory>>(
    "put",
    `/api/inventory_product_category/update/${id}`,
    { data }
  );

export const deleteItemCategory = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/inventory_product_category/delete/${id}`
  );

// ───────── 物料 ─────────
export type Item = {
  can_edit_base_fields?: boolean;
  warehouse_ids?: string[];
  warehouses?: { id: string; warehouse_name: string; org_name: string; is_available: boolean }[];
  id: string;
  item_no: string;
  item_name: string;
  category_id?: string | null;
  category_name?: string | null;
  specification?: string | null;
  unit_code: string;
  sub_unit_code?: string | null;
  unit_price?: Decimalish | null;
  default_supplier_id?: string | null;
  default_supplier_name?: string | null;
  is_asset_managed: boolean;
  default_asset_type_code?: string | null;
  default_asset_management_mode_code?: "individual" | null;
  is_lot_controlled: boolean;
  shelf_life_days?: number | null;
  is_active: boolean;
  remark?: string | null;
  created_at: string;
  updated_at: string;
};

export type ItemBody = {
  warehouse_ids?: string[];
  expected_updated_at?: string;
  item_no?: string | null;
  item_name: string;
  category_id?: string | null;
  specification?: string | null;
  unit_code: string;
  sub_unit_code?: string | null;
  unit_price?: Decimalish | null;
  default_supplier_id?: string | null;
  is_asset_managed?: boolean;
  default_asset_type_code?: string | null;
  default_asset_management_mode_code?: "individual" | null;
  is_lot_controlled?: boolean;
  shelf_life_days?: number | null;
  is_active?: boolean;
  remark?: string | null;
};

export type ItemListParams = PageParams & {
  applicable_warehouse_id?: string;
  is_asset_managed?: boolean;
  category_id?: string;
  default_supplier_id?: string;
  warehouse_id?: string;
  is_active?: boolean;
};

export const listItems = (params?: ItemListParams) =>
  http.request<ApiResponse<PageResult<Item>>>(
    "get",
    "/api/inventory_product/list",
    { params }
  );

export const getItem = (id: string) =>
  http.request<ApiResponse<Item>>("get", `/api/inventory_product/detail/${id}`);

export type ItemWarehouseOption = { id: string; warehouse_name: string; org_name: string; label: string };
export const listItemWarehouseOptions = (action: "list" | "create" | "update" = "list") =>
  http.request<ApiResponse<{ items: ItemWarehouseOption[] }>>("get", "/api/inventory_product/warehouse-options", { params: { action } });

export const createItem = (data: ItemBody) =>
  http.request<ApiResponse<Item>>("post", "/api/inventory_product/create", {
    data
  });

export const updateItem = (id: string, data: Partial<ItemBody>) =>
  http.request<ApiResponse<Item>>(
    "put",
    `/api/inventory_product/update/${id}`,
    { data }
  );

export const deleteItem = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/inventory_product/delete/${id}`
  );

// ───────── 供应商 ─────────
export type SupplierCategory = {
  id: string;
  category_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export const listSupplierCategories = (
  params?: PageParams & { is_active?: boolean }
) =>
  http.request<ApiResponse<PageResult<SupplierCategory>>>(
    "get",
    "/api/supplier_category/list",
    { params }
  );

export const createSupplierCategory = (data: {
  category_name: string;
  is_active?: boolean;
}) =>
  http.request<ApiResponse<SupplierCategory>>(
    "post",
    "/api/supplier_category/create",
    { data }
  );

export const updateSupplierCategory = (
  id: string,
  data: { category_name?: string; is_active?: boolean }
) =>
  http.request<ApiResponse<SupplierCategory>>(
    "put",
    `/api/supplier_category/update/${id}`,
    { data }
  );

export const deleteSupplierCategory = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/supplier_category/delete/${id}`
  );

export type Supplier = {
  id: string;
  supplier_no: string;
  supplier_name: string;
  category_id?: string | null;
  category_name?: string | null;
  party_type_code: string;
  party_id?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  settlement_method_code?: string | null;
  settlement_cycle_code?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SupplierBody = {
  supplier_no?: string | null;
  supplier_name: string;
  category_id?: string | null;
  party_type_code?: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  settlement_method_code?: string | null;
  settlement_cycle_code?: string | null;
  is_active?: boolean;
};

export const listSuppliers = (
  params?: PageParams & { category_id?: string; is_active?: boolean }
) =>
  http.request<ApiResponse<PageResult<Supplier>>>("get", "/api/supplier/list", {
    params
  });

export const createSupplier = (data: SupplierBody) =>
  http.request<ApiResponse<Supplier>>("post", "/api/supplier/create", { data });

export const updateSupplier = (id: string, data: Partial<SupplierBody>) =>
  http.request<ApiResponse<Supplier>>("put", `/api/supplier/update/${id}`, {
    data
  });

export const deleteSupplier = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/supplier/delete/${id}`
  );

export type SupplierOption = {
  id: string;
  supplier_no: string;
  supplier_name: string;
  category_name?: string | null;
};

export const listSupplierOptions = (params?: {
  keyword?: string;
  active_only?: boolean;
}) =>
  http.request<ApiResponse<{ items: SupplierOption[] }>>(
    "get",
    "/api/supplier/options",
    { params }
  );

export type SupplierBankAccount = {
  id: string;
  supplier_id: string;
  account_name: string;
  /** 只返回脱敏账号 */
  account_no_masked?: string | null;
  bank_name?: string | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
};

export type SupplierBankAccountBody = {
  account_name: string;
  /** 明文账号，只写不读 */
  account_no: string;
  bank_name?: string | null;
  is_primary?: boolean;
};

export const listSupplierBankAccounts = (supplierId: string) =>
  http.request<ApiResponse<{ items: SupplierBankAccount[] }>>(
    "get",
    `/api/supplier/${supplierId}/bank_account/list`
  );

export const createSupplierBankAccount = (
  supplierId: string,
  data: SupplierBankAccountBody
) =>
  http.request<ApiResponse<SupplierBankAccount>>(
    "post",
    `/api/supplier/${supplierId}/bank_account/create`,
    { data }
  );

export const updateSupplierBankAccount = (
  supplierId: string,
  accountId: string,
  data: SupplierBankAccountBody
) =>
  http.request<ApiResponse<SupplierBankAccount>>(
    "put",
    `/api/supplier/${supplierId}/bank_account/update/${accountId}`,
    {
      data
    }
  );

export const deleteSupplierBankAccount = (
  supplierId: string,
  accountId: string
) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/supplier/${supplierId}/bank_account/delete/${accountId}`
  );
