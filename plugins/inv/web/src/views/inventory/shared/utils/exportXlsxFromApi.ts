import dayjs from "dayjs";

export const DEFAULT_EXPORT_LIMIT = 10_000;

export function omitEmptyParams<T extends Record<string, unknown>>(
  params: T
): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(
      ([, v]) => v !== undefined && v !== null && v !== ""
    )
  ) as Partial<T>;
}

/** 处理通用 `/export` Blob：若为 JSON（错误响应）则解析抛出带 message；否则触发下载 `.xlsx`。 */
export async function saveExcelBlob(
  blob: Blob,
  basename: string
): Promise<void> {
  const t = (blob.type || "").toLowerCase();
  if (
    t.includes("application/json") ||
    (t.includes("text/") && !t.includes("spreadsheet"))
  ) {
    const text = await blob.text();
    let msg = "导出失败";
    try {
      const j = JSON.parse(text) as { message?: string; detail?: unknown };
      if (typeof j.message === "string" && j.message) msg = j.message;
      else if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* noop */
    }
    throw new Error(msg);
  }
  const name = `${basename}_${dayjs().format("YYYY-MM-DD_HHmm")}.xlsx`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
