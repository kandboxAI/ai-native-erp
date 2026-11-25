<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute } from "vue-router";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getExceptionCases,
  getExceptionCase,
  getExceptionEvents,
  createExceptionCase,
  actOnException,
  exceptionOrderOptions,
  exceptionSourceOptions,
  exceptionAssignees,
  exceptionStatusLabels as statuses,
  exceptionTypeLabels as types,
  exceptionActionLabels as actions,
  type ExceptionCase,
  type ExceptionEvent,
  type ExceptionAction,
} from "@plugins/mes/web/src/api/mesExceptions";
import type { MesOption } from "@plugins/mes/web/src/api/mes";
import RemoteSelect from "../components/RemoteSelect.vue";
import { formatMesDate } from "../shared";
defineOptions({ name: "MesExceptions" });
const route = useRoute();
const filters = reactive({
  keyword: "",
  status_code: "",
  assigned_to_me: false,
  overdue_only: false,
  work_order_id: String(route.query.work_order_id || ""),
});
const rows = ref<ExceptionCase[]>([]),
  page = ref(1),
  size = ref(20),
  total = ref(0),
  loading = ref(false),
  error = ref("");
const visible = ref(false),
  detail = ref<ExceptionCase>(),
  detailLoading = ref(false),
  detailError = ref("");
const events = ref<ExceptionEvent[]>([]),
  eventPage = ref(1),
  eventTotal = ref(0),
  eventError = ref("");
const createVisible = ref(false),
  saving = ref(false);
const form = reactive({
  work_order_id: "",
  operation_id: "",
  title: "",
  description: "",
  exception_type_code: "material_shortage",
  assigned_user_id: "",
  due_at: new Date(Date.now() + 8 * 3600000),
});
const operations = ref<MesOption[]>([]),
  sourceError = ref("");
const action = ref<ExceptionAction>(),
  actionVisible = ref(false);
const command = reactive({
  note: "",
  assigned_user_id: "",
  due_at: new Date(),
});
let listRequest = 0,
  detailRequest = 0,
  sourceRequest = 0,
  historyRequest = 0,
  lastPayload = "",
  creationKey = "";
const canCreate = computed(
  () => hasPerms("mes:exception:create") && hasPerms("mes:work_order:list"),
);
async function load() {
  const current = ++listRequest;
  loading.value = true;
  error.value = "";
  try {
    const result = await getExceptionCases({
      ...filters,
      page: page.value,
      page_size: size.value,
    });
    if (current === listRequest) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause) {
    if (current === listRequest) {
      rows.value = [];
      total.value = 0;
      error.value = getHttpErrorMessage(cause, "异常列表读取失败");
    }
  } finally {
    if (current === listRequest) loading.value = false;
  }
}
function search() {
  page.value = 1;
  return load();
}
function reset() {
  Object.assign(filters, {
    keyword: "",
    status_code: "",
    assigned_to_me: false,
    overdue_only: false,
    work_order_id: "",
  });
  return search();
}
async function loadHistory() {
  const id = detail.value?.id;
  if (!id) return;
  const current = ++historyRequest;
  eventError.value = "";
  try {
    const result = await getExceptionEvents(id, eventPage.value);
    if (current === historyRequest && detail.value?.id === id) {
      events.value = result.data.items;
      eventTotal.value = result.data.total;
    }
  } catch (cause) {
    if (current === historyRequest) {
      events.value = [];
      eventError.value = getHttpErrorMessage(cause, "处理记录读取失败");
    }
  }
}
async function open(id: string) {
  if (saving.value) return;
  const current = ++detailRequest;
  ++historyRequest;
  visible.value = true;
  detail.value = undefined;
  events.value = [];
  eventTotal.value = 0;
  detailError.value = "";
  detailLoading.value = true;
  try {
    const result = await getExceptionCase(id);
    if (current !== detailRequest) return;
    detail.value = result.data;
    eventPage.value = 1;
    await loadHistory();
  } catch (cause) {
    if (current === detailRequest)
      detailError.value = getHttpErrorMessage(cause, "异常详情读取失败");
  } finally {
    if (current === detailRequest) detailLoading.value = false;
  }
}
function create() {
  if (!canCreate.value || saving.value) return;
  Object.assign(form, {
    work_order_id: "",
    operation_id: "",
    title: "",
    description: "",
    exception_type_code: "material_shortage",
    assigned_user_id: "",
    due_at: new Date(Date.now() + 8 * 3600000),
  });
  operations.value = [];
  sourceError.value = "";
  lastPayload = creationKey = "";
  createVisible.value = true;
}
async function sourceChanged() {
  const id = form.work_order_id,
    current = ++sourceRequest;
  form.operation_id = form.assigned_user_id = "";
  operations.value = [];
  sourceError.value = "";
  if (!id) return;
  try {
    const result = await exceptionSourceOptions(id);
    if (current === sourceRequest && id === form.work_order_id)
      operations.value = result.operations;
  } catch (cause) {
    if (current === sourceRequest)
      sourceError.value = getHttpErrorMessage(
        cause,
        "工序与责任人选项加载失败",
      );
  }
}
watch(() => form.work_order_id, sourceChanged);
async function createOwnerOptions(keyword: string) {
  if (!form.work_order_id) return [];
  return (await exceptionSourceOptions(form.work_order_id, keyword)).users;
}
function notice(row: ExceptionCase) {
  if (row.notification_warning)
    message("保存成功；通知未发送，请检查通知场景及接收人配置", {
      type: "warning",
    });
  else message("已保存", { type: "success" });
}
async function submitCreate() {
  if (saving.value) return;
  try {
    if (!form.work_order_id || !form.title.trim() || !form.description.trim())
      throw Error("请选择工单并填写异常标题和现象");
    if (
      !form.due_at ||
      !Number.isFinite(+new Date(form.due_at)) ||
      +new Date(form.due_at) <= Date.now()
    )
      throw Error("请选择晚于当前时间的处理期限");
    const payload = {
      work_order_id: form.work_order_id,
      operation_id: form.operation_id || null,
      title: form.title.trim(),
      description: form.description.trim(),
      exception_type_code: form.exception_type_code,
      assigned_user_id: form.assigned_user_id || null,
      due_at: new Date(form.due_at).toISOString(),
    };
    const fingerprint = JSON.stringify(payload);
    if (fingerprint !== lastPayload || !creationKey) {
      lastPayload = fingerprint;
      creationKey = crypto.randomUUID();
    }
    saving.value = true;
    const result = await createExceptionCase({
      ...payload,
      idempotency_key: creationKey,
    });
    notice(result.data);
    createVisible.value = false;
    await load();
    saving.value = false;
    await open(result.data.id);
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "异常登记失败"));
  } finally {
    saving.value = false;
  }
}
function beginAction(value: ExceptionAction) {
  if (!detail.value?.allowed_actions.includes(value) || saving.value) return;
  action.value = value;
  command.note = "";
  command.assigned_user_id = detail.value.assigned_user_id || "";
  command.due_at = new Date(detail.value.due_at);
  actionVisible.value = true;
}
async function ownerOptions(keyword: string) {
  return detail.value ? exceptionAssignees(detail.value.id, keyword) : [];
}
async function submitAction() {
  if (saving.value || !detail.value || !action.value) return;
  try {
    if (!["start", "approve"].includes(action.value) && !command.note.trim())
      throw Error("请填写处理说明或结果");
    if (action.value === "assign" && !command.assigned_user_id)
      throw Error("请选择责任人");
    const extra =
      action.value === "assign"
        ? {
            assigned_user_id: command.assigned_user_id,
            due_at: new Date(command.due_at).toISOString(),
          }
        : {};
    saving.value = true;
    const result = await actOnException(detail.value.id, action.value, {
      version_no: detail.value.version_no,
      note: command.note.trim(),
      ...extra,
    });
    detail.value = result.data;
    notice(result.data);
    actionVisible.value = false;
    eventPage.value = 1;
    await Promise.all([load(), loadHistory()]);
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "异常处理失败，必要时刷新详情后重试"));
  } finally {
    saving.value = false;
  }
}
watch(
  () => route.query.work_order_id,
  (value) => {
    filters.work_order_id = String(value || "");
    search();
  },
);
watch(
  () => route.query.case_id,
  (value) => {
    if (value) open(String(value));
  },
);
onMounted(() => {
  load();
  if (route.query.case_id) open(String(route.query.case_id));
});
onBeforeUnmount(() => {
  ++listRequest;
  ++detailRequest;
  ++sourceRequest;
  ++historyRequest;
});
</script>
<template>
  <div class="mes-page">
    <div class="heading">
      <div>
        <h2>异常处理</h2>
        <p>登记、指派、处理和复核制造异常，保留全过程记录。</p>
      </div>
      <el-button v-if="canCreate" type="primary" @click="create"
        >登记异常</el-button
      >
    </div>
    <el-card shadow="never"
      ><el-form inline @submit.prevent="search">
        <el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            clearable
            placeholder="异常单 / 标题 / 工单"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-select
            v-model="filters.status_code"
            clearable
            style="width: 140px"
            ><el-option
              v-for="(label, key) in statuses"
              :key="key"
              :value="key"
              :label="label" /></el-select
        ></el-form-item>
        <el-form-item
          ><el-checkbox v-model="filters.assigned_to_me">我负责的</el-checkbox
          ><el-checkbox v-model="filters.overdue_only"
            >仅超时</el-checkbox
          ></el-form-item
        >
        <el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        >
      </el-form>
      <el-alert
        v-if="filters.work_order_id"
        title="当前仅查看所选工单的异常，点击重置可恢复全部授权范围。"
        type="info"
        :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false"
        ><template #default
          ><el-button link @click="load">重新加载</el-button></template
        ></el-alert
      >
      <el-table v-loading="loading" :data="rows" row-key="id"
        ><el-table-column prop="case_no" label="异常单" min-width="210"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="open(row.id)">{{
              row.case_no
            }}</el-button>
            <div>{{ row.work_order_no }}</div></template
          ></el-table-column
        >
        <el-table-column
          prop="title"
          label="异常"
          min-width="230"
          show-overflow-tooltip
          ><template #default="{ row }"
            ><div>{{ row.title }}</div>
            <small>{{
              types[row.exception_type_code] || row.exception_type_code
            }}</small></template
          ></el-table-column
        >
        <el-table-column label="状态" width="130"
          ><template #default="{ row }"
            ><el-tag
              :type="
                row.status_code === 'closed'
                  ? 'success'
                  : row.is_overdue
                    ? 'danger'
                    : 'warning'
              "
              >{{ statuses[(row as ExceptionCase).status_code] }}</el-tag
            >
            <div v-if="row.is_overdue" class="danger">已超时</div></template
          ></el-table-column
        >
        <el-table-column label="责任人 / 提出人" min-width="150"
          ><template #default="{ row }"
            ><div>{{ row.assigned_user_name || "待指派" }}</div>
            <small>提出：{{ row.reporter_name || "—" }}</small></template
          ></el-table-column
        >
        <el-table-column label="处理期限" min-width="175"
          ><template #default="{ row }">{{
            formatMesDate(row.due_at)
          }}</template></el-table-column
        >
        <el-table-column label="操作" width="100"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="open(row.id)"
              >查看 / 办理</el-button
            ></template
          ></el-table-column
        > </el-table
      ><ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total,sizes,prev,pager,next"
        class="pagination"
        @current-change="load"
        @size-change="search"
    /></el-card>
    <el-drawer
      v-model="visible"
      title="异常详情与处理"
      size="min(850px, 96vw)"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <div v-loading="detailLoading">
        <el-alert
          v-if="detailError"
          :title="detailError"
          type="error"
          :closable="false"
        />
        <template v-if="detail"
          ><div class="heading">
            <h3>{{ detail.case_no }} · {{ detail.title }}</h3>
            <el-button :disabled="saving" @click="open(detail.id)"
              >刷新详情</el-button
            >
          </div>
          <el-descriptions :column="2" border
            ><el-descriptions-item label="来源工单">{{
              detail.work_order_no
            }}</el-descriptions-item
            ><el-descriptions-item label="来源工序">{{
              detail.operation_name ||
              (detail.operation_id ? "原工序已不可用" : "整张工单")
            }}</el-descriptions-item
            ><el-descriptions-item label="异常类型">{{
              types[detail.exception_type_code]
            }}</el-descriptions-item
            ><el-descriptions-item label="状态"
              >{{ statuses[detail.status_code] }}
              {{ detail.is_overdue ? " · 已超时" : "" }}</el-descriptions-item
            ><el-descriptions-item label="责任人">{{
              detail.assigned_user_name || "待指派"
            }}</el-descriptions-item
            ><el-descriptions-item label="处理期限">{{
              formatMesDate(detail.due_at)
            }}</el-descriptions-item
            ><el-descriptions-item label="提出人">{{
              detail.reporter_name || "—"
            }}</el-descriptions-item></el-descriptions
          >
          <h4>异常现象</h4>
          <p class="notes">{{ detail.description }}</p>
          <div class="actions">
            <el-button
              v-for="value in detail.allowed_actions"
              :key="value"
              :disabled="saving"
              :type="value === 'approve' ? 'success' : 'primary'"
              @click="beginAction(value)"
              >{{ actions[value] }}</el-button
            >
          </div>
          <p class="muted">
            责任人提交结果后需由另一名有复核权限的人员确认关闭；关闭异常不会自动恢复生产或放行检验。
          </p>
          <h4>处理记录</h4>
          <el-alert
            v-if="eventError"
            :title="eventError"
            type="error"
            :closable="false"
            ><template #default
              ><el-button link @click="loadHistory">重试</el-button></template
            ></el-alert
          >
          <el-timeline
            ><el-timeline-item
              v-for="item in events"
              :key="item.id"
              :timestamp="formatMesDate(item.created_at)"
              ><strong
                >{{ actions[item.action_code] || item.action_code }} ·
                {{ item.actor_name || "—" }}</strong
              >
              <div>
                {{ statuses[item.to_status_code as keyof typeof statuses] }}
              </div>
              <p class="notes">{{ item.note }}</p>
              <small
                >当时责任人：{{ item.assigned_user_name || "待指派" }} ·
                当时期限：{{ formatMesDate(item.due_at_snapshot) }}</small
              ></el-timeline-item
            ></el-timeline
          >
          <ListPagination
            v-model:current-page="eventPage"
            :total="eventTotal"
            :page-size="20"
            layout="total,prev,pager,next"
            @current-change="loadHistory"
          />
        </template>
      </div>
    </el-drawer>
    <el-dialog
      v-model="createVisible"
      title="登记制造异常"
      width="660px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-alert
        v-if="sourceError"
        :title="sourceError"
        type="error"
        :closable="false"
      />
      <el-form label-position="top" :disabled="saving"
        ><el-form-item label="来源工单" required
          ><RemoteSelect
            v-model="form.work_order_id"
            :load-options="exceptionOrderOptions"
            placeholder="按工单号或产品查找"
            :disabled="saving"
        /></el-form-item>
        <el-form-item label="来源工序（可选）"
          ><el-select
            v-model="form.operation_id"
            clearable
            :disabled="!form.work_order_id"
            ><el-option
              v-for="item in operations"
              :key="item.value"
              :value="item.value"
              :label="item.label" /></el-select
        ></el-form-item>
        <el-form-item label="异常类型" required
          ><el-select v-model="form.exception_type_code"
            ><el-option
              v-for="(label, key) in types"
              :key="key"
              :value="key"
              :label="label" /></el-select
        ></el-form-item>
        <el-form-item label="标题" required
          ><el-input v-model="form.title" maxlength="128"
        /></el-form-item>
        <el-form-item label="异常现象" required
          ><el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="4000"
            placeholder="说明现象、影响与需要协助的事项"
        /></el-form-item>
        <el-form-item label="责任人（可稍后指派）"
          ><RemoteSelect
            v-model="form.assigned_user_id"
            :context-key="form.work_order_id"
            :load-options="createOwnerOptions"
            :disabled="!form.work_order_id || saving"
            placeholder="选择本组织责任人"
        /></el-form-item>
        <el-form-item label="处理期限" required
          ><el-date-picker
            v-model="form.due_at"
            type="datetime"
            placeholder="要求处理或复核完成的时间"
        /></el-form-item> </el-form
      ><template #footer
        ><el-button :disabled="saving" @click="createVisible = false"
          >取消</el-button
        ><el-button type="primary" :loading="saving" @click="submitCreate"
          >登记</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="actionVisible"
      :title="action ? actions[action] : '处理异常'"
      width="580px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-form label-position="top" :disabled="saving"
        ><template v-if="action === 'assign'"
          ><el-form-item label="责任人" required
            ><RemoteSelect
              v-model="command.assigned_user_id"
              :context-key="detail?.id"
              :initial-option="
                detail?.assigned_user_id
                  ? {
                      value: detail.assigned_user_id,
                      label: detail.assigned_user_name || '当前责任人',
                    }
                  : undefined
              "
              :load-options="ownerOptions"
              placeholder="选择本组织责任人"
              :disabled="saving" /></el-form-item
          ><el-form-item label="新的处理期限" required
            ><el-date-picker
              v-model="command.due_at"
              type="datetime" /></el-form-item
        ></template>
        <el-form-item
          :label="action === 'resolve' ? '处理结果' : '处理说明'"
          :required="action !== 'start' && action !== 'approve'"
          ><el-input
            v-model="command.note"
            type="textarea"
            :rows="4"
            maxlength="4000"
            placeholder="记录已处理的事项、验证结果或退回原因"
        /></el-form-item> </el-form
      ><template #footer
        ><el-button :disabled="saving" @click="actionVisible = false"
          >取消</el-button
        ><el-button type="primary" :loading="saving" @click="submitAction"
          >确认{{ action ? actions[action] : "" }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.mes-page {
  padding: 20px;
}

.heading,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

h2 {
  margin: 0 0 8px;
}

h3 {
  margin: 0;
}

.heading p,
.muted,
small {
  color: var(--el-text-color-secondary);
}

.actions {
  justify-content: flex-start;
  margin-top: 20px;
}

.actions .el-button {
  margin-left: 0;
}

.notes {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.danger {
  color: var(--el-color-danger);
}

.pagination {
  justify-content: flex-end;
  margin-top: 18px;
}

h4 {
  margin-top: 24px;
}

.muted {
  font-size: 12px;
  line-height: 1.7;
}
</style>
