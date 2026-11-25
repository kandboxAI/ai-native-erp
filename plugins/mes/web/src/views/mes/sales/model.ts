// 仅供流程验证：所有记录均为浏览器内存中的演示数据，不调用业务接口。
export type Role = "sales" | "engineering";
export type QuoteStatus = "draft" | "pending" | "pricing" | "quoted";
export type Drawing = {
  id: string;
  name: string;
  kind: "pdf" | "model";
  size: number;
  is_demo?: boolean;
};
export type QuoteLine = {
  id: string;
  drawing_no: string;
  drawing_revision: string;
  description: string;
  quantity: number | null;
  unit: string;
  customer_material: string;
  quoted_material: string;
  weight_kg: number | null;
  last_quantity: number | null;
  last_price: number | null;
  unit_price: number | null;
  lead_days: number | null;
  surface_treatment: string;
  note: string;
  engineering_note: string;
  files: Drawing[];
  ai_review?: {
    task_id: string;
    reviewed_at: string;
    cost_cny: number;
    currency: string;
    final_unit_price: number;
    quoted_material: string;
    lead_days: number;
    fx_rate: number | null;
    markup_percent: number;
    note: string;
  };
};
export type Quote = {
  id: string;
  quote_no: string;
  revision: number;
  is_current: boolean;
  title: string;
  customer_id: string;
  currency: string;
  owner: string;
  engineer: string;
  deadline: string;
  note: string;
  return_reason: string;
  status: QuoteStatus;
  lines: QuoteLine[];
};
export type OrderLine = {
  id: string;
  quote_id: string;
  quote_line_id: string;
  quote_no: string;
  quote_revision: number;
  snapshot: QuoteLine;
  quantity: number;
  unit_price: number;
  due_date: string;
};
export type CustomerOrder = {
  id: string;
  order_no: string;
  customer_id: string;
  currency: string;
  customer_po_no: string;
  note: string;
  lines: OrderLine[];
};
export type WorkOrder = {
  id: string;
  work_order_no: string;
  order_line_id: string;
  snapshot: QuoteLine;
  quantity: number;
  due_date: string;
  operations: OperationDefinition[];
  process_template_id?: string | null;
  process_template_version_snapshot?: number | null;
  status:
    | "unconfigured"
    | "configured"
    | "released"
    | "waiting_quality"
    | "completed"
    | "cancelled";
  completed_at?: string;
  quality_released_at?: string;
};
export type Production = {
  id: string;
  production_no: string;
  order_id: string;
  customer_id: string;
  orders: WorkOrder[];
};
export type ProductionStatus =
  | "unconfigured"
  | "configuring"
  | "configured"
  | "in_progress"
  | "completed"
  | "cancelled";
export const productionLabels: Record<ProductionStatus, string> = {
  unconfigured: "未配置",
  configuring: "配置中",
  configured: "待下达",
  in_progress: "生产中",
  completed: "已完成",
  cancelled: "已取消",
};
export type DemoState = {
  quotes: Quote[];
  orders: CustomerOrder[];
  productions: Production[];
  shipments: import("./shipmentModel").Shipment[];
  ai_quote_tasks: import("./aiQuoteModel").AiQuoteTask[];
  serial: number;
};
export type OrderCommand = {
  customer_id: string;
  currency: string;
  customer_po_no: string;
  note: string;
  lines: {
    quote_id: string;
    quote_line_id: string;
    quantity: number;
    unit_price: number;
    due_date: string;
    is_price_confirmed: boolean;
  }[];
};
export const customers = [
  { id: "customer-a", name: "演示客户 A · 精密机械", currency: "EUR" },
  { id: "customer-b", name: "演示客户 B · 自动化设备", currency: "CNY" },
];
export const quoteLabels: Record<QuoteStatus, string> = {
  draft: "业务录入",
  pending: "待工程报价",
  pricing: "工程报价中",
  quoted: "报价完成",
};
export const workOrderLabels: Record<WorkOrder["status"], string> = {
  unconfigured: "未配置",
  configured: "待下达",
  released: "已下达生产",
  waiting_quality: "完工待检验",
  completed: "检验已放行",
  cancelled: "已取消",
};
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export const customerName = (id: string) =>
  customers.find((item) => item.id === id)?.name || "未选择客户";
export const quantityUnits = (value: number) => Math.round(value * 1000);
export const lineAmount = (quantity: number, price: number) =>
  Math.round((quantityUnits(quantity) * Math.round(price * 100)) / 1000) / 100;
export const orderAmount = (order: CustomerOrder) =>
  Math.round(
    order.lines.reduce(
      (sum, line) =>
        sum + Math.round(lineAmount(line.quantity, line.unit_price) * 100),
      0,
    ),
  ) / 100;
function id(state: DemoState, prefix: string) {
  return `${prefix}-${++state.serial}`;
}
export function dateAfter(days: number) {
  const day = new Date();
  day.setDate(day.getDate() + days);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}
function validNumber(value: unknown, label: string, zero = false) {
  if (
    value === null ||
    value === "" ||
    !Number.isFinite(Number(value)) ||
    (zero ? Number(value) < 0 : Number(value) <= 0) ||
    Number(value) > 1000000
  )
    throw Error(`${label}须为${zero ? "非负" : "正"}数，且不超过 1000000`);
}
function validQuantity(value: number, label: string) {
  validNumber(value, label);
  if (
    quantityUnits(value) <= 0 ||
    Math.abs(value * 1000 - quantityUnits(value)) > 0.000001
  )
    throw Error(`${label}最多保留三位小数，最小为 0.001`);
}
function requireDate(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    !Number.isFinite(date.getTime()) ||
    date.toISOString().slice(0, 10) !== value
  )
    throw Error("请填写有效交期");
}
export function newLine(state: DemoState): QuoteLine {
  return {
    id: id(state, "line"),
    drawing_no: "",
    drawing_revision: "A",
    description: "",
    quantity: null,
    unit: "件",
    customer_material: "",
    quoted_material: "",
    weight_kg: null,
    last_quantity: null,
    last_price: null,
    unit_price: null,
    lead_days: null,
    surface_treatment: "",
    note: "",
    engineering_note: "",
    files: [],
  };
}
export function newQuote(state: DemoState): Quote {
  const key = id(state, "quote");
  return {
    id: key,
    quote_no: `BJ-${String(state.serial).padStart(4, "0")}`,
    revision: 1,
    is_current: false,
    title: "",
    customer_id: "customer-a",
    currency: "EUR",
    owner: "演示业务员",
    engineer: "演示工程师",
    deadline: dateAfter(3),
    note: "",
    return_reason: "",
    status: "draft",
    lines: [],
  };
}
export function saveQuote(
  state: DemoState,
  draft: Quote,
  action: "save" | "submit" | "finish" | "return",
  role: Role,
) {
  const old = state.quotes.find((row) => row.id === draft.id);
  if (
    !customers.some((row) => row.id === draft.customer_id) ||
    !draft.title.trim()
  )
    throw Error("请选择客户并填写询价名称");
  if (!["EUR", "CNY", "USD"].includes(draft.currency))
    throw Error("请选择有效币种");
  if (old?.status === "quoted") throw Error("已完成的报价不能修改，请新建修订");
  let next: Quote;
  if (!old || old.status === "draft") {
    if (role !== "sales" || !["save", "submit"].includes(action))
      throw Error("请切换业务人员视角录入并提交");
    draft.lines.forEach((line, index) => {
      if (line.weight_kg !== null)
        validNumber(line.weight_kg, `第 ${index + 1} 行净重量`, true);
    });
    next = clone(draft);
    if (action === "submit") {
      if (!next.lines.length) throw Error("请至少录入一种货品");
      const seen = new Set<string>();
      next.lines.forEach((line, index) => {
        if (
          !line.drawing_no.trim() ||
          !line.description.trim() ||
          !line.unit.trim() ||
          !line.customer_material.trim()
        )
          throw Error(`第 ${index + 1} 行请填写图号、描述、单位及客户材料`);
        validQuantity(line.quantity, `第 ${index + 1} 行询价数量`);
        if (!line.files.length)
          throw Error(`第 ${index + 1} 行请添加图纸或模型`);
        const key = `${line.drawing_no.trim().toLowerCase()}/${line.drawing_revision.trim().toLowerCase()}`;
        if (seen.has(key))
          throw Error("同一报价中图号与版本重复，请合并或调整");
        seen.add(key);
      });
      next.status = "pending";
      next.return_reason = "";
    }
  } else {
    if (role !== "engineering") throw Error("请切换工程人员视角处理报价");
    next = clone(old);
    if (action === "return") {
      if (!draft.return_reason.trim()) throw Error("请填写需要补充的资料");
      next.return_reason = draft.return_reason.trim();
      next.status = "draft";
    } else if (["save", "finish"].includes(action)) {
      next.lines = old.lines.map((line) => {
        const edit = draft.lines.find((row) => row.id === line.id);
        if (!edit) throw Error("报价明细已变化，请重新打开");
        return {
          ...clone(line),
          quoted_material: edit.quoted_material,
          unit_price: edit.unit_price,
          lead_days: edit.lead_days,
          engineering_note: edit.engineering_note,
          ai_review:
            edit.ai_review &&
            edit.unit_price === edit.ai_review.final_unit_price &&
            edit.quoted_material === edit.ai_review.quoted_material &&
            edit.lead_days === edit.ai_review.lead_days
              ? clone(edit.ai_review)
              : undefined,
        };
      });
      next.status = action === "finish" ? "quoted" : "pricing";
      if (action === "finish")
        next.lines.forEach((line, index) => {
          if (!line.quoted_material.trim())
            throw Error(`第 ${index + 1} 行请填写报价材料`);
          validNumber(line.unit_price, `第 ${index + 1} 行单价`, true);
          validNumber(line.lead_days, `第 ${index + 1} 行交期天数`);
          if (!Number.isInteger(line.lead_days))
            throw Error("交期天数应为整数");
        });
    } else throw Error("当前状态不允许此操作");
  }
  if (next.status === "quoted") {
    state.quotes
      .filter((row) => row.quote_no === next.quote_no)
      .forEach((row) => {
        row.is_current = false;
      });
    next.is_current = true;
  }
  const index = state.quotes.findIndex((row) => row.id === next.id);
  if (index >= 0) state.quotes[index] = next;
  else state.quotes.unshift(next);
  return next;
}
export function reviseQuote(state: DemoState, quote: Quote) {
  if (quote.status !== "quoted") throw Error("报价完成后才能创建新修订");
  if (
    state.quotes.some(
      (row) => row.quote_no === quote.quote_no && row.status !== "quoted",
    )
  )
    throw Error("该报价已有未完成的修订，请先处理");
  const draft = clone(quote);
  draft.id = id(state, "quote");
  draft.revision =
    Math.max(
      ...state.quotes
        .filter((row) => row.quote_no === quote.quote_no)
        .map((row) => row.revision),
    ) + 1;
  draft.is_current = false;
  draft.status = "draft";
  draft.return_reason = "";
  draft.lines.forEach((row) => {
    row.id = id(state, "line");
    delete row.ai_review;
  });
  return draft;
}
export function acceptedQuantity(state: DemoState, quoteLineId: string) {
  return (
    state.orders
      .flatMap((order) => order.lines)
      .filter((line) => line.quote_line_id === quoteLineId)
      .reduce((sum, line) => sum + quantityUnits(line.quantity), 0) / 1000
  );
}
export function createCustomerOrder(state: DemoState, command: OrderCommand) {
  if (!command.lines.length) throw Error("请至少选择一种成交货品");
  if (
    command.customer_po_no.trim() &&
    state.orders.some(
      (row) =>
        row.customer_id === command.customer_id &&
        row.customer_po_no === command.customer_po_no.trim(),
    )
  )
    throw Error("该客户采购单号已录入，请检查是否重复接单");
  const seen = new Set<string>();
  const lines: OrderLine[] = command.lines.map((row) => {
    const quote = state.quotes.find((item) => item.id === row.quote_id);
    const line = quote?.lines.find((item) => item.id === row.quote_line_id);
    if (!quote || !line || quote.status !== "quoted" || !quote.is_current)
      throw Error("请选择已完成且有效修订的报价明细");
    if (
      quote.customer_id !== command.customer_id ||
      quote.currency !== command.currency
    )
      throw Error("只能合并同一客户、同一币种的报价");
    if (seen.has(line.id)) throw Error("同一报价明细不能重复选择");
    seen.add(line.id);
    validQuantity(row.quantity, "实际购买数量");
    validNumber(row.unit_price, "成交单价", true);
    requireDate(row.due_date);
    if (
      (row.quantity !== line.quantity || row.unit_price !== line.unit_price) &&
      !row.is_price_confirmed
    )
      throw Error(
        `图号 ${line.drawing_no} 的数量或单价已变化，请确认本次成交价格`,
      );
    return {
      id: "",
      quote_id: quote.id,
      quote_line_id: line.id,
      quote_no: quote.quote_no,
      quote_revision: quote.revision,
      snapshot: clone(line),
      quantity: row.quantity,
      unit_price: row.unit_price,
      due_date: row.due_date,
    };
  });
  lines.forEach((line) => {
    line.id = id(state, "order-line");
  });
  const order: CustomerOrder = {
    id: id(state, "order"),
    order_no: `SO-${String(state.serial).padStart(4, "0")}`,
    customer_id: command.customer_id,
    currency: command.currency,
    customer_po_no: command.customer_po_no.trim(),
    note: command.note,
    lines,
  };
  state.orders.unshift(order);
  return order;
}
export function allocatedQuantity(state: DemoState, orderLineId: string) {
  return (
    state.productions
      .flatMap((project) => project.orders)
      .filter(
        (row) =>
          row.order_line_id === orderLineId && row.status !== "cancelled",
      )
      .reduce((sum, row) => sum + quantityUnits(row.quantity), 0) / 1000
  );
}
export function remainingQuantity(state: DemoState, line: OrderLine) {
  return Math.max(
    0,
    (quantityUnits(line.quantity) -
      quantityUnits(allocatedQuantity(state, line.id))) /
      1000,
  );
}
/** 对外一张工单包含本次选择的多项货品；orders 为独立配置工序的货品执行明细。 */
export function productionProgress(production: Production) {
  const active = production.orders.filter((row) => row.status !== "cancelled");
  const configured = active.filter(
    (row) => row.status !== "unconfigured",
  ).length;
  const completed = active.filter((row) => row.status === "completed").length;
  const started = active.filter((row) =>
    ["released", "waiting_quality", "completed"].includes(row.status),
  ).length;
  const status: ProductionStatus = !active.length
    ? "cancelled"
    : completed === active.length
      ? "completed"
      : started
        ? "in_progress"
        : configured === active.length
          ? "configured"
          : configured
            ? "configuring"
            : "unconfigured";
  return {
    status,
    product_count: active.length,
    configured_count: configured,
    completed_count: completed,
  };
}
/** 一次生成一张包含多项货品的生产工单；多次生成保留独立单号与各次选择。 */
export function productionBatches(state: DemoState, orderId: string) {
  return state.productions.filter((project) => project.order_id === orderId);
}
export function productionSummary(state: DemoState, order: CustomerOrder) {
  const batches = productionBatches(state, order.id);
  const active = batches.filter((project) =>
    project.orders.some((row) => row.status !== "cancelled"),
  );
  return {
    batch_count: batches.length,
    active_batch_count: active.length,
    work_order_count: active.length,
    product_count: active.reduce(
      (sum, project) =>
        sum + project.orders.filter((row) => row.status !== "cancelled").length,
      0,
    ),
    fully_arranged_line_count: order.lines.filter(
      (line) => remainingQuantity(state, line) === 0,
    ).length,
    line_count: order.lines.length,
  };
}
export function createProduction(
  state: DemoState,
  orderId: string,
  choices: { order_line_id: string; quantity: number }[],
) {
  const order = state.orders.find((row) => row.id === orderId);
  if (!order || !choices.length) throw Error("请选择客户订单及本次生产明细");
  const seen = new Set<string>();
  const workOrders: WorkOrder[] = choices.map((choice) => {
    const line = order.lines.find((row) => row.id === choice.order_line_id);
    if (!line || seen.has(line.id)) throw Error("订单明细不存在或重复");
    seen.add(line.id);
    validQuantity(choice.quantity, "本次生产数量");
    if (
      quantityUnits(choice.quantity) >
      quantityUnits(remainingQuantity(state, line))
    )
      throw Error(`图号 ${line.snapshot.drawing_no} 的本次数量超过待下达数量`);
    return {
      id: "",
      work_order_no: "",
      order_line_id: line.id,
      snapshot: clone(line.snapshot),
      quantity: choice.quantity,
      due_date: line.due_date,
      operations: [],
      status: "unconfigured",
    };
  });
  const key = id(state, "production"),
    no = `PO-${String(state.serial).padStart(4, "0")}`;
  workOrders.forEach((row, index) => {
    row.id = id(state, "work-order");
    row.work_order_no = `${no}-${String(index + 1).padStart(3, "0")}`;
  });
  const project: Production = {
    id: key,
    production_no: no,
    order_id: order.id,
    customer_id: order.customer_id,
    orders: workOrders,
  };
  state.productions.unshift(project);
  return project;
}
export function configureWorkOrder(
  order: WorkOrder,
  configuration: {
    operations: OperationDefinition[];
    process_template_id?: string | null;
    process_template_version_snapshot?: number | null;
  },
) {
  if (!["unconfigured", "configured"].includes(order.status))
    throw Error("已下达或已取消工单不能修改工序");
  if (!configuration.operations.length) throw Error("请至少配置一道工序");
  order.operations = operationPayload(configuration.operations);
  order.process_template_id = configuration.process_template_id || null;
  order.process_template_version_snapshot =
    configuration.process_template_version_snapshot || null;
  order.status = "configured";
}
export function releaseWorkOrder(order: WorkOrder) {
  if (order.status !== "configured" || !order.operations.length)
    throw Error("请先配置工序，再下达生产");
  order.status = "released";
}
/** 演示桥接：整批完工和检验分开确认，不冒充真实报工或检验记录。 */
export function completeDemoWorkOrder(order: WorkOrder) {
  if (order.status !== "released")
    throw Error("仅已下达生产的工单可登记演示完工");
  order.completed_at = new Date().toISOString();
  order.status = "waiting_quality";
}
export function releaseDemoQuality(order: WorkOrder) {
  if (order.status !== "waiting_quality")
    throw Error("请先登记演示完工，再确认检验放行");
  order.quality_released_at = new Date().toISOString();
  order.status = "completed";
}
export function cancelDemoWorkOrder(order: WorkOrder) {
  if (!["unconfigured", "configured", "released"].includes(order.status))
    throw Error("已完工或已取消的工单不能取消");
  order.status = "cancelled";
}
export function createDemoState(): DemoState {
  const state: DemoState = {
    quotes: [],
    orders: [],
    productions: [],
    shipments: [],
    ai_quote_tasks: [],
    serial: 100,
  };
  const sample = (
    number: string,
    title: string,
    customer: string,
    status: QuoteStatus,
    details: [string, string, number, string, number][],
  ) => {
    const quote = newQuote(state);
    Object.assign(quote, {
      quote_no: number,
      title,
      customer_id: customer,
      currency: customers.find((row) => row.id === customer)!.currency,
      status,
      is_current: status === "quoted",
    });
    quote.lines = details.map(
      ([drawing_no, description, quantity, material, price]) => ({
        ...newLine(state),
        drawing_no,
        description,
        quantity,
        customer_material: material,
        quoted_material: status === "quoted" ? material : "",
        unit_price: status === "quoted" ? price : null,
        lead_days: status === "quoted" ? 14 : null,
        weight_kg: 0.08,
        last_quantity: 50,
        last_price: price,
        surface_treatment: "阳极氧化，按图纸要求",
        files: [
          {
            id: `sample-${drawing_no}`,
            name: `${drawing_no}.pdf`,
            kind: "pdf",
            size: 0,
            is_demo: true,
          },
        ],
      }),
    );
    state.quotes.push(quote);
  };
  sample("BJ-DEMO-001", "上次报价 · 连接板与法兰盘", "customer-a", "quoted", [
    ["PM-Y2008130-01", "CNC 铝合金连接板", 100, "6082-T6", 5.38],
    ["PM-Y2504070-00", "CNC 法兰盘", 50, "6082-T6", 12.8],
  ]);
  sample("BJ-DEMO-002", "本次报价 · 夹紧支架", "customer-a", "quoted", [
    ["PM-Y2504310-00", "夹紧支架", 80, "Aluminium 5083", 17.8],
  ]);
  sample("BJ-DEMO-003", "待工程处理 · 定位块", "customer-b", "pending", [
    ["AUTO-001", "设备定位块", 20, "C45", 28],
  ]);
  return state;
}
import {
  operationPayload,
  type OperationDefinition,
} from "../work-orders/operationDefinitions";
