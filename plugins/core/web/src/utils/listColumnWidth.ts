/** 普通数据列共同参与空间分配，避免仅少数 minWidth 列吸收整张表的空余宽度。 */
export function listColumnWidth(
  column: Record<string, any>,
  keepFixedWidth = false
): { width?: undefined; minWidth?: number } {
  if (
    keepFixedWidth ||
    ["selection", "index", "expand"].includes(column.type) ||
    column.children?.length ||
    column.listWidthFixed === true ||
    column["list-width-fixed"] === true ||
    column.listWidthFixed === "" ||
    column["list-width-fixed"] === ""
  )
    return {};
  const value = column.width ?? column.minWidth ?? column["min-width"] ?? 140;
  // 保留百分比、动态宽度等特殊声明，不能用 parseInt 静默改成像素。
  if (!/^(?:\d+(?:\.\d+)?)(?:px)?$/.test(String(value))) return {};
  const minimum = Number(String(value).replace(/px$/, ""));
  return Number.isFinite(minimum) && minimum > 0
    ? { width: undefined, minWidth: minimum }
    : {};
}
