<script setup lang="ts">
import { ref, watch } from "vue";
import { getMesTask, type MesTaskDetail } from "@plugins/mes/web/src/api/mes";
import {
  formatMesDate,
  mesStatusType,
  mesReportedQuantity,
  mesPercent,
  mesDispatchPersonLabel,
} from "../shared";
const props = defineProps<{ taskId?: string }>();
const visible = defineModel<boolean>({ default: false });
const detail = ref<MesTaskDetail>();
const loading = ref(false);
const error = ref("");
let request = 0;
async function load() {
  const current = ++request;
  detail.value = undefined;
  error.value = "";
  if (!visible.value || !props.taskId) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const res = await getMesTask(props.taskId);
    if (current === request) detail.value = res.data;
  } catch (cause: any) {
    if (current === request) error.value = cause?.message || "任务详情加载失败";
  } finally {
    if (current === request) loading.value = false;
  }
}
watch(() => [visible.value, props.taskId], load);
</script>

<template>
  <el-drawer
    v-model="visible"
    title="工序任务详情"
    size="min(820px, 96vw)"
    append-to-body
    destroy-on-close
  >
    <div v-loading="loading" class="detail-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false"
        ><el-button link type="primary" @click="load"
          >重新加载</el-button
        ></el-alert
      >
      <template v-if="detail">
        <div class="task-heading">
          <div>
            <h2>{{ detail.operation_no }} · {{ detail.operation_name }}</h2>
            <p>{{ detail.work_order_no }} · {{ detail.product_item_name }}</p>
          </div>
          <el-tag :type="mesStatusType(detail.status_code)">{{
            detail.status_label
          }}</el-tag>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="产品编号">{{
            detail.product_item_no
          }}</el-descriptions-item
          ><el-descriptions-item label="派工人员">{{
            mesDispatchPersonLabel(detail)
          }}</el-descriptions-item>
          <el-descriptions-item label="工作中心">{{
            detail.work_center_name || "—"
          }}</el-descriptions-item
          ><el-descriptions-item label="工作站">{{
            detail.workstation_name || "—"
          }}</el-descriptions-item>
          <el-descriptions-item label="实际开始">{{
            formatMesDate(detail.actual_started_at)
          }}</el-descriptions-item
          ><el-descriptions-item label="实际完成">{{
            formatMesDate(detail.actual_finished_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="计划开始">{{
            formatMesDate(detail.planned_start_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="计划结束">{{
            formatMesDate(detail.planned_end_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="工艺说明" :span="2"
            ><span class="instructions">{{
              detail.operation_description || "未填写工艺说明"
            }}</span></el-descriptions-item
          >
          <el-descriptions-item label="质量要求" :span="2">{{
            detail.is_quality_required
              ? "需要检验放行（当前质量放行流程尚未接入）"
              : "无需独立检验放行"
          }}</el-descriptions-item>
        </el-descriptions>
        <h3>报工数量</h3>
        <div class="quantity-grid">
          <div>
            <small>计划</small
            ><strong
              >{{ detail.planned_quantity }} {{ detail.unit_name }}</strong
            >
          </div>
          <div>
            <small>合格</small><strong>{{ detail.good_quantity }}</strong>
          </div>
          <div>
            <small>报废</small><strong>{{ detail.scrap_quantity }}</strong>
          </div>
          <div>
            <small>返工</small><strong>{{ detail.rework_quantity }}</strong>
          </div>
        </div>
        <el-progress
          :percentage="
            mesPercent(mesReportedQuantity(detail), detail.planned_quantity)
          "
          :stroke-width="8"
        />
        <p class="muted">
          已报工 / 计划数量，包含合格、报废和返工；不代表已完成或已通过检验。
        </p>
        <template v-if="detail.material_requirements.length"
          ><h3>物料需求</h3>
          <el-table :data="detail.material_requirements"
            ><el-table-column prop="item_no" label="物料编号" /><el-table-column
              prop="item_name"
              label="物料名称" /><el-table-column
              prop="required_quantity"
              label="需求" /><el-table-column
              prop="consumed_quantity"
              label="已消耗" /><el-table-column
              prop="unit_name"
              label="单位" /></el-table
        ></template>
        <h3>执行记录</h3>
        <el-table
          v-if="detail.executions.length"
          :data="detail.executions"
          size="small"
          ><el-table-column
            label="生产人员"
            min-width="90"
          ><template #default="{ row }">{{ row.production_person_name || row.worker_name || "—" }}</template></el-table-column>
          <el-table-column prop="worker_name" label="录入账号" min-width="90" />
          <el-table-column label="开始" min-width="160"
            ><template #default="{ row }">{{
              formatMesDate(row.tracked_in_at)
            }}</template></el-table-column
          ><el-table-column label="结束" min-width="160"
            ><template #default="{ row }">{{
              formatMesDate(row.tracked_out_at)
            }}</template></el-table-column
          ><el-table-column
            prop="labor_minutes"
            label="人工/分钟"
            min-width="90" /><el-table-column
            prop="machine_minutes"
            label="机器/分钟"
            min-width="90"
        /></el-table>
        <p v-else class="muted">尚无执行记录</p>
        <p v-if="detail.executions.length" class="muted">
          起止时间来自执行区间；人工、机器分钟数来自报工，未填时留空。
        </p>
        <h3>操作记录</h3>
        <el-timeline
          ><el-timeline-item
            v-for="event in detail.events"
            :key="event.id"
            :timestamp="formatMesDate(event.created_at)"
            >{{ event.event_label }} · {{ event.actor_name_snapshot || "系统" }}
            <p class="instructions muted">{{ event.note }}</p></el-timeline-item
          ></el-timeline
        >
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.detail-body {
  min-height: 240px;
}

.task-heading {
  display: flex;
  gap: 20px;
  justify-content: space-between;
  margin-bottom: 24px;
}

h2 {
  margin: 0 0 8px;
  font-size: 21px;
}

h3 {
  margin: 26px 0 14px;
  font-size: 15px;
}

p {
  margin: 4px 0 12px;
}

.muted,
small {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.instructions {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.quantity-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.quantity-grid div {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.quantity-grid strong {
  font-size: 18px;
}
</style>
