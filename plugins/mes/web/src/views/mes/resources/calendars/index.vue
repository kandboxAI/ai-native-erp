<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import ActionButton from "@/components/ActionButton/index.vue";
import ListPagination from "@/components/ListPagination/index.vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import RemoteSelect from "../../components/RemoteSelect.vue";
import {
  resourcePage,
  resourceDetail,
  resourceOrganizations,
  resourceOptions,
  saveResource,
  type ResourceRow,
  type ResourceOptions,
  type CalendarException,
} from "@plugins/mes/web/src/api/mesScheduleResources";
defineOptions({ name: "MesResourceCalendars" });
const query = reactive({ org_id: "", keyword: "", page: 1, page_size: 20 });
const rows = ref<ResourceRow[]>([]),
  total = ref(0),
  busy = ref(false),
  error = ref("");
const editing = ref(false),
  calendar = ref<ResourceRow>();
const resources = ref<ResourceOptions>({ people: [], equipment: [] });
const resourceKind = ref<"person" | "equipment">("person"),
  chosen = ref<string[]>([]);
const form = reactive({
  org_id: "",
  calendar_name: "",
  timezone_name: "Asia/Shanghai",
  valid_from: "",
  valid_to: "",
  is_active: true,
});
type PeriodDraft = {
  weekday_no: number;
  period_type_code: "work" | "lunch";
  start: string;
  end: string;
};
const periods = ref<PeriodDraft[]>([]);
const canManage = computed(() => hasPerms("mes:schedule_resource:manage"));
const exceptionVisible = ref(false),
  selectedException = ref<CalendarException>();
const exceptionForm = reactive({
  start_at: undefined as Date | undefined,
  end_at: undefined as Date | undefined,
  exception_type_code: "unavailable" as "extra_available" | "unavailable",
  reason: "",
  is_active: true,
});
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const minutes = (value: string) => {
  const [h, m] = value.split(":").map(Number);
  return h * 60 + m;
};
const hhmm = (value: number) =>
  `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
const date = (value?: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const baseline = ref("");
const signature = () => JSON.stringify({ ...form, periods: periods.value });
const dirty = computed(() => signature() !== baseline.value);
watch(
  () => form.org_id,
  async (value) => {
    if (!value) {
      resources.value = { people: [], equipment: [] };
      return;
    }
    try {
      resources.value = await resourceOptions(value);
    } catch (e) {
      error.value = getHttpErrorMessage(e, "读取日历资源失败");
    }
  },
);
watch(resourceKind, () => {
  if (!calendar.value) chosen.value = [];
});
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const r = await resourcePage("calendars", {
      ...query,
      org_id: query.org_id || undefined,
    });
    rows.value = r.items;
    total.value = r.total;
  } catch (e) {
    error.value = getHttpErrorMessage(e, "读取工作日历失败");
  } finally {
    busy.value = false;
  }
}
async function open(row?: ResourceRow) {
  busy.value = true;
  error.value = "";
  try {
    calendar.value = row
      ? await resourceDetail("calendars", row.id)
      : undefined;
    const c = calendar.value;
    resourceKind.value = c?.equipment_id ? "equipment" : "person";
    chosen.value = c ? [c.production_person_id || c.equipment_id!] : [];
    Object.assign(form, {
      org_id: c?.org_id || query.org_id,
      calendar_name: c?.calendar_name || "",
      timezone_name: c?.timezone_name || "Asia/Shanghai",
      valid_from: c?.valid_from || new Date().toLocaleDateString("sv-SE"),
      valid_to: c?.valid_to || "",
      is_active: c?.is_active ?? true,
    });
    periods.value = (c?.periods || []).map((p) => ({
      weekday_no: p.weekday_no,
      period_type_code: p.period_type_code,
      start: hhmm(p.start_minute_of_day),
      end: hhmm(p.end_minute_of_day),
    }));
    if (form.org_id) resources.value = await resourceOptions(form.org_id);
    baseline.value = signature();
    editing.value = true;
  } catch (e) {
    error.value = getHttpErrorMessage(e, "读取日历失败");
  } finally {
    busy.value = false;
  }
}
function standardWeek() {
  periods.value = Array.from({ length: 5 }, (_, day) => {
    const times =
      resourceKind.value === "person"
        ? [
            ["work", "08:00", "12:00"],
            ["lunch", "12:00", "13:30"],
            ["work", "13:30", "18:00"],
          ]
        : [["work", "08:00", "18:00"]];
    return times.map(([type, start, end]) => ({
      weekday_no: day + 1,
      period_type_code: type as "work" | "lunch",
      start,
      end,
    }));
  }).flat();
}
async function save() {
  if (
    !form.org_id ||
    !form.calendar_name.trim() ||
    !chosen.value.length ||
    !form.valid_from ||
    !periods.value.length
  ) {
    actionMessage("请填写组织、资源、名称、有效日期和常规时段", "warning");
    return;
  }
  if (chosen.value.length > 100) {
    actionMessage("每次最多批量创建100份日历", "warning");
    return;
  }
  if (periods.value.some((p) => !p.start || !p.end)) {
    actionMessage("请补齐时段起止时间", "warning");
    return;
  }
  busy.value = true;
  try {
    const bodies = chosen.value.map((id) => ({
      ...form,
      version_no: calendar.value?.version_no,
      valid_to: form.valid_to || null,
      calendar_name:
        chosen.value.length > 1
          ? `${form.calendar_name} · ${(resourceKind.value === "person" ? resources.value.people : resources.value.equipment).find((r) => r.id === id)?.label.split(" · ")[0] || id}`
          : form.calendar_name,
      production_person_id: resourceKind.value === "person" ? id : null,
      equipment_id: resourceKind.value === "equipment" ? id : null,
      periods: periods.value.map((p) => ({
        weekday_no: p.weekday_no,
        period_type_code: p.period_type_code,
        start_minute_of_day: minutes(p.start),
        end_minute_of_day: minutes(p.end),
      })),
    }));
    if (bodies.length > 1) {
      await saveResource("calendar-batch", { calendars: bodies });
      editing.value = false;
      await load();
    } else {
      const result = await saveResource(
        calendar.value ? `calendars/${calendar.value.id}` : "calendars",
        bodies[0],
        !!calendar.value,
      );
      await open(result);
    }
    message("日历保存成功", { type: "success" });
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "保存日历失败"));
  } finally {
    busy.value = false;
  }
}
function openException(row?: CalendarException) {
  if (dirty.value) {
    actionMessage("请先保存日历调整，再维护例外", "warning");
    return;
  }
  selectedException.value = row;
  Object.assign(exceptionForm, {
    start_at: row ? new Date(row.start_at) : undefined,
    end_at: row ? new Date(row.end_at) : undefined,
    exception_type_code: row?.exception_type_code || "unavailable",
    reason: row?.reason || "",
    is_active: row?.is_active ?? true,
  });
  exceptionVisible.value = true;
}
async function saveException() {
  if (
    !calendar.value ||
    !exceptionForm.start_at ||
    !exceptionForm.end_at ||
    !exceptionForm.reason.trim()
  ) {
    actionMessage("请填写例外起止时间和原因", "warning");
    return;
  }
  busy.value = true;
  try {
    await saveResource(
      `calendars/${calendar.value.id}/exceptions${selectedException.value ? `/${selectedException.value.id}` : ""}`,
      {
        ...exceptionForm,
        org_id: calendar.value.org_id,
        version_no: selectedException.value?.version_no,
        start_at: exceptionForm.start_at.toISOString(),
        end_at: exceptionForm.end_at.toISOString(),
      },
      !!selectedException.value,
    );
    await open(calendar.value);
    exceptionVisible.value = false;
    message("日历例外已保存", { type: "success" });
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "保存例外失败"));
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div v-loading="busy" class="mes-page resource-calendars">
    <div class="page-heading">
      <div>
        <h2>
          {{
            editing ? (calendar ? "维护工作日历" : "新增工作日历") : "工作日历"
          }}
        </h2>
        <p class="muted">
          维护人员、设备的工作时段及请假、加班、停机例外。不可用优先，午休单独标识。
        </p>
      </div>
      <el-button
        v-if="editing"
        @click="
          editing = false;
          load();
        "
        >返回列表</el-button
      ><ActionButton v-else-if="canManage" intent="create" @click="open()"
        >新增 / 批量创建日历</ActionButton
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <el-card v-if="!editing" shadow="never"
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
            :load-options="resourceOrganizations"
            placeholder="选择组织" /></el-form-item
        ><el-form-item label="日历"
          ><el-input
            v-model="query.keyword"
            clearable
            placeholder="按日历名称搜索" /></el-form-item
        ><el-form-item
          ><el-button type="primary" native-type="submit"
            >查询</el-button
          ></el-form-item
        ></el-form
      ><el-table :data="rows" border
        ><el-table-column
          prop="calendar_name"
          label="日历名称"
          min-width="230"
        /><el-table-column label="资源类型" width="120"
          ><template #default="{ row }">{{
            row.production_person_id ? "生产人员" : "设备"
          }}</template></el-table-column
        ><el-table-column
          prop="timezone_name"
          label="时区"
          width="180"
        /><el-table-column
          prop="valid_from"
          label="生效日期"
          width="130"
        /><el-table-column label="失效日期" width="130"
          ><template #default="{ row }">{{
            row.valid_to || "持续有效"
          }}</template></el-table-column
        ><el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="操作" width="150"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="open(row as ResourceRow)">{{
              canManage ? "维护时段与例外" : "查看时段与例外"
            }}</el-button></template
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
      <el-card shadow="never"
        ><el-form
          label-position="top"
          :disabled="!canManage"
          @submit.prevent="save"
          ><div class="resource-fields">
            <el-form-item label="所属组织" required
              ><RemoteSelect
                v-model="form.org_id"
                :disabled="!!calendar"
                :load-options="resourceOrganizations"
                placeholder="选择组织" /></el-form-item
            ><el-form-item label="资源类型"
              ><el-radio-group v-model="resourceKind" :disabled="!!calendar"
                ><el-radio-button value="person">人员</el-radio-button
                ><el-radio-button value="equipment"
                  >设备</el-radio-button
                ></el-radio-group
              ></el-form-item
            ><el-form-item label="资源（新建支持多选）" required
              ><el-select
                v-model="chosen"
                multiple
                filterable
                :disabled="!!calendar || !form.org_id"
                ><el-option
                  v-for="r in resourceKind === 'person'
                    ? resources.people
                    : resources.equipment"
                  :key="r.id"
                  :value="r.id"
                  :label="r.label" /></el-select></el-form-item
            ><el-form-item label="日历名称" required
              ><el-input
                v-model="form.calendar_name"
                maxlength="100" /></el-form-item
            ><el-form-item label="时区"
              ><el-select v-model="form.timezone_name" filterable allow-create
                ><el-option
                  label="Asia/Shanghai"
                  value="Asia/Shanghai" /></el-select></el-form-item
            ><el-form-item label="生效日期" required
              ><el-date-picker
                v-model="form.valid_from"
                type="date"
                value-format="YYYY-MM-DD" /></el-form-item
            ><el-form-item label="失效日期（不含当天）"
              ><el-date-picker
                v-model="form.valid_to"
                type="date"
                value-format="YYYY-MM-DD"
                clearable /></el-form-item
            ><el-form-item label="启用"
              ><el-switch v-model="form.is_active"
            /></el-form-item>
          </div>
          <div class="page-heading">
            <h3>每周常规时段</h3>
            <div v-if="canManage">
              <el-button @click="standardWeek">填入周一至周五标准时段</el-button
              ><ActionButton
                intent="create"
                @click="
                  periods.push({
                    weekday_no: 1,
                    period_type_code: 'work',
                    start: '08:00',
                    end: '12:00',
                  })
                "
                >添加时段</ActionButton
              >
            </div>
          </div>
          <el-table :data="periods" border
            ><el-table-column label="星期" width="160"
              ><template #default="{ row }"
                ><el-select v-model="row.weekday_no"
                  ><el-option
                    v-for="(day, i) in weekdays"
                    :key="day"
                    :label="day"
                    :value="i + 1" /></el-select></template></el-table-column
            ><el-table-column label="类型" width="180"
              ><template #default="{ row }"
                ><el-select v-model="row.period_type_code"
                  ><el-option label="工作" value="work" /><el-option
                    label="明确的午休"
                    value="lunch" /></el-select></template></el-table-column
            ><el-table-column label="开始" min-width="170"
              ><template #default="{ row }"
                ><el-time-select
                  v-model="row.start"
                  start="00:00"
                  step="00:15"
                  end="23:45" /></template></el-table-column
            ><el-table-column label="结束" min-width="170"
              ><template #default="{ row }"
                ><el-time-select
                  v-model="row.end"
                  start="00:15"
                  step="00:15"
                  end="24:00" /></template></el-table-column
            ><el-table-column v-if="canManage" label="操作" width="100"
              ><template #default="{ $index }"
                ><el-button
                  link
                  type="danger"
                  @click="periods.splice($index, 1)"
                  >移除</el-button
                ></template
              ></el-table-column
            ></el-table
          >
          <div v-if="canManage" class="erp-form-actions">
            <el-button @click="editing = false">取消</el-button
            ><el-button type="primary" native-type="submit">保存日历</el-button>
          </div></el-form
        ></el-card
      >
      <el-card v-if="calendar" shadow="never"
        ><div class="page-heading">
          <h3>日历例外</h3>
          <ActionButton
            v-if="canManage"
            intent="create"
            @click="openException()"
            >登记请假 / 加班 / 停机</ActionButton
          >
        </div>
        <el-table :data="calendar.exceptions" border
          ><el-table-column label="开始时间" min-width="190"
            ><template #default="{ row }">{{
              date(row.start_at)
            }}</template></el-table-column
          ><el-table-column label="结束时间" min-width="190"
            ><template #default="{ row }">{{
              date(row.end_at)
            }}</template></el-table-column
          ><el-table-column label="类型" min-width="180"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.exception_type_code === 'unavailable'
                    ? 'danger'
                    : 'success'
                "
                >{{
                  row.exception_type_code === "unavailable"
                    ? "不可用（请假/停机）"
                    : "临时可用（加班）"
                }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column
            prop="reason"
            label="原因"
            min-width="180"
            show-overflow-tooltip
          /><el-table-column label="状态" width="100"
            ><template #default="{ row }">{{
              row.is_active ? "启用" : "停用"
            }}</template></el-table-column
          ><el-table-column v-if="canManage" label="操作" width="100"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="openException(row as CalendarException)"
                >编辑</el-button
              ></template
            ></el-table-column
          ></el-table
        ></el-card
      >
    </template>
    <el-dialog
      v-model="exceptionVisible"
      title="日历例外"
      width="600px"
      :close-on-click-modal="false"
      ><el-form label-position="top" :disabled="busy"
        ><el-form-item label="类型"
          ><el-select v-model="exceptionForm.exception_type_code"
            ><el-option
              label="不可用：请假、维修、故障等"
              value="unavailable" /><el-option
              label="临时可用：加班等"
              value="extra_available" /></el-select></el-form-item
        ><el-form-item label="开始时间" required
          ><el-date-picker
            v-model="exceptionForm.start_at"
            type="datetime" /></el-form-item
        ><el-form-item label="结束时间" required
          ><el-date-picker
            v-model="exceptionForm.end_at"
            type="datetime" /></el-form-item
        ><el-form-item label="原因" required
          ><el-input
            v-model="exceptionForm.reason"
            type="textarea"
            maxlength="500" /></el-form-item
        ><el-form-item label="启用"
          ><el-switch v-model="exceptionForm.is_active" /></el-form-item
        ><el-alert
          v-if="error"
          type="error"
          :title="error"
          :closable="false" /></el-form
      ><template #footer
        ><el-button :disabled="busy" @click="exceptionVisible = false"
          >取消</el-button
        ><el-button type="primary" :loading="busy" @click="saveException"
          >保存例外</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>
<style scoped>
.resource-calendars :deep(.el-card),
.resource-calendars > :deep(.el-alert) {
  margin-bottom: 20px;
}

.resource-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 0 24px;
}

.resource-fields :deep(.el-select),
.resource-fields :deep(.el-date-editor) {
  width: 100%;
}
</style>
