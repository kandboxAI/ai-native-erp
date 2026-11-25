import QRCode from "qrcode";
import { getMesWorkOrder } from "@plugins/mes/web/src/api/mes";
import { formatMesDate } from "../shared";

export function escapeCardText(value: unknown) {
  return String(value ?? "—").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
}
export async function buildWorkOrderCard(id: string) {
  const { data } = await getMesWorkOrder(id);
  // Existing mobile scanner searches by work-order number, not an unrecognized URI.
  const qr = await QRCode.toDataURL(data.work_order_no, {
    width: 180,
    margin: 1,
  });
  const text = escapeCardText;
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${text(data.work_order_no)} 工单卡</title><style>
    @page{size:A4;margin:16mm}body{font-family:Arial,"Microsoft YaHei",sans-serif;color:#162b42;font-size:12px;margin:24px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:24px}img{width:120px;height:120px}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{border:1px solid #ccc;padding:10px;text-align:left}th{background:#f2f5f8}small{color:#666}.note{white-space:pre-wrap;overflow-wrap:anywhere}tr{break-inside:avoid}footer{margin-top:24px}
    </style></head><body><header><div><h1>生产工单卡</h1><h2>${text(data.work_order_no)}</h2><p>${text(data.product_item_no)} · ${text(data.product_item_name)}</p><p>计划：${text(data.planned_quantity)} ${text(data.unit_name)}　状态：${text(data.status_label)}</p><p>交期：${text(formatMesDate(data.due_at))}</p></div><div><img alt="工单二维码" src="${qr}"><div><small>手机扫码查询工单任务</small></div></div></header><table><thead><tr><th>顺序</th><th>工序号 / 名称</th><th>工作中心 / 站</th><th>计划</th><th>工艺说明</th></tr></thead><tbody>${data.operations.map((row) => `<tr><td>${row.sequence_no}</td><td>${text(row.operation_no)} / ${text(row.operation_name)}</td><td>${text(row.work_center_name)} / ${text(row.workstation_name)}</td><td>${text(row.planned_quantity)} ${text(row.unit_name)}</td><td class="note">${text(row.operation_description)}</td></tr>`).join("")}</tbody></table><footer>生成时间：${text(new Date().toLocaleString("zh-CN"))}。工单状态以系统实时数据为准。</footer></body></html>`;
  return {
    html,
    filename: `${data.work_order_no.replace(/[\\/:*?"<>|]/g, "_")}-工单卡.html`,
  };
}
export async function openWorkOrderCard(id: string, download = false) {
  const { html, filename } = await buildWorkOrderCard(id);
  if (download) {
    const url = URL.createObjectURL(
      new Blob([html], { type: "text/html;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else {
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;width:0;height:0;border:0;";
    frame.setAttribute("sandbox", "allow-same-origin allow-modals");
    frame.onload = () => {
      frame.contentWindow?.addEventListener(
        "afterprint",
        () => frame.remove(),
        { once: true },
      );
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    };
    frame.srcdoc = html;
    document.body.append(frame);
  }
}
