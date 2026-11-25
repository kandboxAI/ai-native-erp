<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="760px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="reset"
  >
    <el-alert
      :title="notice"
      type="warning"
      :closable="false"
      show-icon
      class="import-notice"
    />
    <div class="toolbar">
      <el-button data-action="export" :icon="Download" :loading="downloading" @click="handleDownload"
        >下载最新模板</el-button
      >
      <el-switch
        v-if="showAllowUpdate !== false"
        v-model="allowUpdate"
        active-text="允许更新已有数据"
        :disabled="busy"
        @change="invalidate"
      />
    </div>
    <el-upload
      drag
      action="#"
      accept=".xlsx"
      :auto-upload="false"
      :limit="1"
      :show-file-list="false"
      :disabled="busy"
      :on-change="handleFileChange"
      :on-exceed="handleExceed"
    >
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div>{{ file ? file.name : uploadPlaceholder }}</div>
      <small v-if="file">{{ (file.size / 1024).toFixed(1) }} KB</small>
    </el-upload>

    <template v-if="validation">
      <div class="summary-line">
        <el-tag :type="validation.valid ? 'success' : 'danger'">
          {{
            validation.valid ? "校验通过" : `${validation.errors.length} 项错误`
          }}
        </el-tag>
        <span>{{ summaryText }}</span>
      </div>
      <ReListTable list-key="index-0" :list-controls="false"
        v-if="validation.errors.length"
        :data="validation.errors"
        border
        max-height="260"
      >
        <el-table-column prop="sheet" label="工作表" width="110" />
        <el-table-column prop="row" label="行" width="65" />
        <el-table-column prop="field" label="字段" width="130" />
        <el-table-column prop="message" label="错误说明" min-width="260" />
      </ReListTable>
    </template>

    <template #footer>
      <el-button data-action="neutral" :disabled="busy" @click="visible = false">取消</el-button>
      <el-button
        data-action="primary"
        type="primary"
        :loading="validating"
        :disabled="!file || importing"
        @click="handleValidate"
      >
        预校验
      </el-button>
      <el-button
        data-action="import"
        type="danger"
        :loading="importing"
        :disabled="!canImport"
        @click="handleImport"
        >确认导入</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { Download, UploadFilled } from "@element-plus/icons-vue";
import {
  ElMessage,
  ElMessageBox,
  genFileId,
  type UploadFile,
  type UploadRawFile
} from "element-plus";
import { saveExcelBlob } from "@plugins/inv/web/src/views/inventory/shared/utils/exportXlsxFromApi";
import { getHttpErrorMessage } from "@/utils/http";
import type {
  ExcelImportResponse,
  ExcelImportSummaryItem,
  ExcelImportValidation
} from "./types";

const props = defineProps<{
  modelValue: boolean;
  title: string;
  notice: string;
  uploadPlaceholder: string;
  templateFileName: string;
  confirmMessage: string;
  successMessage: string;
  showAllowUpdate?: boolean;
  summaryItems: ExcelImportSummaryItem[];
  downloadTemplate: () => Promise<Blob>;
  validateImport: (
    file: File,
    allowUpdateExisting: boolean
  ) => Promise<ExcelImportResponse>;
  executeImport: (
    file: File,
    allowUpdateExisting: boolean
  ) => Promise<ExcelImportResponse>;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  success: [result: ExcelImportValidation];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value)
});
const file = ref<File | null>(null);
const allowUpdate = ref(false);
const validation = ref<ExcelImportValidation | null>(null);
const validatedKey = ref("");
const validating = ref(false);
const importing = ref(false);
const downloading = ref(false);
const busy = computed(
  () => validating.value || importing.value || downloading.value
);
const fileKey = computed(() =>
  file.value
    ? `${file.value.name}:${file.value.size}:${file.value.lastModified}:${allowUpdate.value}`
    : ""
);
const canImport = computed(
  () =>
    validation.value?.valid &&
    validatedKey.value === fileKey.value &&
    !busy.value
);
const summaryText = computed(() => {
  if (!validation.value) return "";
  const summary = validation.value.summary as Record<string, number>;
  return props.summaryItems
    .map(item => `${item.label} ${summary[item.key] ?? 0}`)
    .join("，");
});

function invalidate() {
  validation.value = null;
  validatedKey.value = "";
}

function handleFileChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw;
  if (!raw) return;
  if (!raw.name.toLowerCase().endsWith(".xlsx") || raw.size > 5 * 1024 * 1024) {
    file.value = null;
    invalidate();
    ElMessage.error("请选择不超过 5 MB 的 .xlsx 文件");
    return;
  }
  file.value = raw;
  invalidate();
}

function handleExceed(files: File[]) {
  const raw = files[0] as UploadRawFile;
  raw.uid = genFileId();
  handleFileChange({
    name: raw.name,
    size: raw.size,
    status: "ready",
    uid: raw.uid,
    raw
  } as UploadFile);
}

async function handleDownload() {
  downloading.value = true;
  try {
    await saveExcelBlob(await props.downloadTemplate(), props.templateFileName);
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "模板下载失败"));
  } finally {
    downloading.value = false;
  }
}

async function handleValidate() {
  if (!file.value) return;
  validating.value = true;
  try {
    const response = await props.validateImport(file.value, allowUpdate.value);
    validation.value = response.data;
    validatedKey.value = fileKey.value;
    ElMessage[response.data.valid ? "success" : "warning"](
      response.data.valid ? "预校验通过" : "请修正模板中的错误"
    );
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "预校验失败"));
  } finally {
    validating.value = false;
  }
}

async function handleImport() {
  if (!file.value || !canImport.value) return;
  try {
    await ElMessageBox.confirm(props.confirmMessage, "确认正式导入", {
      type: "warning",
      confirmButtonText: "确认导入"
    });
  } catch {
    return;
  }

  importing.value = true;
  try {
    const response = await props.executeImport(file.value, allowUpdate.value);
    if (!response.data.valid) {
      validation.value = response.data;
      validatedKey.value = "";
      ElMessage.error("导入前复核未通过，数据未写入");
      return;
    }
    ElMessage.success(props.successMessage);
    emit("success", response.data);
    visible.value = false;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "导入失败，整批数据已回滚"));
  } finally {
    importing.value = false;
  }
}

function reset() {
  file.value = null;
  allowUpdate.value = false;
  invalidate();
}
</script>

<style scoped>
.import-notice {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.upload-icon {
  font-size: 40px;
  color: var(--el-color-primary);
}

.summary-line {
  display: flex;
  gap: 14px;
  align-items: center;
  margin: 16px 0 10px;
  color: var(--el-text-color-regular);
}

@media (width <= 720px) {
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
