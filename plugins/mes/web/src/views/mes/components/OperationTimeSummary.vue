<script setup lang="ts">
import type { MesOperationProgress } from "@plugins/mes/web/src/api/mes";
import { formatMesDate } from "../shared";
import { durationText } from "../work-orders/operationProgress";
defineProps<{ operation: MesOperationProgress }>();
</script>
<template>
  <div class="operation-times">
    <div class="time-heading">
      <strong>{{ operation.operation_name }}</strong
      ><span>{{ operation.status_label }}</span>
    </div>
    <div class="time-line">
      <span class="time-label">计划</span>
      <time>{{
        operation.planned_start_at
          ? formatMesDate(operation.planned_start_at)
          : "未设置"
      }}</time
      ><span>至</span>
      <time>{{
        operation.planned_end_at
          ? formatMesDate(operation.planned_end_at)
          : "待补充工时"
      }}</time>
      <strong>{{ durationText(operation.planned_duration_minutes) }}</strong>
    </div>
    <div class="time-line">
      <span class="time-label">实际</span>
      <time>{{
        operation.actual_started_at
          ? formatMesDate(operation.actual_started_at)
          : operation.is_imported_snapshot
            ? "未导入"
            : "未开始"
      }}</time
      ><span>至</span>
      <time>{{
        operation.actual_finished_at
          ? formatMesDate(operation.actual_finished_at)
          : operation.is_imported_snapshot
            ? "未导入"
            : "未完成"
      }}</time>
    </div>
    <p class="time-note">
      {{
        operation.plan_source_key === "schedule"
          ? "人工排程计划"
          : operation.is_imported_snapshot
            ? "原系统状态快照；历史计划与报工明细未提供，不按导入时间推算历史。"
            : "配置估算：单件工时 × 本工序计划数量，按工序顺序衔接；不占用设备排程。"
      }}
    </p>
  </div>
</template>
<style scoped>
.operation-times {
  min-width: 0;
}

.time-heading {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  color: var(--el-text-color-primary);
}

.time-heading > span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.time-line {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin: 10px 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.time-line time {
  min-width: 132px;
  color: var(--el-text-color-regular);
}

.time-label {
  padding: 1px 6px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
}

.time-note {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
</style>
