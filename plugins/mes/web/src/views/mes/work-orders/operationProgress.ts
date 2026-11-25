import type { MesOperationProgress } from "@plugins/mes/web/src/api/mes";

const tones: Record<string, string> = {
  completed: "success",
  in_progress: "primary",
  dispatched: "primary",
  waiting_quality: "warning",
  paused: "warning",
};

const numberFormat = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 6,
});
export const progressQuantity = (value: number) => numberFormat.format(value);

export function durationText(minutes?: number | null) {
  if (minutes == null) return "—";
  const whole = Math.round(minutes);
  if (!whole && minutes > 0) return "不足1分钟";
  const hours = Math.floor(whole / 60),
    rest = whole % 60;
  return hours ? `${hours}小时${rest ? `${rest}分` : ""}` : `${rest}分钟`;
}

export function operationProgressSteps(
  operations: MesOperationProgress[] = [],
) {
  return [...operations]
    .sort((a, b) => a.sequence_no - b.sequence_no || a.id.localeCompare(b.id))
    .map((operation) => {
      const reported =
        operation.good_quantity +
        operation.scrap_quantity +
        operation.rework_quantity;
      const isQuantityUnknown =
        operation.is_imported_snapshot && reported === 0;
      const percentage =
        isQuantityUnknown && operation.status_code === "completed"
          ? 100
          : operation.planned_quantity > 0
            ? reported >= operation.planned_quantity
              ? 100
              : Math.min(
                  99,
                  Math.max(
                    0,
                    Math.floor(
                      Number(
                        ((reported / operation.planned_quantity) * 100).toFixed(
                          8,
                        ),
                      ),
                    ),
                  ),
                )
            : 0;
      return {
        ...operation,
        reported,
        isQuantityUnknown,
        percentage,
        tone:
          operation.status_code === "cancelled"
            ? "muted"
            : tones[operation.status_code] || "muted",
        tooltip: isQuantityUnknown
          ? `${operation.operation_name}：原系统状态为${operation.status_label}；报工数量及实际起止时间未提供，完成标记按原状态展示，不代表已导入报工或检验放行。`
          : `${operation.operation_no} · ${operation.operation_name}｜${operation.status_label}；已报 ${progressQuantity(reported)} / ${progressQuantity(operation.planned_quantity)}（合格 ${progressQuantity(operation.good_quantity)}、报废 ${progressQuantity(operation.scrap_quantity)}、返工 ${progressQuantity(operation.rework_quantity)}）。百分比按已报数量计算，不代表检验放行。`,
      };
    });
}
