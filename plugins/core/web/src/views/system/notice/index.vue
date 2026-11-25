<template>
  <ReListPresentation>
  <div class="sys-module sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReListHeading data-list-key="index-0">
        <template #title>公告管理</template>
      </ReListHeading>
      <section class="list-query-panel">
        <div class="filter-panel list-filters">
          <el-form :model="queryForm" label-position="top" class="query-form">
            <div class="filter-row">
              <el-form-item label="标题">
                <el-input
                  v-model="queryForm.title"
                  clearable
                  placeholder="请输入标题"
                />
              </el-form-item>
              <el-form-item label="类型">
                <el-select
                  v-model="queryForm.notice_type_code"
                  placeholder="请选择类型"
                  clearable
                  style="width: 100%"
                >
                  <el-option label="通知" value="notice" />
                  <el-option label="公告" value="announcement" />
                </el-select>
              </el-form-item>
              <el-form-item label="首页显示">
                <el-select
                  v-model="queryForm.is_shown_on_home"
                  placeholder="请选择首页显示状态"
                  clearable
                  style="width: 100%"
                >
                  <el-option label="是" :value="true" />
                  <el-option label="否" :value="false" />
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

        <div class="table-panel list-section">
          <ReListTable
            :list-heading="false"
            list-key="index-0"
            :list-refresh="loadList"
            v-loading="loading"
            :data="tableData"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="title"
              label="标题"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              prop="summary"
              label="摘要"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column
              prop="notice_type_code"
              label="类型"
              width="88"
              align="center"
            >
              <template #default="{ row }">{{
                row.notice_type_code === "announcement" ? "公告" : "通知"
              }}</template>
            </el-table-column>
            <el-table-column
              prop="is_shown_on_home"
              label="首页显示"
              width="96"
              align="center"
            >
              <template #default="{ row }">{{
                row.is_shown_on_home ? "是" : "否"
              }}</template>
            </el-table-column>
            <el-table-column
              label="发送范围"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                targetSummary(row as SystemNoticeRow)
              }}</template>
            </el-table-column>
            <el-table-column label="状态" width="88" align="center">
              <template #default="{ row }">
                <el-tag
                  v-if="row.status_code === 'published'"
                  type="success"
                  size="small"
                  >已发布</el-tag
                >
                <el-tag
                  v-else-if="row.status_code === 'draft'"
                  type="info"
                  size="small"
                  >草稿</el-tag
                >
                <el-tag v-else type="warning" size="small">已下线</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="publisher_name_snapshot"
              label="发布人"
              width="100"
            />
            <el-table-column prop="published_at" label="发布时间" min-width="150">
              <template #default="{ row }">{{
                row.published_at ? formatDt(row.published_at) : "—"
              }}</template>
            </el-table-column>
            <el-table-column
              prop="read_count"
              label="阅读情况"
              width="150"
              align="center"
            >
              <template #default="{ row }">
                <span class="read-stat read-ok"
                  >已读 {{ row.read_count ?? 0 }}</span
                >
                <span class="read-stat read-no"
                  >未读 {{ row.unread_count ?? 0 }}</span
                >
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <span
                  class="action-text primary"
                  @click="openReaders(row as SystemNoticeRow)"
                  >阅读明细</span
                >
                <span
                  class="action-text success"
                  @click="openEdit(row as SystemNoticeRow)"
                  >编辑</span
                >
                <span
                  class="action-text danger"
                  @click="removeRow(row as SystemNoticeRow)"
                  >删除</span
                >
              </template>
            </el-table-column>

            <template #list-actions
              ><div class="header-actions">
                <el-button
                  data-list-action="create"
                  data-action="primary"
                  type="primary"
                  :icon="Plus"
                  @click="openCreate"
                  >新增</el-button
                >
                <el-button
                  data-list-action="import"
                  data-action="import"
                  :icon="Upload"
                  @click="onImport"
                  >导入公告</el-button
                >
                <el-button
                  data-list-action="export"
                  data-action="export"
                  :icon="Download"
                  @click="exportCsv"
                  >导出公告</el-button
                >
              </div></template
            >

            <template #list-pagination
              ><div class="table-footer">

                <ReListPagination
                  v-model:current-page="query.page"
                  v-model:page-size="query.page_size"
                  :total="total"
                  @current-change="loadList" @size-change="handlePageSizeChange" /></div
            ></template>
          </ReListTable>
        </div>
      </section>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑通知公告' : '新增通知公告'"
      width="720px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="256" show-word-limit />
        </el-form-item>
        <el-form-item label="摘要" prop="summary">
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="3"
            placeholder="公告内容，首页显示时展示摘要"
          />
        </el-form-item>
        <el-form-item label="类型" prop="notice_type_code">
          <el-radio-group v-model="form.notice_type_code">
            <el-radio value="notice">通知</el-radio>
            <el-radio value="announcement">公告</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="首页显示">
          <el-switch
            v-model="form.is_shown_on_home"
            active-text="显示"
            inactive-text="不显示"
          />
        </el-form-item>
        <el-form-item label="状态" prop="status_code">
          <el-select v-model="form.status_code" style="width: 100%">
            <el-option label="草稿" value="draft" />
            <el-option label="已发布" value="published" />
            <el-option label="已下线" value="offline" />
          </el-select>
        </el-form-item>
        <el-form-item label="发送范围" prop="target_scope">
          <el-radio-group
            v-model="form.target_scope"
            @change="onTargetScopeChange"
          >
            <el-radio value="all">全部用户</el-radio>
            <el-radio value="role">指定角色</el-radio>
            <el-radio value="user">指定用户</el-radio>
            <el-radio value="mixed">角色+用户</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="form.target_scope === 'role' || form.target_scope === 'mixed'"
          label="接收角色"
          prop="target_role_ids"
        >
          <el-select
            v-model="form.target_role_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :loading="roleLoading"
            placeholder="请选择接收角色"
            style="width: 100%"
            @visible-change="(visible: boolean) => visible && loadRoleOptions()"
          >
            <el-option
              v-for="role in roleOptions"
              :key="role.id"
              :label="`${role.role_name}（${role.role_no}）`"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="form.target_scope === 'user' || form.target_scope === 'mixed'"
          label="接收用户"
          prop="target_user_ids"
        >
          <el-select
            v-model="form.target_user_ids"
            multiple
            filterable
            remote
            reserve-keyword
            collapse-tags
            collapse-tags-tooltip
            :remote-method="searchUserOptions"
            :loading="userLoading"
            placeholder="请输入姓名或账号搜索"
            style="width: 100%"
            @visible-change="(visible: boolean) => visible && loadUserOptions()"
          >
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="user.display_name"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="primary" type="primary" @click="submit">确定</el-button>
        <el-button data-action="neutral" class="btn-cancel" @click="dialogVisible = false"
          >取消</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="readerDialogVisible"
      title="阅读明细"
      width="720px"
      destroy-on-close
    >
      <div class="reader-toolbar">
        <div class="reader-title">{{ readerNoticeTitle }}</div>
        <el-radio-group
          v-model="readerQuery.read_status"
          size="small"
          @change="reloadReaders"
        >
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="read">已读</el-radio-button>
          <el-radio-button value="unread">未读</el-radio-button>
        </el-radio-group>
      </div>
      <ReListTable
        list-key="index-1"
        :list-controls="false"
        :list-refresh="loadReaders"
        v-loading="readerLoading"
        :data="readerRows"
        row-key="user_id"
        height="360"
      >
        <el-table-column
          prop="display_name"
          label="人员"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_read" type="success" size="small">已读</el-tag>
            <el-tag v-else type="info" size="small">未读</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="read_at" label="阅读时间" min-width="150">
          <template #default="{ row }">{{
            row.read_at ? formatDt(row.read_at) : "—"
          }}</template>
        </el-table-column>
      </ReListTable>
      <div class="table-footer">
        <ReListPagination
          v-model:current-page="readerQuery.page"
          :page-size="readerQuery.page_size"
          :total="readerTotal"
          @current-change="loadReaders"
        />
      </div>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { Download, Plus, Upload } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";
import type {
  NoticeReaderRow,
  NoticeReadStatus,
  SystemNoticeRow
} from "@/api/systemNotice";
import {
  createNotice,
  deleteNotice,
  listNoticeReaders,
  listNotices,
  updateNotice
} from "@/api/systemNotice";
import {
  getNoticeTargetOptions,
  type NoticeTargetOptions
} from "@/api/systemNotice";

type RoleOption = NoticeTargetOptions["roles"][number];
type UserOption = NoticeTargetOptions["users"][number];

defineOptions({ name: "NoticeAnnouncement" });

const queryForm = reactive({
  title: "",
  notice_type_code: "" as "" | SystemNoticeRow["notice_type_code"],
  is_shown_on_home: undefined as boolean | undefined
});
const query = reactive({ page: 1, page_size: 20 });
const dialogVisible = ref(false);
const editingId = ref<string | null>(null);
const formRef = ref<FormInstance>();
const loading = ref(false);
const tableData = ref<SystemNoticeRow[]>([]);
const total = ref(0);
const readerDialogVisible = ref(false);
const readerLoading = ref(false);
const readerNoticeId = ref("");
const readerNoticeTitle = ref("");
const readerRows = ref<NoticeReaderRow[]>([]);
const readerTotal = ref(0);
const roleLoading = ref(false);
const userLoading = ref(false);
const roleOptions = ref<RoleOption[]>([]);
const userOptions = ref<UserOption[]>([]);
const readerQuery = reactive({
  page: 1,
  page_size: 10,
  read_status: "all" as NoticeReadStatus
});

const form = reactive({
  title: "",
  summary: "",
  notice_type_code: "notice" as SystemNoticeRow["notice_type_code"],
  is_shown_on_home: true,
  status_code: "draft" as SystemNoticeRow["status_code"],
  target_scope: "all" as SystemNoticeRow["target_scope"],
  target_role_ids: [] as string[],
  target_user_ids: [] as string[]
});

const rules: FormRules = {
  title: [{ required: true, message: "请输入标题", trigger: "blur" }]
};

function formatDt(v: string) {
  return dayjs(v).format("YYYY-M-D HH:mm");
}

function targetSummary(row: SystemNoticeRow) {
  if (!row.target_scope || row.target_scope === "all") return "全部用户";
  const roleNames = (row.target_roles ?? [])
    .map(item => item.role_name)
    .filter(Boolean);
  const userNames = (row.target_users ?? [])
    .map(item => item.display_name)
    .filter(Boolean);
  const parts: string[] = [];
  if (roleNames.length) parts.push(`角色：${roleNames.join("、")}`);
  if (userNames.length) parts.push(`用户：${userNames.join("、")}`);
  return parts.join("；") || "全部用户";
}

async function loadRoleOptions() {
  if (roleLoading.value || roleOptions.value.length) return;
  roleLoading.value = true;
  try {
    const res = await getNoticeTargetOptions();
    roleOptions.value = res.data.roles ?? [];
  } finally {
    roleLoading.value = false;
  }
}

async function loadUserOptions(keyword = "") {
  userLoading.value = true;
  try {
    const res = await getNoticeTargetOptions(keyword.trim());
    const selected = userOptions.value.filter(item =>
      form.target_user_ids.includes(item.id)
    );
    const merged = [...selected, ...(res.data.users ?? [])];
    const seen = new Set<string>();
    userOptions.value = merged.filter(item => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  } finally {
    userLoading.value = false;
  }
}

function searchUserOptions(keyword: string) {
  loadUserOptions(keyword);
}

function onTargetScopeChange() {
  if (form.target_scope === "all") {
    form.target_role_ids = [];
    form.target_user_ids = [];
  } else if (form.target_scope === "role") {
    form.target_user_ids = [];
    loadRoleOptions();
  } else if (form.target_scope === "user") {
    form.target_role_ids = [];
    loadUserOptions();
  } else {
    loadRoleOptions();
    loadUserOptions();
  }
}

async function loadList() {
  loading.value = true;
  try {
    const res = await listNotices({
      page: query.page,
      page_size: query.page_size,
      keyword: queryForm.title.trim() || undefined,
      notice_type_code: queryForm.notice_type_code || undefined,
      is_shown_on_home: queryForm.is_shown_on_home
    });
    tableData.value = res.data.items ?? [];
    total.value = res.data.total ?? 0;
  } finally {
    loading.value = false;
  }
}

async function search() {
  query.page = 1;
  await loadList();
}
async function resetQuery() {
  queryForm.title = "";
  queryForm.notice_type_code = "";
  queryForm.is_shown_on_home = undefined;
  query.page = 1;
  await loadList();
}

async function handlePageSizeChange() {
  query.page = 1;
  await loadList();
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, {
    title: "",
    summary: "",
    notice_type_code: "notice",
    is_shown_on_home: true,
    status_code: "draft",
    target_scope: "all",
    target_role_ids: [],
    target_user_ids: []
  });
  dialogVisible.value = true;
}

function openEdit(row: SystemNoticeRow) {
  editingId.value = row.id;
  form.title = row.title;
  form.summary = row.summary ?? "";
  form.notice_type_code = row.notice_type_code;
  form.is_shown_on_home = row.is_shown_on_home;
  form.status_code = row.status_code;
  form.target_scope = row.target_scope || "all";
  form.target_role_ids = row.target_role_ids?.length
    ? [...row.target_role_ids]
    : (row.target_roles ?? []).map(item => item.id);
  form.target_user_ids = row.target_user_ids?.length
    ? [...row.target_user_ids]
    : (row.target_users ?? []).map(item => item.id);
  if (form.target_scope === "role" || form.target_scope === "mixed") {
    loadRoleOptions();
  }
  if (form.target_scope === "user" || form.target_scope === "mixed") {
    const existingUsers: UserOption[] = (row.target_users ?? []).map(item => ({
      id: item.id,
      display_name: item.display_name
    }));
    userOptions.value = [...existingUsers, ...userOptions.value].filter(
      (item, index, arr) =>
        arr.findIndex(other => other.id === item.id) === index
    );
    loadUserOptions();
  }
  dialogVisible.value = true;
}

async function openReaders(row: SystemNoticeRow) {
  readerNoticeId.value = row.id;
  readerNoticeTitle.value = row.title;
  readerQuery.page = 1;
  readerQuery.read_status = "all";
  readerDialogVisible.value = true;
  await loadReaders();
}

async function reloadReaders() {
  readerQuery.page = 1;
  await loadReaders();
}

async function loadReaders() {
  if (!readerNoticeId.value) return;
  readerLoading.value = true;
  try {
    const res = await listNoticeReaders(readerNoticeId.value, {
      page: readerQuery.page,
      page_size: readerQuery.page_size,
      read_status: readerQuery.read_status
    });
    readerRows.value = res.data.items ?? [];
    readerTotal.value = res.data.total ?? 0;
  } finally {
    readerLoading.value = false;
  }
}

function resetForm() {
  editingId.value = null;
  formRef.value?.clearValidate();
}

async function submit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  if (form.target_scope === "role" && !form.target_role_ids.length) {
    ElMessage.warning("请选择接收角色");
    return;
  }
  if (form.target_scope === "user" && !form.target_user_ids.length) {
    ElMessage.warning("请选择接收用户");
    return;
  }
  if (
    form.target_scope === "mixed" &&
    !form.target_role_ids.length &&
    !form.target_user_ids.length
  ) {
    ElMessage.warning("请选择接收角色或用户");
    return;
  }
  const payload = {
    title: form.title.trim(),
    summary: form.summary.trim() || null,
    notice_type_code: form.notice_type_code,
    is_shown_on_home: form.is_shown_on_home,
    status_code: form.status_code,
    target_scope: form.target_scope,
    target_role_ids:
      form.target_scope === "user" || form.target_scope === "all"
        ? []
        : form.target_role_ids,
    target_user_ids:
      form.target_scope === "role" || form.target_scope === "all"
        ? []
        : form.target_user_ids
  };
  if (editingId.value) {
    await updateNotice(editingId.value, payload);
    ElMessage.success("已保存");
  } else {
    await createNotice(payload);
    ElMessage.success("已新增");
  }
  dialogVisible.value = false;
  await loadList();
}

async function removeRow(row: SystemNoticeRow) {
  await ElMessageBox.confirm(`确定删除「${row.title}」？`, "删除", {
    confirmButtonClass: "app-button-danger",
    type: "warning"
  });
  await deleteNotice(row.id);
  ElMessage.success("已删除");
  await loadList();
}

function onImport() {
  ElMessage.info("导入待接入");
}

function exportCsv() {
  const rows = tableData.value;
  if (!rows.length) {
    ElMessage.warning("暂无可导出数据");
    return;
  }
  const h = ["标题", "摘要", "类型", "首页显示", "状态", "发布人", "发布时间"];
  const lines = rows.map(r =>
    [
      r.title,
      r.summary ?? "",
      r.notice_type_code === "announcement" ? "公告" : "通知",
      r.is_shown_on_home ? "是" : "否",
      r.status_code,
      r.publisher_name_snapshot ?? "",
      r.published_at ? formatDt(r.published_at) : ""
    ]
      .map(c => `"${String(c).replace(/"/g, '""')}"`)
      .join(",")
  );
  const blob = new Blob(["\ufeff" + [h.join(","), ...lines].join("\r\n")], {
    type: "text/csv;charset=utf-8;"
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `通知公告_${dayjs().format("YYYY-MM-DD_HHmm")}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

onMounted(() => {
  loadList();
});
</script>

<style lang="scss">
@use "../system-styles.scss" as *;

.read-stat {
  display: inline-block;
  margin: 0 4px;
  font-size: 12px;
}

.read-ok {
  color: var(--el-color-success);
}

.read-no {
  color: var(--el-color-info);
}

.reader-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.reader-title {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
</style>
