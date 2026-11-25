<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { useRoute } from "vue-router";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch
} from "vue";
import {
  getMesSchedules,
  getMesScheduleResources,
  getMesScheduleOrgOptions,
  updateMesSchedules,
  type MesTask,
  type MesScheduleChange,
  type MesScheduleResource
} from "@plugins/mes/web/src/api/mes";
import {
  archiveOptions,
  type ArchiveOption
} from "@plugins/mes/web/src/api/mesArchives";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import WorkOrderDetail from "../components/WorkOrderDetail.vue";
import RemoteSelect from "../components/RemoteSelect.vue";
import TaskTable from "./TaskTable.vue";
import WorkOrderTable from "./WorkOrderTable.vue";
import EquipmentBoard from "./EquipmentBoard.vue";
import CreatePlan from "../schedule-plans/CreatePlan.vue";
import {
  automaticSelectionError,
  canSchedule,
  continuousPeriods,
  duration,
  periodOnDay,
  scheduleDays,
  shiftDay,
  today
} from "./model";
defineOptions({ name: "MesScheduling" });
const route = useRoute();
type EditingTask = MesTask & { period: Date[]; equipment_changed?: boolean };
const view = ref("tasks"),
  taskDisplay = ref("list");
const orderTable = ref<InstanceType<typeof WorkOrderTable>>();
const filters = reactive({
  org_id: "",
  process_id: "",
  keyword: "",
  product_keyword: "",
  equipment_keyword: "",
  work_center: "",
  scheduled: "",
  status_code: "",
  priority_code: "",
  unfinished_only: true
});
watch(
  () => filters.org_id,
  () => {
    filters.process_id = "";
  }
);
const dates = ref<string[]>([]),
  dueDates = ref<string[]>([]),
  windowDates = ref([shiftDay(today(), -1), shiftDay(today(), 6)]);
const days = computed(() => {
  try {
    return scheduleDays(windowDates.value);
  } catch {
    return [];
  }
});
const page = ref(1),
  size = ref(20),
  total = ref(0),
  loading = ref(false),
  error = ref("");
const rows = ref<MesTask[]>([]),
  resources = ref<MesScheduleResource[]>([]),
  selected = ref<MesTask[]>([]);
const trialVisible = ref(false);
const trialOrg = ref("");
const trialOrderIds = ref<string[]>([]);
function openTrial(values: MesTask[] = selected.value) {
  if (!hasPerms("mes:schedule:manage")) return;
  const problem = automaticSelectionError(values);
  if (problem) {
    message(problem, { type: "warning" });
    return;
  }
  trialOrg.value = values[0].org_id;
  trialOrderIds.value = [...new Set(values.map(row => row.work_order_id))];
  trialVisible.value = true;
}
const editing = ref<EditingTask[]>([]),
  dialogVisible = ref(false),
  saving = ref(false),
  reason = ref("");
const sequenceStart = ref<Date>(),
  sequenceHours = ref(1),
  sequenceGap = ref(0);
const detailVisible = ref(false),
  orderId = ref("");
const resourceVisible = ref(false),
  resource = ref<MesScheduleResource>(),
  resourceRows = ref<MesTask[]>([]),
  resourceSelected = ref<MesTask[]>([]);
const resourcePage = ref(1),
  resourceTotal = ref(0),
  resourceLoading = ref(false),
  resourceError = ref(""),
  resourceDay = ref("");
const candidateVisible = ref(false),
  candidates = ref<MesTask[]>([]),
  candidateSelected = ref<MesTask[]>([]),
  candidateKeyword = ref("");
const candidatePage = ref(1),
  candidateTotal = ref(0),
  candidateLoading = ref(false),
  candidateError = ref("");
let request = 0,
  resourceRequest = 0,
  candidateRequest = 0,
  wholeRequest = 0;
function params() {
  return {
    ...filters,
    scheduled:
      filters.scheduled === "" ? undefined : filters.scheduled === "yes",
    start_date: dates.value?.[0],
    end_date: dates.value?.[1],
    due_from: dueDates.value?.[0],
    due_to: dueDates.value?.[1],
    window_start: windowDates.value?.[0],
    window_end: windowDates.value?.[1]
  };
}
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  selected.value = [];
  orderTable.value?.clearSelection();
  try {
    scheduleDays(windowDates.value);
    const query = { ...params(), page: page.value, page_size: size.value };
    if (view.value === "tasks") {
      const result = await getMesSchedules({
        ...query,
        group_by_work_order: true
      });
      if (current === request)
        ((rows.value = result.data.items), (total.value = result.data.total));
    } else {
      const result = await getMesScheduleResources(query);
      if (current === request)
        ((resources.value = result.data.items),
          (total.value = result.data.total));
    }
    if (current === request) selected.value = [];
  } catch (cause) {
    if (current === request) {
      rows.value = [];
      resources.value = [];
      total.value = 0;
      error.value = getHttpErrorMessage(cause, "排程读取失败");
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  return load();
}
function changeView() {
  selected.value = [];
  return search();
}
function reset() {
  Object.assign(filters, {
    org_id: "",
    process_id: "",
    keyword: "",
    product_keyword: "",
    equipment_keyword: "",
    work_center: "",
    scheduled: "",
    status_code: "",
    priority_code: "",
    unfinished_only: true
  });
  dates.value = [];
  dueDates.value = [];
  return search();
}
function moveWindow(delta: number) {
  try {
    windowDates.value = windowDates.value.map(day => shiftDay(day, delta));
    return search();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause));
  }
}
function edit(values: MesTask[]) {
  if (saving.value || !values.length || !hasPerms("mes:schedule:manage"))
    return;
  ++wholeRequest;
  if (values.length > 100) {
    message("一次最多调整 100 道工序，请分批处理", { type: "warning" });
    return;
  }
  editing.value = values.filter(canSchedule).map(row => ({
    ...row,
    period:
      row.planned_start_at && row.planned_end_at
        ? [new Date(row.planned_start_at), new Date(row.planned_end_at)]
        : [],
    equipment_changed: false
  }));
  reason.value = "";
  sequenceStart.value = editing.value[0]?.period[0];
  dialogVisible.value = editing.value.length > 0;
  if (!editing.value.length)
    message("没有可调整的未开始工序", { type: "warning" });
}
function editAt(row: MesTask, day: string) {
  edit([row]);
  if (dialogVisible.value && editing.value[0])
    editing.value[0].period = periodOnDay(row, day);
}
async function whole(row: MesTask) {
  if (saving.value) return;
  const current = ++wholeRequest;
  try {
    const result = await getMesSchedules({
      work_order_id: row.work_order_id,
      page: 1,
      page_size: 100
    });
    if (current !== wholeRequest) return;
    if (result.data.total > 100)
      throw Error("该工单超过 100 道工序，请按列表分批安排");
    edit(result.data.items);
  } catch (cause) {
    if (current === wholeRequest)
      message(getHttpErrorMessage(cause, "工单工序读取失败"), {
        type: "warning"
      });
  }
}
function fillSequence() {
  try {
    editing.value = continuousPeriods(
      editing.value,
      sequenceStart.value,
      sequenceHours.value,
      sequenceGap.value
    );
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause));
  }
}
async function equipmentOptions(row: EditingTask, keyword: string) {
  return (
    await archiveOptions(
      "equipment",
      row.org_id,
      keyword,
      row.process_id
        ? { applicable_process_id: row.process_id }
        : { generic_equipment_only: true }
    )
  ).filter(
    option => !option.process_id || option.process_id === row.process_id
  );
}
function equipmentPicked(row: EditingTask, option?: ArchiveOption) {
  row.equipment_id = option?.value || null;
  row.equipment_changed = true;
  row.workstation_name = option?.record_no || null;
  row.work_center_name = option?.work_center_name || null;
}
function clearPeriods() {
  if (!saving.value)
    editing.value.forEach(row => {
      row.period = [];
    });
}
async function save() {
  if (saving.value || !editing.value.length) return;
  if (!reason.value.trim()) {
    message("请填写本次排程或调整理由", { type: "warning" });
    return;
  }
  const changes: MesScheduleChange[] = [];
  for (const row of editing.value) {
    const period = row.period || [];
    if (
      !Number.isInteger(row.version_no) ||
      (period.length &&
        (period.length !== 2 ||
          !Number.isFinite(+new Date(period[0])) ||
          !Number.isFinite(+new Date(period[1])) ||
          +new Date(period[0]) >= +new Date(period[1])))
    ) {
      message("请填写有效起止时间，或清空以取消安排；修订失效时请刷新", {
        type: "warning"
      });
      return;
    }
    changes.push({
      operation_id: row.id,
      version_no: row.version_no,
      planned_start_at: period[0] ? new Date(period[0]).toISOString() : null,
      planned_end_at: period[1] ? new Date(period[1]).toISOString() : null,
      ...(row.equipment_changed
        ? { equipment_id: row.equipment_id || null }
        : {})
    });
  }
  saving.value = true;
  try {
    await updateMesSchedules(changes, reason.value.trim());
    message("排程已保存", { type: "success" });
    dialogVisible.value = false;
    await Promise.all([
      load(),
      ...(resourceVisible.value ? [loadResourceTasks()] : [])
    ]);
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "保存失败，请刷新后重试"));
  } finally {
    saving.value = false;
  }
}
function resourceParams(value: MesScheduleResource) {
  return {
    org_id: value.org_id,
    ...(value.equipment_id
      ? { equipment_id: value.equipment_id }
      : value.kind === "unassigned"
        ? {
            unassigned_only: true,
            work_center_exact: value.work_center_name || ""
          }
        : {
            work_center_exact: value.work_center_name || "",
            workstation: value.workstation_name || ""
          })
  };
}
async function openResource(value: MesScheduleResource, day = "") {
  resource.value = value;
  resourceDay.value = day;
  resourcePage.value = 1;
  resourceVisible.value = true;
  await loadResourceTasks();
}
async function addForResource(value: MesScheduleResource) {
  await openResource(value);
  if (resource.value?.resource_key === value.resource_key)
    await openCandidates();
}
async function loadResourceTasks() {
  const value = resource.value;
  if (!value) return;
  const current = ++resourceRequest;
  resourceLoading.value = true;
  resourceError.value = "";
  resourceRows.value = [];
  resourceSelected.value = [];
  resourceTotal.value = 0;
  try {
    const result = await getMesSchedules({
      ...params(),
      ...resourceParams(value),
      ...(resourceDay.value
        ? { start_date: resourceDay.value, end_date: resourceDay.value }
        : {}),
      page: resourcePage.value,
      page_size: 20
    });
    if (current === resourceRequest) {
      resourceRows.value = result.data.items;
      resourceTotal.value = result.data.total;
    }
  } catch (cause) {
    if (current === resourceRequest)
      resourceError.value = getHttpErrorMessage(cause, "设备任务读取失败");
  } finally {
    if (current === resourceRequest) resourceLoading.value = false;
  }
}
async function openCandidates() {
  candidateKeyword.value = "";
  candidatePage.value = 1;
  candidateVisible.value = true;
  await loadCandidates();
}
async function loadCandidates() {
  const value = resource.value;
  if (!value?.equipment_id) return;
  const current = ++candidateRequest;
  candidateLoading.value = true;
  candidateError.value = "";
  candidateSelected.value = [];
  candidates.value = [];
  candidateTotal.value = 0;
  try {
    const result = await getMesSchedules({
      org_id: value.org_id,
      process_id: value.process_id || undefined,
      keyword: candidateKeyword.value,
      unfinished_only: true,
      unassigned_only: true,
      unstarted_only: true,
      page: candidatePage.value,
      page_size: 20
    });
    if (current === candidateRequest) {
      candidates.value = result.data.items;
      candidateTotal.value = result.data.total;
    }
  } catch (cause) {
    if (current === candidateRequest)
      candidateError.value = getHttpErrorMessage(cause, "待分配任务读取失败");
  } finally {
    if (current === candidateRequest) candidateLoading.value = false;
  }
}
function planCandidates() {
  const value = resource.value;
  if (!value?.equipment_id) return;
  edit(candidateSelected.value);
  if (!dialogVisible.value) return;
  editing.value.forEach(row => {
    row.equipment_id = value.equipment_id;
    row.workstation_name = value.equipment_no;
    row.equipment_changed = true;
    row.work_center_name = value.work_center_name;
  });
  candidateVisible.value = false;
}
function inspect(row: MesTask) {
  orderId.value = row.work_order_id;
  detailVisible.value = true;
}
function loadAt(resource: MesScheduleResource, day: string) {
  return resource.daily_load.find(item => item.day === day);
}
function requestedPlan() {
  const raw = route.query.work_order_ids;
  const org = route.query.org_id;
  if (
    typeof raw !== "string" ||
    typeof org !== "string" ||
    !hasPerms("mes:schedule:manage")
  )
    return;
  const ids = [...new Set(raw.split(",").filter(Boolean))];
  if (!ids.length || ids.length > 10) return;
  trialOrg.value = org;
  trialOrderIds.value = ids;
  trialVisible.value = true;
}
watch(() => route.query.work_order_ids, requestedPlan);
onMounted(() => {
  load();
  requestedPlan();
});
onBeforeUnmount(() => {
  ++request;
  ++resourceRequest;
  ++candidateRequest;
  ++wholeRequest;
});
</script>
<template>
  <CreatePlan
    v-if="trialVisible"
    :org-id="trialOrg"
    :work-order-ids="trialOrderIds"
    @close="trialVisible = false"
  />
  <div v-else class="mes-page">
    <div class="page-heading">
      <div>
        <h2>生产排程</h2>
        <p class="muted">选择货品工单进行自动排程，展开查看和调整各道工序。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-card shadow="never" class="filter-card">
      <el-radio-group v-model="view" @change="changeView"
        ><el-radio-button value="tasks">工单排程</el-radio-button
        ><el-radio-button value="equipment">设备看板</el-radio-button
        ><el-radio-button value="equipment-timeline"
          >设备时间轴</el-radio-button
        ></el-radio-group
      >
      <el-form inline class="filters" @submit.prevent="search">
        <el-form-item label="组织"
          ><RemoteSelect
            v-model="filters.org_id"
            style="width: 200px"
            :load-options="getMesScheduleOrgOptions"
            placeholder="授权范围内组织"
        /></el-form-item>
        <el-form-item label="工艺"
          ><RemoteSelect
            v-model="filters.process_id"
            style="width: 200px"
            :disabled="!filters.org_id"
            :context-key="filters.org_id"
            :load-options="
              keyword => archiveOptions('processes', filters.org_id, keyword)
            "
            placeholder="先选组织，可按工艺筛选"
        /></el-form-item>
        <el-form-item label="优先级"
          ><el-select
            v-model="filters.priority_code"
            clearable
            style="width: 120px"
            ><el-option
              v-for="item in [
                { value: 'urgent', label: '紧急' },
                { value: 'high', label: '高' },
                { value: 'normal', label: '普通' },
                { value: 'low', label: '低' }
              ]"
              :key="item.value"
              :value="item.value"
              :label="item.label" /></el-select
        ></el-form-item>
        <el-form-item label="工单 / 项目"
          ><el-input
            v-model="filters.keyword"
            clearable
            maxlength="128"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="货品"
          ><el-input
            v-model="filters.product_keyword"
            clearable
            maxlength="128"
            placeholder="编号 / 名称"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="设备"
          ><el-input
            v-model="filters.equipment_keyword"
            clearable
            maxlength="128"
            placeholder="设备编号 / 名称"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="工作中心"
          ><el-input v-model="filters.work_center" clearable maxlength="128"
        /></el-form-item>
        <el-form-item label="计划状态"
          ><el-select v-model="filters.scheduled" clearable style="width: 125px"
            ><el-option label="已安排" value="yes" /><el-option
              label="未安排"
              value="no" /></el-select
        ></el-form-item>
        <el-form-item label="工序状态"
          ><el-select
            v-model="filters.status_code"
            clearable
            style="width: 130px"
            ><el-option
              v-for="item in [
                { value: 'pending', label: '待执行' },
                { value: 'dispatched', label: '已派工' },
                { value: 'in_progress', label: '执行中' },
                { value: 'waiting_quality', label: '待检验' },
                { value: 'completed', label: '已完成' }
              ]"
              :key="item.value"
              :label="item.label"
              :value="item.value" /></el-select
        ></el-form-item>
        <el-form-item label="交期"
          ><el-date-picker
            v-model="dueDates"
            type="daterange"
            value-format="YYYY-MM-DD"
            style="width: 245px"
        /></el-form-item>
        <el-form-item label="计划区间"
          ><el-date-picker
            v-model="dates"
            type="daterange"
            value-format="YYYY-MM-DD"
            style="width: 245px"
        /></el-form-item>
        <el-form-item
          ><el-checkbox v-model="filters.unfinished_only"
            >仅未完成</el-checkbox
          ></el-form-item
        >
        <el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        >
      </el-form>
    </el-card>
    <el-card
      shadow="never"
      :class="{ 'equipment-panel': view === 'equipment' }"
    >
      <div class="board-toolbar">
        <div
          v-if="view !== 'tasks' || taskDisplay === 'timeline'"
          class="actions"
        >
          <el-button @click="moveWindow(-7)">前 7 天</el-button
          ><el-date-picker
            v-model="windowDates"
            type="daterange"
            value-format="YYYY-MM-DD"
            :clearable="false"
            style="width: 250px"
            @change="search"
          /><el-button @click="moveWindow(7)">后 7 天</el-button
          ><span class="muted">北京时间，最多 31 天</span>
        </div>
        <el-radio-group v-if="view === 'tasks'" v-model="taskDisplay"
          ><el-radio-button value="list">工序列表</el-radio-button
          ><el-radio-button value="timeline"
            >工序时间轴</el-radio-button
          ></el-radio-group
        >
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template v-if="view === 'tasks'">
        <div class="erp-query-form order-toolbar">
          <div class="order-selection">
            <strong>共 {{ total }} 张货品工单</strong>
            <span v-if="selected.length">已选 {{ selected.length }} 张</span>
            <span v-else-if="hasPerms('mes:schedule:manage')" class="muted"
              >同一组织每次最多选择 10 张，按完整路线排程</span
            >
            <span v-else class="muted">展开查看完整路线与工序计划</span>
            <el-button
              v-if="selected.length"
              link
              @click="orderTable?.clearSelection()"
              >清空选择</el-button
            >
          </div>
          <el-button
            v-if="hasPerms('mes:schedule:manage')"
            type="primary"
            :disabled="!selected.length"
            :loading="loading"
            @click="openTrial()"
            >{{
              selected.length
                ? `自动排程（${selected.length} 张工单）`
                : "自动排程"
            }}</el-button
          >
        </div>
        <WorkOrderTable
          ref="orderTable"
          :rows="rows"
          :loading="loading"
          :editable="hasPerms('mes:schedule:manage')"
          :inspectable="hasPerms('mes:work_order:list')"
          :days="taskDisplay === 'timeline' ? days : []"
          @selection="value => (selected = value)"
          @auto="row => openTrial([row])"
          @edit="row => edit([row])"
          @whole="whole"
          @inspect="inspect"
          @day="editAt"
        />
      </template>
      <EquipmentBoard
        v-else-if="view === 'equipment'"
        :resources="resources"
        :days="days"
        :loading="loading"
        :editable="hasPerms('mes:schedule:manage')"
        @open="openResource"
        @add="addForResource"
      />
      <el-table
        v-else
        v-loading="loading"
        :data="resources"
        row-key="resource_key"
        max-height="620"
      >
        <el-table-column label="设备 / 工艺" min-width="230" fixed="left"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="openResource(row as MesScheduleResource)"
              >{{ row.equipment_name }}</el-button
            >
            <div>
              {{ row.equipment_no }} ·
              {{ row.process_name || row.work_center_name || "未限定工艺" }}
            </div></template
          ></el-table-column
        >
        <el-table-column label="任务 / 已安排" width="135"
          ><template #default="{ row }"
            >{{ row.task_count }} / {{ row.scheduled_count }}</template
          ></el-table-column
        >
        <el-table-column
          v-for="day in days"
          :key="day"
          :label="`${day.slice(5)}${day === today() ? ' 今日' : ''}`"
          width="145"
          align="center"
          ><template #default="{ row }"
            ><button
              class="load-cell"
              :class="{
                occupied: loadAt(row as MesScheduleResource, day),
                today: day === today()
              }"
              @click="openResource(row as MesScheduleResource, day)"
            >
              <template v-if="loadAt(row as MesScheduleResource, day)"
                ><strong
                  >{{
                    loadAt(row as MesScheduleResource, day).task_count
                  }}
                  道工序</strong
                ><small>{{
                  duration(
                    loadAt(row as MesScheduleResource, day).planned_minutes
                  )
                }}</small></template
              ><span v-else>—</span>
            </button></template
          ></el-table-column
        >
        <el-table-column label="操作" width="100" fixed="right"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="openResource(row as MesScheduleResource)"
              >任务管理</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <p class="muted board-note">
        <template v-if="view === 'tasks'"
          >按货品工单分页；工艺、设备及工序状态用于筛选工单，展开后显示完整授权路线。自动排程后需核对并确认应用方案。</template
        >
        <template v-else
          >设备数量、计划时长按完整授权筛选结果汇总；按日时长为计划区间与当日的交集，不扣班次、休息及停机，不代表实际产能或实际加工工时。</template
        >
      </p>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="search"
      />
    </el-card>
    <el-drawer
      v-model="resourceVisible"
      :title="`${resource?.equipment_name || '设备'} · 任务管理${resourceDay ? ' · ' + resourceDay : ''}`"
      size="min(1180px, 96vw)"
      @closed="++resourceRequest"
    >
      <div class="actions">
        <el-button
          v-if="hasPerms('mes:schedule:manage')"
          type="primary"
          :disabled="!resourceSelected.length"
          @click="edit(resourceSelected)"
          >批量计划（{{ resourceSelected.length }}）</el-button
        ><el-button
          v-if="
            resource?.equipment_id &&
            resource.is_active &&
            hasPerms('mes:schedule:manage')
          "
          @click="openCandidates"
          >添加待排任务</el-button
        ><el-button
          @click="
            resourceDay = '';
            loadResourceTasks();
          "
          >查看全部日期</el-button
        >
      </div>
      <el-alert
        v-if="resourceError"
        :title="resourceError"
        type="error"
        :closable="false"
      />
      <TaskTable
        :rows="resourceRows"
        :loading="resourceLoading"
        :editable="hasPerms('mes:schedule:manage')"
        :inspectable="hasPerms('mes:work_order:list')"
        @selection="value => (resourceSelected = value)"
        @edit="row => edit([row])"
        @whole="whole"
        @inspect="inspect"
      />
      <ListPagination
        v-model:current-page="resourcePage"
        :page-size="20"
        :total="resourceTotal"
        layout="total, prev, pager, next"
        @current-change="loadResourceTasks"
      />
    </el-drawer>
    <el-dialog
      v-model="candidateVisible"
      title="选择未分配设备的待排工序"
      width="min(1150px, 96vw)"
      append-to-body
      @closed="++candidateRequest"
    >
      <p>
        只列出本组织、适用工艺且尚未分配设备的任务；选择后先预览计划，确认保存后才生效。
      </p>
      <div class="actions">
        <el-input
          v-model="candidateKeyword"
          placeholder="工单 / 项目 / 工序"
          clearable
          style="width: 280px"
          @keyup.enter="
            candidatePage = 1;
            loadCandidates();
          "
        /><el-button
          @click="
            candidatePage = 1;
            loadCandidates();
          "
          >查询</el-button
        >
      </div>
      <el-alert
        v-if="candidateError"
        :title="candidateError"
        type="error"
        :closable="false"
      />
      <TaskTable
        :rows="candidates"
        :loading="candidateLoading"
        :editable="true"
        :actions="false"
        @selection="value => (candidateSelected = value)"
      />
      <ListPagination
        v-model:current-page="candidatePage"
        :page-size="20"
        :total="candidateTotal"
        layout="total, prev, pager, next"
        @current-change="loadCandidates"
      />
      <template #footer
        ><el-button @click="candidateVisible = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!candidateSelected.length"
          @click="planCandidates"
          >配置选中任务</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="dialogVisible"
      title="生产计划 / 批量变更"
      width="min(1200px, 96vw)"
      :close-on-click-modal="false"
      :show-close="!saving"
      :close-on-press-escape="!saving"
      append-to-body
    >
      <p>
        调整未开始工序的计划时间与设备；清空时间表示取消安排。任一工序冲突时整批不保存。
      </p>
      <div class="sequence-toolbar">
        <el-date-picker
          v-model="sequenceStart"
          type="datetime"
          placeholder="连续安排的开始时间"
          :disabled="saving"
        /><span>每工序</span
        ><el-input-number
          v-model="sequenceHours"
          :min="0.001"
          :max="744"
          :precision="3"
          :disabled="saving"
          style="width: 125px"
        /><span>小时，间隔</span
        ><el-input-number
          v-model="sequenceGap"
          :min="0"
          :max="1440"
          :disabled="saving"
          style="width: 115px"
        /><span>分钟</span
        ><el-button :disabled="saving" @click="fillSequence"
          >按工单 / 工序顺序填入</el-button
        ><el-button :disabled="saving" @click="clearPeriods"
          >清空计划时间</el-button
        >
      </div>
      <el-table :data="editing" max-height="430" row-key="id">
        <el-table-column
          prop="work_order_no"
          label="工单 / 产品"
          min-width="170"
          ><template #default="{ row }"
            >{{ row.work_order_no }}
            <div>{{ row.product_item_name }}</div></template
          ></el-table-column
        >
        <el-table-column label="工序 / 计划数量" min-width="145"
          ><template #default="{ row }"
            >{{ row.sequence_no }}. {{ row.operation_name }}
            <div>{{ row.planned_quantity }} {{ row.unit_name }}</div></template
          ></el-table-column
        >
        <el-table-column label="计划加工设备" min-width="235"
          ><template #default="{ row }"
            ><RemoteSelect
              :model-value="row.equipment_id || ''"
              :disabled="saving"
              :context-key="`${row.org_id}:${row.process_id}`"
              :load-options="
                keyword => equipmentOptions(row as EditingTask, keyword)
              "
              :initial-option="
                row.equipment_id
                  ? {
                      value: row.equipment_id,
                      label: row.workstation_name || '已选设备'
                    }
                  : undefined
              "
              placeholder="可选，按工艺筛选"
              @select="
                option =>
                  equipmentPicked(
                    row as EditingTask,
                    option as ArchiveOption | undefined
                  )
              "
            /><small v-if="!row.equipment_id && row.workstation_name"
              >保留手工工作站：{{ row.workstation_name }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="计划开始 / 结束" min-width="405"
          ><template #default="{ row }"
            ><el-date-picker
              v-model="row.period"
              type="datetimerange"
              :disabled="saving"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              style="width: 100%" /></template
        ></el-table-column>
        <el-table-column label="计划时长" width="115"
          ><template #default="{ row }">{{
            row.period?.length === 2
              ? duration(
                  (+new Date(row.period[1]) - +new Date(row.period[0])) / 60000
                )
              : "未安排"
          }}</template></el-table-column
        >
      </el-table>
      <el-input
        v-model="reason"
        :disabled="saving"
        type="textarea"
        :rows="2"
        maxlength="1000"
        placeholder="必填：本次排程或调整理由"
        class="reason"
      />
      <template #footer
        ><el-button :disabled="saving" @click="dialogVisible = false"
          >取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存全部计划</el-button
        ></template
      >
    </el-dialog>
    <WorkOrderDetail v-model="detailVisible" :work-order-id="orderId" />
  </div>
</template>
<style scoped>
.mes-page {
  padding: 20px;
}

.page-heading,
.board-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

h2 {
  margin: 0 0 8px;
}

.muted {
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}

.filter-card {
  margin-bottom: 16px;
}

.filters {
  margin-top: 18px;
}

.board-toolbar {
  margin-bottom: 18px;
}

.order-toolbar,
.order-selection {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.order-toolbar {
  justify-content: space-between;
}

.actions,
.sequence-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}

.equipment-panel {
  background: color-mix(
    in srgb,
    var(--el-color-primary) 5%,
    var(--el-bg-color)
  );
}

.load-cell strong,
.load-cell small {
  display: block;
}

.equipment-panel .board-toolbar .actions {
  margin-bottom: 0;
}

small {
  color: var(--el-text-color-secondary);
}

.load-cell {
  width: 100%;
  min-height: 62px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 5px;
}

.load-cell.occupied {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.load-cell.today {
  border-color: var(--el-color-primary-light-5);
}

.board-note {
  margin: 16px 0;
  font-size: 12px;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}

.reason {
  margin-top: 16px;
}
</style>
