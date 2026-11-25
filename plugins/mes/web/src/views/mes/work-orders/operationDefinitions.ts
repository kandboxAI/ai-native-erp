import type { MesOrderDefinition } from "@plugins/mes/web/src/api/mes";

export type OperationDefinition = MesOrderDefinition["operations"][number];
let nextKey = 0;
export function operation(index: number) {
  return {
    key: ++nextKey,
    process_id: null as string | null,
    equipment_id: null as string | null,
    requirement_id: null as string | null,
    operation_no: String(index * 10),
    operation_name: "",
    work_center_name: "",
    workstation_name: "",
    assigned_user_id: "",
    planned_quantity: undefined as number | undefined,
    standard_minutes_per_unit: undefined as number | null | undefined,
    operation_description: "",
    assigned_user_name: "",
    is_quality_required: false,
  };
}

export type OperationDraft = ReturnType<typeof operation>;
export type OperationForm = {
  org_id: string;
  product_item_id: string;
  planned_quantity: number;
  process_template_id: string | null;
  process_template_version_snapshot: number | null;
  operations: OperationDraft[];
};
export function operationDrafts(rows: OperationDefinition[]) {
  return rows.map((row, index) => ({
    ...operation(index + 1),
    ...row,
    assigned_user_id: row.assigned_user_id || "",
    assigned_user_name: row.assigned_user_name || "",
    work_center_name: row.work_center_name || "",
    workstation_name: row.workstation_name || "",
    operation_description: row.operation_description || "",
  }));
}
export function operationPayload(
  rows: OperationDefinition[],
): OperationDefinition[] {
  const numbers = new Set<string>();
  return rows.map((row, index) => {
    const no = row.operation_no.trim(),
      name = row.operation_name.trim();
    if (!no || !name) throw Error(`请补全第 ${index + 1} 道工序的编号和名称`);
    if (numbers.has(no)) throw Error("工序编号不能重复");
    numbers.add(no);
    if (
      row.planned_quantity != null &&
      (!Number.isFinite(row.planned_quantity) || row.planned_quantity <= 0)
    )
      throw Error("工序计划数量须为正数");
    if (
      row.standard_minutes_per_unit != null &&
      (!Number.isFinite(row.standard_minutes_per_unit) ||
        row.standard_minutes_per_unit <= 0)
    )
      throw Error("单件工时须为正数");
    return {
      operation_no: no,
      operation_name: name,
      process_id: row.process_id || null,
      equipment_id: row.equipment_id || null,
      requirement_id: row.requirement_id || null,
      planned_quantity: row.planned_quantity || undefined,
      standard_minutes_per_unit: row.standard_minutes_per_unit ?? null,
      work_center_name: row.work_center_name?.trim() || undefined,
      workstation_name: row.workstation_name?.trim() || undefined,
      assigned_user_id: row.assigned_user_id || undefined,
      assigned_user_name: row.assigned_user_id
        ? row.assigned_user_name || undefined
        : undefined,
      is_quality_required: row.is_quality_required ?? false,
      operation_description: row.operation_description?.trim() || undefined,
    };
  });
}
