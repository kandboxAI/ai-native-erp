import type { MesOrderDefinition } from "@plugins/mes/web/src/api/mes";

/** 路线只保存工艺定义，不带入当前工单的数量、人员或执行事实。 */
export function routeOperations(operations: MesOrderDefinition["operations"]) {
  if (!operations.length) throw new Error("请先添加至少一道工序");
  const numbers = new Set<string>();
  return operations.map((row, index) => {
    const operation_no = row.operation_no.trim(),
      operation_name = row.operation_name.trim();
    if (!operation_no || !operation_name)
      throw new Error(`请补全第 ${index + 1} 道工序的编号和名称`);
    if (numbers.has(operation_no))
      throw new Error(`工序编号 ${operation_no} 重复，请先调整`);
    numbers.add(operation_no);
    return {
      operation_no,
      operation_name,
      process_id: row.process_id || null,
      equipment_id: row.equipment_id || null,
      requirement_id: row.requirement_id || null,
      work_center_name: row.work_center_name?.trim() || undefined,
      workstation_name: row.workstation_name?.trim() || undefined,
      is_quality_required: row.is_quality_required ?? false,
      standard_minutes_per_unit: row.standard_minutes_per_unit ?? null,
      operation_description: row.operation_description?.trim() || undefined,
    };
  });
}
