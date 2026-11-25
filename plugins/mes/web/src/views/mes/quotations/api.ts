import { http } from "@/utils/http";
import { getToken } from "@/utils/auth";
export type QuoteFile = {
  attachment_id: string;
  kind: "pdf" | "model";
  name: string;
  size: number;
};
export type CncRecord = {
  id: string;
  part_id: string;
  is_stale: boolean;
  created_at: string;
  status_code: string;
  stage: string;
};
export type CncProgress = {
  lines: { id: string; cnc_records: CncRecord[] }[];
};
export type ExchangeRateReference = {
  base: string;
  quote: string;
  rate: string;
  rate_date: string;
  provider: string;
  fetched_at: string;
  reference: string;
};
export type QuoteLine = {
  historical_reference?: {
    quotation_line_id: string;
    quote_no: string;
    revision: number;
    quoted_at: string;
    currency: string;
    drawing_revision: string;
    quoted_material: string;
    quantity: string;
    unit_price: string;
    weight_kg: string | null;
    unit_name: string;
    is_compatible: boolean;
  };
  id?: string;
  drawing_no: string;
  drawing_revision: string;
  description: string;
  quantity: number;
  unit_name: string;
  customer_material: string;
  surface_treatment: string;
  note: string;
  quoted_material: string;
  weight_kg: number | null;
  unit_price: number | null;
  lead_days: number | null;
  engineering_note: string;
  adopted_cnc_quote_id?: string;
  files: QuoteFile[];
  cnc_records?: CncRecord[];
  quantity_tiers?: {
    id?: string;
    quantity: number;
    unit_price: number | null;
    calculation_note?: string;
  }[];
};
export type Quote = {
  id?: string;
  customer_order_count?: number;
  org_id?: string;
  quote_no: string;
  revision: number;
  version_no: number;
  title: string;
  customer_id: string;
  customer_name_snapshot?: string;
  currency: string;
  deadline: string | null;
  status_code: string;
  note: string;
  return_reason?: string;
  lines: QuoteLine[];
  events?: {
    id: string;
    action_key: string;
    note: string;
    created_at: string;
  }[];
};
export async function request<T>(path: string, method = "get", data?: unknown) {
  const identity = getToken()?.userId;
  const result = await http
    .request<{ code: number; message: string; data: T }>(
      method as "get" | "post" | "put" | "delete",
      `/api/mes/quotations${path}`,
      {
        data,
        ...(data instanceof FormData
          ? { headers: { "Content-Type": undefined } }
          : {}),
        timeout: 120000,
      },
    )
    .catch(async (cause) => {
      throw await responseError(cause);
    });
  if (getToken()?.userId !== identity)
    throw Error("登录身份已变化，请重新加载询价");
  if (result.code !== 0)
    throw new QuotationError(result.message || "询价操作失败", result.code);
  return result.data;
}
export class QuotationError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
async function responseError(cause: {
  response?: { status?: number; data?: { message?: string } | Blob };
  message?: string;
}) {
  let data = cause?.response?.data;
  if (data instanceof Blob) {
    try {
      data = JSON.parse(await data.text());
    } catch {
      data = undefined;
    }
  }
  return new QuotationError(
    (data as { message?: string })?.message ||
      cause?.message ||
      "请求失败，请重试",
    cause?.response?.status,
  );
}
export function normalize(quote: Quote): Quote {
  return {
    ...quote,
    lines: quote.lines.map((line) => ({
      ...line,
      quantity: Number(line.quantity),
      weight_kg: line.weight_kg == null ? null : Number(line.weight_kg),
      unit_price: line.unit_price == null ? null : Number(line.unit_price),
      quantity_tiers: (line.quantity_tiers || []).map((tier) => ({
        ...tier,
        quantity: Number(tier.quantity),
        unit_price: tier.unit_price == null ? null : Number(tier.unit_price),
      })),
    })),
  };
}
export function requirements(quote: Quote) {
  return {
    org_id: quote.org_id,
    version_no: quote.version_no,
    title: quote.title,
    customer_id: quote.customer_id,
    currency: quote.currency,
    deadline: quote.deadline || null,
    note: quote.note,
    lines: quote.lines.map((line) => ({
      ...(line.id ? { id: line.id } : {}),
      drawing_no: line.drawing_no,
      drawing_revision: line.drawing_revision,
      description: line.description,
      quantity: line.quantity,
      unit_name: line.unit_name,
      customer_material: line.customer_material,
      surface_treatment: line.surface_treatment,
      note: line.note,
      quantity_tiers: (line.quantity_tiers || []).map((tier) => tier.quantity),
      files: line.files.map((file) => ({
        attachment_id: file.attachment_id,
        kind: file.kind,
      })),
    })),
  };
}
export function engineering(quote: Quote) {
  return {
    version_no: quote.version_no,
    lines: quote.lines.map((line) => ({
      id: line.id,
      quoted_material: line.quoted_material,
      weight_kg: line.weight_kg,
      unit_price: line.unit_price,
      engineering_note: line.engineering_note || "",
      quantity_tiers: (line.quantity_tiers || []).map((tier) => ({
        id: tier.id,
        unit_price: tier.unit_price,
        calculation_note: tier.calculation_note || "",
      })),
    })),
  };
}
export const DEFAULT_DRAWING_REVISION = "A";
export const newLine = (): QuoteLine => ({
  drawing_no: "",
  drawing_revision: DEFAULT_DRAWING_REVISION,
  description: "",
  quantity: 1,
  unit_name: "件",
  customer_material: "",
  surface_treatment: "",
  note: "",
  quoted_material: "",
  weight_kg: null,
  unit_price: null,
  lead_days: null,
  engineering_note: "",
  files: [],
});

export async function download(path: string, name: string) {
  const identity = getToken()?.userId;
  const blob = await http
    .request<Blob>("get", path, {
      responseType: "blob",
      timeout: 120000,
    })
    .catch(async (cause) => {
      throw await responseError(cause);
    });
  if (getToken()?.userId !== identity)
    throw Error("登录身份已变化，已取消下载");
  if (blob.type.includes("json")) {
    const result = JSON.parse(await blob.text());
    throw Error(result.message || "下载失败");
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
