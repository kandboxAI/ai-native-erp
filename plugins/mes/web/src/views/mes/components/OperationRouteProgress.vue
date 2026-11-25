<script setup lang="ts">
import { computed } from "vue";
import type {
  MesWorkOrder,
  MesOperationProgress,
} from "@plugins/mes/web/src/api/mes";
import OperationTimeSummary from "./OperationTimeSummary.vue";
import {
  operationProgressSteps,
  progressQuantity,
} from "../work-orders/operationProgress";

defineOptions({ name: "MesOperationRouteProgress" });
const props = defineProps<{
  order: Pick<
    MesWorkOrder,
    | "operation_progress"
    | "operation_count"
    | "completed_operation_count"
    | "unit_name"
  >;
  canViewReports?: boolean;
}>();
const emit = defineEmits<{ viewReports: [operation: MesOperationProgress] }>();
const steps = computed(() =>
  operationProgressSteps(props.order.operation_progress),
);
</script>

<template>
  <div class="operation-route">
    <div
      class="route-summary"
      :title="`已完成 ${order.completed_operation_count} / ${order.operation_count} 道工序；完成以工序状态为准`"
    >
      <span class="summary-label">工序完成</span>
      <span class="summary-count"
        ><strong>{{ order.completed_operation_count }}</strong
        ><span>/ {{ order.operation_count }}</span></span
      >
    </div>
    <div
      v-if="steps.length"
      class="route-scroll"
      tabindex="0"
      role="group"
      aria-label="工艺路线，可左右滚动查看全部工序"
    >
      <ol class="route-steps">
        <li
          v-for="(step, index) in steps"
          :key="step.id"
          class="route-step"
          :class="`tone-${step.tone}`"
        >
          <el-popover
            trigger="hover"
            :show-after="180"
            placement="top"
            :width="600"
            popper-class="mes-operation-time-popover"
          >
            <template #reference>
              <button
                type="button"
                class="step-trigger"
                :class="{ 'is-clickable': canViewReports }"
                :aria-disabled="!canViewReports"
                :aria-label="`${step.operation_name}，${step.tooltip}${canViewReports ? '，点击查看报工记录' : '，当前无报工查询权限'}`"
                @click="canViewReports && emit('viewReports', step)"
              >
                <div
                  class="step-ring"
                  role="progressbar"
                  :aria-label="`${step.operation_name}已报进度，${step.status_label}`"
                  :aria-valuenow="step.percentage"
                  :aria-valuemin="0"
                  :aria-valuemax="100"
                >
                  <svg viewBox="0 0 44 44" aria-hidden="true">
                    <circle class="ring-track" cx="22" cy="22" r="19" />
                    <circle
                      class="ring-value"
                      cx="22"
                      cy="22"
                      r="19"
                      pathLength="100"
                      stroke-dasharray="100"
                      :stroke-dashoffset="100 - step.percentage"
                    />
                  </svg>
                  <span class="ring-label"
                    >{{
                      step.isQuantityUnknown && step.status_code !== "completed"
                        ? "—"
                        : step.percentage
                    }}<small
                      v-if="
                        !step.isQuantityUnknown ||
                        step.status_code === 'completed'
                      "
                      >%</small
                    ></span
                  >
                </div>
                <div class="step-content">
                  <div class="step-heading">
                    <span class="step-number">{{ index + 1 }}</span
                    ><span class="step-name">{{ step.operation_name }}</span>
                  </div>
                  <div class="step-status">
                    <span class="status-dot" />{{ step.status_label }}
                  </div>
                  <span v-if="step.isQuantityUnknown" class="step-quantity"
                    >原状态 · 报工数量未导入</span
                  >
                  <span v-else class="step-quantity"
                    >已报 {{ progressQuantity(step.reported) }} /
                    {{ progressQuantity(step.planned_quantity) }}
                    {{ order.unit_name }}</span
                  >
                </div>
              </button>
            </template>
            <OperationTimeSummary :operation="step" />
          </el-popover>
          <svg
            v-if="index < steps.length - 1"
            class="step-arrow"
            viewBox="0 0 16 16"
            aria-hidden="true"
          >
            <path d="M2 8h11M9 4l4 4-4 4" />
          </svg>
        </li>
      </ol>
    </div>
    <span v-else class="route-empty">{{
      order.operation_count ? "工序进度未返回，请刷新后重试" : "尚未配置工序"
    }}</span>
  </div>
</template>

<style scoped>
.operation-route {
  display: flex;
  gap: 14px;
  align-items: center;
  min-width: 0;
  padding: 6px 0;
}

.route-summary {
  display: flex;
  flex: 0 0 65px;
  flex-direction: column;
  gap: 4px;
  padding-right: 12px;
  border-right: 1px solid var(--el-border-color-lighter);
}

.summary-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.summary-count {
  display: flex;
  gap: 5px;
  align-items: baseline;
  color: var(--el-text-color-secondary);
}

.summary-count strong {
  font-size: 19px;
  font-weight: 650;
  color: var(--el-text-color-primary);
}

.summary-count > span {
  font-size: 12px;
}

.route-scroll {
  min-width: 0;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-color: var(--el-border-color) transparent;
  scrollbar-width: thin;
}

.route-scroll:focus-visible {
  outline: 2px solid var(--el-color-primary-light-5);
  outline-offset: 3px;
  border-radius: 4px;
}

.route-steps {
  display: flex;
  width: max-content;
  padding: 3px 0 6px;
  margin: 0;
  list-style: none;
}

.route-step {
  --step-color: var(--el-text-color-secondary);

  display: flex;
  flex: 0 0 auto;
  gap: 9px;
  align-items: center;
}

.step-trigger {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 0;
  font: inherit;
  text-align: left;
  cursor: default;
  background: transparent;
  border: 0;
}

.step-trigger.is-clickable {
  cursor: pointer;
}

.step-trigger.is-clickable:hover .step-name {
  color: var(--el-color-primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.step-trigger:focus-visible {
  outline: 2px solid var(--el-color-primary-light-5);
  outline-offset: 3px;
  border-radius: 4px;
}

:global(.mes-operation-time-popover) {
  max-width: calc(100vw - 24px);
}

.tone-primary {
  --step-color: var(--el-color-primary);
}

.tone-success {
  --step-color: var(--el-color-success);
}

.tone-warning {
  --step-color: var(--el-color-warning);
}

.step-ring {
  position: relative;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  color: var(--step-color);
}

.step-ring svg {
  display: block;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.step-ring circle {
  fill: none;
  stroke-width: 3;
}

.ring-track {
  stroke: var(--el-fill-color-darker);
}

.ring-value {
  stroke: var(--step-color);
  stroke-linecap: round;
}

.ring-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.ring-label small {
  margin-top: 2px;
  font-size: 9px;
  font-weight: 500;
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 105px;
  max-width: 160px;
}

.step-heading {
  display: flex;
  gap: 5px;
  align-items: center;
  min-width: 0;
  line-height: 18px;
}

.step-number {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
}

.step-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 550;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.step-status {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 11px;
  line-height: 15px;
  color: var(--step-color);
}

.status-dot {
  width: 5px;
  height: 5px;
  background: currentcolor;
  border-radius: 50%;
}

.step-quantity {
  font-size: 11px;
  line-height: 15px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.step-arrow {
  flex: 0 0 18px;
  width: 18px;
  height: 18px;
  margin: 0 12px 0 3px;
  fill: none;
  stroke: var(--el-border-color-darker);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.route-empty {
  padding: 12px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
