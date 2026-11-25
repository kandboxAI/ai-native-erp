<script setup lang="ts">
import type { MesTask } from "@plugins/mes/web/src/api/mes";
import { formatMesDate, mesDispatchPersonLabel, mesStatusType } from "../shared";
import {
  canSchedule,
  duration,
  overlapMinutes,
  progress,
  today
} from "./model";
withDefaults(
  defineProps<{
    rows: MesTask[];
    loading?: boolean;
    editable?: boolean;
    inspectable?: boolean;
    days?: string[];
    actions?: boolean;
    selectionEnabled?: boolean;
    showOrder?: boolean;
  }>(),
  { days: () => [], actions: true, selectionEnabled: true, showOrder: true }
);
defineEmits<{
  selection: [rows: MesTask[]];
  edit: [row: MesTask];
  whole: [row: MesTask];
  inspect: [row: MesTask];
  day: [row: MesTask, day: string];
}>();
</script>
<template>
  <el-table
    v-loading="loading"
    :data="rows"
    row-key="id"
    max-height="620"
    @selection-change="value => $emit('selection', value)"
  >
    <el-table-column
      v-if="editable && selectionEnabled"
      type="selection"
      :selectable="canSchedule"
      width="42"
      fixed="left"
    />
    <el-table-column
      v-if="showOrder"
      label="工单 / 项目 / 产品"
      min-width="245"
      :fixed="days.length ? 'left' : undefined"
    >
      <template #default="{ row }"
        ><el-button
          v-if="inspectable"
          link
          type="primary"
          @click="$emit('inspect', row as MesTask)"
          >{{ row.work_order_no }}</el-button
        ><strong v-else>{{ row.work_order_no }}</strong>
        <div>{{ row.product_item_name }}</div>
        <small>{{ row.project_name || row.product_item_no }}</small></template
      >
    </el-table-column>
    <el-table-column label="工序 / 已报进度" min-width="165"
      ><template #default="{ row }"
        ><div>{{ row.sequence_no }}. {{ row.operation_name }}</div>
        <el-progress
          :percentage="progress(row as MesTask)"
          :stroke-width="5"
        /><small
          >已报
          {{ row.good_quantity + row.scrap_quantity + row.rework_quantity }} /
          {{ row.planned_quantity }} {{ row.unit_name }}</small
        ></template
      ></el-table-column
    >
    <el-table-column label="设备 / 工作中心" min-width="155"
      ><template #default="{ row }"
        >{{ row.workstation_name || "未分配" }}
        <div>
          <small>{{ row.work_center_name || "—" }}</small>
        </div></template
      ></el-table-column
    >
    <el-table-column label="计划开始 / 结束" min-width="180"
      ><template #default="{ row }"
        >{{ formatMesDate(row.planned_start_at) }}
        <div>{{ formatMesDate(row.planned_end_at) }}</div>
        <small
          v-if="
            row.planned_end_at &&
            row.due_at &&
            new Date(row.planned_end_at) > new Date(row.due_at)
          "
          class="warning"
          >计划晚于交期</small
        ></template
      ></el-table-column
    >
    <el-table-column label="状态 / 交期" min-width="145"
      ><template #default="{ row }"
        ><el-tag :type="mesStatusType(row.status_code)">{{
          row.status_label
        }}</el-tag>
        <div>
          <small>{{ formatMesDate(row.due_at) }}</small>
        </div></template
      ></el-table-column
    >
    <el-table-column v-if="!days.length" label="实际开始 / 完成" min-width="180"
      ><template #default="{ row }"
        >{{ formatMesDate(row.actual_started_at) }}
        <div>{{ formatMesDate(row.actual_finished_at) }}</div></template
      ></el-table-column
    >
    <el-table-column v-if="!days.length" label="安排人员" min-width="120">
      <template #default="{ row }">{{ mesDispatchPersonLabel(row) }}</template>
    </el-table-column>
    <el-table-column
      v-for="day in days"
      :key="day"
      :label="`${day.slice(5)}${day === today() ? ' 今日' : ''}`"
      width="145"
      align="center"
    >
      <template #default="{ row }"
        ><button
          class="day-slot"
          :class="{
            planned:
              overlapMinutes(row.planned_start_at, row.planned_end_at, day) > 0,
            complete: row.status_code === 'completed',
            today: day === today()
          }"
          :disabled="!editable || !canSchedule(row as MesTask)"
          :aria-label="`${row.work_order_no} ${row.operation_name} ${day} 计划`"
          @click="$emit('day', row as MesTask, day)"
        >
          <template
            v-if="
              overlapMinutes(row.planned_start_at, row.planned_end_at, day) > 0
            "
            ><strong>{{ row.operation_name }}</strong
            ><small>{{
              duration(
                overlapMinutes(row.planned_start_at, row.planned_end_at, day)
              )
            }}</small></template
          ><span v-else>{{
            editable && canSchedule(row as MesTask) ? "＋ 安排" : "—"
          }}</span>
        </button></template
      >
    </el-table-column>
    <el-table-column
      v-if="editable && actions"
      label="操作"
      width="230"
      fixed="right"
      ><template #default="{ row }"
        ><el-button
          link
          type="primary"
          :disabled="!canSchedule(row as MesTask)"
          @click="$emit('edit', row as MesTask)"
          >调整本工序</el-button
        ><el-button link type="primary" @click="$emit('whole', row as MesTask)"
          >整单人工计划</el-button
        ></template
      ></el-table-column
    >
  </el-table>
</template>
<style scoped>
small {
  color: var(--el-text-color-secondary);
}

.warning {
  color: var(--el-color-danger);
}

.day-slot {
  width: 100%;
  min-height: 58px;
  padding: 6px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: 5px;
}

.day-slot strong,
.day-slot small {
  display: block;
}

.day-slot.planned {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
}

.day-slot.complete {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.day-slot.today {
  border-color: var(--el-color-primary);
}

.day-slot:disabled {
  cursor: default;
}
</style>
