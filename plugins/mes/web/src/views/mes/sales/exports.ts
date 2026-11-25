import { customerName, lineAmount, type Quote } from "./model";
import type { LocalDrawings } from "./files";

export async function quoteWorkbook(quote: Quote): Promise<Uint8Array> {
  const XLSX = await import("xlsx");
  const rows: (string | number)[][] = [
    ["报价明细表（前端流程演示）"],
    [
      "报价单号",
      quote.quote_no,
      "版本",
      `R${quote.revision}`,
      "客户",
      customerName(quote.customer_id),
      "币种",
      quote.currency,
    ],
    [
      "价格口径",
      "每个计量单位的单价；演示按未税价格录入",
      "交期口径",
      "客户确认后起算的自然日；接单时另行确认实际交付日期",
    ],
    [
      "序号",
      "图号",
      "零件描述",
      "本次询价数量",
      "客户材料",
      "报价材料",
      "净重量（kg）",
      "上次订单数量",
      "上次订单单价",
      "本次单价",
      "交期（天）",
      "表面处理要求",
      "备注",
      "图纸版本",
      "单位",
      "小计",
    ],
    ...quote.lines.map((line, index) => [
      index + 1,
      line.drawing_no,
      line.description,
      line.quantity ?? "",
      line.customer_material,
      line.quoted_material,
      line.weight_kg ?? "",
      line.last_quantity ?? "",
      line.last_price ?? "",
      line.unit_price ?? "",
      line.lead_days ?? "",
      line.surface_treatment,
      line.note,
      line.drawing_revision,
      line.unit,
      line.quantity !== null && line.unit_price !== null
        ? lineAmount(line.quantity, line.unit_price)
        : "",
    ]),
  ];
  const sheet = XLSX.utils.aoa_to_sheet(rows);
  sheet["!merges"] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 15 } }];
  sheet["!cols"] = [
    6, 24, 30, 16, 20, 20, 16, 16, 16, 16, 14, 32, 32, 14, 8, 16,
  ].map((wch) => ({ wch }));
  sheet["!autofilter"] = { ref: `A4:P${Math.max(4, rows.length)}` };
  for (let r = 4; r < rows.length; ++r)
    for (const c of [8, 9, 15]) {
      const cell = sheet[XLSX.utils.encode_cell({ r, c })];
      if (cell?.t === "n") cell.z = "#,##0.00";
    }
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "报价明细");
  const fileRows = [
    ["图号", "版本", "文件名", "文件类型", "来源"],
    ...quote.lines.flatMap((line) =>
      line.files.map((file) => [
        line.drawing_no,
        line.drawing_revision,
        file.name,
        file.kind === "pdf" ? "二维 PDF" : "三维模型",
        file.is_demo ? "示例文件名，不含真实文件" : "本次浏览器选择的文件",
      ]),
    ),
  ];
  const fileSheet = XLSX.utils.aoa_to_sheet(fileRows);
  fileSheet["!cols"] = [24, 12, 45, 16, 38].map((wch) => ({ wch }));
  XLSX.utils.book_append_sheet(workbook, fileSheet, "附件清单");
  return new Uint8Array(
    XLSX.write(workbook, { type: "array", bookType: "xlsx" }),
  );
}
export function downloadBytes(bytes: Uint8Array, name: string, type: string) {
  const url = URL.createObjectURL(
    new Blob([new Uint8Array(bytes).buffer], { type }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function safeName(value: string) {
  return (
    value.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").replace(/^\.+$/, "_") ||
    "file"
  );
}
const crcTable = Array.from({ length: 256 }, (_, n) => {
  for (let i = 0; i < 8; ++i) n = n & 1 ? 0xedb88320 ^ (n >>> 1) : n >>> 1;
  return n >>> 0;
});
function crc32(bytes: Uint8Array) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}
// 无压缩 ZIP，UTF-8 文件名；文件仅从用户本次选择的浏览器 File 对象读取。
export function zipFiles(entries: { name: string; bytes: Uint8Array }[]) {
  const local: Uint8Array[] = [],
    central: Uint8Array[] = [];
  let offset = 0;
  for (const entry of entries) {
    const name = new TextEncoder().encode(entry.name),
      crc = crc32(entry.bytes);
    const header = new Uint8Array(30 + name.length),
      h = new DataView(header.buffer);
    h.setUint32(0, 0x04034b50, true);
    h.setUint16(4, 20, true);
    h.setUint16(6, 0x800, true);
    h.setUint16(12, 33, true);
    h.setUint32(14, crc, true);
    h.setUint32(18, entry.bytes.length, true);
    h.setUint32(22, entry.bytes.length, true);
    h.setUint16(26, name.length, true);
    header.set(name, 30);
    local.push(header, entry.bytes);
    const directory = new Uint8Array(46 + name.length),
      d = new DataView(directory.buffer);
    d.setUint32(0, 0x02014b50, true);
    d.setUint16(4, 20, true);
    d.setUint16(6, 20, true);
    d.setUint16(8, 0x800, true);
    d.setUint32(16, crc, true);
    d.setUint32(20, entry.bytes.length, true);
    d.setUint32(24, entry.bytes.length, true);
    d.setUint16(28, name.length, true);
    d.setUint32(42, offset, true);
    directory.set(name, 46);
    d.setUint16(14, 33, true);
    central.push(directory);
    offset += header.length + entry.bytes.length;
  }
  const size = central.reduce((sum, bytes) => sum + bytes.length, 0),
    end = new Uint8Array(22),
    e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true);
  e.setUint16(8, entries.length, true);
  e.setUint16(10, entries.length, true);
  e.setUint32(12, size, true);
  e.setUint32(16, offset, true);
  const output = new Uint8Array(offset + size + end.length);
  let cursor = 0;
  for (const chunk of [...local, ...central, end]) {
    output.set(chunk, cursor);
    cursor += chunk.length;
  }
  return output;
}
export async function exportQuote(
  quote: Quote,
  files: LocalDrawings,
  withDrawings = false,
) {
  const workbook = await quoteWorkbook(quote),
    base = `演示_${safeName(quote.quote_no)}_R${quote.revision}`;
  if (!withDrawings) {
    downloadBytes(
      workbook,
      `${base}.xlsx`,
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    return { included: 0, missing: 0 };
  }
  const entries = [{ name: `${base}.xlsx`, bytes: workbook }],
    missing: string[] = [];
  let included = 0;
  for (const [index, line] of quote.lines.entries())
    for (const attachment of line.files) {
      const file = files.get(attachment.id);
      if (!file) {
        missing.push(
          `${line.drawing_no} / ${attachment.name}：示例仅文件名，不含真实图纸`,
        );
        continue;
      }
      entries.push({
        name: `drawings/${String(index + 1).padStart(3, "0")}_${safeName(line.drawing_no)}/${safeName(file.name)}`,
        bytes: new Uint8Array(await file.arrayBuffer()),
      });
      ++included;
    }
  entries.push({
    name: "演示说明.txt",
    bytes: new TextEncoder().encode(
      ["前端流程演示文件，请勿作为正式报价发给客户。", ...missing].join("\n"),
    ),
  });
  downloadBytes(zipFiles(entries), `${base}.zip`, "application/zip");
  return { included, missing: missing.length };
}
