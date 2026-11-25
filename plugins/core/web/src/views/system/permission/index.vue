<template>
  <ReListPresentation>
  <div class="sys-module sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReListHeading data-list-key="index-0">
        <template #title>权限管理</template>
      </ReListHeading>
      <section class="list-query-panel">
        <div class="filter-panel list-filters">
          <el-form :model="queryForm" label-position="top" class="query-form">
            <div class="filter-row">
              <el-form-item label="关键词">
                <el-input
                  v-model="queryForm.keyword"
                  clearable
                  placeholder="请输入标识 / 名称 / 模块"
                  @keyup.enter="search"
                />
              </el-form-item>
              <el-form-item label="权限标识">
                <el-input
                  v-model="queryForm.permission_key"
                  clearable
                  placeholder="请输入权限标识"
                />
              </el-form-item>
              <el-form-item label="所属模块">
                <el-select
                  v-model="queryForm.module_code"
                  clearable
                  placeholder="请选择所属模块"
                  style="width: 100%"
                >
                  <el-option
                    v-for="(label, code) in PERMISSION_MODULE_LABELS"
                    :key="code"
                    :label="label"
                    :value="code"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="状态">
                <el-select
                  v-model="queryForm.is_active"
                  clearable
                  placeholder="请选择状态"
                  style="width: 100%"
                >
                  <el-option label="启用" :value="true" />
                  <el-option label="停用" :value="false" />
                </el-select>
              </el-form-item>
              <el-form-item label="排序">
                <el-select v-model="queryForm.sort_by" style="width: 100%">
                  <el-option label="权限标识" value="permission_key" />
                  <el-option label="所属模块" value="module_code" />
                  <el-option label="已分配角色数" value="role_count" />
                  <el-option label="更新时间" value="updated_at" />
                </el-select>
              </el-form-item>
              <el-form-item label="顺序">
                <el-select v-model="queryForm.sort_order" style="width: 100%">
                  <el-option label="升序" value="asc" />
                  <el-option label="降序" value="desc" />
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
            :list-refresh="loadPermissions"
            v-loading="loading"
            :data="tableData"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="permission_key"
              label="权限标识"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column
              prop="permission_name"
              label="权限名称"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column prop="module_code" label="所属模块" min-width="120">
              <template #default="{ row }">
                {{ formatPermissionModuleLabel(row.module_code) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="is_active"
              label="状态"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="role_count"
              label="已分配角色"
              width="110"
              align="center"
            >
              <template #default="{ row }">{{ row.role_count }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="160">
              <template #default="{ row }">{{
                formatDt(row.updated_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <span
                  class="action-text primary"
                  @click="openView(row as SystemPermissionListRow)"
                  >查看</span
                >
                <span
                  class="action-text success"
                  @click="openEdit(row as SystemPermissionListRow)"
                  >编辑</span
                >
                <span
                  class="action-text danger"
                  @click="toggleActive(row as SystemPermissionListRow)"
                  >{{ row.is_active ? "停用" : "启用" }}</span
                >
              </template>
            </el-table-column>

            <template #list-pagination
              ><div class="table-footer">
                <ReListPagination
                  v-model:current-page="query.page"
                  v-model:page-size="query.page_size"
                  :total="total"
                  @current-change="loadPermissions"
                  @size-change="handlePageSizeChange"
                /></div
            ></template>
          </ReListTable>
        </div>
      </section>
    </section>

    <el-dialog
      v-model="formVisible"
      title="编辑权限"
      width="520px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
      >
        <el-form-item label="权限标识">
          <el-input v-model="form.permission_key" disabled />
        </el-form-item>
        <el-form-item label="权限名称" prop="permission_name">
          <el-input
            v-model="form.permission_name"
            maxlength="128"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="是否启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="primary" type="primary" :loading="submitting" @click="submitForm"
          >确定</el-button
        >
        <el-button data-action="neutral" @click="formVisible = false">取消</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="detailVisible"
      title="权限详情"
      width="560px"
      destroy-on-close
    >
      <el-skeleton v-if="detailLoading" :rows="5" animated />
      <template v-else-if="detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="权限标识">{{
            detail.permission_key
          }}</el-descriptions-item>
          <el-descriptions-item label="权限名称">{{
            detail.permission_name
          }}</el-descriptions-item>
          <el-descriptions-item label="所属模块">
            {{ formatPermissionModuleLabel(detail.module_code) }}（{{
              detail.module_code
            }}）
          </el-descriptions-item>
          <el-descriptions-item label="状态">{{
            detail.is_active ? "启用" : "停用"
          }}</el-descriptions-item>
          <el-descriptions-item label="已分配角色数">{{
            detail.role_count
          }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{
            formatDt(detail.updated_at)
          }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.roles?.length" class="detail-roles">
          <div class="detail-roles-title">拥有此权限的角色</div>
          <el-tag
            v-for="role in detail.roles"
            :key="role.id"
            class="role-tag"
            type="info"
            size="small"
          >
            {{ role.role_name }}（{{ role.role_no }}）
          </el-tag>
        </div>
        <p v-else class="detail-empty">暂无角色拥有此权限</p>
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import dayjs from "dayjs";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";
import type {
  PermissionListParams,
  SystemPermissionDetail,
  SystemPermissionListRow
} from "@/api/systemPermission";
import {
  getPermissionDetail,
  listPermissions,
  updatePermission
} from "@/api/systemPermission";
import { getHttpErrorMessage } from "@/utils/http";
import {
  PERMISSION_MODULE_LABELS,
  formatPermissionModuleLabel
} from "../role/utils/permissionModules";

defineOptions({ name: "PermissionManagement" });

const queryForm = reactive({
  keyword: "",
  permission_key: "",
  module_code: "",
  is_active: undefined as boolean | undefined,
  sort_by: "permission_key" as NonNullable<PermissionListParams["sort_by"]>,
  sort_order: "asc" as "asc" | "desc"
});
const query = reactive({ page: 1, page_size: 20 });
const loading = ref(false);
const tableData = ref<SystemPermissionListRow[]>([]);
const total = ref(0);

const formVisible = ref(false);
const editingId = ref<string | null>(null);
const formRef = ref<FormInstance>();
const submitting = ref(false);
const form = reactive({
  permission_key: "",
  permission_name: "",
  is_active: true
});

const detailVisible = ref(false);
const detailLoading = ref(false);
const detail = ref<SystemPermissionDetail | null>(null);

const formRules: FormRules = {
  permission_name: [
    { required: true, message: "请输入权限名称", trigger: "blur" }
  ]
};

function formatDt(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}

async function loadPermissions() {
  loading.value = true;
  try {
    const res = await listPermissions({
      page: query.page,
      page_size: query.page_size,
      keyword: queryForm.keyword.trim() || undefined,
      permission_key: queryForm.permission_key.trim() || undefined,
      module_code: queryForm.module_code || undefined,
      is_active: queryForm.is_active,
      sort_by: queryForm.sort_by,
      sort_order: queryForm.sort_order
    });
    if (res.code !== 0) throw new Error(res.message || "加载失败");
    tableData.value = res.data.items ?? [];
    total.value = res.data.total ?? 0;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "加载失败"));
  } finally {
    loading.value = false;
  }
}

async function search() {
  query.page = 1;
  await loadPermissions();
}

async function resetQuery() {
  queryForm.keyword = "";
  queryForm.permission_key = "";
  queryForm.module_code = "";
  queryForm.is_active = undefined;
  queryForm.sort_by = "permission_key";
  queryForm.sort_order = "asc";
  query.page = 1;
  await loadPermissions();
}

function handlePageSizeChange() {
  query.page = 1;
  loadPermissions();
}

function resetForm() {
  editingId.value = null;
  form.permission_key = "";
  form.permission_name = "";
  form.is_active = true;
  formRef.value?.clearValidate();
}

function openEdit(row: SystemPermissionListRow) {
  resetForm();
  editingId.value = row.id;
  form.permission_key = row.permission_key;
  form.permission_name = row.permission_name;
  form.is_active = row.is_active;
  formVisible.value = true;
}

async function openView(row: SystemPermissionListRow) {
  detail.value = null;
  detailVisible.value = true;
  detailLoading.value = true;
  try {
    const res = await getPermissionDetail(row.id);
    if (res.code !== 0) throw new Error(res.message || "加载详情失败");
    detail.value = res.data;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "加载详情失败"));
    detailVisible.value = false;
  } finally {
    detailLoading.value = false;
  }
}

async function submitForm() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !editingId.value) return;
  submitting.value = true;
  try {
    const res = await updatePermission(editingId.value, {
      permission_name: form.permission_name.trim(),
      is_active: form.is_active
    });
    if (res.code !== 0) throw new Error(res.message || "保存失败");
    ElMessage.success("已保存");
    formVisible.value = false;
    await loadPermissions();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "保存失败"));
  } finally {
    submitting.value = false;
  }
}

function toggleActive(row: SystemPermissionListRow) {
  const next = !row.is_active;
  const tip = next
    ? `确定启用权限「${row.permission_name}」？`
    : `停用后，所有角色都将失去权限「${row.permission_name}」（${row.permission_key}），确定停用？`;
  ElMessageBox.confirm(tip, next ? "启用" : "停用", {
    confirmButtonClass: next ? "app-button-success" : "app-button-warning",
    type: "warning"
  })
    .then(async () => {
      const res = await updatePermission(row.id, { is_active: next });
      if (res.code !== 0) throw new Error(res.message || "操作失败");
      ElMessage.success(next ? "已启用" : "已停用");
      await loadPermissions();
    })
    .catch(error => {
      if (error === "cancel" || error === "close") return;
      ElMessage.error(getHttpErrorMessage(error, "操作失败"));
    });
}

onMounted(loadPermissions);
</script>

<style lang="scss" scoped>
@use "../system-styles.scss" as *;

.page-tip {
  font-size: 12px;
  color: #94a3b8;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 16px 12px 4px;
}

.detail-roles {
  margin-top: 16px;
}

.detail-roles-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.role-tag {
  margin: 0 8px 8px 0;
}

.detail-empty {
  margin-top: 12px;
  color: #94a3b8;
}
</style>
