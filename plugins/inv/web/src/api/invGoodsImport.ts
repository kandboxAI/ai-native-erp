/** 物资 Excel 导入：物料分类、物料档案、库存盘点（生成盘点调整单据并记账）。 */
import { http } from "@/utils/http";
import type { ExcelImportValidation } from "@plugins/inv/web/src/views/inventory/shared/components/ExcelImportDialog/types";

export type GoodsImportKind = "category" | "product" | "stock";

export type GoodsImportResult = ExcelImportValidation & {
  summary: {
    rows: number;
    categories: number;
    items: number;
    warehouses: number;
  };
  created?: number;
  updated?: number;
  unchanged?: number;
  /** 库存盘点导入生成的盘点调整单据 */
  stock_order_ids?: string[];
};

type ApiResponse<T> = { code: number; message: string; data: T };

const endpoints: Record<GoodsImportKind, string> = {
  category: "/api/inventory_product_category/import",
  product: "/api/inventory_product/import",
  stock: "/api/inventory_item/import"
};

const uploadConfig = {
  timeout: 180_000,
  skipScheduler: true,
  transformRequest: [
    (data: unknown, headers: Record<string, unknown>) => {
      if (typeof FormData !== "undefined" && data instanceof FormData) {
        delete headers["Content-Type"];
      }
      return data;
    }
  ]
};

function form(file: File, allowUpdateExisting: boolean) {
  const data = new FormData();
  data.append("file", file);
  data.append("allow_update_existing", String(allowUpdateExisting));
  return data;
}

export function downloadGoodsImportTemplate(kind: GoodsImportKind) {
  return http.request<Blob>("get", `${endpoints[kind]}/template`, {
    responseType: "blob",
    timeout: 60_000
  });
}

/** 导出当前筛选下的全部物料，工作表及字段与导入模板一致。 */
export function exportGoodsTemplateData(params: Record<string, unknown>) {
  return http.request<Blob>("get", `${endpoints.product}/export`, {
    params,
    responseType: "blob",
    timeout: 120_000
  });
}

export function validateGoodsImport(
  kind: GoodsImportKind,
  file: File,
  allowUpdateExisting: boolean
) {
  return http.request<ApiResponse<GoodsImportResult>>(
    "post",
    `${endpoints[kind]}/validate`,
    {
      data: form(file, allowUpdateExisting),
      ...uploadConfig
    }
  );
}

export function executeGoodsImport(
  kind: GoodsImportKind,
  file: File,
  allowUpdateExisting: boolean
) {
  return http.request<ApiResponse<GoodsImportResult>>("post", endpoints[kind], {
    data: form(file, allowUpdateExisting),
    ...uploadConfig
  });
}
