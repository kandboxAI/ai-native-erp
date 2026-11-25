import type { Quote, QuoteLine } from "./api";

export function hasApprovalPriceChanges(quote: Quote, original?: Quote) {
  if (!original) return false;
  const lines = new Map(original.lines.map((line) => [line.id, line]));
  return quote.lines.some((line) => {
    const before = lines.get(line.id);
    if (!before || line.unit_price !== before.unit_price) return true;
    const tiers = new Map(
      (before.quantity_tiers || []).map((tier) => [tier.id, tier.unit_price]),
    );
    return (line.quantity_tiers || []).some(
      (tier) => tier.unit_price !== tiers.get(tier.id),
    );
  });
}

export function approvalBody(quote: Quote, reason: string, note = "") {
  return {
    version_no: quote.version_no,
    note,
    price_adjustment_reason: reason.trim(),
    lines: quote.lines.map((line) => ({
      id: line.id,
      lead_days: line.lead_days,
      unit_price: line.unit_price,
      quantity_tiers: (line.quantity_tiers || []).map((tier) => ({
        id: tier.id,
        unit_price: tier.unit_price,
      })),
    })),
  };
}

export function originalLine(quote: Quote | undefined, line: QuoteLine) {
  return quote?.lines.find((item) => item.id === line.id);
}
