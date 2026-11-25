/**
 * 物资与库存接口（统一库存模型）。
 *
 * - 入库、出库、调拨、借出归还、报损都是同一张库存单据（/api/inventory_stock_order），按单据类型区分；
 *   单据类型从后端读取（/api/inventory_stock_order_type/options?form=...），前端不写死类型选项。
 * - 确认（confirm）即记账：生成库存流水并更新余额；余额不足返回 409。
 * - 库存数量只在余额（/api/inventory_item/list 汇总、/api/inventory_item/balance/list 明细），
 *   变化记录在流水（/api/inventory_movement/list）。
 * - 字段名与数据库字段一致（snake_case）；数量、金额以字符串返回（Decimal），数量展示保留字符串精度。
 */
import { http } from "@/utils/http";
import { formatQuantity as formatQuantityDisplay } from "@/utils/quantity";

export type ApiResponse<T> = { code: number; message: string; data: T };
export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type PageParams = {
  warehouse_scope_key?: string;
  page?: number;
  page_size?: number;
  keyword?: string;
};
export type Decimalish = string | number;

/** 单据表单：决定类型出现在哪个页面、使用哪组权限 */
export type StockOrderForm =
  "inbound" | "outbound" | "transfer" | "lend" | "return" | "damage" | "adjust";

export type StockDirection = "in" | "out" | "move" | "status" | "adjust";
export type StockOrderStatus =
  "draft" | "submitted" | "approved" | "confirmed" | "voided";

export const STOCK_ORDER_STATUS_LABELS: Record<StockOrderStatus, string> = {
  draft: "草稿",
  submitted: "待审批",
  approved: "已审批",
  confirmed: "已确认",
  voided: "已作废",
};

/** 各表单对应的权限资源（沿用原页面权限标识） */
export const FORM_PERMISSION_RESOURCE: Record<StockOrderForm, string> = {
  inbound: "inventory_inbound",
  outbound: "inventory_outbound",
  transfer: "inventory_transfer",
  lend: "inventory_lend",
  return: "inventory_lend",
  damage: "inventory_damage",
  adjust: "inventory_stocktake",
};

// ───────── 字典选项 ─────────
export type DictOption = { value: string; label: string };
export type InventoryMetaOptions = Record<string, DictOption[]>;

export const getInventoryMetaOptions = () =>
  http.request<ApiResponse<InventoryMetaOptions>>(
    "get",
    "/api/inventory_meta/options",
  );

let metaCache: Promise<InventoryMetaOptions> | null = null;
/** 页面共享的字典选项（计量单位、库存状态、处理方式等），只请求一次 */
export function loadInventoryMeta(
  force = false,
): Promise<InventoryMetaOptions> {
  if (!metaCache || force) {
    metaCache = getInventoryMetaOptions()
      .then((res) => (res.code === 0 ? res.data : {}))
      .catch(() => {
        metaCache = null;
        return {};
      });
  }
  return metaCache;
}

export function dictLabel(
  meta: InventoryMetaOptions,
  dictCode: string,
  value?: string | null,
): string {
  if (!value) return "";
  return meta[dictCode]?.find((o) => o.value === value)?.label ?? value;
}

// ───────── 单据类型 ─────────
export type StockOrderType = {
  id: string;
  type_no: string;
  type_name: string;
  direction_code: StockDirection;
  default_from_status_code?: string | null;
  default_to_status_code?: string | null;
  is_approval_required: boolean;
  required_field_config?: Record<string, unknown> | null;
  is_negative_allowed: boolean;
  is_builtin: boolean;
  is_source_managed?: boolean;
  is_active: boolean;
  sort_no?: number | null;
  form?: StockOrderForm | null;
  required_fields: string[];
  created_at: string;
  updated_at: string;
};

export const listStockOrderTypeOptions = (params?: {
  warehouse_scope_key?: string;
  form?: StockOrderForm;
  direction_code?: StockDirection;
  include_inactive?: boolean;
}) =>
  http.request<ApiResponse<{ items: StockOrderType[] }>>(
    "get",
    "/api/inventory_stock_order_type/options",
    { params },
  );

export const listStockOrderTypes = (
  params?: PageParams & { direction_code?: string; is_active?: boolean },
) =>
  http.request<ApiResponse<PageResult<StockOrderType>>>(
    "get",
    "/api/inventory_stock_order_type/list",
    { params },
  );

export type StockOrderTypeUpdateBody = Partial<
  Pick<
    StockOrderType,
    | "type_name"
    | "default_from_status_code"
    | "default_to_status_code"
    | "is_approval_required"
    | "required_field_config"
    | "is_negative_allowed"
    | "is_active"
    | "sort_no"
  >
>;

export const createStockOrderType = (
  data: StockOrderTypeUpdateBody & {
    type_no: string;
    type_name: string;
    direction_code: StockDirection;
  },
) =>
  http.request<ApiResponse<StockOrderType>>(
    "post",
    "/api/inventory_stock_order_type/create",
    { data },
  );

export const updateStockOrderType = (
  id: string,
  data: StockOrderTypeUpdateBody,
) =>
  http.request<ApiResponse<StockOrderType>>(
    "put",
    `/api/inventory_stock_order_type/update/${id}`,
    { data },
  );

export const deleteStockOrderType = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/inventory_stock_order_type/delete/${id}`,
  );

// ───────── 仓库 ─────────
export type Warehouse = {
  requisition_approval_department_id?: string | null;
  requisition_approval_department_name?: string | null;
  requisition_approval_label?: string;
  default_asset_department_id?: string | null;
  default_asset_custodian_user_id?: string | null;
  default_asset_department_name?: string | null;
  default_asset_custodian_name?: string | null;
  id: string;
  org_id: string;
  org_name?: string | null;
  warehouse_no: string;
  warehouse_name: string;
  location_id?: string | null;
  location_name?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  coordinate_system_code?: string | null;
  location?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type WarehouseBody = {
  requisition_approval_department_id?: string | null;
  default_asset_department_id?: string | null;
  default_asset_custodian_user_id?: string | null;
  org_id: string;
  warehouse_no: string;
  warehouse_name: string;
  location_id?: string | null;
  location?: string | null;
  is_active?: boolean;
};

export type WarehouseRequisitionScope = {
  warehouse_id: string;
  warehouse_name: string;
  owner_org_id: string;
  owner_org_name: string;
  expected_updated_at: string;
  recipient_org_ids: string[];
  organizations: Array<{
    id: string;
    org_name: string;
    parent_id: string | null;
    is_available: boolean;
  }>;
};

export const getWarehouseRequisitionScope = (id: string) =>
  http.request<ApiResponse<WarehouseRequisitionScope>>(
    "get",
    `/api/inventory_warehouse/${id}/requisition-scope`,
  );

export const saveWarehouseRequisitionScope = (
  id: string,
  data: {
    expected_updated_at: string;
    recipient_org_ids: string[];
  },
) =>
  http.request<ApiResponse<WarehouseRequisitionScope>>(
    "put",
    `/api/inventory_warehouse/${id}/requisition-scope`,
    { data },
  );

export const listWarehouses = (
  params?: PageParams & { org_id?: string; is_active?: boolean },
) =>
  http.request<ApiResponse<PageResult<Warehouse>>>(
    "get",
    "/api/inventory_warehouse/list",
    { params },
  );
export const createWarehouse = (data: WarehouseBody) =>
  http.request<ApiResponse<Warehouse>>(
    "post",
    "/api/inventory_warehouse/create",
    {
      data,
    },
  );
export const listWarehouseCreateOrgOptions = () =>
  http.request<ApiResponse<{ items: { value: string; label: string }[] }>>(
    "get",
    "/api/inventory_warehouse/create_org_options",
  );
export const listWarehouseAssetDepartmentOptions = (params: { org_id: string; permission_key: string }) =>
  http.request<ApiResponse<{ items: { value: string; label: string; org_id: string }[] }>>(
    "get", "/api/inventory_warehouse/department-options", { params }
  );
export const listWarehouseAssetCustodianOptions = (params: { org_id: string; permission_key: string }) =>
  http.request<ApiResponse<{ items: { value: string; label: string; org_id: string }[] }>>(
    "get", "/api/inventory_warehouse/custodian-options", { params }
  );
export const updateWarehouse = (
  id: string,
  data: Partial<Pick<WarehouseBody, "warehouse_name" | "location" | "location_id" | "default_asset_department_id" | "default_asset_custodian_user_id" | "requisition_approval_department_id">>
) =>
  http.request<ApiResponse<Warehouse>>(
    "put",
    `/api/inventory_warehouse/update/${id}`,
    { data },
  );
export const deleteWarehouse = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/inventory_warehouse/delete/${id}`,
  );

export type WarehouseOption = {
  default_asset_department_id?: string | null;
  default_asset_custodian_user_id?: string | null;
  id: string;
  org_id: string;
  org_name?: string | null;
  warehouse_no: string;
  warehouse_name: string;
  warehouse_type_code: string;
  location_id?: string | null;
  location?: string | null;
  /** 组织 / 仓库 */
  label: string;
};

export const listWarehouseOptions = (params?: {
  warehouse_scope_key?: string;
  org_id?: string;
  all_orgs?: boolean;
}) =>
  http.request<ApiResponse<{ items: WarehouseOption[] }>>(
    "get",
    "/api/inventory_warehouse/options",
    { params },
  );

// ───────── 物料选择 ─────────
export type ItemOption = {
  is_asset_managed?: boolean;
  default_asset_type_code?: string | null;
  default_asset_management_mode_code?: string | null;
  id: string;
  item_no: string;
  item_name: string;
  category_id?: string | null;
  category_name?: string | null;
  specification?: string | null;
  unit_code: string;
  unit_price?: Decimalish | null;
  is_lot_controlled: boolean;
  /** 传 warehouse_id / org_id 时返回可用数量 */
  available_quantity?: Decimalish | null;
};

export const listItemOptions = (params?: {
  inbound_warehouse_id?: string;
  inbound_action?: "create" | "update";
  item_id?: string;
  is_asset_managed?: boolean;
  keyword?: string;
  category_id?: string;
  warehouse_id?: string;
  org_id?: string;
  in_stock_only?: boolean;
  stock_status_code?: string;
  usage_scope_code?: "general_warehouse" | "canteen_warehouse";
  limit?: number;
}) =>
  http.request<ApiResponse<{ items: ItemOption[] }>>(
    "get",
    "/api/inventory_product/options",
    { params },
  );

export type LotOption = {
  id: string;
  lot_no: string;
  production_date?: string | null;
  expiry_date?: string | null;
  supplier_id?: string | null;
  available_quantity: Decimalish;
};

export const listLotOptions = (params: {
  item_id: string;
  warehouse_id?: string;
  stock_status_code?: string;
  in_stock_only?: boolean;
}) =>
  http.request<ApiResponse<{ items: LotOption[] }>>(
    "get",
    "/api/inventory_item/lots",
    {
      params,
    },
  );

// ───────── 库存查询 ─────────
export type InventoryAlertStatus =
  "unconfigured" | "out_of_stock" | "low_stock" | "normal" | "overstock";
export type InventoryAlertFilter = InventoryAlertStatus | "replenishment";

export const ALERT_STATUS_LABELS: Record<InventoryAlertStatus, string> = {
  unconfigured: "未配置",
  out_of_stock: "缺货",
  low_stock: "库存不足",
  normal: "正常",
  overstock: "库存积压",
};

/** 库存查询：物料 × 仓库汇总 */
export type StockSummaryRow = {
  item_id: string;
  org_id: string;
  org_name: string;
  warehouse_id?: string;
  warehouse_name?: string;
  item_no: string;
  item_name: string;
  category_id?: string | null;
  category_name?: string | null;
  specification?: string | null;
  unit_code: string;
  unit_price?: Decimalish | null;
  min_quantity?: Decimalish | null;
  max_quantity?: Decimalish | null;
  /** 账面数量（含借出） */
  quantity: Decimalish;
  /** 可用数量（预警口径） */
  available_quantity: Decimalish;
  lent_quantity: Decimalish;
  reserved_quantity: Decimalish;
  stock_alert_status: InventoryAlertStatus;
  stock_alert_label: string;
  suggested_replenishment_quantity: Decimalish;
  inventory_value: Decimalish;
  updated_at?: string | null;
};

export type StockSummaryParams = PageParams & {
  org_id?: string;
  warehouse_id?: string;
  category_id?: string;
  item_id?: string;
  alert_status?: InventoryAlertFilter;
  include_zero?: boolean;
};

export const listStockSummary = (params: StockSummaryParams) =>
  http.request<ApiResponse<PageResult<StockSummaryRow>>>(
    "get",
    "/api/inventory_item/list",
    { params },
  );

export type StockAlertParams = PageParams & {
  org_id?: string;
  warehouse_id?: string;
  category_id?: string;
  item_id?: string;
  status_code?: "replenishment" | "out_of_stock" | "low_stock" | "unconfigured";
};

export type LowStockAlertRow = Pick<
  StockSummaryRow,
  | "item_id"
  | "org_id"
  | "org_name"
  | "warehouse_id"
  | "warehouse_name"
  | "item_no"
  | "item_name"
  | "category_id"
  | "category_name"
  | "specification"
  | "unit_code"
  | "min_quantity"
  | "max_quantity"
  | "available_quantity"
  | "stock_alert_status"
  | "stock_alert_label"
  | "suggested_replenishment_quantity"
  | "updated_at"
>;

/** 后勤低库存补货预警：仅返回缺货或低于安全库存的物料 */
export const listLowStockAlerts = (params: StockAlertParams) =>
  http.request<ApiResponse<PageResult<LowStockAlertRow>>>(
    "get",
    "/api/inventory_stock_alert/list",
    { params },
  );

export type StockThresholdBody = {
  min_quantity: Decimalish;
  max_quantity: Decimalish;
};

export type StockSettingStatusFilter =
  "all" | "configured" | InventoryAlertStatus;

export type StockSettingParams = PageParams & {
  warehouse_scope_key?: string;
  org_id?: string;
  warehouse_id?: string;
  category_id?: string;
  item_id?: string;
  keyword?: string;
  status_code?: StockSettingStatusFilter;
};

export type StockSettingRow = Pick<
  StockSummaryRow,
  | "item_id"
  | "org_id"
  | "org_name"
  | "warehouse_id"
  | "warehouse_name"
  | "item_no"
  | "item_name"
  | "category_id"
  | "category_name"
  | "specification"
  | "unit_code"
  | "min_quantity"
  | "max_quantity"
  | "available_quantity"
  | "stock_alert_status"
  | "stock_alert_label"
  | "updated_at"
>;

/** 安全库存设置：已有库存余额或已有阈值的物料 × 仓库组合 */
export const listStockSettings = (params: StockSettingParams) =>
  http.request<ApiResponse<PageResult<StockSettingRow>>>(
    "get",
    "/api/inventory_item_warehouse_setting/list",
    { params },
  );

export const configureStockThreshold = (
  itemId: string,
  warehouseId: string,
  data: StockThresholdBody,
) =>
  http.request<
    ApiResponse<
      StockThresholdBody & {
        item_id: string;
        warehouse_id: string;
        org_id: string;
      }
    >
  >("put", `/api/inventory_stock_alert/${itemId}/${warehouseId}/threshold`, {
    data,
  });

/** 新增或调整安全库存设置；支持尚未产生库存余额的物料仓库组合 */
export const saveStockSetting = (
  itemId: string,
  warehouseId: string,
  data: StockThresholdBody,
) =>
  http.request<
    ApiResponse<
      StockThresholdBody & {
        item_id: string;
        warehouse_id: string;
        org_id: string;
      }
    >
  >("put", `/api/inventory_item_warehouse_setting/${itemId}/${warehouseId}`, {
    data,
  });

/** 余额明细：物料 × 仓库 × 批次 × 库存状态 */
export type StockBalanceRow = {
  id: string;
  org_id: string;
  org_name: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification?: string | null;
  unit_code: string;
  warehouse_id: string;
  warehouse_no: string;
  warehouse_name: string;
  lot_id?: string | null;
  lot_no?: string | null;
  production_date?: string | null;
  expiry_date?: string | null;
  stock_status_code: string;
  quantity: Decimalish;
  reserved_quantity: Decimalish;
  available_quantity: Decimalish;
  version_no: number;
  updated_at: string;
};

export const listStockBalances = (
  params: PageParams & {
    org_id?: string;
    warehouse_id?: string;
    item_id?: string;
    lot_id?: string;
    stock_status_code?: string;
    include_zero?: boolean;
  },
) =>
  http.request<ApiResponse<PageResult<StockBalanceRow>>>(
    "get",
    "/api/inventory_item/balance/list",
    { params },
  );

/** 库存流水：每条可追溯到单据（stock_order_id）与单据明细（stock_order_line_id） */
export type StockTransactionRow = {
  id: string;
  org_id: string;
  transaction_no: string;
  transaction_type_code: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification?: string | null;
  unit_code: string;
  lot_id?: string | null;
  lot_no?: string | null;
  from_warehouse_id?: string | null;
  from_warehouse_label?: string | null;
  to_warehouse_id?: string | null;
  to_warehouse_label?: string | null;
  from_stock_status_code?: string | null;
  to_stock_status_code?: string | null;
  quantity: Decimalish;
  stock_order_id: string;
  stock_order_line_id: string;
  order_no: string;
  order_type_name: string;
  direction_code: StockDirection;
  occurred_at: string;
  created_by?: string | null;
};

export const listStockTransactions = (
  params: PageParams & {
    org_id?: string;
    item_id?: string;
    warehouse_id?: string;
    lot_id?: string;
    stock_order_id?: string;
    transaction_type_code?: string;
    occurred_date_start?: string;
    occurred_date_end?: string;
  },
) =>
  http.request<ApiResponse<PageResult<StockTransactionRow>>>(
    "get",
    "/api/inventory_movement/list",
    { params },
  );

// ───────── 库存单据 ─────────
export type WarehouseLabel = {
  org_id: string;
  org_name: string;
  warehouse_id: string;
  warehouse_name: string;
  label: string;
};

export type StockOrderLineTransaction = {
  id: string;
  transaction_no: string;
  transaction_type_code: string;
  lot_id?: string | null;
  lot_no?: string | null;
  from_warehouse_id?: string | null;
  to_warehouse_id?: string | null;
  from_stock_status_code?: string | null;
  to_stock_status_code?: string | null;
  quantity: Decimalish;
  occurred_at: string;
};

export type StockOrderLine = {
  is_asset_managed?: boolean;
  default_asset_type_code?: string | null;
  default_asset_management_mode_code?: string | null;
  tracking?: Record<string, any>;
  id: string;
  org_id: string;
  stock_order_id: string;
  line_no: number;
  item_id: string;
  item_no?: string | null;
  item_name?: string | null;
  specification?: string | null;
  lot_id?: string | null;
  lot_no?: string | null;
  production_date?: string | null;
  expiry_date?: string | null;
  from_warehouse_id?: string | null;
  to_warehouse_id?: string | null;
  from_warehouse?: WarehouseLabel | null;
  to_warehouse?: WarehouseLabel | null;
  from_stock_status_code?: string | null;
  to_stock_status_code?: string | null;
  quantity: Decimalish;
  unit_code: string;
  unit_price?: Decimalish | null;
  amount?: Decimalish | null;
  source_line_id?: string | null;
  counted_quantity?: Decimalish | null;
  remark?: string | null;
  /** 借出行：已归还 / 未归还数量 */
  returned_quantity: Decimalish;
  unreturned_quantity: Decimalish;
  transactions?: StockOrderLineTransaction[];
  created_at: string;
  updated_at: string;
};

export type RelatedStockOrder = {
  id: string;
  order_no: string;
  status_code: StockOrderStatus;
  business_date: string;
  confirmed_at?: string | null;
  is_reversal: boolean;
};

/** 列表逐行物料摘要，数量始终与单据明细的单位配对。 */
export type StockOrderItemSummary = {
  line_no: number;
  item_name: string;
  quantity: Decimalish;
  unit_code: string;
};

export type StockOrder = {
  id: string;
  org_id: string;
  org_name?: string | null;
  order_no: string;
  order_type_id: string;
  order_type?: StockOrderType | null;
  order_type_name?: string | null;
  direction_code?: StockDirection | null;
  form?: StockOrderForm | null;
  status_code: StockOrderStatus;
  business_date: string;
  from_warehouse_id?: string | null;
  to_warehouse_id?: string | null;
  from_warehouse?: WarehouseLabel | null;
  to_warehouse?: WarehouseLabel | null;
  counterparty_party_id?: string | null;
  counterparty_name_snapshot?: string | null;
  department_id?: string | null;
  department_name?: string | null;
  purpose?: string | null;
  reason?: string | null;
  handling_method_code?: string | null;
  expected_return_date?: string | null;
  source_doc_type_code?: string | null;
  source_doc_id?: string | null;
  reversal_of_order_id?: string | null;
  total_amount?: Decimalish | null;
  currency_code?: string | null;
  confirmed_at?: string | null;
  confirmed_by?: string | null;
  confirmed_by_name?: string | null;
  voided_at?: string | null;
  voided_by?: string | null;
  voided_by_name?: string | null;
  void_reason?: string | null;
  remark?: string | null;
  flex_form?: Record<string, unknown>;
  created_at: string;
  created_by?: string | null;
  created_by_name?: string | null;
  updated_at: string;
  line_count: number;
  total_quantity: Decimalish;
  item_names: string;
  item_summaries: StockOrderItemSummary[];
  /** 详情接口返回 */
  lines?: StockOrderLine[];
  related_orders?: RelatedStockOrder[];
  /** 确认接口返回：本次记账触发的库存预警 */
  stock_alerts?: Record<string, unknown>[];
};

export type StockOrderListParams = PageParams & {
  form?: StockOrderForm;
  direction_code?: StockDirection;
  order_type_id?: string;
  /** 多个状态用逗号分隔 */
  status_code?: string;
  org_id?: string;
  warehouse_id?: string;
  item_id?: string;
  business_date_start?: string;
  business_date_end?: string;
  has_unreturned?: boolean;
};

/** 按明细展开的列表行：明细字段 + order（单据头） */
export type StockOrderLineRow = StockOrderLine & { order: StockOrder };

export type StockOrderLineWrite = {
  tracking?: Record<string, any>;
  item_id: string;
  lot_id?: string | null;
  /** 入库：按批次号查找或新建批次 */
  lot_no?: string | null;
  production_date?: string | null;
  expiry_date?: string | null;
  from_warehouse_id?: string | null;
  to_warehouse_id?: string | null;
  from_stock_status_code?: string | null;
  to_stock_status_code?: string | null;
  quantity?: Decimalish | null;
  unit_code?: string | null;
  unit_price?: Decimalish | null;
  source_line_id?: string | null;
  counted_quantity?: Decimalish | null;
  remark?: string | null;
};

export type StockOrderHeaderWrite = {
  org_id?: string | null;
  business_date?: string | null;
  from_warehouse_id?: string | null;
  to_warehouse_id?: string | null;
  /** 供应商：写入往来方与名称快照 */
  supplier_id?: string | null;
  counterparty_party_id?: string | null;
  /** 领用人 / 借用人为本校用户时传 */
  counterparty_user_id?: string | null;
  counterparty_name_snapshot?: string | null;
  department_id?: string | null;
  purpose?: string | null;
  reason?: string | null;
  handling_method_code?: string | null;
  expected_return_date?: string | null;
  currency_code?: string | null;
  remark?: string | null;
};

export type StockOrderCreateBody = StockOrderHeaderWrite & {
  order_type_id: string;
  lines: StockOrderLineWrite[];
  /** 保存后提交 */
  submit?: boolean;
  /** 保存后直接确认记账（类型需要审批时不可用） */
  confirm?: boolean;
};

export type StockOrderUpdateBody = StockOrderHeaderWrite & {
  lines?: StockOrderLineWrite[];
};

export const listStockOrders = (params: StockOrderListParams) =>
  http.request<ApiResponse<PageResult<StockOrder>>>(
    "get",
    "/api/inventory_stock_order/list",
    { params },
  );

export const listStockOrderLines = (
  params: StockOrderListParams & { item_keyword?: string },
) =>
  http.request<ApiResponse<PageResult<StockOrderLineRow>>>(
    "get",
    "/api/inventory_stock_order/line/list",
    { params },
  );

export const getStockOrder = (id: string) =>
  http.request<ApiResponse<StockOrder>>(
    "get",
    `/api/inventory_stock_order/detail/${id}`,
  );

export const createStockOrder = (data: StockOrderCreateBody) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    "/api/inventory_stock_order/create",
    {
      data,
    },
  );

export const batchCreateStockOrders = (orders: StockOrderCreateBody[]) =>
  http.request<ApiResponse<{ items: StockOrder[]; count: number }>>(
    "post",
    "/api/inventory_stock_order/batch_create",
    { data: { orders } },
  );

export const updateStockOrder = (id: string, data: StockOrderUpdateBody) =>
  http.request<ApiResponse<StockOrder>>(
    "put",
    `/api/inventory_stock_order/update/${id}`,
    { data },
  );

export const deleteStockOrder = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/inventory_stock_order/delete/${id}`,
  );

export const submitStockOrder = (id: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/submit/${id}`,
  );

export const approveStockOrder = (id: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/approve/${id}`,
  );

export const rejectStockOrder = (id: string, reason?: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/reject/${id}`,
    { data: { reason: reason ?? null } },
  );

/** 确认 = 记账；余额不足时后端返回 409 */
export const confirmStockOrder = (id: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/confirm/${id}`,
  );

export type InboundOverstockWarning = {
  item_id: string;
  item_name: string;
  unit_code: string;
  current_quantity: Decimalish;
  inbound_quantity: Decimalish;
  projected_quantity: Decimalish;
  max_quantity: Decimalish;
};

export const previewStockOrderWarnings = (id: string) =>
  http.request<ApiResponse<{ warnings: InboundOverstockWarning[] }>>(
    "get",
    `/api/inventory_stock_order/confirm-preview/${id}`,
  );

export const voidStockOrder = (id: string, voidReason?: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/void/${id}`,
    { data: { void_reason: voidReason ?? null } },
  );

/** 冲销已确认的单据（新建冲销单并反向记账） */
export const reverseStockOrder = (id: string, reason?: string) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/reverse/${id}`,
    { data: { void_reason: reason ?? null } },
  );

/** 按借出单生成并确认归还单；不传 lines 时归还全部未归还数量 */
export const returnLendOrder = (
  lendOrderId: string,
  data?: {
    lines?: { source_line_id: string; quantity: Decimalish; tracking?: Record<string, any> }[];
    business_date?: string | null;
    remark?: string | null;
  },
) =>
  http.request<ApiResponse<StockOrder>>(
    "post",
    `/api/inventory_stock_order/return/${lendOrderId}`,
    { data: data ?? {} },
  );

export type PersonnelOptions = {
  departments: { id: string; department_name: string }[];
  users: {
    user_id: string;
    party_id?: string | null;
    display_name: string;
    department_id?: string | null;
    department_name?: string | null;
  }[];
};

export const listPersonnelOptions = (orgId?: string) =>
  http.request<ApiResponse<PersonnelOptions>>(
    "get",
    "/api/inventory_stock_order/personnel-options",
    { params: { org_id: orgId } },
  );

// ───────── 显示工具 ─────────
export function toNumber(value: Decimalish | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatQuantity(value: Decimalish | null | undefined): string {
  return formatQuantityDisplay(value);
}

export function formatMoney(value: Decimalish | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return `¥${toNumber(value).toFixed(2)}`;
}
export type WarehouseManagementAccess = {
  warehouse_id: string;
  warehouse_name: string;
  expected_updated_at: string;
  user_ids: string[];
  users: { id: string; display_name: string; is_available: boolean; is_recommended?: boolean }[];
};

export const getWarehouseManagementAccess = (warehouseId: string) =>
  http.request<{ code: number; message: string; data: WarehouseManagementAccess }>(
    "get", `/api/inventory_warehouse/${warehouseId}/management-access`,
  );

export const saveWarehouseManagementAccess = (warehouseId: string, data: {
  expected_updated_at: string; user_ids: string[];
}) => http.request<{ code: number; message: string; data: WarehouseManagementAccess }>(
  "put", `/api/inventory_warehouse/${warehouseId}/management-access`, { data },
);
