import {
  clone,
  newLine,
  type DemoState,
  type Drawing,
  type QuoteLine,
} from "./model";

export function drawingKind(name: string): Drawing["kind"] {
  if (/\.pdf$/i.test(name)) return "pdf";
  if (/\.(stp|step)$/i.test(name)) return "model";
  throw Error("仅支持 PDF、STP、STEP 文件");
}
export class LocalDrawings {
  private files = new Map<string, File>();
  private urls = new Map<string, string>();
  private serial = 0;
  get(id: string) {
    return this.files.get(id);
  }
  clear() {
    this.urls.forEach((url) => URL.revokeObjectURL(url));
    this.urls.clear();
    this.files.clear();
  }
  url(drawing: Drawing) {
    const file = this.files.get(drawing.id);
    if (!file) throw Error("示例只展示文件名，请上传自己的图纸或模型后查看");
    if (!this.urls.has(drawing.id))
      this.urls.set(drawing.id, URL.createObjectURL(file));
    return this.urls.get(drawing.id)!;
  }
  attach(
    state: DemoState,
    lines: QuoteLine[],
    incoming: File[],
    targetId?: string,
  ): QuoteLine[] {
    if (!incoming.length) return lines;
    if (incoming.length > 100) throw Error("每次最多选择 100 个文件");
    if (
      [...this.files.values()].reduce((sum, file) => sum + file.size, 0) +
        incoming.reduce((sum, file) => sum + file.size, 0) >
      200 * 1024 * 1024
    )
      throw Error("本次演示文件累计不能超过 200MB，请重置演示后再试");
    const next = clone(lines),
      planned: { row: QuoteLine; file: File; kind: Drawing["kind"] }[] = [];
    const seen = new Set<string>();
    for (const file of incoming) {
      const kind = drawingKind(file.name);
      if (!file.size || file.size > 20 * 1024 * 1024)
        throw Error("单个文件不能为空且不能超过 20MB");
      const stem = file.name.replace(/\.[^.]+$/, "").trim();
      if (!stem) throw Error("文件名缺少图号，请重新命名或在货品行内选择文件");
      if (
        !targetId &&
        next.filter(
          (line) => line.drawing_no.trim().toLowerCase() === stem.toLowerCase(),
        ).length > 1
      )
        throw Error(`图号 ${stem} 存在多个版本，请在对应货品行内上传文件`);
      let row = targetId
        ? next.find((line) => line.id === targetId)
        : next.find(
            (line) =>
              line.drawing_no.trim().toLowerCase() === stem.toLowerCase(),
          );
      if (targetId && !row) throw Error("货品行已被移除");
      if (!row) {
        row = newLine(state);
        row.drawing_no = stem;
        row.description = stem;
        next.push(row);
      }
      const key = `${row.id}/${kind}`;
      if (seen.has(key))
        throw Error(
          `图号 ${row.drawing_no} 选中了多个${kind === "pdf" ? "PDF" : "三维模型"}，请分别上传确认版本`,
        );
      seen.add(key);
      planned.push({ row, file, kind });
    }
    for (const { row, file, kind } of planned) {
      const attachment: Drawing = {
        id: `local-file-${++this.serial}`,
        name: file.name,
        kind,
        size: file.size,
      };
      this.files.set(attachment.id, file);
      row.files = [
        ...row.files.filter((item) => item.kind !== kind),
        attachment,
      ];
    }
    return next;
  }
}
