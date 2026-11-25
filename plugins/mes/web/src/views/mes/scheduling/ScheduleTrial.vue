<script setup lang="ts">
import { computed, h, onBeforeUnmount, reactive, ref, watch } from "vue";
import ListPagination from "@/components/ListPagination/index.vue";
import { getHttpErrorMessage } from "@/utils/http";
import { actionMessage } from "@/utils/message";
import {
  prepareScheduleTrial,
  solveScheduleTrial,
  type TrialPrepared,
  type TrialScope,
  type TrialSolve,
  type TrialOperationRule,
  type TrialResult
} from "@plugins/mes/web/src/api/mesScheduleTrial";

const props = defineProps<{
  orgId: string;
  workOrderIds: string[];
  formal?: boolean;
  compute?: (body: TrialSolve) => Promise<TrialResult>;
}>();
const emit = defineEmits<{
  close: [];
  prepared: [data: TrialPrepared, scope: TrialScope];
  saved: [planId: string];
}>();
function nextWorkday() {
  const value = new Date();
  value.setDate(value.getDate() + 1);
  value.setHours(8, 0, 0, 0);
  while ([0, 6].includes(value.getDay())) value.setDate(value.getDate() + 1);
  return value;
}
const startAt = ref(nextWorkday());
const endAt = ref(new Date(startAt.value.getTime() + 7 * 86400000));
const loading = ref(false);
let notice: ReturnType<typeof actionMessage> | undefined;
let disposed = false;
const issueItems = ref<string[]>([]);
const issuesTitle = ref("排程问题");
const issuesVisible = ref(false);
function clearNotice() {
  notice?.close();
  notice = undefined;
}
function reportError(detail: string) {
  if (disposed) return;
  clearNotice();
  notice = actionMessage(detail);
}
function viewIssues(items: string[], title: string) {
  issueItems.value = [...items];
  issuesTitle.value = title;
  issuesVisible.value = true;
  clearNotice();
}
function reportIssues(items: string[], title: string) {
  if (disposed) return;
  clearNotice();
  notice = actionMessage(
    h("div", { class: "schedule-notice-content" }, [
      h("span", `${title}（${items.length}项）`),
      h(
        "button",
        { class: "schedule-notice-link", type: "button", onClick: () => viewIssues(items, title) },
        "查看详情"
      )
    ]),
    "warning"
  );
}
onBeforeUnmount(() => {
  disposed = true;
  clearNotice();
});
const prepared = ref<TrialPrepared>();
const scope = ref<TrialScope>();
const result = ref<TrialResult>();
const orders = ref<Array<{ id: string; ready_at: Date; confirmed: boolean }>>(
  []
);
const confirmedOrderCount = computed(
  () => orders.value.filter(row => row.confirmed).length
);
function confirmOrders(value: boolean) {
  for (const row of orders.value) row.confirmed = value;
}
type ShippingDraft = {
  delivery_mode_key: "whole_project" | "individual";
  shipping_preparation_minutes: number | undefined;
  shipping_windows: Array<{ start_at: string; end_at: string }>;
};
const shipping = ref<Record<string, ShippingDraft>>({});
const shippingOrder = ref("");
const shippingHours = ref<[string, string]>(["08:00", "17:00"]);
function generateShippingWindows() {
  if (!scope.value || !shippingOrder.value) return;
  const windows: ShippingDraft["shipping_windows"] = [];
  const day = new Date(scope.value.start_at);
  day.setHours(0, 0, 0, 0);
  const limit = new Date(scope.value.end_at).getTime();
  while (day.getTime() < limit) {
    if (![0, 6].includes(day.getDay())) {
      const values = shippingHours.value.map(time => {
        const value = new Date(day);
        const [h, m] = time.split(":").map(Number);
        value.setHours(h, m, 0, 0);
        return value.getTime();
      });
      const a = Math.max(values[0], new Date(scope.value.start_at).getTime()),
        b = Math.min(values[1], limit);
      if (a < b)
        windows.push({
          start_at: new Date(a).toISOString(),
          end_at: new Date(b).toISOString()
        });
    }
    day.setDate(day.getDate() + 1);
  }
  shipping.value[shippingOrder.value].shipping_windows = windows;
}
function copyShippingToProject() {
  const order = prepared.value?.orders.find(o => o.id === shippingOrder.value);
  if (!order?.production_order_id) return;
  const selected = shipping.value[shippingOrder.value];
  for (const peer of prepared.value!.orders.filter(
    o => o.production_order_id === order.production_order_id
  ))
    shipping.value[peer.id] = {
      ...selected,
      shipping_windows: selected.shipping_windows.map(w => ({ ...w }))
    };
}
type RuleDraft = Omit<
  TrialOperationRule,
  | "kind_key"
  | "setup_minutes"
  | "load_minutes"
  | "unload_minutes"
  | "inspection"
> & {
  work_order_no: string;
  operation_name: string;
  standard_minutes_per_unit: number | null;
  kind_key: TrialOperationRule["kind_key"] | "";
  setup_minutes: number | undefined;
  load_minutes: number | undefined;
  unload_minutes: number | undefined;
  inspection?: {
    process_id: string;
    is_equipment_required: boolean;
    minutes_per_piece: number | undefined;
  } | null;
};
const rules = ref<RuleDraft[]>([]);
const editingRule = ref<RuleDraft>();
const qaProcesses = computed(() =>
  (prepared.value?.processes || []).filter(p =>
    ["inspection", "machine_inspection"].includes(p.execution_kind_code || "")
  )
);
function editConditions(row: RuleDraft) {
  editingRule.value = row;
}
function enableQa(enabled: boolean) {
  if (editingRule.value)
    editingRule.value.inspection = enabled
      ? {
          process_id: "",
          is_equipment_required: false,
          minutes_per_piece: undefined
        }
      : null;
}
function qaProcessChanged(id: string) {
  if (editingRule.value?.inspection)
    editingRule.value.inspection.is_equipment_required =
      !!qaProcesses.value.find(p => p.id === id)?.is_equipment_required;
}
const timingConfirmed = ref(false);
const calendarConfirmed = ref(false);
const inspection = reactive({
  mode_key: "" as "" | "separate" | "last_operation",
  process_id: "",
  equipment: "",
  minutes: undefined as number | undefined
});
const operationPage = ref(1);
const resultPage = ref(1);
const resultSize = ref(20);
const resultKeyword = ref("");
const operationRows = computed(() =>
  rules.value.slice((operationPage.value - 1) * 20, operationPage.value * 20)
);
const resultRows = computed(() =>
  (result.value?.segments || []).filter(row =>
    `${row.work_order_no} ${row.operation_name}`
      .toLowerCase()
      .includes(resultKeyword.value.trim().toLowerCase())
  )
);
const pageRows = computed(() =>
  resultRows.value.slice(
    (resultPage.value - 1) * resultSize.value,
    resultPage.value * resultSize.value
  )
);
const labels: Record<string, string> = {
  preparation: "一次性准备",
  load: "装料",
  run: "加工 / 测量",
  unload: "卸料",
  waiting_unload: "占机等待卸料",
  manual: "人工操作",
  inspection: "检验",
  external_wait: "委外加工 / 等待回厂"
};
const statuses: Record<string, string> = {
  PRECHECK_FAILED: "资料预检未通过",
  OPTIMAL: "已找到本窗口内检验目标最优方案",
  FEASIBLE: "已找到可行方案，尚未证明最优",
  INFEASIBLE: "当前窗口及约束下无可行方案",
  UNKNOWN: "计算时间内尚未找到方案",
  MODEL_INVALID: "排程模型校验失败"
};
const displayTime = (value?: string | Date | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "未填写";
function invalidate() {
  result.value = undefined;
}
defineExpose({ invalidate });
watch(
  [rules, orders, timingConfirmed, calendarConfirmed, inspection, shipping],
  invalidate,
  { deep: true }
);
watch([startAt, endAt], () => {
  clearNotice();
  issuesVisible.value = false;
  prepared.value = undefined;
  scope.value = undefined;
  invalidate();
});
watch(resultKeyword, () => {
  resultPage.value = 1;
});
async function load() {
  clearNotice();
  issuesVisible.value = false;
  if (!startAt.value || !endAt.value) {
    reportError("请选择完整试排窗口");
    return;
  }
  loading.value = true;
  prepared.value = undefined;
  invalidate();
  try {
    scope.value = {
      org_id: props.orgId,
      work_order_ids: props.workOrderIds,
      start_at: startAt.value.toISOString(),
      end_at: endAt.value.toISOString()
    };
    prepared.value = await prepareScheduleTrial(scope.value);
    if (prepared.value.issues.length)
      reportIssues(prepared.value.issues, "请先处理工单资料");
    rules.value = prepared.value.orders.flatMap(order =>
      order.operations.map((op): RuleDraft => {
        const saved = prepared.value?.settings?.find(
          row => row.operation_id === op.id
        );
        const kind = op.execution_kind_code || saved?.execution_kind_code || "";
        return {
          operation_id: op.id,
          version_no: op.version_no,
          operation_name: op.operation_name,
          work_order_no: order.work_order_no,
          standard_minutes_per_unit: op.standard_minutes_per_unit,
          kind_key: kind,
          setup_minutes:
            saved?.setup_minutes ?? (kind === "external" ? 0 : undefined),
          load_minutes:
            saved?.load_minutes ?? (kind && kind !== "machine" ? 0 : undefined),
          unload_minutes:
            saved?.unload_minutes ??
            (kind && kind !== "machine" ? 0 : undefined),
          supervision_key: saved?.can_supervise_two_machines
            ? "two_machines"
            : "exclusive",
          is_lunch_auto_allowed: saved?.can_run_during_lunch || false,
          is_timing_confirmed:
            !!saved?.is_timing_confirmed &&
            saved.source_version_no_snapshot === op.version_no,
          inspection: saved?.inspection_process_id
            ? {
                process_id: saved.inspection_process_id,
                is_equipment_required: !!saved.is_inspection_equipment_required,
                minutes_per_piece: Number(saved.inspection_minutes_per_piece)
              }
            : null,
          external_first_return_at: saved?.external_first_return_at || null,
          external_remaining_return_at:
            saved?.external_remaining_return_at || null
        };
      })
    );
    orders.value = prepared.value.orders.map(order => ({
      id: order.id,
      ready_at: new Date(startAt.value),
      confirmed: false
    }));
    shipping.value = Object.fromEntries(
      prepared.value.orders.map(order => [
        order.id,
        {
          delivery_mode_key: "whole_project",
          shipping_preparation_minutes: undefined,
          shipping_windows: []
        }
      ])
    );
    timingConfirmed.value =
      !!rules.value.length && rules.value.every(row => row.is_timing_confirmed);
    calendarConfirmed.value = false;
    const inspections = prepared.value.inspection_settings || [];
    const first = inspections[0];
    if (
      first &&
      inspections.length === prepared.value.orders.length &&
      inspections.every(
        row =>
          row.inspection_mode_code === first.inspection_mode_code &&
          row.process_id === first.process_id &&
          row.minutes_per_piece === first.minutes_per_piece &&
          row.is_equipment_required === first.is_equipment_required
      )
    ) {
      Object.assign(inspection, {
        mode_key: first.inspection_mode_code,
        process_id: first.process_id || "",
        equipment: first.is_equipment_required ? "required" : "none",
        minutes:
          first.minutes_per_piece == null
            ? undefined
            : Number(first.minutes_per_piece)
      });
    }
    emit("prepared", prepared.value, scope.value);
    operationPage.value = 1;
  } catch (e) {
    reportError(getHttpErrorMessage(e, "读取试排资料失败"));
  } finally {
    loading.value = false;
  }
}
function kindChanged(operationId: string) {
  const rule = rules.value.find(row => row.operation_id === operationId);
  if (!rule) return;
  if (rule.kind_key !== "machine") {
    rule.load_minutes = rule.unload_minutes = 0;
    rule.supervision_key = "exclusive";
    rule.is_lunch_auto_allowed = false;
  } else {
    rule.load_minutes = rule.unload_minutes = undefined;
  }
  timingConfirmed.value = false;
}
async function solve() {
  clearNotice();
  if (!prepared.value || !scope.value) return;
  if (prepared.value.issues.length) {
    reportIssues(prepared.value.issues, "请先处理工单资料");
    return;
  }
  if (
    !timingConfirmed.value ||
    !calendarConfirmed.value ||
    orders.value.some(row => !row.confirmed || !row.ready_at)
  ) {
    reportError("请确认就绪时间、工时口径和常规日历");
    return;
  }
  if (
    rules.value.some(
      row =>
        !row.kind_key ||
        [row.setup_minutes, row.load_minutes, row.unload_minutes].some(
          v => v == null
        )
    )
  ) {
    reportError(
      "请补齐每道工序的执行方式、准备及装卸时间；确实没有的动作填写0"
    );
    return;
  }
  if (
    !inspection.mode_key ||
    (inspection.mode_key === "separate" &&
      (!inspection.process_id ||
        inspection.minutes == null ||
        inspection.minutes <= 0 ||
        !inspection.equipment))
  ) {
    reportError("请选择首件/最终检验工艺、设备要求和单件检验耗时");
    return;
  }
  if (
    rules.value.some(
      row =>
        row.inspection &&
        (!row.inspection.process_id ||
          row.inspection.minutes_per_piece == null ||
          row.inspection.minutes_per_piece <= 0)
    )
  ) {
    reportError("请补齐独立工序检验的工艺和实际单件耗时");
    return;
  }
  const body: TrialSolve = {
    ...scope.value,
    snapshot_key: prepared.value.snapshot_key,
    operation_rules: rules.value.map(row => ({
      operation_id: row.operation_id,
      version_no: row.version_no,
      kind_key: row.kind_key as TrialOperationRule["kind_key"],
      setup_minutes: row.setup_minutes!,
      load_minutes: row.load_minutes!,
      unload_minutes: row.unload_minutes!,
      supervision_key: row.supervision_key,
      is_lunch_auto_allowed: row.is_lunch_auto_allowed,
      is_timing_confirmed: timingConfirmed.value,
      inspection: row.inspection
        ? {
            ...row.inspection,
            minutes_per_piece: row.inspection.minutes_per_piece!
          }
        : null,
      external_first_return_at: row.external_first_return_at,
      external_remaining_return_at: row.external_remaining_return_at
    })),
    order_rules: orders.value.map(row => ({
      work_order_id: row.id,
      version_no: prepared.value!.orders.find(order => order.id === row.id)!
        .version_no,
      ready_at: row.ready_at.toISOString(),
      is_readiness_confirmed: row.confirmed,
      delivery_mode_key: shipping.value[row.id].delivery_mode_key,
      shipping_preparation_minutes:
        shipping.value[row.id].shipping_preparation_minutes ?? null,
      shipping_windows: shipping.value[row.id].shipping_windows
    })),
    inspection: {
      mode_key: inspection.mode_key,
      process_id:
        inspection.mode_key === "separate" ? inspection.process_id : null,
      minutes_per_piece:
        inspection.mode_key === "separate" ? inspection.minutes! : null,
      is_equipment_required:
        inspection.mode_key === "separate" &&
        inspection.equipment === "required"
    },
    is_regular_calendar_confirmed: calendarConfirmed.value,
    time_limit_seconds: 60
  };
  loading.value = true;
  invalidate();
  try {
    result.value = await (props.compute
      ? props.compute(body)
      : solveScheduleTrial(body));
    resultPage.value = 1;
    if (result.value.plan_id) {
      const title = `方案 ${result.value.plan_no} 已保存`;
      if (result.value.issues.length)
        reportIssues(result.value.issues, `${title}，请核对排程结果`);
      else if (!disposed)
        notice = actionMessage(title, "success");
      if (props.formal && !disposed && ["OPTIMAL", "FEASIBLE"].includes(result.value.status_code))
        emit("saved", result.value.plan_id);
    } else if (result.value.issues.length) {
      reportIssues(result.value.issues, "请核对排程结果");
    }
  } catch (e) {
    reportError(getHttpErrorMessage(e, "自动试排失败"));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div v-loading="loading" class="mes-page schedule-trial">
    <div class="page-heading">
      <div>
        <h2>{{ formal ? "自动生产排程" : "自动生产试排" }}</h2>
        <p class="muted">
          {{
            formal
              ? "读取完整工单与资源，计算并保存方案；核对后再确认应用。首件实际检验通过后才准入剩余批量。"
              : "按完整工单试排：首件走完路线并检验，再安排剩余批量。结果供核对，不写入生产计划。"
          }}
        </p>
      </div>
      <el-button :disabled="loading" @click="emit('close')"
        >返回生产排程</el-button
      >
    </div>
    <el-card shadow="never">
      <slot name="plan-name" />
      <el-form
        inline
        class="erp-query-form"
        :disabled="loading"
        @submit.prevent="load"
      >
        <el-form-item :label="formal ? '排程窗口' : '试排窗口'"
          ><el-date-picker
            v-model="startAt"
            type="datetime"
            placeholder="开始时间"
        /></el-form-item>
        <el-form-item label="至"
          ><el-date-picker
            v-model="endAt"
            type="datetime"
            placeholder="结束时间"
        /></el-form-item>
        <el-form-item
          ><el-button type="primary" native-type="submit"
            >读取完整工单</el-button
          ></el-form-item
        >
      </el-form>
      <p class="muted">
        已选择
        {{ workOrderIds.length }}
        张货品工单；最多10张、31天。将读取所选工单的全部工序。
      </p>
      <p class="muted">
        窗口开始时间是允许排程的起点。实际安排还取决于开工条件和工作日历；已派工的工序只检查指定人员。
      </p>
    </el-card>
    <template v-if="prepared">
      <el-form :disabled="loading" @submit.prevent="solve">
        <el-card shadow="never">
          <h3>1. 工单与开工条件</h3>
          <el-table :data="prepared.orders" border>
            <el-table-column
              prop="work_order_no"
              label="货品工单"
              min-width="180"
            />
            <el-table-column label="交付数量" width="140"
              ><template #default="{ row }"
                >{{ row.quantity }} {{ row.unit_code }}</template
              ></el-table-column
            >
            <el-table-column label="承诺交期" min-width="180"
              ><template #default="{ row }">{{
                displayTime(row.due_at)
              }}</template></el-table-column
            >
            <el-table-column v-if="!formal" label="最早就绪时间" min-width="230"
              ><template #default="{ $index }"
                ><el-date-picker
                  v-model="orders[$index].ready_at"
                  type="datetime" /></template
            ></el-table-column>
            <el-table-column label="就绪条件确认" min-width="230"
              ><template #header>
                <el-checkbox
                  :model-value="
                    !!orders.length && confirmedOrderCount === orders.length
                  "
                  :indeterminate="
                    confirmedOrderCount > 0 &&
                    confirmedOrderCount < orders.length
                  "
                  @change="value => confirmOrders(!!value)"
                  >全部核对（{{ confirmedOrderCount }}/{{
                    orders.length
                  }}）</el-checkbox
                > </template
              ><template #default="{ $index }"
                ><el-checkbox v-model="orders[$index].confirmed">{{
                  prepared.orders[$index].schedule_mode_code === "remaining"
                    ? "保留已放行首件，仅重排未开工剩余批量"
                    : "首件未生产；开工资料已核对"
                }}</el-checkbox></template
              ></el-table-column
            >
            <el-table-column label="出货条件" min-width="190"
              ><template #default="{ row }"
                ><el-button
                  link
                  type="primary"
                  @click="shippingOrder = row.id"
                  >{{
                    shipping[row.id]?.shipping_windows.length
                      ? "已填写，查看/修改"
                      : "填写准备时间与窗口"
                  }}</el-button
                ></template
              ></el-table-column
            >
          </el-table>
          <slot name="readiness" />
        </el-card>
        <el-card shadow="never">
          <h3>2. 工序阶段参数</h3>
          <p class="muted">
            耗时均为分钟。标准工时按单件读取；装卸逐件计算，准备只算一次。不确定的参数请先核对，不要填写0。
          </p>
          <el-table :data="operationRows" border>
            <el-table-column label="工单 / 工序" min-width="220"
              ><template #default="{ row }"
                ><div>{{ row.work_order_no }}</div>
                <strong>{{ row.operation_name }}</strong></template
              ></el-table-column
            >
            <el-table-column
              prop="standard_minutes_per_unit"
              label="单件标准工时"
              width="130"
            />
            <el-table-column label="执行方式" width="155"
              ><template #default="{ row }"
                ><el-select
                  v-model="row.kind_key"
                  placeholder="明确选择"
                  disabled
                  @change="kindChanged(row.operation_id)"
                  ><el-option label="机器加工" value="machine" /><el-option
                    label="纯人工"
                    value="manual" /><el-option
                    label="检验"
                    value="inspection" /><el-option
                    label="设备检验"
                    value="machine_inspection" /><el-option
                    label="委外"
                    value="external" /></el-select></template
            ></el-table-column>
            <el-table-column label="一次性准备" width="145"
              ><template #default="{ row }"
                ><el-input-number
                  v-model="row.setup_minutes"
                  :min="0"
                  :max="1440"
                  :precision="0"
                  controls-position="right" /></template
            ></el-table-column>
            <el-table-column label="逐件装料" width="140"
              ><template #default="{ row }"
                ><el-input-number
                  v-model="row.load_minutes"
                  :disabled="row.kind_key !== 'machine'"
                  :min="0"
                  :max="240"
                  :precision="0"
                  controls-position="right" /></template
            ></el-table-column>
            <el-table-column label="逐件卸料" width="140"
              ><template #default="{ row }"
                ><el-input-number
                  v-model="row.unload_minutes"
                  :disabled="row.kind_key !== 'machine'"
                  :min="0"
                  :max="240"
                  :precision="0"
                  controls-position="right" /></template
            ></el-table-column>
            <el-table-column label="自动加工照看" width="160"
              ><template #default="{ row }"
                ><el-select
                  v-model="row.supervision_key"
                  :disabled="row.kind_key !== 'machine'"
                  ><el-option label="人员独占" value="exclusive" /><el-option
                    label="允许一人两机"
                    value="two_machines" /></el-select></template
            ></el-table-column>
            <el-table-column label="午休无人运行" width="135"
              ><template #default="{ row }"
                ><el-checkbox
                  v-model="row.is_lunch_auto_allowed"
                  :disabled="row.kind_key !== 'machine'"
                  >允许</el-checkbox
                ></template
              ></el-table-column
            >
            <el-table-column label="独立检验 / 委外" width="170"
              ><template #default="{ row }"
                ><el-button
                  link
                  type="primary"
                  @click="editConditions(row as RuleDraft)"
                  >{{ row.inspection ? "已配置检验" : "配置条件" }}</el-button
                ></template
              ></el-table-column
            >
          </el-table>
          <ListPagination
            v-model:current-page="operationPage"
            :page-size="20"
            :total="rules.length"
            layout="total, prev, pager, next"
          />
          <el-checkbox v-model="timingConfirmed" class="trial-confirm"
            >已核对全部工序：标准工时为净加工/人工耗时；准备、装卸另计且未重复，准备不因中途换型重新发生。</el-checkbox
          >
        </el-card>
        <el-card shadow="never">
          <h3>3. 首件与最终检验</h3>
          <p class="muted">
            路线末道已包含全路线检验时可复用；否则增加独立检验。两者不会重复计算。
          </p>
          <div class="inspection-fields">
            <el-form-item label="检验安排"
              ><el-select
                v-model="inspection.mode_key"
                placeholder="明确检验安排"
                ><el-option
                  label="复用路线末道检验"
                  value="last_operation" /><el-option
                  label="路线外增加独立检验"
                  value="separate" /></el-select
            ></el-form-item>
            <el-form-item
              v-if="inspection.mode_key === 'separate'"
              label="检验工艺"
              ><el-select
                v-model="inspection.process_id"
                filterable
                placeholder="选择检验工艺"
                ><el-option
                  v-for="p in qaProcesses"
                  :key="p.id"
                  :value="p.id"
                  :label="p.process_name" /></el-select
            ></el-form-item>
            <el-form-item
              v-if="inspection.mode_key === 'separate'"
              label="检验设备"
              ><el-select
                v-model="inspection.equipment"
                placeholder="明确设备要求"
                ><el-option
                  label="需要匹配检验设备"
                  value="required" /><el-option
                  label="仅需检验人员"
                  value="none" /></el-select
            ></el-form-item>
            <el-form-item
              v-if="inspection.mode_key === 'separate'"
              label="单件检验分钟"
              ><el-input-number
                v-model="inspection.minutes"
                :min="0.001"
                :max="1440"
                :precision="3"
                controls-position="right"
            /></el-form-item>
          </div>
          <el-checkbox v-model="calendarConfirmed" class="trial-confirm"
            >已核对本次窗口：现有常规日历适用，暂无未登记的请假、维修或节假日例外。</el-checkbox
          >
          <div class="erp-form-actions">
            <el-button
              v-if="prepared.issues.length"
              type="warning"
              link
              @click="viewIssues(prepared.issues, '请先处理工单资料')"
              >查看资料问题（{{ prepared.issues.length }}）</el-button
            >
            <el-button :disabled="loading" @click="emit('close')"
              >取消</el-button
            ><el-button
              type="primary"
              native-type="submit"
              :loading="loading"
              :disabled="!!prepared.issues.length"
              >{{ formal ? "计算并保存方案" : "开始试排" }}</el-button
            >
          </div>
        </el-card>
      </el-form>
    </template>
    <el-card v-if="result" shadow="never">
      <slot name="saved-result" :result="result" />
      <h3>{{ statuses[result.status_code] || result.status_code }}</h3>
      <el-button
        v-if="result.issues.length"
        type="warning"
        link
        @click="viewIssues(result.issues, '请核对排程结果')"
        >查看结果问题（{{ result.issues.length }}）</el-button
      >
      <el-alert
        v-if="
          result.status_code === 'INFEASIBLE' ||
          result.status_code === 'UNKNOWN'
        "
        type="warning"
        title="请核对窗口、逐件连续加工时长和资源能力；系统没有放松约束或截断数量。"
        :closable="false"
      />
      <template v-if="result.completions.length">
        <p v-for="warning in result.warnings" :key="warning" class="muted">
          {{ warning }}
        </p>
        <el-table :data="result.completions" border>
          <el-table-column
            prop="work_order_no"
            label="货品工单"
            min-width="180"
          />
          <el-table-column label="首件预计检验放行" min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.first_article_release_at)
            }}</template></el-table-column
          >
          <el-table-column label="整批预计检验放行" min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.inspection_release_at)
            }}</template></el-table-column
          >
          <el-table-column label="承诺出货交期" min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.due_at)
            }}</template></el-table-column
          >
          <el-table-column label="出货评估" min-width="150"
            ><template #default="{ row }"
              ><span v-if="row.shipping_complete">{{
                displayTime(row.shipping_release_at)
              }}</span
              ><el-tag v-else type="warning">出货条件不完整</el-tag></template
            ></el-table-column
          >
        </el-table>
        <h3 class="stage-heading">分阶段资源安排</h3>
        <el-form inline class="erp-query-form" @submit.prevent
          ><el-form-item label="工单 / 工序"
            ><el-input
              v-model="resultKeyword"
              clearable
              placeholder="搜索工单或工序" /></el-form-item
        ></el-form>
        <el-table :data="pageRows" border>
          <el-table-column prop="work_order_no" label="工单" min-width="180" />
          <el-table-column prop="operation_name" label="工序" min-width="140" />
          <el-table-column label="批次 / 件次" width="145"
            ><template #default="{ row }"
              >{{ row.batch_key === "first" ? "首件" : "剩余批量"
              }}<span v-if="row.piece_no"> · {{ row.piece_no }}</span></template
            ></el-table-column
          >
          <el-table-column label="阶段" min-width="140"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.kind_key === 'waiting_unload'
                    ? 'warning'
                    : row.kind_key === 'inspection'
                      ? 'success'
                      : 'primary'
                "
                >{{ labels[row.kind_key] }}</el-tag
              ></template
            ></el-table-column
          >
          <el-table-column label="开始时间" min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.start_at)
            }}</template></el-table-column
          >
          <el-table-column label="结束时间" min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.end_at)
            }}</template></el-table-column
          >
          <el-table-column prop="person_no" label="人员编号" min-width="150" />
          <el-table-column prop="equipment_name" label="设备" min-width="180" />
        </el-table>
        <ListPagination
          v-model:current-page="resultPage"
          v-model:page-size="resultSize"
          :total="resultRows.length"
          @size-change="resultPage = 1"
        />
        <p class="muted">
          资料快照：{{
            displayTime(result.captured_at)
          }}。修改输入后需重新试排。
        </p>
      </template>
    </el-card>
    <el-drawer
      v-model="issuesVisible"
      :title="issuesTitle"
      size="min(640px, 95vw)"
    >
      <ol class="schedule-issues">
        <li v-for="(issue, index) in issueItems" :key="index">{{ issue }}</li>
      </ol>
      <template #footer
        ><el-button @click="issuesVisible = false">关闭</el-button></template
      >
    </el-drawer>
    <el-dialog
      :model-value="!!editingRule"
      title="工序检验与委外条件"
      width="640px"
      :close-on-click-modal="false"
      @close="editingRule = undefined"
    >
      <el-form v-if="editingRule" label-position="top">
        <p>{{ editingRule.operation_name }}</p>
        <template v-if="editingRule.kind_key === 'external'">
          <el-form-item label="首件预计回厂"
            ><el-date-picker
              v-model="editingRule.external_first_return_at"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
          /></el-form-item>
          <el-form-item label="剩余批量预计回厂（数量大于1时必填）"
            ><el-date-picker
              v-model="editingRule.external_remaining_return_at"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
          /></el-form-item>
          <p class="muted">
            委外等待不占用本厂人机；首件及剩余批量回厂后分别检验。
          </p>
        </template>
        <el-checkbox
          :model-value="!!editingRule.inspection"
          @change="enableQa(!!$event)"
          >完成后安排独立工序检验</el-checkbox
        >
        <template v-if="editingRule.inspection">
          <el-form-item label="检验工艺"
            ><el-select
              v-model="editingRule.inspection.process_id"
              filterable
              @change="qaProcessChanged"
              ><el-option
                v-for="p in qaProcesses"
                :key="p.id"
                :value="p.id"
                :label="p.process_name" /></el-select
          ></el-form-item>
          <el-form-item label="单件检验分钟"
            ><el-input-number
              v-model="editingRule.inspection.minutes_per_piece"
              :min="0.001"
              :max="1440"
              :precision="3"
          /></el-form-item>
          <p class="muted">
            {{
              editingRule.inspection.is_equipment_required
                ? "需要匹配检验设备及人员资格"
                : "需要检验人员资格及工作日历"
            }}。请填写实际工时。
          </p>
        </template>
        <div class="erp-form-actions">
          <el-button type="primary" @click="editingRule = undefined"
            >确定</el-button
          >
        </div>
      </el-form>
    </el-dialog>
    <el-dialog
      :model-value="!!shippingOrder"
      title="出货准备与发货窗口"
      width="720px"
      :close-on-click-modal="false"
      @close="shippingOrder = ''"
    >
      <el-form
        v-if="shippingOrder && shipping[shippingOrder]"
        label-position="top"
      >
        <el-form-item label="交付安排"
          ><el-radio-group v-model="shipping[shippingOrder].delivery_mode_key"
            ><el-radio-button value="whole_project"
              >项目整单齐套</el-radio-button
            ><el-radio-button value="individual"
              >本货品单独发货</el-radio-button
            ></el-radio-group
          ></el-form-item
        >
        <el-form-item label="齐套后出货准备时间（分钟）"
          ><el-input-number
            v-model="shipping[shippingOrder].shipping_preparation_minutes"
            :min="0"
            :max="10080"
            :precision="0"
        /></el-form-item>
        <p class="muted">
          包含打包、文件等出货缓冲。整单评估须选择全部交付货品并填写相同出货条件；留空只预测检验放行。
        </p>
        <el-form-item label="窗口内的周一至周五发货时段"
          ><el-time-picker
            v-model="shippingHours"
            is-range
            value-format="HH:mm"
            format="HH:mm"
          /><el-button @click="generateShippingWindows"
            >生成时段</el-button
          ></el-form-item
        >
        <el-table
          :data="shipping[shippingOrder].shipping_windows"
          border
          max-height="260"
          ><el-table-column label="开始"
            ><template #default="{ row }"
              ><el-date-picker
                v-model="row.start_at"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ssZ" /></template></el-table-column
          ><el-table-column label="截止"
            ><template #default="{ row }"
              ><el-date-picker
                v-model="row.end_at"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ssZ" /></template></el-table-column
          ><el-table-column label="操作" width="80"
            ><template #default="{ $index }"
              ><el-button
                link
                type="danger"
                @click="
                  shipping[shippingOrder].shipping_windows.splice($index, 1)
                "
                >移除</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <div class="erp-form-actions">
          <el-button @click="copyShippingToProject"
            >应用到本项目所选货品</el-button
          ><el-button type="primary" @click="shippingOrder = ''"
            >确定</el-button
          >
        </div>
      </el-form>
    </el-dialog>
  </div>
</template>

<style scoped>
.schedule-trial > :deep(.el-card),
.schedule-trial :deep(.el-form > .el-card) {
  margin-bottom: 20px;
}

.schedule-trial :deep(.el-input-number) {
  width: 118px;
}

.inspection-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 0 24px;
}

.inspection-fields :deep(.el-select) {
  width: 220px;
}

.trial-confirm {
  height: auto;
  margin-top: 20px;
  white-space: normal;
}

.trial-confirm :deep(.el-checkbox__label) {
  white-space: normal;
}

.stage-heading {
  margin-top: 24px;
}

.schedule-trial h3 {
  margin-bottom: 16px;
}

.schedule-issues {
  padding-left: 24px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.schedule-issues li + li {
  margin-top: 12px;
}

:global(.schedule-notice-content) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

:global(.schedule-notice-link) {
  padding: 0;
  color: inherit;
  text-decoration: underline;
  cursor: pointer;
  background: transparent;
  border: 0;
}
</style>
