<script setup lang="ts">
import { computed, ref } from "vue";
import type { MesTask } from "@plugins/mes/web/src/api/mes";
import { formatMesDate } from "../shared";
import TaskTable from "./TaskTable.vue";
import { progress, scheduleWorkOrders, type ScheduleWorkOrder } from "./model";

const props = withDefaults(
  defineProps<{
    rows: MesTask[];
    loading?: boolean;
    editable?: boolean;
    inspectable?: boolean;
    days?: string[];
  }>(),
  { days: () => [] }
);
const emit = defineEmits<{
  selection: [rows: MesTask[]];
  auto: [row: MesTask];
  edit: [row: MesTask];
  whole: [row: MesTask];
  inspect: [row: MesTask];
  day: [row: MesTask, day: string];
}>();
const table = ref();
const groups = computed(() => scheduleWorkOrders(props.rows));
const picked = ref<ScheduleWorkOrder[]>([]);
let selecting = false;
function select(rows: ScheduleWorkOrder[]) {
  if (selecting) return;
  const kept = rows
    .filter(
      row => row.canAutoSchedule && row.first.org_id === rows[0]?.first.org_id
    )
    .slice(0, 10);
  selecting = true;
  try {
    for (const row of rows) {
      if (!kept.includes(row)) table.value?.toggleRowSelection(row, false);
    }
    picked.value = kept;
    emit(
      "selection",
      kept.map(row => row.first)
    );
  } finally {
    selecting = false;
  }
}
function selectable(row: ScheduleWorkOrder) {
  if (!row.canAutoSchedule) return false;
  if (picked.value.some(item => item.id === row.id)) return true;
  return (
    picked.value.length < 10 &&
    (!picked.value.length || picked.value[0].first.org_id === row.first.org_id)
  );
}
function expand(row: ScheduleWorkOrder) {
  table.value?.toggleRowExpansion(row);
}
defineExpose({ clearSelection: () => table.value?.clearSelection() });
</script>

<template>
  <el-table
    ref="table"
    v-loading="loading"
    :data="groups"
    row-key="id"
    @selection-change="select"
  >
    <el-table-column
      v-if="editable"
      type="selection"
      :selectable="selectable"
      width="44"
    />
    <el-table-column type="expand" width="40">
      <template #default="{ row }">
        <div class="order-operations">
          <div class="operation-heading">
            <strong>{{ row.first.work_order_no }} · 工序明细</strong
            ><span>按执行顺序排列，可单独调整工序计划</span>
          </div>
          <TaskTable
            :rows="row.tasks"
            :editable="editable"
            :inspectable="inspectable"
            :days="days"
            :selection-enabled="false"
            :show-order="false"
            @edit="task => emit('edit', task)"
            @whole="task => emit('whole', task)"
            @inspect="task => emit('inspect', task)"
            @day="(task, day) => emit('day', task, day)"
          />
        </div>
      </template>
    </el-table-column>
    <el-table-column label="货品工单 / 产品" min-width="235">
      <template #default="{ row }">
        <el-button
          v-if="inspectable"
          type="primary"
          link
          @click="emit('inspect', row.first)"
          >{{ row.first.work_order_no }}</el-button
        >
        <strong v-else>{{ row.first.work_order_no }}</strong>
        <div>{{ row.first.product_item_name }}</div>
        <small
          >{{ row.first.product_item_no
          }}<template v-if="row.first.project_name">
            · {{ row.first.project_name }}</template
          ></small
        >
      </template>
    </el-table-column>
    <el-table-column label="工艺路线" min-width="360">
      <template #default="{ row }">
        <div class="route-summary">
          <strong>{{ row.tasks.length }} 道工序</strong
          ><small>已完成 {{ row.completed }} 道</small>
        </div>
        <div class="route-steps">
          <el-tooltip
            v-for="(task, index) in row.tasks.slice(0, 6)"
            :key="task.id"
            :content="`${task.sequence_no}. ${task.operation_name} · ${task.status_label} · ${progress(task)}%`"
          >
            <button
              class="route-step"
              :class="{ complete: task.status_code === 'completed' }"
              @click="expand(row as ScheduleWorkOrder)"
            >
              <span v-if="index" class="route-arrow" aria-hidden="true">→</span
              ><span>{{ task.operation_name }}</span
              ><b>{{ progress(task) }}%</b>
            </button>
          </el-tooltip>
          <el-button
            v-if="row.tasks.length > 6"
            type="primary"
            link
            @click="expand(row as ScheduleWorkOrder)"
            >另 {{ row.tasks.length - 6 }} 道</el-button
          >
        </div>
      </template>
    </el-table-column>
    <el-table-column label="计划安排" width="155">
      <template #default="{ row }">
        <el-tag
          :type="
            row.scheduled === row.tasks.length
              ? 'success'
              : row.scheduled
                ? 'warning'
                : 'info'
          "
          >{{
            row.scheduled === row.tasks.length
              ? "全部已安排"
              : row.scheduled
                ? "部分已安排"
                : "尚未安排"
          }}</el-tag
        >
        <div>
          <small
            >{{ row.scheduled }} / {{ row.tasks.length }} 道已安排时间</small
          >
        </div>
        <small v-if="row.first.work_order_status_code === 'draft'"
          >工单尚未下单</small
        >
      </template>
    </el-table-column>
    <el-table-column label="交付时间" width="160"
      ><template #default="{ row }">{{
        formatMesDate(row.first.due_at)
      }}</template></el-table-column
    >
    <el-table-column label="操作" :width="editable ? 190 : 110" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link @click="expand(row as ScheduleWorkOrder)"
          >查看工序</el-button
        >
        <el-button
          v-if="editable"
          type="primary"
          link
          :disabled="!row.canAutoSchedule"
          @click="emit('auto', row.first)"
          >自动排程</el-button
        >
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
small {
  color: var(--el-text-color-secondary);
}

.route-summary,
.route-steps,
.route-step,
.operation-heading {
  display: flex;
  gap: 10px;
  align-items: center;
}

.route-summary {
  margin-bottom: 10px;
}

.route-steps {
  flex-wrap: wrap;
  gap: 8px;
}

.route-step {
  padding: 4px 8px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.route-step b {
  font-size: 12px;
  color: var(--el-color-primary);
}

.route-step.complete b {
  color: var(--el-color-success);
}

.route-step:hover,
.route-step:focus-visible {
  border-color: var(--el-color-primary);
}

.route-arrow {
  color: var(--el-text-color-placeholder);
}

.order-operations {
  padding: 20px;
  background: var(--el-fill-color-extra-light);
}

.operation-heading {
  flex-wrap: wrap;
  justify-content: space-between;
  margin-bottom: 20px;
}

.operation-heading span {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
