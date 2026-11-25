<script setup lang="ts">
import { ref, watch } from "vue";
import {
  getMesWorkOrder,
  type MesWorkOrder,
  type MesTask,
} from "@plugins/mes/web/src/api/mes";
import {
  formatMesDate,
  mesStatusType,
  mesWorkOrderStatusKey,
  mesWorkOrderStatusLabel,
  mesProcessingTypeLabel,
  mesPercent,
  mesReportedQuantity,
  isMesOverdue,
} from "../shared";
import TaskDetail from "./TaskDetail.vue";
import WorkOrderDrawings from "./WorkOrderDrawings.vue";
const props = defineProps<{ workOrderId?: string }>();
const visible = defineModel<boolean>({ default: false });
const detail = ref<Awaited<ReturnType<typeof getMesWorkOrder>>["data"]>();
const loading = ref(false);
const error = ref("");
const taskVisible = ref(false);
const taskId = ref("");
const sourceOrderId = ref("");
function emitSource(id: string) {
  sourceOrderId.value = id;
  load();
}
let request = 0;
async function load() {
  const current = ++request;
  detail.value = undefined;
  error.value = "";
  if (!visible.value || !props.workOrderId) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const res = await getMesWorkOrder(sourceOrderId.value || props.workOrderId);
    if (current === request) detail.value = res.data;
  } catch (cause: any) {
    if (current === request) error.value = cause?.message || "工单详情加载失败";
  } finally {
    if (current === request) loading.value = false;
  }
}
function inspect(id: string) {
  taskId.value = id;
  taskVisible.value = true;
}
watch(
  () => [visible.value, props.workOrderId],
  () => {
    taskVisible.value = false;
    sourceOrderId.value = "";
    load();
  },
);
</script>

<template>
  <el-drawer
    v-model="visible"
    title="生产工单详情"
    size="min(1180px, 98vw)"
    destroy-on-close
  >
    <div v-loading="loading" class="detail-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false"
        ><el-button link type="primary" @click="load"
          >重新加载</el-button
        ></el-alert
      >
      <template v-if="detail">
        <div class="order-heading">
          <div>
            <div class="eyebrow">生产工单</div>
            <h2>{{ detail.work_order_no }}</h2>
            <p>{{ detail.product_item_no }} · {{ detail.product_item_name }}</p>
          </div>
          <div class="heading-actions">
            <el-button
              v-if="sourceOrderId"
              @click="
                sourceOrderId = '';
                load();
              "
              >返回原工单</el-button
            ><el-tag :type="mesStatusType(mesWorkOrderStatusKey(detail))">{{
              mesWorkOrderStatusLabel(detail)
            }}</el-tag
            ><el-button @click="load">刷新</el-button>
          </div>
        </div>
        <el-descriptions :column="3" border
          ><el-descriptions-item label="计划数量"
            >{{ detail.planned_quantity }}
            {{ detail.unit_name }}</el-descriptions-item
          ><el-descriptions-item label="货品类型">{{
            mesProcessingTypeLabel(detail.processing_type_code)
          }}</el-descriptions-item
          ><el-descriptions-item label="优先级">{{
            detail.priority_label
          }}</el-descriptions-item
          ><el-descriptions-item label="交付时间"
            ><span :class="{ overdue: isMesOverdue(detail) }"
              >{{ formatMesDate(detail.due_at)
              }}{{ isMesOverdue(detail) ? " · 已逾期" : "" }}</span
            ></el-descriptions-item
          ><el-descriptions-item label="成品合格"
            >{{ detail.good_quantity }}
            {{ detail.unit_name }}</el-descriptions-item
          ><el-descriptions-item label="成品报废 / 返工"
            >{{ detail.scrap_quantity }} /
            {{ detail.rework_quantity }}</el-descriptions-item
          ><el-descriptions-item
            v-if="detail.material_name_snapshot"
            label="加工材料"
            >{{ detail.material_name_snapshot }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="detail.heat_treatment_snapshot"
            label="热处理"
            >{{ detail.heat_treatment_snapshot }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="detail.surface_treatment_snapshot"
            label="表面处理"
            >{{ detail.surface_treatment_snapshot }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="detail.process_requirement_snapshot"
            label="工艺要求"
            :span="3"
            >{{ detail.process_requirement_snapshot }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="detail.outsourced_due_at"
            label="外协交期"
            >{{ formatMesDate(detail.outsourced_due_at) }}</el-descriptions-item
          >
          <el-descriptions-item label="最近更新">{{
            formatMesDate(detail.updated_at)
          }}</el-descriptions-item></el-descriptions
        >
        <p class="muted">
          工单关闭时按末道工序结算成品产量；进行中的产出请查看下方各工序报工。
        </p>
        <p v-if="detail.source_work_order_id">
          返修来源：<el-button
            v-if="detail.source_work_order_no"
            link
            type="primary"
            @click="emitSource(detail.source_work_order_id)"
            >{{ detail.source_work_order_no }}</el-button
          ><span v-else>来源工单不在当前查看范围内</span>
        </p>
        <WorkOrderDrawings :order-id="detail.id" @saved="load" />
        <template v-if="detail.note"
          ><h3>工单说明</h3>
          <p class="instructions">{{ detail.note }}</p></template
        >
        <template v-if="detail.events?.length"
          ><h3>工单操作记录</h3>
          <el-timeline
            ><el-timeline-item
              v-for="event in detail.events"
              :key="event.id"
              :timestamp="formatMesDate(event.created_at)"
              >{{
                {
                  created: "创建",
                  updated: "变更配置",
                  published: "下单",
                  paused: "暂停生产",
                  resumed: "恢复生产",
                  withdrawn: "撤回下单",
                  completed: "完结",
                  cancelled: "取消",
                  deleted: "删除",
                  scheduled: "排程调整",
                  drawing_updated: "图纸更新",
                  report_corrected: "报工更正",
                  process_change_requested: "发起工艺变更",
                  process_change_closed: "关闭工艺变更",
                  process_changed: "工艺变更生效",
                }[event.event_type_code] || event.event_type_code
              }}
              · 版本 {{ event.version_no }}
              <p class="instructions muted">
                {{ event.note }}
              </p></el-timeline-item
            ></el-timeline
          ></template
        >
        <div class="section-heading">
          <h3>加工进度</h3>
          <span
            >完成 {{ detail.completed_operation_count }} /
            {{ detail.operation_count }} 道工序</span
          >
        </div>
        <el-progress
          :percentage="
            mesPercent(detail.completed_operation_count, detail.operation_count)
          "
          :stroke-width="8"
        />
        <div class="process-flow">
          <button
            v-for="task in detail.operations"
            :key="task.id"
            type="button"
            class="process-node"
            :class="[task.status_code]"
            @click="inspect(task.id)"
          >
            <span class="node-order">{{
              task.status_code === "completed" ? "✓" : task.sequence_no
            }}</span
            ><strong>{{ task.operation_name }}</strong
            ><small>{{ task.status_label }}</small
            ><small
              >{{ task.good_quantity }} / {{ task.planned_quantity }}
              {{ task.unit_name }} 合格</small
            >
          </button>
        </div>
        <div class="section-heading">
          <h3>工序明细</h3>
          <span>点击工序查看工艺说明与执行记录</span>
        </div>
        <el-table :data="detail.operations" row-key="id"
          ><el-table-column
            prop="sequence_no"
            label="顺序"
            width="65"
          /><el-table-column label="工序" min-width="145"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="inspect(row.id)"
                >{{ row.operation_no }} · {{ row.operation_name }}</el-button
              ></template
            ></el-table-column
          ><el-table-column label="派工人员" min-width="100"
            ><template #default="{ row }">{{
              row.assigned_user_name || "未派工"
            }}</template></el-table-column
          ><el-table-column
            prop="work_center_name"
            label="工作中心"
            min-width="100"
          /><el-table-column label="报工 / 计划" min-width="160"
            ><template #default="{ row }"
              ><el-progress
                :percentage="
                  mesPercent(mesReportedQuantity(row), row.planned_quantity)
                "
                :show-text="false"
                :stroke-width="6"
              /><small
                >{{ mesReportedQuantity(row) }} / {{ row.planned_quantity }}
                {{ row.unit_name }}</small
              ></template
            ></el-table-column
          ><el-table-column label="合格 / 报废 / 返工" min-width="150"
            ><template #default="{ row }"
              >{{ row.good_quantity }} / {{ row.scrap_quantity }} /
              {{ row.rework_quantity }}</template
            ></el-table-column
          ><el-table-column label="状态" width="100"
            ><template #default="{ row }"
              ><el-tag :type="mesStatusType(row.status_code)">{{
                row.status_label
              }}</el-tag></template
            ></el-table-column
          ><el-table-column label="实际开始 / 完成" min-width="175"
            ><template #default="{ row }"
              ><div>{{ formatMesDate(row.actual_started_at) }}</div>
              <div class="muted">
                {{ formatMesDate(row.actual_finished_at) }}
              </div></template
            ></el-table-column
          ></el-table
        >
        <p class="muted">
          报工进度包含合格、报废和返工；工序完成以执行状态为准。
        </p>
      </template>
    </div>
    <TaskDetail v-model="taskVisible" :task-id="taskId" />
  </el-drawer>
</template>

<style scoped>
.detail-body {
  min-height: 260px;
}

.instructions {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.order-heading,
.heading-actions,
.section-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.order-heading {
  margin-bottom: 24px;
}

.eyebrow,
.muted,
.section-heading span,
small {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

h2 {
  margin: 6px 0 8px;
  font-size: 26px;
}

h3 {
  margin: 0;
  font-size: 16px;
}

.section-heading {
  margin: 28px 0 16px;
}

p {
  margin: 10px 0;
}

.overdue {
  color: var(--el-color-danger);
}

.process-flow {
  display: flex;
  gap: 12px;
  padding: 22px 0 12px;
  overflow-x: auto;
}

.process-node {
  display: flex;
  flex: 0 0 150px;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  padding: 16px;
  text-align: left;
  cursor: pointer;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  transition: border-color 0.15s;
}

.process-node:hover,
.process-node:focus-visible {
  outline: 2px solid var(--el-color-primary-light-8);
  border-color: var(--el-color-primary);
}

.node-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-radius: 50%;
}

.completed .node-order {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.in_progress .node-order {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.paused .node-order,
.waiting_quality .node-order {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
</style>
