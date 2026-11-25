import type { Quote, QuoteLine } from "./api";

export function fillHistoricalPrices(quote: Quote) {
  if (!["pending", "pricing"].includes(quote.status_code)) return;
  for (const line of quote.lines) {
    const previous = line.historical_reference;
    if (
      !previous?.is_compatible ||
      previous.currency !== quote.currency ||
      line.unit_price != null ||
      line.adopted_cnc_quote_id
    )
      continue;
    const price = Number(previous.unit_price);
    if (!Number.isFinite(price) || price < 0) continue;
    const source = `参考报价 ${previous.quote_no} R${previous.revision}；图号 ${line.drawing_no} / ${previous.drawing_revision}；历史数量 ${previous.quantity}，单价 ${previous.unit_price} ${previous.currency}。`;
    const note = line.engineering_note?.includes(source)
      ? line.engineering_note
      : [line.engineering_note, source].filter(Boolean).join("\n");
    // 保留原说明；不足以记录来源时只展示参考，避免自动补价后无法正常保存。
    if (note.length > 1000) continue;
    line.unit_price = price;
    if (!line.quoted_material) line.quoted_material = previous.quoted_material;
    if (line.weight_kg == null && previous.weight_kg != null)
      line.weight_kg = Number(previous.weight_kg);
    line.engineering_note = note;
  }
}

export const matchesDrawing = (line: QuoteLine, keyword: string) =>
  line.drawing_no
    .toLocaleLowerCase()
    .includes(keyword.trim().toLocaleLowerCase());

export function pageItems<T>(items: T[], page: number, size: number): T[] {
  return items.slice((page - 1) * size, page * size);
}

export const canSelectAdoption = (line: QuoteLine) => {
  const record = line.cnc_records?.[0];
  return (
    !!line.id &&
    !!record &&
    record.status_code === "completed" &&
    !record.is_stale
  );
};

export type AdoptionPreview = {
  line_id: string;
  can_adopt: boolean;
  cnc_quote_id?: string;
  quoted_material?: string;
  net_weight_kg?: string | null;
  cnc_unit_price?: string | number;
  cnc_currency?: string;
  suggested_unit_price?: string | number | null;
  price_message?: string;
  message: string;
};
export type AdoptionReview = AdoptionPreview & {
  drawing_no: string;
  unit_price: number | null;
  original_unit_price: number | null;
  state: "ready" | "blocked" | "success" | "failed";
};
export type AdoptionResult = {
  line_id: string;
  is_success: boolean;
  code: number;
  message: string;
};

export function reviewAdoptions(
  lines: QuoteLine[],
  items: AdoptionPreview[],
): AdoptionReview[] {
  const byId = new Map(lines.map((line) => [line.id, line]));
  return items.map((item) => {
    const line = byId.get(item.line_id);
    const price =
      item.suggested_unit_price == null
        ? null
        : Number(item.suggested_unit_price);
    const validPrice =
      price != null &&
      Number.isFinite(price) &&
      price >= 0 &&
      price <= 100000000;
    const canAdopt =
      !!line && item.can_adopt && validPrice && !!item.cnc_quote_id;
    return {
      ...item,
      drawing_no: line?.drawing_no || "货品已移除",
      unit_price: price ?? null,
      original_unit_price: line?.unit_price ?? null,
      can_adopt: canAdopt,
      state: canAdopt ? "ready" : "blocked",
      message: !line
        ? "货品已移除"
        : !item.can_adopt
          ? item.message
          : !validPrice
            ? item.price_message || "暂无可用的 AI 报价，请完成核算"
            : "确认后将 AI 报价写入实际对客单价",
    };
  });
}
