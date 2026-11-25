/** 入库页面（form = inbound）的表单明细行；入库单本身是统一库存单据，见 inventoryManagement.ts。 */
import type { Decimalish } from "./inventoryManagement";

export type InboundFormLine = {
  key: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification?: string | null;
  unit_code: string;
  quantity: number;
  unit_price: number;
  lot_no?: string | null;
  production_date?: string | null;
  expiry_date?: string | null;
  remark?: string | null;
  available_quantity?: Decimalish | null;
};
