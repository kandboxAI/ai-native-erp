/** 出库页面（form = outbound）的表单明细行；出库单本身是统一库存单据，见 inventoryManagement.ts。 */
import type { Decimalish } from "@plugins/inv/web/src/api/inventoryManagement";

export type OutboundFormLine = {
  key: string;
  item_id: string;
  item_no: string;
  item_name: string;
  specification?: string | null;
  unit_code: string;
  quantity: number;
  lot_id?: string | null;
  remark?: string | null;
  /** 来源仓库的可用数量 */
  available_quantity?: Decimalish | null;
};
