import { requestApi } from "@/api/client";
export interface StockRow {
  item_id: string; org_id: string; org_name: string; item_no: string;
  item_name: string; unit_code: string; quantity: string; available_quantity: string;
}
export const listInventoryStock = (page: number, keyword: string) =>
  requestApi<{ items: StockRow[]; total: number; page: number; page_size: number }>({
    path: "/api/inventory_item/list", data: { page, page_size: 20, keyword }
  });
