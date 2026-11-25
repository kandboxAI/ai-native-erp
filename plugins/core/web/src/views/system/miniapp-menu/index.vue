<template>
  <ReListPresentation>
  <div class="sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReListHeading data-list-key="index-0">
        <template #title>小程序菜单管理</template>
      </ReListHeading>
      <section class="list-query-panel">
        <div class="filter-panel list-filters">
          <el-form :model="queryForm" label-position="top" class="query-form">
            <div class="filter-row">
              <el-form-item label="菜单关键字">
                <el-input
                  v-model="queryForm.keyword"
                  clearable
                  placeholder="请输入名称 / 编码 / 分组 / 路径"
                />
              </el-form-item>
              <el-form-item label="小程序端">
                <el-select
                  v-model="queryForm.portal_code"
                  clearable
                  placeholder="请选择小程序端"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in MINIAPP_PORTALS"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
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
            :list-refresh="loadMenus"
            v-loading="loading"
            :data="tableData"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="portal_code"
              label="端"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                <el-tag type="primary">
                  {{ portalLabel(row.portal_code) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="menu_name" label="菜单名称" min-width="120" />
            <el-table-column
              prop="menu_key"
              label="菜单编码"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column prop="group_name" label="分组名称" min-width="120" />
            <el-table-column
              prop="group_key"
              label="分组编码"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              prop="path"
              label="页面路径"
              min-width="260"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.path || "—" }}</template>
            </el-table-column>
            <el-table-column
              prop="sort_no"
              label="排序"
              width="80"
              align="center"
            />
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
            <el-table-column prop="updated_at" label="更新时间" min-width="150">
              <template #default="{ row }">{{
                formatDt(row.updated_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <span
                  class="action-text success"
                  @click="openEdit(row as MiniappMenuRow)"
                  >编辑</span
                >
                <span
                  class="action-text danger"
                  @click="removeRow(row as MiniappMenuRow)"
                  >删除</span
                >
              </template>
            </el-table-column>

            <template #list-actions
              ><div class="header-actions">
                <el-button
                  data-action="neutral"
                  type="primary"
                  plain
                  @click="bannerManagerVisible = true"
                  >首页轮播图</el-button
                >
                <!-- <el-button
                type="primary"
                :icon="Plus"
                @click="openCreate"
              >
                新增菜单
              </el-button> -->
              </div></template
            >

            <template #list-pagination
              ><div class="table-footer">

                <ReListPagination
                  v-model:current-page="query.page"
                  v-model:page-size="query.page_size"
                  :total="total"
                  @current-change="loadMenus" @size-change="handlePageSizeChange" /></div
            ></template>
          </ReListTable>
        </div>
      </section>
    </section>

    <el-dialog
      v-model="bannerManagerVisible"
      title="首页轮播图管理"
      width="900px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <BannerManager v-if="bannerManagerVisible" />
    </el-dialog>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑小程序菜单' : '新增小程序菜单'"
      width="560px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="小程序端" prop="portal_code">
          <el-radio-group v-model="form.portal_code" :disabled="!!editingId">
            <el-radio
              v-for="item in MINIAPP_PORTALS"
              :key="item.value"
              :value="item.value"
              >{{ item.label }}</el-radio
            >
          </el-radio-group>
        </el-form-item>
        <el-form-item label="菜单名称" prop="menu_name">
          <el-input v-model="form.menu_name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="菜单标识" prop="menu_key">
          <el-input
            v-model="form.menu_key"
            :disabled="!!editingId"
            maxlength="128"
            show-word-limit
            placeholder="例如 inventory_query"
          />
        </el-form-item>
        <el-form-item label="分组名称" prop="group_name">
          <el-input v-model="form.group_name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="分组编码" prop="group_key">
          <el-input
            v-model="form.group_key"
            maxlength="128"
            show-word-limit
            placeholder="例如 inventory"
          />
        </el-form-item>
        <el-form-item label="页面路径">
          <el-input
            v-model="form.path"
            maxlength="512"
            show-word-limit
            placeholder="/pages/home/index"
          />
        </el-form-item>
        <el-form-item label="排序" prop="sort_no">
          <el-input-number
            v-model="form.sort_no"
            :min="0"
            :max="999999"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-radio-group v-model="form.is_active">
            <el-radio :value="true">启用</el-radio>
            <el-radio :value="false">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="primary" type="primary" :loading="saving" @click="submit">
          确定
        </el-button>
        <el-button data-action="neutral" class="btn-cancel" @click="dialogVisible = false">
          取消
        </el-button>
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { Plus } from "@element-plus/icons-vue";
import BannerManager from "./BannerManager.vue";
import dayjs from "dayjs";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";
import type {
  MiniappMenuPayload,
  MiniappMenuRow,
  MiniappPortal
} from "@/api/miniappMenu";
import {
  createMiniappMenu,
  deleteMiniappMenu,
  listMiniappMenus,
  updateMiniappMenu
} from "@/api/miniappMenu";
import { getDictionaryOptions } from "@/api/systemDictionary";
import { apiErrorMessage } from "@/views/system/role-management/utils";

defineOptions({ name: "MiniappMenuManagement" });
const bannerManagerVisible = ref(false);

const MINIAPP_PORTALS = ref([{ value: "standard", label: "用户" }]);
const portalLabel = (key: string) =>
  MINIAPP_PORTALS.value.find(item => item.value === key)?.label || key;
const queryForm = reactive({
  keyword: "",
  portal_code: undefined as MiniappPortal | undefined,
  is_active: undefined as boolean | undefined
});
const query = reactive({ page: 1, page_size: 20 });
const loading = ref(false);
const saving = ref(false);
const tableData = ref<MiniappMenuRow[]>([]);
const total = ref(0);
const dialogVisible = ref(false);
const editingId = ref<string | null>(null);
const formRef = ref<FormInstance>();

const form = reactive<MiniappMenuPayload>({
  portal_code: "standard",
  menu_key: "",
  menu_name: "",
  group_key: "",
  group_name: "",
  path: "",
  sort_no: 10,
  is_active: true
});

const codePattern = /^[a-z][a-z0-9_]*$/;

const rules: FormRules = {
  portal_code: [
    { required: true, message: "请选择小程序端", trigger: "change" }
  ],
  menu_name: [{ required: true, message: "请输入菜单名称", trigger: "blur" }],
  menu_key: [
    { required: true, message: "请输入菜单编码", trigger: "blur" },
    {
      validator: (_r, v, cb) => {
        if (!codePattern.test(String(v || ""))) {
          cb(new Error("菜单编码需小写字母开头，仅支持小写字母、数字、下划线"));
        } else cb();
      },
      trigger: "blur"
    }
  ],
  group_key: [
    {
      validator: (_r, v, cb) => {
        if (v && !codePattern.test(String(v))) {
          cb(new Error("分组编码需小写字母开头，仅支持小写字母、数字、下划线"));
        } else cb();
      },
      trigger: "blur"
    }
  ]
};

function formatDt(v: string) {
  return v ? dayjs(v).format("YYYY-M-D HH:mm") : "—";
}

async function loadMenus() {
  loading.value = true;
  try {
    const res = await listMiniappMenus({
      page: query.page,
      page_size: query.page_size,
      keyword: queryForm.keyword.trim() || undefined,
      portal_code: queryForm.portal_code,
      is_active: queryForm.is_active
    });
    tableData.value = res.data.items ?? [];
    total.value = res.data.total ?? 0;
  } finally {
    loading.value = false;
  }
}

async function search() {
  query.page = 1;
  await loadMenus();
}

async function resetQuery() {
  queryForm.keyword = "";
  queryForm.portal_code = undefined;
  queryForm.is_active = undefined;
  query.page = 1;
  await loadMenus();
}

async function handlePageSizeChange() {
  query.page = 1;
  await loadMenus();
}

function resetPayload(portal: MiniappPortal = "standard") {
  Object.assign(form, {
    portal_code: portal,
    menu_key: "",
    menu_name: "",
    group_key: "",
    group_name: "",
    path: "",
    sort_no: 10,
    is_active: true
  });
}

function openCreate() {
  editingId.value = null;
  resetPayload(queryForm.portal_code ?? "standard");
  dialogVisible.value = true;
}

function openEdit(row: MiniappMenuRow) {
  editingId.value = row.id;
  Object.assign(form, {
    portal_code: row.portal_code,
    menu_key: row.menu_key,
    menu_name: row.menu_name,
    group_key: row.group_key ?? "",
    group_name: row.group_name ?? "",
    path: row.path ?? "",
    sort_no: row.sort_no,
    is_active: row.is_active
  });
  dialogVisible.value = true;
}

function resetForm() {
  editingId.value = null;
  formRef.value?.clearValidate();
}

function buildPayload(): MiniappMenuPayload {
  return {
    portal_code: form.portal_code,
    menu_key: form.menu_key.trim(),
    menu_name: form.menu_name.trim(),
    group_key: form.group_key?.trim() || null,
    group_name: form.group_name?.trim() || null,
    path: form.path?.trim() || null,
    sort_no: form.sort_no ?? 0,
    is_active: form.is_active
  };
}

async function submit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      const { portal_code: _portal, menu_key: _key, ...rest } = payload;
      await updateMiniappMenu(editingId.value, rest);
      ElMessage.success("已保存");
    } else {
      await createMiniappMenu(payload);
      ElMessage.success("已新增");
    }
    dialogVisible.value = false;
    await loadMenus();
  } catch (err) {
    ElMessage.error(apiErrorMessage(err));
  } finally {
    saving.value = false;
  }
}

async function removeRow(row: MiniappMenuRow) {
  await ElMessageBox.confirm(
    `确定删除「${portalLabel(row.portal_code)} - ${row.menu_name}」？已配置给角色的关联也将无法继续生效。`,
    "删除",
    {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    }
  );
  try {
    await deleteMiniappMenu(row.id);
    ElMessage.success("已删除");
    await loadMenus();
  } catch (err) {
    ElMessage.error(apiErrorMessage(err));
  }
}

onMounted(async () => {
  try {
    const response = await getDictionaryOptions(["sys_miniapp_portal"]);
    if (response.code === 0)
      MINIAPP_PORTALS.value = (response.data.sys_miniapp_portal || []).map(
        item => ({ value: item.item_code, label: item.item_name })
      );
    await loadMenus();
  } catch (error) {
    ElMessage.error(apiErrorMessage(error));
  }
});
</script>

<style scoped lang="scss">
.sys-card {
  border-radius: 16px;

  :deep(.el-card__header) {
    padding: 16px 22px;
    border-bottom: none;
  }

  :deep(.el-card__body) {
    padding: 0 22px 22px;
  }
}

.page-header {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  font-size: 30px;
  font-weight: 700;
  color: #111827;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.filter-panel {
  padding: 10px 12px 12px;
  background: linear-gradient(180deg, #fbfdff 0%, #f6faff 100%);
  border-radius: 20px;
}

.query-form :deep(.el-form-item__label) {
  font-size: 15px;
  font-weight: 600;
  color: #4b5563;
}

.query-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.filter-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  gap: 16px 14px;
  align-items: start;
}

.filter-row :deep(.el-input__wrapper),
.filter-row :deep(.el-select__wrapper) {
  height: 48px;
  background: #f2f2f2;
  border-radius: 14px;
  box-shadow: none;
}

.query-actions {
  display: flex;
  gap: 14px;
  align-items: center;
  padding-top: 31px;
}

.search-btn,
.reset-btn {
  min-width: 132px;
  height: 48px;
  font-size: 16px;
  border-radius: 14px;
}

.search-btn {
  color: #409eff;
  background: #fff;
  border-color: #bcdcff;
}

.reset-btn {
  color: #6b7280;
  background: #fff;
  border-color: #d1d5db;
}

.table-panel {
  padding: 10px 0;
  margin-top: 18px;
  background: #fff;
  border: 1px solid #edf2f7;
  border-radius: 18px;
}

.data-table {
  :deep(th.el-table__cell) {
    height: 58px;
    font-weight: 600;
    color: #475569;
    background: #f8fafc;
    border-bottom: 1px solid #e8eef5;
  }

  :deep(td.el-table__cell) {
    height: 72px;
    color: #334155;
  }

  :deep(.el-table__inner-wrapper::before) {
    display: none;
  }
}

.action-text.success {
  margin-right: 10px;
  font-weight: 600;
  color: #22c55e;
  cursor: pointer;
}

.action-text.danger {
  font-weight: 600;
  color: #ef4444;
  cursor: pointer;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 8px 0;
}

.page-size-box {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #6b7280;
}

.page-size-select {
  width: 72px;
}

.btn-cancel {
  color: #b45309;
  background: #fffbeb;
  border-color: #fcd34d;
}

@media (width <= 1100px) {
  .filter-row {
    grid-template-columns: 1fr;
  }

  .query-actions {
    padding-top: 0;
  }
}
</style>
