import { clone, customerName, quantityUnits, type DemoState } from "./model";

export type ShipmentLine = {
  production_id: string;
  production_no: string;
  work_order_id: string;
  work_order_no: string;
  order_id: string;
  order_no: string;
  order_line_id: string;
  drawing_no: string;
  drawing_revision: string;
  description: string;
  unit: string;
  quantity: number;
};
export type Shipment = {
  id: string;
  shipment_no: string;
  customer_id: string;
  currency: string;
  shipping_date: string;
  recipient: string;
  contact: string;
  address: string;
  carrier: string;
  tracking_no: string;
  note: string;
  status: "draft" | "posted" | "cancelled";
  lines: ShipmentLine[];
  posted_at?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
};
export type ShipmentCommand = Pick<
  Shipment,
  | "customer_id"
  | "currency"
  | "shipping_date"
  | "recipient"
  | "contact"
  | "address"
  | "carrier"
  | "tracking_no"
  | "note"
> & { lines: { work_order_id: string; quantity: number }[] };
export const shipmentLabels: Record<Shipment["status"], string> = {
  draft: "待发货",
  posted: "已发货",
  cancelled: "已取消",
};
export function shippedQuantity(
  state: DemoState,
  key: string,
  byOrderLine = false,
) {
  return (
    state.shipments
      .filter((row) => row.status === "posted")
      .flatMap((row) => row.lines)
      .filter(
        (row) => (byOrderLine ? row.order_line_id : row.work_order_id) === key,
      )
      .reduce((sum, row) => sum + quantityUnits(row.quantity), 0) / 1000
  );
}
export function shipmentSources(state: DemoState) {
  return state.productions.flatMap((project) => {
    const order = state.orders.find((row) => row.id === project.order_id);
    if (!order) return [];
    return project.orders.flatMap((workOrder) => {
      const line = order.lines.find(
        (row) => row.id === workOrder.order_line_id,
      );
      if (!line || workOrder.status !== "completed") return [];
      // 同一图号也不合并，始终由明确的工单及货品执行明细交付对应订单行。
      const available =
        Math.max(
          0,
          Math.min(
            quantityUnits(workOrder.quantity) -
              quantityUnits(shippedQuantity(state, workOrder.id)),
            quantityUnits(line.quantity) -
              quantityUnits(shippedQuantity(state, line.id, true)),
          ),
        ) / 1000;
      return [
        {
          production_id: project.id,
          production_no: project.production_no,
          work_order_id: workOrder.id,
          work_order_no: workOrder.work_order_no,
          order_id: order.id,
          order_no: order.order_no,
          order_line_id: line.id,
          customer_id: order.customer_id,
          currency: order.currency,
          drawing_no: workOrder.snapshot.drawing_no,
          drawing_revision: workOrder.snapshot.drawing_revision,
          description: workOrder.snapshot.description,
          unit: workOrder.snapshot.unit,
          quantity: workOrder.quantity,
          shipped_quantity: shippedQuantity(state, workOrder.id),
          available_quantity: available,
        },
      ];
    });
  });
}
/** 整单发货默认选中全部未发货品；未齐套时不静默降级成部分发货。 */
export function productionShipment(state: DemoState, productionId: string) {
  const production = state.productions.find((row) => row.id === productionId);
  const active =
    production?.orders.filter((row) => row.status !== "cancelled") || [];
  const remaining = active
    .map((row) => ({
      item: row,
      quantity:
        Math.max(
          0,
          quantityUnits(row.quantity) -
            quantityUnits(shippedQuantity(state, row.id)),
        ) / 1000,
    }))
    .filter((row) => row.quantity > 0);
  const sources = shipmentSources(state);
  const waiting = remaining.filter(
    (row) => row.item.status !== "completed",
  ).length;
  const insufficient = remaining.some(
    (row) =>
      row.quantity >
      (sources.find((source) => source.work_order_id === row.item.id)
        ?.available_quantity || 0),
  );
  const reason = !production
    ? "工单不存在或暂存数据已清空"
    : !active.length
      ? "本工单没有有效货品"
      : !remaining.length
        ? "本工单已全部发货"
        : waiting
          ? `还有 ${waiting} 项货品未完工或未检验放行，暂不能整单发货`
          : insufficient
            ? "部分货品可发数量不足，请核对订单和出货记录"
            : "";
  return {
    is_ready: !reason,
    reason,
    remaining_count: remaining.length,
    waiting_count: waiting,
    lines: reason
      ? []
      : remaining.map((row) => ({
          work_order_id: row.item.id,
          quantity: row.quantity,
        })),
  };
}
function validatedLines(
  state: DemoState,
  command: ShipmentCommand,
): ShipmentLine[] {
  if (!command.lines.length) throw Error("请至少选择一种已检验放行的货品");
  const date = new Date(`${command.shipping_date}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(command.shipping_date) ||
    !Number.isFinite(date.getTime()) ||
    date.toISOString().slice(0, 10) !== command.shipping_date
  )
    throw Error("请选择有效的发货日期");
  if (!command.recipient.trim() || !command.address.trim())
    throw Error("请填写收货人和收货地址");
  const seen = new Set<string>();
  const allocated = new Map<string, number>();
  const sources = shipmentSources(state);
  return command.lines.map((row) => {
    const source = sources.find(
      (item) => item.work_order_id === row.work_order_id,
    );
    if (!source || seen.has(row.work_order_id))
      throw Error("货品尚未检验放行、已失效或重复选择");
    if (
      source.customer_id !== command.customer_id ||
      source.currency !== command.currency
    )
      throw Error("只能合并同一客户、同一币种的订单货品");
    const units = quantityUnits(row.quantity);
    if (
      !Number.isFinite(row.quantity) ||
      units <= 0 ||
      Math.abs(row.quantity * 1000 - units) > 0.000001
    )
      throw Error("出货数量须大于零，最多保留三位小数");
    if (units > quantityUnits(source.available_quantity))
      throw Error(
        `货品明细 ${source.work_order_no} 可发数量不足，请刷新后调整`,
      );
    const line = state.orders
      .find((order) => order.id === source.order_id)!
      .lines.find((item) => item.id === source.order_line_id)!;
    const chosen = (allocated.get(line.id) || 0) + units;
    if (
      chosen + quantityUnits(shippedQuantity(state, line.id, true)) >
      quantityUnits(line.quantity)
    )
      throw Error("本次合并出货超过客户订单待发数量");
    allocated.set(line.id, chosen);
    seen.add(row.work_order_id);
    return {
      production_id: source.production_id,
      production_no: source.production_no,
      work_order_id: source.work_order_id,
      work_order_no: source.work_order_no,
      order_id: source.order_id,
      order_no: source.order_no,
      order_line_id: source.order_line_id,
      drawing_no: source.drawing_no,
      drawing_revision: source.drawing_revision,
      description: source.description,
      unit: source.unit,
      quantity: units / 1000,
    };
  });
}
export function saveDemoShipment(
  state: DemoState,
  command: ShipmentCommand,
  documentId?: string,
) {
  const existing = documentId
    ? state.shipments.find((row) => row.id === documentId)
    : undefined;
  if (documentId && !existing) throw Error("出货单暂存数据已清空");
  if (existing && existing.status !== "draft")
    throw Error("只能编辑待发货单据");
  // 完整校验之后才修改状态，避免部分写入或消耗单号。
  const lines = validatedLines(state, command);
  const next: Shipment = {
    id: existing?.id || `shipment-${++state.serial}`,
    shipment_no:
      existing?.shipment_no || `SH-${String(state.serial).padStart(4, "0")}`,
    customer_id: command.customer_id,
    currency: command.currency,
    shipping_date: command.shipping_date,
    recipient: command.recipient.trim(),
    contact: command.contact.trim(),
    address: command.address.trim(),
    carrier: command.carrier.trim(),
    tracking_no: command.tracking_no.trim(),
    note: command.note.trim(),
    status: "draft",
    lines,
  };
  if (existing) Object.assign(existing, next);
  else state.shipments.unshift(next);
  return existing || state.shipments[0];
}
export function confirmDemoShipment(state: DemoState, documentId: string) {
  const shipment = state.shipments.find((row) => row.id === documentId);
  if (!shipment || shipment.status !== "draft")
    throw Error("仅待发货单据可以确认发货");
  validatedLines(state, shipment);
  shipment.status = "posted";
  shipment.posted_at = new Date().toISOString();
}
export function cancelDemoShipment(
  state: DemoState,
  documentId: string,
  reason: string,
) {
  const shipment = state.shipments.find((row) => row.id === documentId);
  if (!shipment || shipment.status === "cancelled")
    throw Error("出货单不存在或已取消");
  if (!reason.trim()) throw Error("请填写取消或撤销发货的原因");
  shipment.cancellation_reason = reason.trim();
  shipment.cancelled_at = new Date().toISOString();
  shipment.status = "cancelled";
}
export function orderDelivery(state: DemoState, orderId: string) {
  const order = state.orders.find((row) => row.id === orderId);
  if (!order)
    return { shipped_line_count: 0, complete_line_count: 0, shipment_count: 0 };
  return {
    shipped_line_count: order.lines.filter(
      (row) => shippedQuantity(state, row.id, true) > 0,
    ).length,
    complete_line_count: order.lines.filter(
      (row) =>
        quantityUnits(shippedQuantity(state, row.id, true)) >=
        quantityUnits(row.quantity),
    ).length,
    shipment_count: state.shipments.filter(
      (row) =>
        row.status === "posted" &&
        row.lines.some((line) => line.order_id === orderId),
    ).length,
  };
}
/** 客户出货凭证不含成交单价或工程内部信息。 */
export function shipmentRows(shipment: Shipment): (string | number)[][] {
  return [
    [
      "出货单（前端流程演示）",
      shipment.shipment_no,
      shipmentLabels[shipment.status],
    ],
    [
      "客户",
      customerName(shipment.customer_id),
      "发货日期",
      shipment.shipping_date,
    ],
    ["收货人", shipment.recipient, "联系方式", shipment.contact],
    ["收货地址", shipment.address],
    ["承运商", shipment.carrier, "物流单号", shipment.tracking_no],
    [
      "客户订单",
      "生产工单",
      "货品明细编号",
      "图号",
      "版本",
      "描述",
      "数量",
      "单位",
    ],
    ...shipment.lines.map((line) => [
      line.order_no,
      line.production_no,
      line.work_order_no,
      line.drawing_no,
      line.drawing_revision,
      line.description,
      line.quantity,
      line.unit,
    ]),
    ["备注", shipment.note],
    ["取消／撤销原因", shipment.cancellation_reason || ""],
    ["仅前端流程验证，未写入数据库，不代表真实发货或库存记账。"],
  ];
}
export function shipmentCsv(shipment: Shipment) {
  const safe = (value: string | number) => {
    let text = String(value);
    if (/^[\s\uFEFF]*[=+\-@\t\r]/.test(text)) text = "'" + text;
    return `"${text.replace(/"/g, '""')}"`;
  };
  return (
    "\uFEFF" +
    shipmentRows(shipment)
      .map((row) => row.map(safe).join(","))
      .join("\r\n")
  );
}
export function shipmentHtml(shipment: Shipment) {
  const escape = (value: string | number) =>
    String(value).replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char]!,
    );
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${escape(shipment.shipment_no)}</title><style>body{font:14px Arial,sans-serif;margin:24px}table{width:100%;border-collapse:collapse}td{padding:10px;border:1px solid #ddd;white-space:pre-wrap;overflow-wrap:anywhere}tr{break-inside:avoid}</style><h1>生产直发出货单 · 演示</h1><table>${shipmentRows(
    clone(shipment),
  )
    .map(
      (row) =>
        `<tr>${row.map((value) => `<td>${escape(value)}</td>`).join("")}</tr>`,
    )
    .join("")}</table><p>客户签收：____________　日期：____________</p></html>`;
}
