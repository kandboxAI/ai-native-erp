import {
  newLine,
  DEFAULT_DRAWING_REVISION,
  type QuoteLine,
  type QuoteFile,
} from "./api";

export type ImportItem = Pick<
  QuoteLine,
  | "drawing_no"
  | "quantity"
  | "description"
  | "customer_material"
  | "surface_treatment"
  | "note"
> & { row_no: number };
export type ExcelPreview = {
  items: ImportItem[];
  errors: { row_no: number; message: string }[];
  total_rows: number;
};
export type DrawingImport = {
  file: File;
  drawing_no: string;
  kind: QuoteFile["kind"];
  action: string;
  error: string;
  message?: string;
  is_skipped: boolean;
  status: "待上传" | "上传中" | "已上传" | "上传失败" | "已跳过";
};
export type DrawingImportMode = "existing" | "add";
const key = (value: string) => value.trim().toLowerCase();
export const isBlank = (line: QuoteLine) =>
  !line.id &&
  !line.drawing_no &&
  !line.description &&
  !line.customer_material &&
  !line.surface_treatment &&
  !line.note &&
  (!line.drawing_revision ||
    line.drawing_revision === DEFAULT_DRAWING_REVISION) &&
  !line.files.length &&
  line.quantity === 1;

function matching(lines: QuoteLine[], number: string) {
  const matches = lines.filter((line) => key(line.drawing_no) === key(number));
  if (matches.length > 1)
    throw Error(`${number} 存在多条货品或多个版本，请先在明细中明确图号`);
  return matches[0];
}

/** Pure preflight: no mutation, so a rejected row never partially alters the draft. */
export function mergeExcel(lines: QuoteLine[], items: ImportItem[]) {
  const result = lines.map((line) => ({ ...line, files: [...line.files] }));
  const seen = new Set<string>();
  let added = 0,
    updated = 0;
  for (const item of items) {
    if (seen.has(key(item.drawing_no)))
      throw Error(`${item.drawing_no} 图号重复`);
    seen.add(key(item.drawing_no));
    let line = matching(result, item.drawing_no);
    if (line) updated++;
    else {
      line = result.find(isBlank);
      if (!line) {
        line = newLine();
        result.push(line);
      }
      added++;
    }
    // Preserve identifiers, version, attachments and all fields outside the fixed template.
    Object.assign(line, {
      drawing_no: item.drawing_no,
      quantity: Number(item.quantity),
      description: item.description,
      customer_material: item.customer_material,
      surface_treatment: item.surface_treatment,
      note: item.note || "",
    });
  }
  if (result.length > 500) throw Error("导入后货品超过 500 项，请拆分询价");
  return { lines: result, added, updated };
}

export function planDrawings(
  lines: QuoteLine[],
  files: File[],
  target?: QuoteLine,
  mode: DrawingImportMode = "add",
): DrawingImport[] {
  const targetNumber = target
    ? target.drawing_no.trim() || files[0]?.name.replace(/\.[^.]+$/, "").trim()
    : "";
  const result = files.map((file) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    const kind: QuoteFile["kind"] = ext === "pdf" ? "pdf" : "model";
    const number = targetNumber || file.name.replace(/\.[^.]+$/, "").trim();
    let error = "",
      is_skipped = false,
      action = "新增货品";
    try {
      const line = target || (number ? matching(lines, number) : undefined);
      is_skipped = !target && mode === "existing" && !line;
      if (is_skipped) action = "跳过未匹配";
      else {
        if (!["pdf", "stp", "step"].includes(ext || ""))
          throw Error("仅支持 PDF、STP、STEP");
        if (!file.size || file.size > 20 * 1024 * 1024)
          throw Error("文件须非空且不超过 20MB");
        if (!number || number.length > 64)
          throw Error("图号为空或超过 64 字，请调整文件名");
        if (line)
          action = line.files.some((value) => value.kind === kind)
            ? "替换现有文件"
            : "匹配现有货品";
      }
    } catch (cause) {
      error = (cause as Error).message;
    }
    return {
      file,
      drawing_no: number,
      kind,
      action,
      error,
      is_skipped,
      status: is_skipped ? ("已跳过" as const) : ("待上传" as const),
    };
  });
  const counts = new Map<string, number>();
  const included = result.filter((row) => !row.is_skipped);
  included.forEach((row) => {
    const value = `${key(row.drawing_no)}:${row.kind}`;
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  included.forEach((row) => {
    if (counts.get(`${key(row.drawing_no)}:${row.kind}`)! > 1)
      row.error = "同图号重复上传同类文件，请仅保留一份（STP/STEP 属于同类）";
  });
  const additions = new Set(
    included
      .filter((row) => !row.error && row.action === "新增货品")
      .map((row) => key(row.drawing_no)),
  );
  if (
    lines.length + Math.max(0, additions.size - lines.filter(isBlank).length) >
    500
  )
    throw Error("导入后货品超过 500 项，请拆分询价");
  return result;
}

export function bindDrawing(
  lines: QuoteLine[],
  row: DrawingImport,
  file: QuoteFile,
  target?: QuoteLine,
) {
  if (row.is_skipped) throw Error("未匹配文件已跳过，不能绑定到货品");
  let line = target || matching(lines, row.drawing_no);
  if (!line) {
    line = lines.find(isBlank);
    if (!line) {
      line = newLine();
      lines.push(line);
    }
  }
  if (!line.drawing_no) {
    line.drawing_no = row.drawing_no;
    line.description ||= row.drawing_no;
  }
  line.files = [
    ...line.files.filter((value) => value.kind !== file.kind),
    file,
  ];
}
