<template>
  <ReListPresentation>
  <div class="sys-module sys-page list-page list-presentation-container">
    <el-alert
      v-if="!hasPerms('workflow_task:list')"
      type="error"
      :closable="false"
      title="没有查看审批任务的权限"
    />
    <section class="list-section" v-else>
      <ReMenuViews
        v-model="activeTab"
        class="workflow-tabs list-tabs"
        @tab-change="handleTabChange"
      >
        <el-tab-pane label="待我审批" name="approval" />
        <el-tab-pane label="抄送我的" name="cc" />
      </ReMenuViews>

      <ReListHeading
        v-if="activeTab === 'approval'"
        title="待我审批"
        data-list-key="index-0"
      >
      </ReListHeading>
      <ReListHeading v-else title="抄送我的" data-list-key="index-1">
      </ReListHeading>

      <section class="list-query-panel">
        <div class="filter-panel list-filters">
          <el-form label-position="top" class="query-form">
            <div class="filter-row">
              <el-form-item label="业务类型">
                <el-select
                  v-model="queryForm.business_type_code"
                  clearable
                  placeholder="请选择业务类型"
                  style="width: 100%"
                >
                  <el-option
                    v-for="opt in businessTypeOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="queryForm.status_code" style="width: 100%">
                  <template v-if="activeTab === 'approval'">
                    <el-option label="待办" value="pending" />
                    <el-option label="已办" value="completed" />
                  </template>
                  <template v-else>
                    <el-option label="未读" value="unread" />
                    <el-option label="已读" value="read" />
                  </template>
                </el-select>
              </el-form-item>
              <div class="query-actions">
                <el-button
                  data-list-query="search"
                  class="search-btn"
                  @click="search"
                  >搜索</el-button
                >
                <el-button
                  data-list-query="reset"
                  class="reset-btn"
                  @click="resetQuery"
                  >重置</el-button
                >
              </div>
            </div>
          </el-form>
        </div>

        <div v-if="activeTab === 'approval'" class="table-panel list-section">
          <ReListTable
            list-key="index-0"
            :list-heading="false"
            :list-refresh="loadList"
            v-loading="loading"
            :data="taskData"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="business_summary"
              label="业务摘要"
              min-width="200"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span class="approval-subject">
                  <el-avatar v-if="row.business_avatar_url" :src="row.business_avatar_url" :size="36" />
                  <span>{{ row.business_summary }}</span>
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="task_name" label="节点" min-width="120">
              <template #default="{ row }">{{
                row.task_name || row.task_key
              }}</template>
            </el-table-column>
            <el-table-column prop="business_type_code" label="业务" width="100">
              <template #default="{ row }">
                {{ businessTypeLabel(row.business_type_code) }}
              </template>
            </el-table-column>
            <el-table-column label="审批方式" width="120" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="row.approval_mode_code === 'all' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ approvalModeLabel(row as WorkflowTaskRow) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="arrived_at" label="到达时间" min-width="150">
              <template #default="{ row }">{{
                formatDt(row.arrived_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="hasPerms('workflow_task:detail')"
                  link
                  type="primary"
                  data-action="view"
                  @click="openTaskDetail(row as WorkflowTaskRow)"
                  >详情</el-button
                >
                <el-button
                  v-if="canAct(row as WorkflowTaskRow)"
                  link
                  type="success"
                  data-action="success"
                  @click="handleComplete(row as WorkflowTaskRow)"
                  >同意</el-button
                >
                <el-button
                  v-if="canAct(row as WorkflowTaskRow)"
                  link
                  type="warning"
                  data-action="warning"
                  @click="handleReject(row as WorkflowTaskRow)"
                  >驳回</el-button
                >
              </template>
            </el-table-column>

            <template #list-pagination
              ><div class="table-footer">
                <ReListPagination
                  v-model:current-page="query.page"
                  v-model:page-size="query.page_size"
                  :total="total"
                  @current-change="loadList"
                /></div
            ></template>
          </ReListTable>
        </div>

        <div v-else class="table-panel list-section">
          <ReListTable
            list-key="index-1"
            :list-heading="false"
            :list-refresh="loadList"
            v-loading="loading"
            :data="ccData"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="business_summary"
              label="业务摘要"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column prop="task_name" label="抄送节点" min-width="120">
              <template #default="{ row }">{{
                row.task_name || row.task_key || "—"
              }}</template>
            </el-table-column>
            <el-table-column prop="business_type_code" label="业务" width="100">
              <template #default="{ row }">
                {{ businessTypeLabel(row.business_type_code) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="status_code"
              label="状态"
              width="88"
              align="center"
            >
              <template #default="{ row }">
                <el-tag
                  :type="row.status_code === 'unread' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ row.status_code === "unread" ? "未读" : "已读" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="抄送时间" min-width="150">
              <template #default="{ row }">{{
                formatDt(row.created_at)
              }}</template>
            </el-table-column>
            <el-table-column prop="read_at" label="阅读时间" min-width="150">
              <template #default="{ row }">{{ formatDt(row.read_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  data-action="view"
                  @click="openCcDetail(row as WorkflowCcRow)"
                  >详情</el-button
                >
                <el-button
                  v-if="row.status_code === 'unread'"
                  link
                  type="success"
                  data-action="success"
                  @click="handleCcRead(row as WorkflowCcRow)"
                >
                  标记已读
                </el-button>
              </template>
            </el-table-column>

            <template #list-pagination
              ><div class="table-footer">
                <ReListPagination
                  v-model:current-page="query.page"
                  v-model:page-size="query.page_size"
                  :total="total"
                  @current-change="loadList"
                /></div
            ></template>
          </ReListTable>
        </div>
      </section>
    </section>

    <WorkflowTaskDialog
      v-model="taskDetailVisible"
      :task-id="activeTaskId"
      :fallback-task="activeTask"
      secondary-action-label="在业务页中打开"
      @secondary="goTaskBusinessPage"
      @success="loadList"
      @closed="clearLinkedTask"
    />

    <el-dialog
      v-model="ccDetailVisible"
      title="抄送详情"
      width="720px"
      destroy-on-close
      class="cc-detail-dialog"
    >
      <div v-loading="ccDetailLoading">
        <template v-if="ccDetail">
          <div class="detail-section">
            <div class="detail-section-title">流程信息</div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="业务类型">
                {{ businessTypeLabel(ccDetail.business_type_code) }}
              </el-descriptions-item>
              <el-descriptions-item label="抄送节点">
                {{ ccDetail.task_name || ccDetail.task_key || "—" }}
              </el-descriptions-item>
              <el-descriptions-item label="抄送时间">
                {{ formatDt(ccDetail.created_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="阅读状态">
                {{ ccDetail.status_code === "unread" ? "未读" : "已读" }}
              </el-descriptions-item>
              <el-descriptions-item :span="2" label="业务摘要">
                {{ ccDetail.business_summary || "—" }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <WorkflowApprovalProgress
            class="detail-section"
            :items="ccDetail.timeline ?? []"
          />

          <div
            v-if="ccDetail.business_detail?.fields?.length"
            class="detail-section"
          >
            <div class="detail-section-title">业务详情</div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="field in ccDetail.business_detail.fields"
                :key="field.label"
                :label="field.label"
                :span="
                  ['markdown', 'markdown_diff'].includes(field.type) ? 2 : 1
                "
              >
                <el-avatar
                  v-if="field.type === 'avatar'"
                  :size="56"
                  :src="field.value || undefined"
                />
                <el-image
                  v-else-if="field.type === 'image' && field.value"
                  :src="field.value"
                  :preview-src-list="[field.value]"
                  fit="cover"
                  class="field-photo"
                />
                <MarkdownComparison
                  v-else-if="field.type === 'markdown_diff'"
                  :old-content="field.old_value ?? null"
                  :new-content="field.value"
                  :old-label="field.old_label"
                  :new-label="field.label"
                  :unavailable-reason="field.unavailable_reason"
                />
                <MarkdownPreview
                  v-else-if="field.type === 'markdown'"
                  :content="field.value || ''"
                />
                <span v-else>{{ displayValue(field.value) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div v-if="ccDetail.business_detail?.contract" class="detail-section">
            <WorkflowContractPreview
              :contract="ccDetail.business_detail.contract"
            />
          </div>

          <div
            v-for="(table, idx) in ccDetail.business_detail?.tables ?? []"
            :key="idx"
            class="detail-section"
          >
            <div class="detail-section-title">{{ table.title }}</div>
            <ReListTable
              list-key="index-2"
              :list-controls="false"
              :data="table.rows"
              border
              size="small"
              max-height="240"
            >
              <el-table-column
                v-for="col in table.columns"
                :key="col.prop"
                :prop="col.prop"
                :label="col.label"
                min-width="88"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ displayValue(row[col.prop]) }}
                </template>
              </el-table-column>
            </ReListTable>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button data-action="neutral" @click="ccDetailVisible = false">关闭</el-button>
        <el-button
          data-action="success"
          v-if="ccDetail?.status_code === 'unread'"
          type="primary"
          @click="handleCcReadFromDetail"
        >
          标记已读
        </el-button>
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { useMenuView } from "@/utils/menuView";
import { onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { isWorkflowActionTimeout, workflowActionErrorMessage } from "@/utils/workflowAction";
import {
  completeWorkflowTask,
  getWorkflowCcDetail,
  listWorkflowCcRecords,
  listWorkflowTasks,
  listWorkflowTaskBusinessTypes,
  type WorkflowTaskBusinessTypeOption,
  markWorkflowCcRead,
  rejectWorkflowTask,
  type WorkflowCcDetail,
  type WorkflowCcRow,
  type WorkflowTaskRow
} from "@/api/workflowTask";
import WorkflowTaskDialog from "@/layout/components/lay-notice/components/WorkflowTaskDialog.vue";
import WorkflowApprovalProgress from "@/components/workflow/WorkflowApprovalProgress.vue";
import WorkflowContractPreview from "@/components/workflow/WorkflowContractPreview.vue";
import MarkdownPreview from "@/components/MarkdownPreview/index.vue";
import MarkdownComparison from "@/components/MarkdownComparison/index.vue";
import { emitter } from "@/utils/mitt";
import { buildWorkflowBusinessRoute } from "@/utils/workflowBusinessRoute";

defineOptions({ name: "WorkflowTask" });

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const activeTab = useMenuView("approval", ["approval","cc"]);
const taskData = ref<WorkflowTaskRow[]>([]);
const actingTasks = reactive(new Set<string>());
const ccData = ref<WorkflowCcRow[]>([]);
const taskDetailVisible = ref(false);
const activeTaskId = ref<string | null>(null);
const activeTask = ref<WorkflowTaskRow | null>(null);
const ccDetailVisible = ref(false);
const ccDetailLoading = ref(false);
const ccDetail = ref<WorkflowCcDetail | null>(null);
const total = ref(0);
const query = reactive({ page: 1, page_size: 20 });
const queryForm = reactive({
  business_type_code: "" as string | undefined,
  status_code: defaultStatus()
});
const businessTypeOptions = ref<WorkflowTaskBusinessTypeOption[]>([]);

function businessTypeLabel(value: string) {
  return (
    businessTypeOptions.value.find(opt => opt.value === value)?.label ?? value
  );
}

/** 待我办理：待处理且尚未投票（会签时已投票的待办不会出现在“待办”中） */
function canAct(row: WorkflowTaskRow) {
  return (
    hasPerms("workflow_task:complete") &&
    !actingTasks.has(row.id) &&
    queryForm.status_code === "pending" &&
    row.status_code === "pending"
  );
}

function approvalModeLabel(row: WorkflowTaskRow) {
  if (row.approval_mode_code === "all") {
    return `会签 ${row.approved_count}/${row.required_count}`;
  }
  if (row.approval_mode_code === "any") return "或签";
  return "单人审批";
}

async function loadBusinessTypeOptions() {
  const res = await listWorkflowTaskBusinessTypes();
  if (res.code !== 0) throw new Error(res.message || "加载业务类型失败");
  businessTypeOptions.value = res.data ?? [];
}

function formatDt(v: string | null) {
  if (!v) return "—";
  return v.replace("T", " ").slice(0, 19);
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

let listRequest = 0;
async function loadList() {
  const request = ++listRequest;
  const tab = activeTab.value;
  taskData.value = [];
  ccData.value = [];
  total.value = 0;
  if (!hasPerms("workflow_task:list")) return;
  loading.value = true;
  try {
    const params = {
      page: query.page,
      page_size: query.page_size,
      status_code: queryForm.status_code,
      business_type_code: queryForm.business_type_code || undefined
    };
    const res =
      tab === "approval"
        ? await listWorkflowTasks(params)
        : await listWorkflowCcRecords(params);
    if (res.code !== 0) throw new Error(res.message);
    if (request !== listRequest) return;
    if (tab === "approval") {
      taskData.value = res.data.items as WorkflowTaskRow[];
    } else {
      ccData.value = res.data.items as WorkflowCcRow[];
    }
    total.value = res.data.total;
  } catch (e: unknown) {
    if (request === listRequest)
      ElMessage.error(getHttpErrorMessage(e, "加载失败"));
  } finally {
    if (request === listRequest) loading.value = false;
  }
}

function search() {
  query.page = 1;
  loadList();
}

function defaultStatus() {
  return activeTab.value === "approval" ? "pending" : "unread";
}

function resetQuery() {
  queryForm.business_type_code = undefined;
  queryForm.status_code = defaultStatus();
  search();
}

function handleTabChange() {
  query.page = 1;
  queryForm.status_code = defaultStatus();
  loadList();
}

function openTaskDetail(row: WorkflowTaskRow) {
  if (!hasPerms("workflow_task:detail")) return;
  activeTaskId.value = row.id;
  activeTask.value = row;
  taskDetailVisible.value = true;
}

watch(
  () =>
    ["/system/workflow-task/index", "/system/workflow-task/approval"].includes(
      route.path
    )
      ? route.query.task_id
      : null,
  taskId => {
    if (!hasPerms("workflow_task:detail") || typeof taskId !== "string") return;
    activeTask.value = null;
    activeTaskId.value = taskId;
    taskDetailVisible.value = true;
  },
  { immediate: true }
);

function clearLinkedTask() {
  if (!route.query.task_id || route.query.task_id !== activeTaskId.value) return;
  // 布局按 fullPath 挂载页面，提前清理参数会卸载正在打开的详情。
  const query = { ...route.query };
  delete query.task_id;
  void router.replace({ path: route.path, query });
}

function goTaskBusinessPage(
  query?: Record<string, string>,
  task = activeTask.value
) {
  const target = buildWorkflowBusinessRoute(
    task?.business_type_code,
    task?.business_id,
    query
  );
  if (!target) {
    ElMessage.info("该待办暂无对应业务页面");
    return;
  }
  taskDetailVisible.value = false;
  router.push(target).catch(() => {});
}

async function handleComplete(row: WorkflowTaskRow) {
  if (!canAct(row)) return;
  const { value } = await ElMessageBox.prompt("审批意见（可选）", "同意", {
    confirmButtonClass: "app-button-success",
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    inputType: "textarea"
  }).catch(() => ({ value: null }));
  if (value === null) return;
  if (actingTasks.has(row.id)) return;
  actingTasks.add(row.id);
  try {
    const res = await completeWorkflowTask(row.id, value || undefined);
    if (res.code !== 0) throw new Error(res.message);
    emitter.emit("workflowBusinessChanged", {
      business_type: row.business_type_code,
      business_id: row.business_id,
      instance_status:
        typeof res.data?.instance_status_code === "string"
          ? res.data.instance_status_code
          : undefined
    });
    ElMessage.success("已同意");
    loadList();
  } catch (e: unknown) {
    ElMessage.error(workflowActionErrorMessage(e));
    if (isWorkflowActionTimeout(e)) await loadList();
  } finally {
    actingTasks.delete(row.id);
  }
}

async function handleReject(row: WorkflowTaskRow) {
  if (!canAct(row)) return;
  const { value } = await ElMessageBox.prompt("请填写驳回原因", "驳回", {
    confirmButtonClass: "app-button-warning",
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    inputType: "textarea",
    inputValidator: value =>
      Boolean(String(value || "").trim()) || "驳回原因不能为空"
  }).catch(() => ({ value: null }));
  if (value === null) return;
  if (actingTasks.has(row.id)) return;
  actingTasks.add(row.id);
  try {
    const res = await rejectWorkflowTask(row.id, value || undefined);
    if (res.code !== 0) throw new Error(res.message);
    emitter.emit("workflowBusinessChanged", {
      business_type: row.business_type_code,
      business_id: row.business_id,
      instance_status:
        typeof res.data?.instance_status_code === "string"
          ? res.data.instance_status_code
          : undefined
    });
    ElMessage.success("已驳回");
    loadList();
  } catch (e: unknown) {
    ElMessage.error(workflowActionErrorMessage(e));
    if (isWorkflowActionTimeout(e)) await loadList();
  } finally {
    actingTasks.delete(row.id);
  }
}

async function openCcDetail(row: WorkflowCcRow) {
  ccDetailVisible.value = true;
  ccDetail.value = null;
  ccDetailLoading.value = true;
  try {
    const res = await getWorkflowCcDetail(row.id);
    if (res.code !== 0) throw new Error(res.message);
    ccDetail.value = res.data;
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "加载详情失败");
    ccDetailVisible.value = false;
  } finally {
    ccDetailLoading.value = false;
  }
}

async function handleCcRead(row: WorkflowCcRow) {
  try {
    const res = await markWorkflowCcRead(row.id);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已标记为已读");
    loadList();
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}

async function handleCcReadFromDetail() {
  if (!ccDetail.value) return;
  try {
    const res = await markWorkflowCcRead(ccDetail.value.id);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已标记为已读");
    ccDetail.value = { ...ccDetail.value, status_code: "read" };
    loadList();
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}

onMounted(async () => {
  if (!hasPerms("workflow_task:list")) return;
  await Promise.all([
    loadBusinessTypeOptions().catch((e: unknown) => {
      ElMessage.warning(e instanceof Error ? e.message : "业务类型加载失败");
    }),
    loadList()
  ]);
});
</script>

<style lang="scss">
@use "../system-styles.scss" as *;

.approval-subject { display: flex; align-items: center; gap: 10px; }
.approval-subject .el-avatar { flex-shrink: 0; }

.muted {
  color: var(--el-text-color-placeholder);
}

.detail-section + .detail-section {
  margin-top: 16px;
}

.detail-section-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.field-photo {
  width: 40px;
  height: 40px;
  border-radius: 6px;
}
</style>
