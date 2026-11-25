import { http } from "@/utils/http";
import { getToken } from "@/utils/auth";

export type QuantityTier = {
  id: string;
  quantity: string | number;
  unit_price: string | number;
};
export type ProductionDefaults = {
  unit_names: Record<string, string>;
  lines: {
    order_line_id: string;
    product_item_id: string | null;
    item_no: string | null;
    item_name: string | null;
    unit_code: string | null;
    order_unit_code: string | null;
    material: string;
    unit_name: string | null;
    match_source: string | null;
    match_status: string;
    is_create_product: boolean;
    can_create: boolean;
  }[];
};
export type OrderSource = {
  id: string;
  quotation_id: string;
  quotation_version_no: number;
  quote_no: string;
  revision: number;
  org_id: string;
  customer_id: string;
  customer_name_snapshot: string;
  currency: string;
  drawing_no: string;
  drawing_revision: string;
  description: string;
  material: string;
  quantity: string | number;
  unit_price: string | number;
  unit_name: string;
  lead_days: number;
  quantity_tiers: QuantityTier[];
};
export type SourceCustomer = { id: string; name: string };
export type OrderLine = {
  id: string;
  quotation_line_id: string;
  quotation_tier_id?: string;
  quote_no_snapshot: string;
  quotation_revision_snapshot: number;
  drawing_no_snapshot: string;
  drawing_revision_snapshot: string;
  description_snapshot: string;
  material_snapshot: string;
  unit_name_snapshot: string;
  quoted_quantity_snapshot: string;
  original_unit_price_snapshot: string;
  discount_rate?: string | number | null;
  quantity: string;
  unit_price: string;
  due_date: string;
  adjustment_reason: string;
  allocated_quantity: string;
  remaining_quantity: string;
};
export type CustomerOrder = {
  id: string;
  org_id: string;
  version_no: number;
  order_no: string;
  customer_name_snapshot: string;
  customer_po_no: string;
  currency: string;
  status_code: "confirmed" | "approved" | "cancelled";
  amount: string;
  line_count: number;
  remaining_count: number;
  note: string;
  events?: {
    id: string;
    action_key: string;
    note: string;
    created_at: string;
  }[];
  lines: OrderLine[];
  productions: {
    id: string;
    production_order_id: string;
    production_order_no: string;
    created_at: string;
    lines: {
      order_line_id: string;
      work_order_id: string;
      quantity: string;
      status_code: string;
    }[];
  }[];
};
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export async function orderRequest<T>(
  path: string,
  method: "get" | "post" | "put" = "get",
  data?: unknown,
  params?: unknown,
) {
  const identity = getToken()?.userId;
  try {
    const response = await http.request<{
      code: number;
      message: string;
      data: T;
    }>(method, `/api/mes/sales-orders${path}`, {
      data,
      params,
      timeout: 120000,
    });
    if (identity !== getToken()?.userId)
      throw Error("登录身份已变化，请重新进入客户订单");
    if (response.code !== 0) throw Error(response.message || "订单操作失败");
    return response.data;
  } catch (cause: any) {
    throw Error(
      cause?.response?.data?.message || cause?.message || "订单操作失败",
    );
  }
}
export function deliveryDate(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
