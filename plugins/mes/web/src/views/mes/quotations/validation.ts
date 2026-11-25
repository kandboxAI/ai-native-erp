import type { Quote } from "./api";

export function validateRequirements(quote: Quote, submitting = false) {
  if (!quote.title.trim()) throw Error("请填写询价名称");
  if (!quote.customer_id) throw Error("请选择客户");
  if (!quote.lines.length) throw Error("请至少录入一项货品");
  quote.lines.forEach((line, index) => {
    const missing: string[] = [];
    if (!line.drawing_no.trim()) missing.push("图号");
    if (!line.description.trim()) missing.push("描述");
    if (!Number.isFinite(line.quantity) || line.quantity <= 0)
      missing.push("有效数量");
    if (!line.customer_material.trim()) missing.push("客户材料");
    if (missing.length)
      throw Error(
        `${line.drawing_no || `第 ${index + 1} 项货品`}：请填写${missing.join("、")}`,
      );
    if (submitting && !line.files.length)
      throw Error(`${line.drawing_no}：请上传图纸或模型`);
  });
}

export function validateEngineering(quote: Quote) {
  if (!quote.lines.length) throw Error("请至少录入一项货品");
  quote.lines.forEach((line) => {
    const missing: string[] = [];
    if (!line.quoted_material.trim()) missing.push("报价采用材料");
    if (
      line.unit_price == null ||
      !Number.isFinite(line.unit_price) ||
      line.unit_price < 0
    )
      missing.push("有效单价");
    if (missing.length)
      throw Error(`${line.drawing_no}：请填写${missing.join("、")}`);
    if (
      (line.quantity_tiers || []).some(
        (tier) =>
          tier.unit_price == null ||
          !Number.isFinite(tier.unit_price) ||
          tier.unit_price < 0,
      )
    )
      throw Error(`${line.drawing_no}：请完成所有数量档的报价`);
  });
}

export function validateApproval(quote: Quote) {
  validateEngineering(quote);
  if (!quote.lines.length) throw Error("请至少录入一项货品");
  quote.lines.forEach((line) => {
    if (
      line.lead_days == null ||
      !Number.isInteger(line.lead_days) ||
      line.lead_days < 1 ||
      line.lead_days > 3650
    )
      throw Error(`${line.drawing_no}：请填写最终交期（1–3650 个自然日）`);
  });
}
