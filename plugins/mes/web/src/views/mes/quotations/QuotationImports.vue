<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import ActionButton from "@/components/ActionButton/index.vue";
import { computed, nextTick, onBeforeUnmount, ref, shallowRef } from "vue";
import { ElMessage } from "element-plus";
import { download, request, type QuoteLine, type QuoteFile } from "./api";
import {
  mergeExcel,
  planDrawings,
  bindDrawing,
  type ExcelPreview,
  type DrawingImport,
  type DrawingImportMode,
} from "./imports";

const props = defineProps<{ lines: QuoteLine[] }>();
const emit = defineEmits<{
  apply: [lines: QuoteLine[]];
  busy: [value: boolean];
}>();
const excelInput = ref<HTMLInputElement>(),
  drawingInput = ref<HTMLInputElement>();
const excel = shallowRef<ExcelPreview>(),
  drawings = ref<DrawingImport[]>([]);
const sourceFiles = shallowRef<File[]>([]),
  drawingMode = ref<DrawingImportMode>("existing");
const excelVisible = ref(false),
  drawingVisible = ref(false),
  loading = ref(false);
let alive = true,
  base: QuoteLine[] | undefined,
  targetIndex = -1;
onBeforeUnmount(() => {
  alive = false;
  emit("busy", false);
});
const merge = computed(() => {
  try {
    return excel.value
      ? { ...mergeExcel(props.lines, excel.value.items), error: "" }
      : undefined;
  } catch (cause) {
    return { lines: [], added: 0, updated: 0, error: (cause as Error).message };
  }
});
const invalid = computed(() =>
  drawings.value.some((row) => !row.is_skipped && !!row.error),
);
const hasUploaded = computed(() =>
  drawings.value.some((row) => row.status === "已上传"),
);
const skipped = computed(
  () => drawings.value.filter((row) => row.is_skipped).length,
);
const included = computed(() =>
  drawings.value.filter((row) => !row.is_skipped),
);
const addedGoods = computed(
  () =>
    new Set(
      included.value
        .filter((row) => row.action === "新增货品")
        .map((row) => row.drawing_no.toLowerCase()),
    ).size,
);
const remaining = computed(
  () => included.value.filter((row) => row.status !== "已上传").length,
);
async function task(action: () => Promise<void>) {
  if (loading.value) return;
  loading.value = true;
  emit("busy", true);
  try {
    await action();
  } catch (cause) {
    if (alive) {
      actionMessage((cause as Error).message || "导入失败，请重试");
    }
  } finally {
    if (alive) {
      loading.value = false;
      emit("busy", false);
    }
  }
}
function pick(line?: QuoteLine) {
  targetIndex = line ? props.lines.indexOf(line) : -1;
  sourceFiles.value = [];
  drawings.value = [];
  base = props.lines;
  drawingMode.value = props.lines.some((row) => !!row.drawing_no.trim())
    ? "existing"
    : "add";
  drawingVisible.value = true;
}
defineExpose({ pick });
async function readExcel(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  input.value = "";
  if (!file) return;
  excel.value = undefined;
  excelVisible.value = true;
  base = props.lines;
  await task(async () => {
    if (
      !/\.xlsx$/i.test(file.name) ||
      !file.size ||
      file.size > 5 * 1024 * 1024
    )
      throw Error("请选择非空且不超过 5MB 的 .xlsx 模板文件");
    const form = new FormData();
    form.append("file", file);
    const result = await request<ExcelPreview>("/import-preview", "post", form);
    if (alive && base === props.lines) excel.value = result;
  });
}
function applyExcel() {
  if (
    !excel.value ||
    excel.value.errors.length ||
    !merge.value ||
    merge.value.error
  )
    return;
  if (base !== props.lines) {
    actionMessage("当前货品已变化，请重新选择 Excel", "warning");
    return;
  }
  emit("apply", merge.value.lines);
  excelVisible.value = false;
  ElMessage.success(
    `已导入 ${excel.value.items.length} 项货品，请保存录入或提交工程报价`,
  );
  excel.value = undefined;
}
function readDrawings(event: Event) {
  const input = event.target as HTMLInputElement,
    files = [...(input.files || [])];
  input.value = "";
  if (!files.length) return;
  sourceFiles.value = files;
  base = props.lines;
  replanDrawings();
}
function replanDrawings() {
  drawings.value = [];
  try {
    drawings.value = planDrawings(
      props.lines,
      sourceFiles.value,
      targetIndex >= 0 ? props.lines[targetIndex] : undefined,
      drawingMode.value,
    );
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
async function uploadDrawings() {
  if (invalid.value || !drawings.value.length || !remaining.value) return;
  await task(async () => {
    if (base !== props.lines) throw Error("当前货品已变化，请重新选择文件");
    const working = props.lines.map((line) => ({
      ...line,
      files: [...line.files],
    }));
    let count = 0;
    for (const row of included.value.filter(
      (value) => value.status !== "已上传",
    )) {
      if (!alive) return;
      row.status = "上传中";
      row.message = "";
      try {
        const form = new FormData();
        form.append("file", row.file);
        const file = await request<QuoteFile>("/files", "post", form);
        if (!alive) return;
        bindDrawing(
          working,
          row,
          file,
          targetIndex >= 0 ? working[targetIndex] : undefined,
        );
        row.status = "已上传";
        count++;
      } catch (cause) {
        row.status = "上传失败";
        row.message = (cause as Error).message;
      }
    }
    if (count && alive) {
      emit("apply", working);
      await nextTick();
      base = props.lines;
      const failed = included.value.filter(
        (row) => row.status === "上传失败",
      ).length;
      if (!failed) {
        drawingVisible.value = false;
        ElMessage.success(`已上传 ${included.value.length} 份，请保存询价`);
      } else {
        ElMessage.warning(`已上传 ${count} 份，${failed} 份失败，可重试`);
      }
    }
  });
}
</script>

<template>
  <div class="quotation-imports">
    <ActionButton
      intent="download"
      :disabled="loading"
      @click="
        task(() =>
          download(
            '/api/mes/quotations/import-template',
            '询价货品导入模板.xlsx',
          ),
        )
      "
      >下载 Excel 模板</ActionButton
    >
    <ActionButton
      intent="import"
      :disabled="loading"
      @click="excelInput?.click()"
      >导入 Excel</ActionButton
    >
    <ActionButton intent="upload" :disabled="loading" @click="pick()"
      >批量导入图纸 / 模型</ActionButton
    >
    <slot />
    <input
      ref="excelInput"
      hidden
      type="file"
      accept=".xlsx"
      @change="readExcel"
    />
    <input
      ref="drawingInput"
      hidden
      multiple
      type="file"
      accept=".pdf,.stp,.step"
      @change="readDrawings"
    />
  </div>
  <el-dialog
    v-model="excelVisible"
    title="导入询价货品"
    width="min(1100px, 94vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    destroy-on-close
  >
    <p>
      模板包含图号、描述、数量、客户材料、表面处理和客户备注。同图号更新这些字段并保留版本及附件，未匹配的货品新增。工程人员采用 AI 报价时带入预计净重。
    </p>
    <el-alert
      v-if="merge?.error"
      :title="merge.error"
      type="error"
      :closable="false"
    />
    <template v-if="excel">
      <el-alert
        :title="`读取 ${excel.total_rows} 行，${excel.errors.length} 行有误；将新增 ${merge?.added || 0} 项、更新 ${merge?.updated || 0} 项`"
        :type="excel.errors.length || merge?.error ? 'error' : 'info'"
        :closable="false"
      />
      <el-table
        v-if="excel.errors.length"
        :data="excel.errors"
        max-height="180"
        border
        ><el-table-column
          prop="row_no"
          label="Excel 行号"
          width="110" /><el-table-column
          prop="message"
          label="请修改后重新导入（未写入当前询价）"
      /></el-table>
      <el-table :data="excel.items" max-height="380" border>
        <el-table-column
          prop="row_no"
          label="行号"
          width="65"
        /><el-table-column
          prop="drawing_no"
          label="图号"
          min-width="160"
        /><el-table-column
          prop="description"
          label="描述"
          min-width="180"
        /><el-table-column
          prop="quantity"
          label="数量"
          width="100"
        /><el-table-column
          prop="customer_material"
          label="客户材料"
          min-width="140"
        /><el-table-column
          prop="surface_treatment"
          label="表面处理"
          min-width="160"
        />
        <el-table-column
          prop="note"
          label="客户备注"
          min-width="220"
          show-overflow-tooltip
        />
      </el-table>
    </template>
    <template #footer
      ><el-button :disabled="loading" @click="excelVisible = false"
        >取消</el-button
      ><el-button
        type="primary"
        :loading="loading"
        :disabled="!excel || !!excel.errors.length || !!merge?.error"
        @click="applyExcel"
        >确认导入当前询价</el-button
      ></template
    >
  </el-dialog>
  <el-dialog
    v-model="drawingVisible"
    title="批量导入图纸与模型"
    width="min(1050px, 94vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    destroy-on-close
  >
    <div class="drawing-import-controls">
      <el-radio-group
        v-if="targetIndex < 0"
        v-model="drawingMode"
        :disabled="loading || hasUploaded"
        @change="replanDrawings"
      >
        <el-radio-button value="existing">仅匹配现有货品</el-radio-button>
        <el-radio-button value="add">新增货品并匹配</el-radio-button>
      </el-radio-group>
      <span v-else
        >上传到当前货品：{{
          props.lines[targetIndex]?.drawing_no || "未填写图号"
        }}</span
      >
      <ActionButton
        intent="upload"
        :disabled="loading"
        @click="drawingInput?.click()"
        >{{ sourceFiles.length ? "重新选择文件" : "选择文件" }}</ActionButton
      >
    </div>
    <p v-if="targetIndex < 0" class="drawing-import-help">
      {{
        drawingMode === "existing"
          ? "只匹配清单内图号，其余跳过。"
          : "未匹配图号会新增货品，稍后补齐资料。"
      }}
    </p>
    <p class="drawing-import-help">
      文件名与图号一致 · PDF / STP / STEP · 单份 ≤ 20MB
    </p>
    <el-alert
      v-if="drawings.length"
      :title="`上传 ${included.length} 份 · 新增 ${addedGoods} 项 · 跳过 ${skipped} 份`"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="invalid"
      title="预检发现问题，本批尚未上传。请调整文件后重新选择。"
      type="error"
      :closable="false"
    />
    <el-table v-if="drawings.length" :data="drawings" max-height="420" border>
      <el-table-column label="文件" min-width="220"
        ><template #default="{ row }">{{
          row.file.name
        }}</template></el-table-column
      ><el-table-column
        prop="drawing_no"
        label="匹配图号"
        min-width="170"
      /><el-table-column
        prop="action"
        label="处理方式"
        width="135"
      /><el-table-column
        prop="status"
        label="状态"
        width="100"
      /><el-table-column label="提示" min-width="220"
        ><template #default="{ row }"
          ><span :class="{ 'import-error': row.error || row.message }">{{
            row.error ||
            row.message ||
            (row.is_skipped
              ? "未匹配，已跳过"
              : row.action === "新增货品"
                ? "稍后补齐资料"
                : "")
          }}</span></template
        ></el-table-column
      >
    </el-table>
    <template #footer
      ><el-button :disabled="loading" @click="drawingVisible = false">{{
        hasUploaded ? "关闭" : "取消"
      }}</el-button
      ><el-button
        type="primary"
        :loading="loading"
        :disabled="invalid || !remaining"
        @click="uploadDrawings"
        >{{
          drawings.some((row) => row.status === "上传失败")
            ? "重试失败项"
            : "开始上传"
        }}</el-button
      ></template
    >
  </el-dialog>
</template>

<style scoped>
.quotation-imports {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quotation-imports > .el-button {
  margin-left: 0;
}

.import-error {
  color: var(--el-color-danger);
}

.drawing-import-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.drawing-import-help {
  color: var(--el-text-color-secondary);
}
</style>
