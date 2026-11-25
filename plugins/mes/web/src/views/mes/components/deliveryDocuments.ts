import type {
  DeliveryDocument,
  DeliveryKind
} from "@plugins/mes/web/src/api/mesDelivery";

export function deliveryLabel(code: string) {
  return (
    (
      {
        draft: "草稿",
        posted: "已出货",
        confirmed: "已确认",
        cancelled: "已取消",
        awaiting_stock: "待库存办理",
        submitted: "待审批",
        approved: "待记账",
        voided: "已作废",
        reversed: "已冲销"
      } as Record<string, string>
    )[code] || code
  );
}

export function deliveryCurrency(orderCurrency?: string | null) {
  return orderCurrency || "CNY";
}

export function deliveryPriceLabel(orderCurrency?: string | null) {
  return orderCurrency ? `未税单价（${orderCurrency}）` : "含税单价（CNY）";
}

// Three quantity decimals, two price decimals; round each line half up to cents.
export function deliveryAmount(
  quantity: string,
  price: string,
  adjustment = "0"
) {
  function scaled(value: string, digits: number) {
    if (!/^-?\d+(\.\d+)?$/.test(value)) throw Error("数量或金额格式不正确");
    const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
    if (fraction.length > digits)
      throw Error("数量最多三位小数，金额最多两位小数");
    return (
      BigInt(whole + fraction.padEnd(digits, "0")) *
      (value.startsWith("-") ? -1n : 1n)
    );
  }
  const product = scaled(quantity, 3) * scaled(price, 2);
  const cents = (product + 500n) / 1000n + scaled(adjustment, 2);
  return `${cents < 0 ? "-" : ""}${(cents < 0 ? -cents : cents) / 100n}.${((cents < 0 ? -cents : cents) % 100n).toString().padStart(2, "0")}`;
}

function escape(value: unknown) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    char =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ]
  );
}
export function documentRows(document: DeliveryDocument, kind: DeliveryKind) {
  return document.lines.map(line => [
    line.shipment_no || document.shipment_no || "",
    line.work_order_no_snapshot,
    line.product_item_name_snapshot,
    line.quantity,
    line.unit_code,
    line.unit_price,
    kind === "reconciliations" ? line.adjustment_amount : "0.00",
    line.amount,
    line.adjustment_reason || ""
  ]);
}
const headings = (orderCurrency?: string | null) => [
  "出货单",
  "工单",
  "产品",
  "数量",
  "单位",
  deliveryPriceLabel(orderCurrency),
  `调整（${deliveryCurrency(orderCurrency)}）`,
  `金额（${deliveryCurrency(orderCurrency)}）`,
  "调整原因"
];
export function documentCsv(document: DeliveryDocument, kind: DeliveryKind) {
  const safe = (value: unknown) => {
    let text = String(value ?? "");
    if (/^[\s\uFEFF]*[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  };
  const metadata = [
    "单号",
    document.shipment_no || document.reconciliation_no,
    "客户编号",
    document.customer_no_snapshot,
    "客户",
    document.customer_name_snapshot,
    "状态",
    deliveryLabel(document.status_code),
    "期间",
    document.business_date ||
      `${document.period_start} ~ ${document.period_end}`,
    `总额（${deliveryCurrency(document.order_currency_snapshot)}）`,
    document.total_amount
  ];
  return (
    "\uFEFF" +
    [metadata, headings(document.order_currency_snapshot), ...documentRows(document, kind)]
      .map(row => row.map(safe).join(","))
      .join("\r\n")
  );
}
export function documentHtml(document: DeliveryDocument, kind: DeliveryKind) {
  const title =
    kind === "shipments"
      ? `出货单（${document.fulfillment_mode_code === "stock" ? "仓储出货" : "生产直发"}）`
      : "客户出货对账单";
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${title}</title><style>body{font:14px Arial,sans-serif;margin:24px;color:#172c43}table{width:100%;border-collapse:collapse}td,th{padding:8px;border:1px solid #bbb;text-align:left;overflow-wrap:anywhere}tr{break-inside:avoid}.note{white-space:pre-wrap}</style></head><body><h1>${title}</h1><p>${escape(document.shipment_no || document.reconciliation_no)} · ${escape(deliveryLabel(document.status_code))}</p><p>客户：${escape(document.customer_no_snapshot)} / ${escape(document.customer_name_snapshot)}</p><p>日期/期间：${escape(document.business_date || `${document.period_start} ~ ${document.period_end}`)}</p><table><thead><tr>${headings(document.order_currency_snapshot).map(value => `<th>${escape(value)}</th>`).join("")}</tr></thead><tbody>${documentRows(
    document,
    kind
  )
    .map(
      row =>
        `<tr>${row.map(value => `<td>${escape(value)}</td>`).join("")}</tr>`
    )
    .join(
      ""
    )}</tbody></table><p>合计：${escape(document.total_amount)} ${escape(deliveryCurrency(document.order_currency_snapshot))}</p><p class="note">${escape(document.note)}</p><p class="note">${escape(document.cancellation_reason)}</p><p>仓储出货的库存变化以关联库存单据为准；本单不表示已收款或开票。客户签字：________　日期：________</p></body></html>`;
}
export function exportDelivery(document: DeliveryDocument, kind: DeliveryKind) {
  const url = URL.createObjectURL(
    new Blob([documentCsv(document, kind)], { type: "text/csv;charset=utf-8" })
  );
  const link = window.document.createElement("a");
  link.href = url;
  link.download = `${(document.shipment_no || document.reconciliation_no).replace(/[\\/:*?"<>|]/g, "_")}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function printDelivery(document: DeliveryDocument, kind: DeliveryKind) {
  const frame = window.document.createElement("iframe");
  frame.style.cssText = "position:fixed;width:0;height:0;border:0";
  frame.setAttribute("sandbox", "allow-same-origin allow-modals");
  frame.onload = () => {
    frame.contentWindow?.addEventListener("afterprint", () => frame.remove(), {
      once: true
    });
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
  };
  frame.srcdoc = documentHtml(document, kind);
  window.document.body.append(frame);
}
