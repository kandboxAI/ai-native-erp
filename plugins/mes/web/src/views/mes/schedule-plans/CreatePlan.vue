<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import ScheduleTrial from "../scheduling/ScheduleTrial.vue";
import {
  createSchedulePlan,
  type ReadinessInput
} from "@plugins/mes/web/src/api/mesSchedulePlans";
import type {
  TrialPrepared,
  TrialScope,
  TrialSolve
} from "@plugins/mes/web/src/api/mesScheduleTrial";
const props = defineProps<{ orgId: string; workOrderIds: string[] }>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const trial = ref<InstanceType<typeof ScheduleTrial>>();
const planName = ref(`生产排程 ${new Date().toLocaleDateString("zh-CN")}`);
const conditions = ref<
  Array<{
    work_order_id: string;
    work_order_no: string;
    kinds: Array<{
      key: ReadinessInput["readiness_kind_code"];
      label: string;
      expected_at: Date | undefined;
      is_confirmed: boolean;
    }>;
  }>
>([]);
const labels = {
  material: "材料",
  drawing: "图纸",
  program: "程序",
  tool: "刀具"
} as const;
type ReadinessKind = keyof typeof labels;
type ReadinessOrder = (typeof conditions.value)[number];
const selectedOrderIds = ref<string[]>([]);
const batchScope = ref<"all" | "selected">("all");
const batchKind = ref<ReadinessKind | "all">("all");
const batchExpectedAt = ref<Date>();
const targets = computed(() =>
  conditions.value.filter(
    row =>
      batchScope.value === "all" ||
      selectedOrderIds.value.includes(row.work_order_id)
  )
);
const targetConditions = computed(() =>
  targets.value.flatMap(row =>
    row.kinds.filter(
      kind => batchKind.value === "all" || kind.key === batchKind.value
    )
  )
);
const readinessCount = computed(() =>
  conditions.value.reduce(
    (count, row) => count + row.kinds.filter(kind => kind.is_confirmed).length,
    0
  )
);
const canApplyTime = computed(
  () =>
    targetConditions.value.length > 0 &&
    batchExpectedAt.value instanceof Date &&
    Number.isFinite(batchExpectedAt.value.getTime())
);
function selectOrders(rows: typeof conditions.value) {
  selectedOrderIds.value = rows.map(row => row.work_order_id);
  if (rows.length) batchScope.value = "selected";
}
function applyExpectedTime() {
  if (!canApplyTime.value) return;
  for (const kind of targetConditions.value)
    kind.expected_at = new Date(batchExpectedAt.value!.getTime());
}
function confirmReadiness(value: boolean) {
  for (const kind of targetConditions.value) kind.is_confirmed = value;
}
function condition(row: ReadinessOrder, key: ReadinessKind) {
  return row.kinds.find(kind => kind.key === key)!;
}
watch([conditions, planName], () => trial.value?.invalidate(), { deep: true });
function prepared(data: TrialPrepared, scope: TrialScope) {
  selectedOrderIds.value = [];
  batchScope.value = "all";
  batchKind.value = "all";
  batchExpectedAt.value = new Date(scope.start_at);
  conditions.value = data.orders.map(order => ({
    work_order_id: order.id,
    work_order_no: order.work_order_no,
    kinds: (Object.keys(labels) as Array<keyof typeof labels>).map(key => {
      const record = data.readiness?.find(
        r => r.work_order_id === order.id && r.readiness_kind_code === key
      );
      return {
        key,
        label: labels[key],
        expected_at: record
          ? new Date(record.expected_at)
          : new Date(scope.start_at),
        is_confirmed: !!record?.confirmed_at
      };
    })
  }));
}
async function compute(body: TrialSolve) {
  if (!planName.value.trim()) throw new Error("请填写方案名称");
  if (conditions.value.some(row => row.kinds.some(kind => !kind.expected_at)))
    throw new Error("请逐项填写材料、图纸、程序及刀具的预计就绪时间");
  return createSchedulePlan({
    ...body,
    plan_name: planName.value,
    readiness: conditions.value.flatMap(row =>
      row.kinds.map(kind => ({
        work_order_id: row.work_order_id,
        readiness_kind_code: kind.key,
        expected_at: kind.expected_at!.toISOString(),
        is_confirmed: kind.is_confirmed
      }))
    )
  });
}
async function openPlan(planId: string) {
  const failure = await router.push({
    path: "/mes/schedule-plans",
    query: { plan_id: planId }
  });
  if (!failure) emit("close");
}
</script>
<template>
  <ScheduleTrial
    ref="trial"
    :org-id="props.orgId"
    :work-order-ids="props.workOrderIds"
    formal
    :compute="compute"
    @close="emit('close')"
    @prepared="prepared"
    @saved="openPlan"
  >
    <template #plan-name
      ><el-form label-position="top"
        ><el-form-item label="方案名称" required
          ><el-input
            v-model="planName"
            maxlength="128"
            style="max-width: 600px" /></el-form-item></el-form
    ></template>
    <template #readiness>
      <div class="readiness-panel">
        <h3>就绪条件</h3>
        <p class="muted">
          预计时间用于排程，不会自动确认实际就绪。已确认 {{ readinessCount }}/{{
            conditions.length * 4
          }}
          项。
        </p>
        <div class="erp-query-form readiness-toolbar">
          <div class="readiness-controls">
            <el-radio-group v-model="batchScope" aria-label="批量就绪操作范围">
              <el-radio-button value="all"
                >全部工单（{{ conditions.length }}）</el-radio-button
              >
              <el-radio-button value="selected"
                >已选工单（{{ selectedOrderIds.length }}）</el-radio-button
              >
            </el-radio-group>
            <el-select
              v-model="batchKind"
              style="width: 150px"
              aria-label="批量就绪条件"
            >
              <el-option label="全部条件" value="all" />
              <el-option
                v-for="(label, key) in labels"
                :key="key"
                :value="key"
                :label="label"
              />
            </el-select>
          </div>
          <div class="readiness-controls">
            <el-date-picker
              v-model="batchExpectedAt"
              type="datetime"
              placeholder="统一预计就绪时间"
              aria-label="统一预计就绪时间"
            />
            <el-button :disabled="!canApplyTime" @click="applyExpectedTime"
              >应用预计时间</el-button
            >
            <el-button
              type="primary"
              :disabled="!targetConditions.length"
              @click="confirmReadiness(true)"
              >批量确认已就绪</el-button
            >
            <el-button
              :disabled="!targetConditions.length"
              @click="confirmReadiness(false)"
              >取消就绪确认</el-button
            >
            <span class="muted"
              >作用于 {{ targets.length }} 张工单、{{
                targetConditions.length
              }}
              项条件</span
            >
          </div>
        </div>
        <el-table
          :data="conditions"
          row-key="work_order_id"
          border
          @selection-change="selectOrders"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column
            prop="work_order_no"
            label="货品工单"
            min-width="210"
          />
          <el-table-column
            v-for="(label, key) in labels"
            :key="key"
            :label="`${label}预计就绪`"
            min-width="235"
          >
            <template #default="{ row }"
              ><div class="readiness-condition">
                <el-date-picker
                  v-model="condition(row as ReadinessOrder, key).expected_at"
                  type="datetime"
                  style="width: 100%"
                  :aria-label="`${row.work_order_no} ${label}预计就绪`"
                />
                <el-checkbox
                  v-model="condition(row as ReadinessOrder, key).is_confirmed"
                  >实际已就绪</el-checkbox
                >
              </div></template
            >
          </el-table-column>
        </el-table>
      </div>
    </template>
    <template #saved-result="{ result }">
      <el-button
        v-if="result.plan_id"
        link
        type="primary"
        @click="openPlan(result.plan_id)"
        >查看方案 {{ result.plan_no }}</el-button
      >
    </template>
  </ScheduleTrial>
</template>
<style scoped>
.readiness-panel {
  margin-top: 24px;
}

.readiness-toolbar,
.readiness-condition {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.readiness-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.readiness-controls :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
