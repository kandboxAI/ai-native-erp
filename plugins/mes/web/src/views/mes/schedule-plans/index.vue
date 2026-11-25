<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import ActionButton from "@/components/ActionButton/index.vue";
import ListPagination from "@/components/ListPagination/index.vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import RemoteSelect from "../components/RemoteSelect.vue";
import ReadinessPanel from "./ReadinessPanel.vue";
import PlanTimeline from "./PlanTimeline.vue";
import { equipmentLabel, personLabel, stageLabels } from "./timeline";
import { getMesScheduleOrgOptions } from "@plugins/mes/web/src/api/mes";
import {
  schedulePlans,
  schedulePlan,
  schedulePlanCommand,
  type SchedulePlan,
  type PlanDetail,
} from "@plugins/mes/web/src/api/mesSchedulePlans";
defineOptions({ name: "MesSchedulePlans" });
const route = useRoute(),
  router = useRouter();
const query = reactive({
  org_id: "",
  keyword: "",
  status_code: "",
  page: 1,
  page_size: 20,
});
const rows = ref<SchedulePlan[]>([]),
  total = ref(0),
  busy = ref(false),
  error = ref("");
const detail = ref<PlanDetail>();
const search = ref(""),
  segmentPage = ref(1),
  segmentSize = ref(20);
const statuses: Record<string, string> = {
  draft: "待计算",
  calculating: "计算中",
  ready: "待确认",
  applied: "已应用",
  superseded: "已被替代",
  invalid: "已失效",
  failed: "计算失败",
  cancelled: "已取消",
};
const color = (status: string) =>
  status === "applied"
    ? "success"
    : ["failed", "invalid"].includes(status)
      ? "danger"
      : status === "ready"
        ? "warning"
        : status === "calculating"
          ? "primary"
          : "info";
const time = (value?: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const segments = computed(() =>
  (detail.value?.segments || []).filter((row) =>
    `${row.work_order_no} ${row.operation_name} ${equipmentLabel(row)} ${personLabel(row)} ${row.equipment_name_snapshot || ""} ${row.person_no_snapshot || ""}`
      .toLowerCase()
      .includes(search.value.trim().toLowerCase()),
  ),
);
const pageSegments = computed(() =>
  segments.value.slice(
    (segmentPage.value - 1) * segmentSize.value,
    segmentPage.value * segmentSize.value,
  ),
);
let timer: ReturnType<typeof setTimeout> | undefined,
  generation = 0;
function stop() {
  if (timer) clearTimeout(timer);
  timer = undefined;
}
function poll() {
  stop();
  if (
    detail.value?.status_code === "calculating" ||
    (!detail.value &&
      rows.value.some((row) => row.status_code === "calculating"))
  )
    timer = setTimeout(
      () => (detail.value ? open(detail.value.id) : load()),
      2000,
    );
}
async function load() {
  stop();
  const current = ++generation;
  busy.value = true;
  error.value = "";
  try {
    const r = await schedulePlans({
      ...query,
      org_id: query.org_id || undefined,
      status_code: query.status_code || undefined,
    });
    if (current !== generation) return;
    rows.value = r.items;
    total.value = r.total;
    poll();
  } catch (e) {
    if (current === generation)
      error.value = getHttpErrorMessage(e, "读取排程方案失败");
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function open(id: string) {
  stop();
  const current = ++generation;
  busy.value = true;
  error.value = "";
  try {
    const r = await schedulePlan(id);
    if (current !== generation) return;
    detail.value = r;
    poll();
  } catch (e) {
    if (current === generation)
      error.value = getHttpErrorMessage(e, "读取方案失败");
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function command(action: "apply" | "cancel") {
  if (!detail.value) return;
  try {
    await ElMessageBox.confirm(
      action === "apply"
        ? "确认应用后将写入正式工序计划和资源占用；系统会再次核对工单、资格、日历及占用。"
        : "确认取消此未应用方案？",
      action === "apply" ? "确认应用排程方案" : "取消方案",
      { type: action === "apply" ? "warning" : "info" },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    await schedulePlanCommand(
      detail.value.id,
      action,
      detail.value.version_no,
      action === "apply" ? "排产员确认应用方案" : "排产员取消方案",
    );
    await open(detail.value.id);
    message(action === "apply" ? "方案已应用" : "方案已取消", {
      type: "success",
    });
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "方案操作失败"));
  } finally {
    busy.value = false;
  }
}
function replan() {
  if (!detail.value) return;
  router.push({
    path: "/mes/scheduling",
    query: {
      org_id: detail.value.org_id,
      work_order_ids: [
        ...new Set(detail.value.operations.map((op) => op.work_order_id)),
      ].join(","),
    },
  });
}
function back() {
  ++generation;
  detail.value = undefined;
  stop();
  router.replace({ path: "/mes/schedule-plans" });
  load();
}
watch(search, () => {
  segmentPage.value = 1;
});
watch(
  () => route.query.plan_id,
  (value) => {
    if (typeof value === "string") open(value);
  },
);
onMounted(() => {
  const id = route.query.plan_id;
  if (typeof id === "string") open(id);
  else load();
});
onBeforeUnmount(() => {
  ++generation;
  stop();
});
</script>
<template>
  <div v-loading="busy" class="mes-page schedule-plans">
    <div class="page-heading">
      <div>
        <h2>
          {{ detail ? `${detail.plan_name} · ${detail.plan_no}` : "排程方案" }}
        </h2>
        <p class="muted">
          保留计算输入与阶段安排；仅确认应用的方案占用正式资源，资料变化后须重新计算。
        </p>
      </div>
      <div v-if="detail" class="plan-heading-actions">
        <el-button :disabled="busy" @click="open(detail.id)">刷新状态</el-button
        ><el-button @click="back">返回列表</el-button>
      </div>
      <ActionButton
        v-else-if="hasPerms('mes:schedule:manage')"
        intent="create"
        @click="router.push('/mes/scheduling')"
        >选择工单生成方案</ActionButton
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <el-card v-if="!detail" shadow="never"
      ><el-form
        inline
        class="erp-query-form"
        @submit.prevent="
          query.page = 1;
          load();
        "
        ><el-form-item label="组织"
          ><RemoteSelect
            v-model="query.org_id"
            :load-options="getMesScheduleOrgOptions"
            placeholder="选择组织" /></el-form-item
        ><el-form-item label="方案"
          ><el-input
            v-model="query.keyword"
            placeholder="方案编号或名称"
            clearable /></el-form-item
        ><el-form-item label="状态"
          ><el-select v-model="query.status_code" clearable style="width: 160px"
            ><el-option
              v-for="(label, key) in statuses"
              :key="key"
              :value="key"
              :label="label" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" native-type="submit">查询</el-button
          ><el-button @click="load">刷新</el-button></el-form-item
        ></el-form
      ><el-table :data="rows" border
        ><el-table-column
          prop="plan_no"
          label="方案编号"
          min-width="230"
        /><el-table-column
          prop="plan_name"
          label="方案名称"
          min-width="200"
        /><el-table-column label="状态" width="130"
          ><template #default="{ row }"
            ><el-tag :type="color(row.status_code)">{{
              statuses[row.status_code] || row.status_code
            }}</el-tag></template
          ></el-table-column
        ><el-table-column
          prop="solver_result_code"
          label="求解结果"
          width="150"
        /><el-table-column label="排程窗口" min-width="280"
          ><template #default="{ row }"
            >{{ time(row.window_start_at) }} —
            {{ time(row.window_end_at) }}</template
          ></el-table-column
        ><el-table-column label="操作" width="110"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="open(row.id)"
              >查看方案</el-button
            ></template
          ></el-table-column
        ></el-table
      ><ListPagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        @current-change="load"
        @size-change="
          query.page = 1;
          load();
        "
    /></el-card>
    <template v-else>
      <el-alert
        v-for="risk in detail.risk_issues || []"
        :key="risk"
        :title="risk"
        type="warning"
        :closable="false"
        show-icon
      />
      <ReadinessPanel
        :plan="detail"
        :editable="
          detail.status_code === 'applied' && hasPerms('mes:schedule:manage')
        "
        @saved="open(detail.id)"
      />
      <el-card shadow="never"
        ><el-descriptions :column="3" border
          ><el-descriptions-item label="状态"
            ><el-tag :type="color(detail.status_code)">{{
              statuses[detail.status_code]
            }}</el-tag></el-descriptions-item
          ><el-descriptions-item label="求解结果">{{
            detail.solver_result_code || "—"
          }}</el-descriptions-item
          ><el-descriptions-item label="工序数">{{
            detail.operations.length
          }}</el-descriptions-item
          ><el-descriptions-item label="开始时间">{{
            time(detail.window_start_at)
          }}</el-descriptions-item
          ><el-descriptions-item label="结束时间">{{
            time(detail.window_end_at)
          }}</el-descriptions-item
          ><el-descriptions-item label="应用时间">{{
            time(detail.confirmed_at)
          }}</el-descriptions-item></el-descriptions
        ><el-alert
          v-for="issue in detail.result.issues"
          :key="issue"
          :title="issue"
          type="error"
          :closable="false"
        />
        <p
          v-for="warning in detail.result.warnings"
          :key="warning"
          class="muted"
        >
          {{ warning }}
        </p></el-card
      >
      <el-card v-if="detail.result.completions?.length" shadow="never"
        ><h3>预计检验放行与交期</h3>
        <el-table :data="detail.result.completions" border
          ><el-table-column
            prop="work_order_no"
            label="货品工单"
            min-width="180"
          /><el-table-column label="首件检验放行" min-width="190"
            ><template #default="{ row }">{{
              time(row.first_article_release_at)
            }}</template></el-table-column
          ><el-table-column label="整批检验放行" min-width="190"
            ><template #default="{ row }">{{
              time(row.inspection_release_at)
            }}</template></el-table-column
          ><el-table-column label="承诺出货交期" min-width="190"
            ><template #default="{ row }">{{
              time(row.due_at)
            }}</template></el-table-column
          ><el-table-column label="预计可出货" min-width="190"
            ><template #default="{ row }"
              ><span v-if="row.shipping_complete">{{
                time(row.shipping_release_at)
              }}</span
              ><el-tag v-else type="warning"
                >齐套 / 出货条件不完整</el-tag
              ></template
            ></el-table-column
          ></el-table
        ></el-card
      >
      <el-card shadow="never"
        ><h3>排程甘特图</h3>
        <el-form inline class="erp-query-form" @submit.prevent
          ><el-form-item label="搜索"
            ><el-input
              v-model="search"
              clearable
              placeholder="工单、工序、人员或设备" /></el-form-item></el-form
        ><PlanTimeline
          :key="detail.id"
          :start-at="detail.window_start_at"
          :end-at="detail.window_end_at"
          :segments="segments"
          :operations="detail.operations"
          :completions="detail.result.completions || []"
          :search="search"
        /><el-table :data="pageSegments" border class="stage-table"
          ><el-table-column
            prop="work_order_no"
            label="货品工单"
            min-width="170"
          /><el-table-column
            prop="operation_name"
            label="工序"
            min-width="140"
          /><el-table-column label="批次" width="110"
            ><template #default="{ row }">{{
              row.production_phase_code === "first" ? "首件" : "剩余批量"
            }}</template></el-table-column
          ><el-table-column label="阶段" min-width="150"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.segment_type_code === 'waiting_unload'
                    ? 'warning'
                    : row.segment_type_code === 'inspection'
                      ? 'success'
                      : 'primary'
                "
                >{{
                  row.is_independent_inspection
                    ? "独立检验"
                    : stageLabels[row.segment_type_code] || row.segment_type_code
                }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column label="开始" min-width="185"
            ><template #default="{ row }">{{
              time(row.planned_start_at)
            }}</template></el-table-column
          ><el-table-column label="结束" min-width="185"
            ><template #default="{ row }">{{
              time(row.planned_end_at)
            }}</template></el-table-column
          ><el-table-column label="人员姓名" min-width="150">
            <template #default="{ row }">{{ personLabel(row) }}</template>
          </el-table-column><el-table-column label="设备名称" min-width="180">
            <template #default="{ row }">{{ equipmentLabel(row) }}</template>
          </el-table-column><el-table-column label="人员占用" width="120"
            ><template #default="{ row }">{{
              row.person_capacity_units_snapshot === 2
                ? "专注操作"
                : row.person_capacity_units_snapshot === 1
                  ? "两机照看"
                  : "无人员占用"
            }}</template></el-table-column
          ></el-table
        ><ListPagination
          v-model:current-page="segmentPage"
          v-model:page-size="segmentSize"
          :total="segments.length"
          @size-change="segmentPage = 1"
        />
        <div class="erp-form-actions">
          <el-button v-if="hasPerms('mes:schedule:manage')" @click="replan"
            >重新排程</el-button
          ><el-button
            v-if="
              hasPerms('mes:schedule:manage') &&
              !['applied', 'superseded', 'cancelled'].includes(
                detail.status_code,
              )
            "
            @click="command('cancel')"
            >取消方案</el-button
          ><el-button
            v-if="
              hasPerms('mes:schedule:apply') &&
              hasPerms('mes:schedule:manage') &&
              detail.status_code === 'ready'
            "
            type="primary"
            @click="command('apply')"
            >确认应用方案</el-button
          >
        </div></el-card
      >
    </template>
  </div>
</template>
<style scoped>
.schedule-plans > :deep(.el-card),
.schedule-plans > :deep(.el-alert) {
  margin-bottom: 20px;
}

.schedule-plans h3 {
  margin-bottom: 20px;
}

.stage-table {
  margin-top: 20px;
}

.plan-heading-actions {
  display: flex;
  gap: 12px;
}
</style>
