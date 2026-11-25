/** 仅前端流程验证：固定示例参数与演示调度，不读取图纸内容，不调用加工报价/模型接口。 */
import {
  clone,
  saveQuote,
  type DemoState,
  type Quote,
  type QuoteLine,
} from "./model";

export type AiQuoteStatus =
  | "queued"
  | "running"
  | "needs_input"
  | "review"
  | "adopted"
  | "rejected"
  | "failed"
  | "stale";
export type AiOperation = {
  id: string;
  name: string;
  minutes_per_unit: number;
  hourly_rate_cny: number;
};
export type AiReview = {
  material: string;
  stock_weight_kg: number;
  material_price_cny: number;
  operations: AiOperation[];
  external_unit_cny: number;
  other_batch_cny: number;
  markup_percent: number;
  fx_rate: number | null;
  final_unit_price: number | null;
  lead_days: number;
  note: string;
};
export type AiCost = {
  material_unit_cny: number;
  machining_unit_cny: number;
  external_unit_cny: number;
  other_unit_cny: number;
  unit_cost_cny: number;
  total_cost_cny: number;
  unit_minutes: number;
};
export type AiQuoteTask = {
  id: string;
  batch_id: string;
  quote_id: string;
  quote_no: string;
  quote_revision: number;
  line_id: string;
  currency: string;
  input: QuoteLine;
  source_key: string;
  status: AiQuoteStatus;
  step: number;
  created_at: string;
  completed_at?: string;
  stage: string;
  missing: string[];
  error: string;
  review?: AiReview;
  cost?: AiCost;
  cost_key?: string;
  original_cost?: AiCost;
  original_review?: AiReview;
  adoption?: NonNullable<QuoteLine["ai_review"]>;
  rejection_reason?: string;
};
export const aiQuoteLabels: Record<AiQuoteStatus, string> = {
  queued: "排队中",
  running: "处理中",
  needs_input: "待补充",
  review: "待复核",
  adopted: "已采用",
  rejected: "不采用",
  failed: "失败",
  stale: "需重新分析",
};
export function aiSourceKey(quote: Quote, line: QuoteLine) {
  return JSON.stringify([
    quote.id,
    quote.revision,
    quote.customer_id,
    quote.currency,
    line.id,
    line.drawing_no,
    line.drawing_revision,
    line.description,
    line.quantity,
    line.unit,
    line.customer_material,
    line.quoted_material,
    line.weight_kg,
    line.surface_treatment,
    line.files.map((file) => [file.id, file.name, file.kind, file.size]),
  ]);
}
export function aiTaskStale(task: AiQuoteTask, quote?: Quote) {
  const line = quote?.lines.find((row) => row.id === task.line_id);
  // 人工复核采用的材料替换是本次已确认的结果；其余材料变更仍令旧依据失效。
  const basis =
    line &&
    task.adoption &&
    line.quoted_material === task.adoption.quoted_material
      ? { ...line, quoted_material: task.input.quoted_material }
      : line;
  return !quote || !basis || aiSourceKey(quote, basis) !== task.source_key;
}
export function latestAiTask(
  state: DemoState,
  quoteId: string,
  lineId: string,
) {
  return state.ai_quote_tasks.find(
    (task) => task.quote_id === quoteId && task.line_id === lineId,
  );
}
export function aiMissing(line: QuoteLine) {
  const missing: string[] = [];
  if (!line.files.length) missing.push("图纸或模型");
  if (!line.customer_material.trim() && !line.quoted_material.trim())
    missing.push("材料牌号");
  if (
    !Number.isInteger(line.quantity) ||
    !(line.quantity > 0) ||
    line.quantity > 1000000
  )
    missing.push("1 至 1000000 的整数件数");
  if (
    !["件", "pcs", "piece", "pieces"].includes(line.unit.trim().toLowerCase())
  )
    missing.push("按件计量单位（件/pcs/piece）");
  return missing;
}
function editableQuote(state: DemoState, quoteId: string) {
  const quote = state.quotes.find((row) => row.id === quoteId);
  if (!quote || !["pending", "pricing"].includes(quote.status))
    throw Error("当前报价不处于工程报价阶段");
  return quote;
}
export function createAiQuoteTasks(
  state: DemoState,
  quoteId: string,
  lineIds: string[],
  rerun = false,
) {
  const quote = editableQuote(state, quoteId);
  const ids = [...new Set(lineIds)];
  if (!ids.length) throw Error("请先选择需要 AI 报价的货品");
  if (ids.some((id) => !quote.lines.some((line) => line.id === id)))
    throw Error("所选货品已变化，请重新选择");
  const eligible = ids.filter((id) => {
    const latest = latestAiTask(state, quote.id, id);
    return (
      !latest ||
      (!["queued", "running"].includes(latest.status) &&
        (rerun ||
          aiTaskStale(latest, quote) ||
          !["adopted", "review"].includes(latest.status)))
    );
  });
  if (!eligible.length)
    throw Error(
      "所选货品正在分析或已有待复核/已采用结果；需要时请明确点击重新分析",
    );
  const batch = `ai-batch-${++state.serial}`;
  const tasks = eligible.map((id) => {
    const line = quote.lines.find((row) => row.id === id)!;
    const missing = aiMissing(line);
    return {
      id: `ai-task-${++state.serial}`,
      batch_id: batch,
      quote_id: quote.id,
      quote_no: quote.quote_no,
      quote_revision: quote.revision,
      line_id: id,
      currency: quote.currency,
      input: clone(line),
      source_key: aiSourceKey(quote, line),
      status: missing.length ? "needs_input" : "queued",
      step: 0,
      created_at: new Date().toISOString(),
      stage: missing.length ? "资料待补充，尚未开始分析" : "等待演示分析",
      missing,
      error: "",
    } satisfies AiQuoteTask;
  });
  state.ai_quote_tasks.unshift(...tasks);
  return tasks;
}
const cents = (value: number) =>
  Math.round((value + Number.EPSILON) * 100) / 100;
function number(
  value: unknown,
  label: string,
  allowZero = true,
  limit = 1000000,
) {
  if (
    value === null ||
    value === "" ||
    !Number.isFinite(value) ||
    Number(value) < (allowZero ? 0 : Number.MIN_VALUE) ||
    Number(value) > limit
  )
    throw Error(
      `${label}须为${allowZero ? "非负" : "正"}数，且不超过 ${limit}`,
    );
}
export function aiCostKey(review: AiReview) {
  return JSON.stringify([
    review.material,
    review.stock_weight_kg,
    review.material_price_cny,
    review.operations,
    review.external_unit_cny,
    review.other_batch_cny,
  ]);
}
export function calculateAiCost(review: AiReview, quantity: number): AiCost {
  if (!Number.isInteger(quantity) || quantity <= 0 || quantity > 1000000)
    throw Error("请核对本次核价件数");
  if (!review.material.trim()) throw Error("请确认报价采用材料");
  number(review.stock_weight_kg, "单件毛坯重量", false);
  number(review.material_price_cny, "材料单价");
  number(review.external_unit_cny, "单件外协费");
  number(review.other_batch_cny, "整批其他费用");
  if (!review.operations.length) throw Error("请至少保留一道工序");
  review.operations.forEach((operation) => {
    if (!operation.name.trim()) throw Error("请填写工序名称");
    number(operation.minutes_per_unit, "单件工时（分钟）", false, 60000);
    number(operation.hourly_rate_cny, "工序费率");
  });
  const material = cents(review.stock_weight_kg * review.material_price_cny);
  const machining = cents(
    review.operations.reduce(
      (sum, operation) =>
        sum + (operation.minutes_per_unit * operation.hourly_rate_cny) / 60,
      0,
    ),
  );
  const external = cents(review.external_unit_cny);
  const other = cents(review.other_batch_cny / quantity);
  const unit = cents(material + machining + external + other);
  number(unit, "核算成本");
  return {
    material_unit_cny: material,
    machining_unit_cny: machining,
    external_unit_cny: external,
    other_unit_cny: other,
    unit_cost_cny: unit,
    total_cost_cny: cents(unit * quantity),
    unit_minutes:
      Math.round(
        review.operations.reduce((sum, row) => sum + row.minutes_per_unit, 0) *
          1000,
      ) / 1000,
  };
}
function demoReview(task: AiQuoteTask): AiReview {
  return {
    material: task.input.quoted_material || task.input.customer_material,
    stock_weight_kg: task.input.weight_kg
      ? cents(task.input.weight_kg * 1.3)
      : 0.1,
    material_price_cny: 30,
    operations: [
      {
        id: "demo-cut",
        name: "下料（演示）",
        minutes_per_unit: 3,
        hourly_rate_cny: 60,
      },
      {
        id: "demo-cnc",
        name: "CNC 加工（演示）",
        minutes_per_unit: 20,
        hourly_rate_cny: 120,
      },
      {
        id: "demo-qa",
        name: "检验（演示）",
        minutes_per_unit: 5,
        hourly_rate_cny: 80,
      },
    ],
    external_unit_cny: 0,
    other_batch_cny: 0,
    markup_percent: 20,
    fx_rate: task.currency === "CNY" ? 1 : null,
    final_unit_price: null,
    lead_days: task.input.lead_days || 14,
    note: "",
  };
}
/** 每次 tick 推进演示阶段，最多两项并行；离开页面不影响 Pinia 中的调度。 */
export function advanceAiQuoteTasks(state: DemoState) {
  const stages = [
    "演示：读取已有图纸与模型",
    "演示：生成工艺与工时建议",
    "演示：整理材料与加工成本",
  ];
  for (const task of state.ai_quote_tasks.filter((row) =>
    ["queued", "running"].includes(row.status),
  )) {
    const quote = state.quotes.find((row) => row.id === task.quote_id);
    if (
      aiTaskStale(task, quote) ||
      !quote ||
      !["pending", "pricing"].includes(quote.status)
    ) {
      task.status = "stale";
      task.stage = "来源或报价阶段已变化，请重新确认";
      continue;
    }
    if (task.status !== "running") continue;
    task.step += 1;
    if (task.step < stages.length) {
      task.stage = stages[task.step];
      continue;
    }
    try {
      task.review = demoReview(task);
      task.cost = calculateAiCost(task.review, task.input.quantity!);
      task.cost_key = aiCostKey(task.review);
      task.original_cost = clone(task.cost);
      task.original_review = clone(task.review);
      task.status = "review";
      task.stage = "演示建议已生成，等待工程人员复核";
      task.completed_at = new Date().toISOString();
    } catch (cause) {
      task.status = "failed";
      task.error = (cause as Error).message;
      task.stage = "演示生成失败，可重新分析";
    }
  }
  let running = state.ai_quote_tasks.filter(
    (row) => row.status === "running",
  ).length;
  for (const task of [...state.ai_quote_tasks].reverse()) {
    if (running >= 2) break;
    if (task.status === "queued") {
      task.status = "running";
      task.stage = stages[0];
      running += 1;
    }
  }
}
function reviewTask(state: DemoState, id: string) {
  const task = state.ai_quote_tasks.find((row) => row.id === id);
  if (!task || task.status !== "review" || !task.review)
    throw Error("仅待复核结果可以修改或采用");
  const quote = editableQuote(state, task.quote_id);
  if (aiTaskStale(task, quote))
    throw Error("图纸、材料要求或数量已变化，请重新分析");
  if (latestAiTask(state, task.quote_id, task.line_id)?.id !== id)
    throw Error("已有新一轮分析，请复核最新结果");
  return { task, quote, review: task.review };
}
export function updateAiQuoteCost(state: DemoState, id: string) {
  const { task, review } = reviewTask(state, id);
  const cost = calculateAiCost(review, task.input.quantity!);
  task.cost = cost;
  task.cost_key = aiCostKey(review);
  return cost;
}
export function suggestAiPrice(state: DemoState, id: string) {
  const { task, review } = reviewTask(state, id);
  if (task.cost_key !== aiCostKey(review) || !task.cost)
    throw Error("请先更新核价");
  number(review.markup_percent, "成本加价比例", true, 1000);
  const rate = task.currency === "CNY" ? 1 : review.fx_rate;
  number(rate, "汇率（1 外币折合人民币）", false);
  review.final_unit_price = cents(
    (task.cost.unit_cost_cny * (1 + review.markup_percent / 100)) / rate!,
  );
  return review.final_unit_price;
}
export function adoptAiQuote(state: DemoState, id: string, confirmed: boolean) {
  const { task, quote, review } = reviewTask(state, id);
  if (!confirmed) throw Error("请确认已复核工艺、工时、材料和最终报价");
  if (!task.cost || task.cost_key !== aiCostKey(review))
    throw Error("工艺或材料费用已修改，请先更新核价");
  number(review.final_unit_price, "最终对客单价");
  number(review.lead_days, "交期天数", false, 3650);
  if (!Number.isInteger(review.lead_days)) throw Error("交期天数须为整数");
  number(review.markup_percent, "成本加价比例", true, 1000);
  if (review.fx_rate !== null) number(review.fx_rate, "汇率", false);
  const draft = clone(quote),
    line = draft.lines.find((row) => row.id === task.line_id)!;
  const adoption = {
    task_id: task.id,
    reviewed_at: new Date().toISOString(),
    cost_cny: task.cost.unit_cost_cny,
    currency: task.currency,
    final_unit_price: review.final_unit_price!,
    quoted_material: review.material,
    lead_days: review.lead_days,
    fx_rate: task.currency === "CNY" ? 1 : review.fx_rate,
    markup_percent: review.markup_percent,
    note: review.note,
  };
  Object.assign(line, {
    quoted_material: review.material,
    unit_price: review.final_unit_price,
    lead_days: review.lead_days,
    ai_review: adoption,
  });
  const saved = saveQuote(state, draft, "save", "engineering");
  task.adoption = clone(adoption);
  task.status = "adopted";
  task.stage = "工程人员已复核采用";
  return saved;
}
export function rejectAiQuote(state: DemoState, id: string, reason: string) {
  const { task } = reviewTask(state, id);
  if (!reason.trim()) throw Error("请填写不采用原因");
  task.status = "rejected";
  task.stage = "工程人员不采用本次建议";
  task.rejection_reason = reason.trim();
}
