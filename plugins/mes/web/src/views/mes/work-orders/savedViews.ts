import type { MesListParams } from "@plugins/mes/web/src/api/mes";
export type MesSavedView = {
  name: string;
  mode: "project" | "product";
  filters: MesListParams;
};
const strings = [
  "keyword",
  "status_code",
  "priority_code",
  "customer",
  "creator",
  "order_type_code",
  "processing_type_code",
  "created_from",
  "created_to",
  "due_from",
  "due_to",
  "configuration",
] as const;
function cleanFilters(source: unknown): MesListParams {
  if (!source || typeof source !== "object" || Array.isArray(source)) return {};
  const result: Record<string, any> = {};
  for (const key of strings)
    if (typeof source[key] === "string" && source[key].length <= 128)
      result[key] = source[key];
  result.overdue_only = source["overdue_only"] === true;
  return result;
}
export function loadMesViews(
  storage: Pick<Storage, "getItem">,
  userId?: string,
): MesSavedView[] {
  if (!userId) return [];
  try {
    const value = JSON.parse(
      storage.getItem(`mes-work-order-views:${userId}`) || "[]",
    );
    return Array.isArray(value)
      ? value
          .filter(
            (row) =>
              row &&
              typeof row.name === "string" &&
              row.name.trim() &&
              row.name.length <= 40 &&
              ["project", "product"].includes(row.mode),
          )
          .slice(0, 10)
          .map((row) => ({
            name: row.name,
            mode: row.mode,
            filters: cleanFilters(row.filters),
          }))
      : [];
  } catch {
    return [];
  }
}
export function saveMesViews(
  storage: Pick<Storage, "setItem">,
  userId: string | undefined,
  views: MesSavedView[],
) {
  if (!userId) throw new Error("登录状态已变化，请重新登录");
  storage.setItem(
    `mes-work-order-views:${userId}`,
    JSON.stringify(
      views.slice(0, 10).map((row) => ({
        name: row.name.slice(0, 40),
        mode: row.mode,
        filters: cleanFilters(row.filters),
      })),
    ),
  );
}
