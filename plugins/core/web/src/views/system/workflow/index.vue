<template>
  <ReListPresentation>
  <div class="sys-module sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReListHeading data-list-key="index-0" />
      <section class="list-query-panel">
        <div class="filter-panel list-filters">
          <el-form :model="queryForm" label-position="top" class="query-form">
            <div class="filter-rows">
              <div class="filter-row workflow-filter-fields">
                <el-form-item label="关键词">
                  <el-input
                    v-model="queryForm.keyword"
                    clearable
                    placeholder="请输入编号 / 名称 / 业务类型"
                  />
                </el-form-item>
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
                <el-form-item label="适用租户">
                  <el-select
                    v-model="queryForm.org_id"
                    clearable
                    placeholder="请选择适用租户"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="org in organizationOptions"
                      :key="org.id"
                      :label="org.org_name"
                      :value="org.id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="启用">
                  <el-select
                    v-model="queryForm.is_active"
                    clearable
                    placeholder="请选择启用状态"
                    style="width: 100%"
                  >
                    <el-option label="是" :value="true" />
                    <el-option label="否" :value="false" />
                  </el-select>
                </el-form-item>
              </div>
              <div class="filter-row workflow-filter-actions">
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
              prop="definition_no"
              label="流程编号"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              prop="definition_name"
              label="名称"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              prop="business_type_code"
              label="业务类型"
              width="120"
            >
              <template #default="{ row }">{{
                businessTypeLabel(row.business_type_code)
              }}</template>
            </el-table-column>
            <el-table-column
              prop="org_name"
              label="适用租户"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.org_name || "—" }}</template>
            </el-table-column>
            <el-table-column
              prop="current_version_no"
              label="当前版本"
              width="96"
              align="center"
            >
              <template #default="{ row }">{{
                row.current_version_no ?? "—"
              }}</template>
            </el-table-column>
            <el-table-column
              prop="is_active"
              label="启用"
              width="80"
              align="center"
            >
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{
                  row.is_active ? "是" : "否"
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="150">
              <template #default="{ row }">{{
                formatDt(row.updated_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <div class="table-actions">
                  <span
                    class="action-text success"
                    @click="openDetail(row as WorkflowDefinitionRow)"
                    >版本</span
                  >
                  <span
                    class="action-text primary"
                    @click="openDesigner(row as WorkflowDefinitionRow)"
                    >流程设计</span
                  >
                  <span
                    class="action-text primary"
                    @click="openUpload(row as WorkflowDefinitionRow)"
                    >上传BPMN</span
                  >
                  <span
                    class="action-text success"
                    @click="openEdit(row as WorkflowDefinitionRow)"
                    >编辑</span
                  >
                  <span
                    class="action-text danger"
                    @click="removeRow(row as WorkflowDefinitionRow)"
                    >删除</span
                  >
                </div>
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
                  >新建流程</el-button
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
      v-model="formVisible"
      :title="editingId ? '编辑流程' : '新建流程'"
      width="520px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
      >
        <el-form-item label="流程编号">
          <el-input
            v-model="form.definition_no"
            disabled
            placeholder="自动生成"
          />
        </el-form-item>
        <el-form-item label="名称" prop="definition_name">
          <el-input v-model="form.definition_name" maxlength="128" />
        </el-form-item>
        <el-form-item label="业务类型" prop="business_type_code">
          <el-select
            v-model="form.business_type_code"
            style="width: 100%"
            placeholder="请选择"
          >
            <el-option
              v-for="opt in businessTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="适用组织">
          <el-select
            v-model="form.org_id"
            clearable
            placeholder="不选则为当前用户所属组织；下级组织未配置时沿用上级组织的流程"
            style="width: 100%"
            @clear="form.org_id = null"
          >
            <el-option
              v-for="org in organizationOptions"
              :key="org.id"
              :label="org.org_name"
              :value="org.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item label="组织默认流程">
          <el-switch v-model="form.is_default" />
          <span class="ml-2 text-sm text-[var(--el-text-color-secondary)]">关闭后可供具体知识库指定，不替换组织默认流程</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="neutral" @click="formVisible = false">取消</el-button>
        <el-button data-action="primary" type="primary" :loading="saving" @click="submitForm"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="detailVisible"
      title="版本与发布"
      width="720px"
      destroy-on-close
    >
      <div v-if="detail" class="detail-head">
        <div>{{ detail.definition_name }}（{{ detail.definition_no }}）</div>
        <div class="detail-sub">
          业务：{{ businessTypeLabel(detail.business_type_code) }} · 组织：{{
            detail.org_name || "—"
          }}
          · 当前版本：{{ detail.current_version_no ?? "未发布" }}
        </div>
      </div>
      <ReListTable
        list-key="index-1"
        :list-controls="false"
        :data="detail?.versions ?? []"
        row-key="id"
        size="small"
        class="data-table"
      >
        <el-table-column
          prop="version_no"
          label="版本"
          width="72"
          align="center"
        />
        <el-table-column
          prop="bpmn_process_no"
          label="BPMN 流程标识"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column label="来源/状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="String(row.source || '').startsWith('designer')"
              type="primary"
              size="small"
              >设计器</el-tag
            >
            <el-tag v-else type="warning" size="small">BPMN</el-tag>
            <el-tag
              v-if="row.is_current"
              type="success"
              size="small"
              class="mt-1"
              >当前生效</el-tag
            >
            <el-tag
              v-else-if="row.status_code === 'offline'"
              type="info"
              size="small"
              class="mt-1"
              >已下线</el-tag
            >
            <el-tag v-else type="warning" size="small" class="mt-1"
              >草稿</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column prop="published_at" label="发布时间" min-width="150">
          <template #default="{ row }">{{
            row.published_at ? formatDt(row.published_at) : "—"
          }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <span v-if="row.is_current" class="muted">—</span>
            <span
              v-else
              class="action-text success"
              @click="publishVersion(row as WorkflowDefinitionVersionRow)"
            >
              {{ row.published_at ? "设为当前" : "发布" }}
            </span>
          </template>
        </el-table-column>
      </ReListTable>
    </el-dialog>

    <el-dialog
      v-model="designerVisible"
      :title="
        designTarget ? `流程设计 · ${designTarget.definition_name}` : '流程设计'
      "
      fullscreen
      destroy-on-close
      class="designer-dialog"
    >
      <WorkflowDesigner
        v-if="designerVisible && designTarget"
        :definition-id="designTarget.id"
        :business-type="designTarget.business_type_code"
        @cancel="designerVisible = false"
        @saved="onDesignSaved"
      />
    </el-dialog>

    <el-dialog
      v-model="uploadVisible"
      title="上传 BPMN（高级）"
      width="480px"
      destroy-on-close
    >
      <p v-if="uploadTarget" class="upload-hint">
        流程：{{ uploadTarget.definition_name }}
      </p>
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".bpmn,.xml"
        :on-change="onFileChange"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或点击选择 .bpmn / .xml</div>
      </el-upload>
      <el-input
        v-model="uploadRemark"
        class="mt-3"
        placeholder="版本备注（可选）"
      />
      <template #footer>
        <el-button data-action="neutral" @click="uploadVisible = false">取消</el-button>
        <el-button
          data-action="import"
          type="primary"
          :loading="uploading"
          :disabled="!uploadFile"
          @click="submitUpload"
          >上传</el-button
        >
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules,
  type UploadFile
} from "element-plus";
import { Plus, UploadFilled } from "@element-plus/icons-vue";
import WorkflowDesigner from "./WorkflowDesigner.vue";
import {
  createWorkflowDefinition,
  deleteWorkflowDefinition,
  generateWorkflowDefinitionCode,
  getWorkflowDefinitionDetail,
  listWorkflowDefinitions,
  listWorkflowBusinessTypes,
  publishBpmnVersion,
  updateWorkflowDefinition,
  uploadBpmnVersionFile,
  type WorkflowBusinessTypeOption,
  type WorkflowDefinitionDetail,
  type WorkflowDefinitionRow,
  type WorkflowDefinitionVersionRow
} from "@/api/workflowDefinition";
import { type OrganizationListRow } from "@/api/organizationStructure";
import { useBasicDataStoreHook } from "@/store/modules/basicData";
import { getHttpErrorMessage } from "@/utils/http";

defineOptions({ name: "WorkflowDefinition" });

const loading = ref(false);
const saving = ref(false);
const uploading = ref(false);
const tableData = ref<WorkflowDefinitionRow[]>([]);
const total = ref(0);
const query = reactive({ page: 1, page_size: 20 });
const queryForm = reactive({
  keyword: "",
  business_type_code: "" as string | undefined,
  org_id: "" as string | undefined,
  is_active: undefined as boolean | undefined
});

const formVisible = ref(false);
const editingId = ref<string | null>(null);
const formRef = ref<FormInstance>();
const formRules: FormRules = {
  definition_name: [{ required: true, message: "请输入名称", trigger: "blur" }],
  business_type_code: [
    { required: true, message: "请选择业务类型", trigger: "change" }
  ]
};

const detailVisible = ref(false);
const detail = ref<WorkflowDefinitionDetail | null>(null);

const designerVisible = ref(false);
const designTarget = ref<WorkflowDefinitionRow | null>(null);
const uploadVisible = ref(false);
const uploadTarget = ref<WorkflowDefinitionRow | null>(null);
const uploadFile = ref<File | null>(null);
const uploadRemark = ref("");
const businessTypeOptions = ref<WorkflowBusinessTypeOption[]>([]);
const organizationOptions = ref<OrganizationListRow[]>([]);
const basicDataStore = useBasicDataStoreHook();

function businessTypeLabel(value: string) {
  return (
    businessTypeOptions.value.find(opt => opt.value === value)?.label ?? value
  );
}

async function loadBusinessTypeOptions() {
  const res = await listWorkflowBusinessTypes();
  if (res.code !== 0) throw new Error(res.message || "加载业务类型失败");
  businessTypeOptions.value = res.data ?? [];
}

const form = reactive({
  definition_no: "",
  definition_name: "",
  business_type_code: "",
  org_id: null as string | null,
  description: "",
  is_active: false,
  is_default: true
});

function formatDt(v: string) {
  if (!v) return "—";
  return v.replace("T", " ").slice(0, 19);
}

async function loadOrganizationOptions() {
  organizationOptions.value = await basicDataStore.loadOrganizations();
}

async function loadList() {
  loading.value = true;
  try {
    const res = await listWorkflowDefinitions({
      page: query.page,
      page_size: query.page_size,
      keyword: queryForm.keyword || undefined,
      business_type_code: queryForm.business_type_code || undefined,
      org_id: queryForm.org_id || undefined,
      is_active: queryForm.is_active
    });
    if (res.code !== 0) throw new Error(res.message);
    tableData.value = res.data.items;
    total.value = res.data.total;
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}

function search() {
  query.page = 1;
  loadList();
}

function resetQuery() {
  queryForm.keyword = "";
  queryForm.business_type_code = undefined;
  queryForm.org_id = undefined;
  queryForm.is_active = undefined;
  search();
}

function handlePageSizeChange() {
  query.page = 1;
  loadList();
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, {
    definition_no: generateWorkflowDefinitionCode(),
    definition_name: "",
    business_type_code: businessTypeOptions.value[0]?.value ?? "",
    org_id: null,
    description: "",
    is_active: false,
    is_default: true
  });
  formVisible.value = true;
}

function openEdit(row: WorkflowDefinitionRow) {
  editingId.value = row.id;
  Object.assign(form, {
    definition_no: row.definition_no,
    definition_name: row.definition_name,
    business_type_code: row.business_type_code,
    org_id: row.org_id,
    description: row.description ?? "",
    is_active: row.is_active,
    is_default: row.is_default
  });
  formVisible.value = true;
}

async function submitForm() {
  await formRef.value?.validate();
  saving.value = true;
  try {
    if (editingId.value) {
      const res = await updateWorkflowDefinition(editingId.value, {
        definition_name: form.definition_name,
        business_type_code: form.business_type_code,
        org_id: form.org_id || null,
        description: form.description || null,
        is_active: form.is_active,
        is_default: form.is_default
      });
      if (res.code !== 0) throw new Error(res.message);
    } else {
      const res = await createWorkflowDefinition({
        definition_no: form.definition_no,
        definition_name: form.definition_name,
        business_type_code: form.business_type_code,
        org_id: form.org_id || null,
        description: form.description || null,
        is_active: form.is_active,
        is_default: form.is_default
      });
      if (res.code !== 0) throw new Error(res.message);
    }
    ElMessage.success("已保存");
    formVisible.value = false;
    loadList();
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeRow(row: WorkflowDefinitionRow) {
  await ElMessageBox.confirm(
    `确定删除流程「${row.definition_name}」？`,
    "提示",
    {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    }
  );
  const res = await deleteWorkflowDefinition(row.id);
  if (res.code !== 0) {
    ElMessage.error(res.message);
    return;
  }
  ElMessage.success("已删除");
  loadList();
}

async function openDetail(row: WorkflowDefinitionRow) {
  const res = await getWorkflowDefinitionDetail(row.id);
  if (res.code !== 0) {
    ElMessage.error(res.message);
    return;
  }
  detail.value = res.data;
  detailVisible.value = true;
}

function openDesigner(row: WorkflowDefinitionRow) {
  designTarget.value = row;
  designerVisible.value = true;
}

async function onDesignSaved() {
  designerVisible.value = false;
  await loadList();
  if (
    detail.value &&
    designTarget.value &&
    detail.value.id === designTarget.value.id
  ) {
    await openDetail(designTarget.value);
  }
}

function openUpload(row: WorkflowDefinitionRow) {
  uploadTarget.value = row;
  uploadFile.value = null;
  uploadRemark.value = "";
  uploadVisible.value = true;
}

function onFileChange(file: UploadFile) {
  uploadFile.value = file.raw ?? null;
}

async function submitUpload() {
  if (!uploadTarget.value || !uploadFile.value) return;
  uploading.value = true;
  try {
    const fd = new FormData();
    fd.append("definition_id", uploadTarget.value.id);
    fd.append("file", uploadFile.value);
    if (uploadRemark.value) fd.append("remark", uploadRemark.value);
    const res = await uploadBpmnVersionFile(fd);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success(`已上传版本 v${res.data.version_no}`);
    uploadVisible.value = false;
    loadList();
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function publishVersion(row: {
  id: string;
  version_no: number;
  published_at?: string | null;
}) {
  const isRepublish = !!row.published_at;
  const message = isRepublish
    ? `将版本 v${row.version_no} 设为当前生效版本？进行中的审批实例仍按原版本继续。`
    : `发布版本 v${row.version_no} 并设为当前生效版本？`;
  try {
    await ElMessageBox.confirm(message, isRepublish ? "设为当前版本" : "发布", {
      confirmButtonClass: "app-button-success",
      type: "info"
    });
    const res = await publishBpmnVersion(row.id);
    if (res.code !== 0) {
      ElMessage.error(res.message || "发布失败");
      return;
    }
    ElMessage.success(isRepublish ? "已切换为当前版本" : "已发布");
    if (detail.value) {
      const d = await getWorkflowDefinitionDetail(detail.value.id);
      if (d.code === 0) detail.value = d.data;
    }
    loadList();
  } catch (error) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(getHttpErrorMessage(error, "发布失败"));
  }
}

onMounted(async () => {
  await Promise.all([
    Promise.all([loadBusinessTypeOptions(), loadOrganizationOptions()]).catch(
      (e: unknown) => {
        ElMessage.warning(e instanceof Error ? e.message : "选项加载失败");
      }
    ),
    loadList()
  ]);
});
</script>

<style lang="scss">
@use "../system-styles.scss" as *;

.detail-head {
  margin-bottom: 12px;
}

.detail-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.upload-hint {
  margin-bottom: 12px;
  font-size: 14px;
}

.mt-3 {
  margin-top: 12px;
}

.muted {
  color: var(--el-text-color-placeholder);
}

.designer-dialog.el-dialog {
  padding: 0;

  .el-dialog__header {
    display: flex;
    align-items: center;
    height: 60px;
    padding: 0 24px;
    margin: 0;
    border-bottom: 1px solid #e8eaed;
  }

  .el-dialog__headerbtn {
    top: 6px;
  }

  .el-dialog__body {
    padding: 0;
  }
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
}

.filter-rows {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sys-module {
  .filter-row.workflow-filter-fields {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .filter-row.workflow-filter-actions {
    display: flex;
    justify-content: flex-end;

    .query-actions {
      padding-top: 0;
    }
  }
}

@media (width <= 1200px) {
  .sys-module .filter-row.workflow-filter-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (width <= 900px) {
  .sys-module .filter-row.workflow-filter-fields {
    grid-template-columns: 1fr;
  }

  .sys-module .filter-row.workflow-filter-actions {
    justify-content: flex-start;
  }
}
</style>
