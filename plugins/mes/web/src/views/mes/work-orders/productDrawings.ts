import { uploadFile, discardFile } from "@/api/systemFile";

import type { MesProductDrawing } from "@plugins/mes/web/src/api/mes";
export type ProductDrawing = MesProductDrawing;
export function drawingKind(name: string) {
  if (/\.pdf$/i.test(name)) return "pdf";
  if (/\.(stp|step)$/i.test(name)) return "model";
  return undefined;
}
export function selectProductDrawings(
  files: File[],
  kind: ProductDrawing["kind"],
  existingCount: number,
): ProductDrawing[] {
  if (files.length > 1)
    throw new Error("每个货品只允许一份 PDF 和一份 STP/STEP");
  if (existingCount + files.length > 2)
    throw new Error("图纸与模型合计最多2个文件");
  return files.map((raw) => {
    if (drawingKind(raw.name) !== kind)
      throw new Error(
        kind === "pdf" ? "二维图纸只支持PDF文件" : "三维模型只支持STP/STEP文件",
      );
    if (raw.size <= 0 || raw.size > 20 * 1024 * 1024)
      throw new Error("每个文件须大于0且不超过20MB");
    return { name: raw.name, kind, size: raw.size, raw };
  });
}
/** One picker accepts both types; validate the whole batch before replacing either slot. */
export function mergeProductDrawingSelection(
  incoming: File[],
  current: ProductDrawing[] = [],
): ProductDrawing[] {
  if (!incoming.length) return [...current];
  if (incoming.length > 2)
    throw new Error("一次最多选择一份 PDF 和一份 STP/STEP");
  const selected = incoming.map((raw) => {
    const kind = drawingKind(raw.name);
    if (!kind) throw new Error("只支持 PDF 图纸和 STP/STEP 三维模型");
    return selectProductDrawings([raw], kind, 0)[0];
  });
  const kinds = new Set(selected.map((file) => file.kind));
  if (kinds.size !== selected.length)
    throw new Error(
      "同一批次每类只能选择一份文件，请选择一份 PDF 和一份 STP/STEP",
    );
  return [...current.filter((file) => !kinds.has(file.kind)), ...selected].sort(
    (a, b) => Number(a.kind === "model") - Number(b.kind === "model"),
  );
}
export async function uploadProductDrawings(files: ProductDrawing[] = []) {
  if (
    files.length > 2 ||
    new Set(files.map((file) => file.kind)).size !== files.length
  )
    throw new Error("每个货品只允许一份 PDF 和一份 STP/STEP");
  const ids: string[] = [];
  for (const file of files) {
    if (!file.id) {
      if (!file.raw || drawingKind(file.name) !== file.kind)
        throw new Error("图纸文件已失效，请重新选择");
      const contentType =
        file.kind === "pdf" ? "application/pdf" : "application/step";
      const raw =
        file.raw.type === contentType
          ? file.raw
          : new File([file.raw], file.raw.name, { type: contentType });
      const uploaded = await uploadFile(raw, "mes_work_order_drawing");
      file.id = uploaded.id;
      file.pending = true;
    }
    ids.push(file.id);
  }
  return ids;
}
export function releaseProductDrawings(
  files: ProductDrawing[] = [],
  retained: ProductDrawing[] = [],
) {
  const keep = new Set(retained.map((file) => file.id).filter(Boolean));
  for (const file of files)
    if (file.pending && file.id && !keep.has(file.id))
      discardFile(file.id).catch(() => undefined);
}
export function markProductDrawingsBound(files: ProductDrawing[] = []) {
  for (const file of files) file.pending = false;
}
