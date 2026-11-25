<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import {
  getMesDrawings,
  getMesDrawingHistory,
  saveMesDrawings,
  type MesDrawings,
  type MesDrawingRevision,
} from "@plugins/mes/web/src/api/mes";
import { hasPerms } from "@/utils/auth";
import { actionMessage, message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { formatMesDate } from "../shared";
import {
  drawingKind,
  selectProductDrawings,
  uploadProductDrawings,
  releaseProductDrawings,
  markProductDrawingsBound,
  type ProductDrawing,
} from "../work-orders/productDrawings";

const props = defineProps<{ orderId: string }>();
const emit = defineEmits<{ saved: [] }>();
type Drawing = Omit<ProductDrawing, "kind"> & {
  kind?: "pdf" | "model";
  url?: string;
};
type Kind = "pdf" | "model";
const kinds: Kind[] = ["pdf", "model"];
const data = ref<MesDrawings>();
const entries = ref<Drawing[]>([]);
const revision = ref(""),
  changeNote = ref("");
const loading = ref(false),
  saving = ref(false),
  error = ref("");
const saveFailed = ref(false);
const fileInput = ref<HTMLInputElement>(),
  selectedKind = ref<Kind>("pdf");
const historyOpen = ref<string[]>([]),
  history = ref<MesDrawingRevision[]>([]);
const historyPage = ref(1),
  historyTotal = ref(0),
  historyLoading = ref(false),
  historyError = ref("");
let request = 0,
  historyRequest = 0;
const canEdit = computed(
  () => !!data.value?.editable && hasPerms("mes:work_order:manage"),
);
const recognized = computed(
  () => entries.value.filter((row) => !!row.kind) as ProductDrawing[],
);
const dirty = computed(() => {
  if (!data.value) return false;
  const original = data.value.items.map((row) => row.id);
  return (
    entries.value.some((row) => !!row.raw) ||
    recognized.value.length !== original.length ||
    recognized.value.some((row) => !row.id || !original.includes(row.id)) ||
    revision.value.trim() !== (data.value.revision_label || "").trim()
  );
});
function group(kind: Kind) {
  return entries.value.filter((row) => row.kind === kind);
}
function originalGroup(kind: Kind): Drawing[] {
  return (data.value?.items || [])
    .filter((row) => drawingKind(row.file_name) === kind)
    .map((row) => ({
      name: row.file_name,
      id: row.id,
      url: row.url,
      size: row.file_size,
      kind,
    }));
}
function state(file: Drawing) {
  if (!file.raw) return data.value?.is_legacy ? "旧附件（未归档）" : "当前文件";
  return saving.value ? "正在更新" : "尚未更新成功";
}
function cleanup(rows = entries.value) {
  releaseProductDrawings(rows.filter((row) => !!row.kind) as ProductDrawing[]);
}
async function load() {
  saveFailed.value = false;
  const current = ++request;
  ++historyRequest;
  loading.value = true;
  error.value = "";
  cleanup();
  entries.value = [];
  data.value = undefined;
  history.value = [];
  historyTotal.value = 0;
  historyLoading.value = false;
  historyError.value = "";
  changeNote.value = "";
  const id = props.orderId;
  try {
    const result = await getMesDrawings(id);
    if (current !== request || id !== props.orderId) return;
    data.value = result.data;
    revision.value = result.data.revision_label || "";
    entries.value = result.data.items.map((row) => ({
      id: row.id,
      name: row.file_name,
      url: row.url,
      size: row.file_size,
      kind: drawingKind(row.file_name),
    }));
    if (historyOpen.value.includes("history")) await loadHistory(1);
  } catch (cause: any) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "图纸读取失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
async function refresh() {
  if (saving.value || loading.value) return;
  if (dirty.value || changeNote.value.trim()) {
    try {
      await ElMessageBox.confirm(
        "刷新将放弃尚未更新成功的文件，是否继续？",
        "刷新图纸",
        {
          type: "warning",
          confirmButtonText: "放弃修改并刷新",
          cancelButtonText: "继续编辑",
        },
      );
    } catch {
      return;
    }
  }
  await load();
}
function pick(kind: Kind) {
  if (!canEdit.value || saving.value) return;
  selectedKind.value = kind;
  fileInput.value?.click();
}
async function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  if (!canEdit.value || saving.value || !files.length) return;
  try {
    const kind = selectedKind.value;
    const selected = selectProductDrawings(
      files,
      kind,
      entries.value.filter((row) => row.kind && row.kind !== kind).length,
    );
    // Each upload replaces only its own slot. Do not implicitly retry another failed update.
    cleanup();
    entries.value = [
      ...originalGroup(kind === "pdf" ? "model" : "pdf"),
      ...selected,
    ];
    changeNote.value = `上传更新${kind === "pdf" ? "二维图纸" : "三维模型"}：${selected[0].name}`;
    saveFailed.value = false;
    await save();
  } catch (cause: any) {
    actionMessage(getHttpErrorMessage(cause, "图纸选择失败"), "warning");
  }
}
function undo(kind: Kind) {
  if (saving.value) return;
  cleanup(group(kind));
  entries.value = [
    ...entries.value.filter((row) => row.kind !== kind),
    ...originalGroup(kind),
  ];
  changeNote.value = "";
  saveFailed.value = false;
}
async function save() {
  if (saving.value || !canEdit.value || !data.value) return;
  if (kinds.some((kind) => group(kind).length > 1)) {
    actionMessage("请为当前货品选定一份 PDF 和一份 STP/STEP。原有多余文件会保留到历史版本。", "warning");
    return;
  }
  if (!dirty.value) {
    message("文件和图纸版次没有变化，无需保存新版本", { type: "warning" });
    return;
  }
  if (!recognized.value.length) {
    actionMessage("请先选择 PDF 图纸或 STP/STEP 模型", "warning");
    return;
  }
  if (!changeNote.value.trim()) {
    actionMessage("请填写本次变更说明", "warning");
    return;
  }
  saving.value = true;
  const current = request,
    id = props.orderId,
    draft = recognized.value;
  const label = revision.value.trim(),
    note = changeNote.value.trim(),
    version = data.value.version_no;
  try {
    const ids = await uploadProductDrawings(draft);
    if (current !== request || id !== props.orderId) {
      releaseProductDrawings(draft);
      return;
    }
    await saveMesDrawings(id, {
      version_no: version,
      revision_label: label,
      change_note: note,
      attachment_ids: ids,
    });
    markProductDrawingsBound(draft);
    if (current !== request || id !== props.orderId) return;
    message("文件已更新，旧文件保留在历史版本中", { type: "success" });
    emit("saved");
    await load();
  } catch (cause: any) {
    if (current === request) {
      saveFailed.value = true;
      actionMessage(
        getHttpErrorMessage(cause, "更新失败，原文件仍有效，可重试或重新选择文件"),
      );
    }
  } finally {
    saving.value = false;
  }
}
async function loadHistory(page = 1) {
  const current = ++historyRequest,
    id = props.orderId;
  historyLoading.value = true;
  historyError.value = "";
  try {
    const result = await getMesDrawingHistory(id, page);
    if (current !== historyRequest || id !== props.orderId) return;
    history.value = result.data.items;
    historyTotal.value = result.data.total;
    historyPage.value = page;
  } catch (cause: any) {
    if (current === historyRequest)
      historyError.value = getHttpErrorMessage(cause, "历史版本读取失败");
  } finally {
    if (current === historyRequest) historyLoading.value = false;
  }
}
watch(historyOpen, (value) => {
  if (value.includes("history")) loadHistory(1);
});
watch(() => props.orderId, load, { immediate: true });
onBeforeUnmount(() => {
  ++request;
  ++historyRequest;
  cleanup();
});
</script>
<template>
  <section v-loading="loading" class="drawings">
    <div class="heading">
      <div class="title">
        <h3>工单图纸</h3>
        <el-tag v-if="data" type="info">{{
          data.is_legacy
            ? "旧附件 · 尚未归档"
            : data.revision_no
              ? "当前 V" + data.revision_no
              : "尚未上传"
        }}</el-tag>
      </div>
      <el-button
        link
        :disabled="saving || loading"
        title="获取最新图纸和下载链接"
        @click="refresh"
        >刷新图纸</el-button
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <template v-if="data">
      <p v-if="!data.editable" class="muted">
        工单已执行或已结束，图纸已冻结，可查看当前及历史版本。
      </p>
      <el-alert
        v-if="data.is_legacy"
        title="以下文件来自原附件记录，图纸版本表尚无记录，不代表多个当前版本。首次更新时会归档原附件，保留历史下载记录。"
        type="info"
        :closable="false"
      />
      <div class="drawing-groups">
        <div v-for="kind in kinds" :key="kind" class="drawing-group">
          <div class="heading">
            <strong>{{
              kind === "pdf" ? "二维图纸 · PDF" : "三维模型 · STP / STEP"
            }}</strong>
            <el-button
              v-if="canEdit"
              class="drawing-action"
              size="default"
              :disabled="saving"
              @click="pick(kind)"
              >{{ group(kind).length ? "上传更新" : "上传文件" }}</el-button
            >
          </div>
          <p v-if="!group(kind).length" class="muted">尚未上传</p>
          <div
            v-for="file in group(kind)"
            :key="file.id || file.name"
            class="file-row"
          >
            <a
              v-if="file.url"
              :href="file.url"
              target="_blank"
              rel="noopener noreferrer"
              >{{ file.name }}</a
            >
            <span v-else>{{ file.name }}</span>
            <el-tag size="small" :type="file.raw ? 'warning' : 'info'">{{
              state(file)
            }}</el-tag>
            <el-button
              v-if="canEdit && file.raw"
              link
              :disabled="saving"
              @click="undo(kind)"
              >取消本次更新</el-button
            >
          </div>
        </div>
      </div>
      <input
        ref="fileInput"
        type="file"
        hidden
        :disabled="saving"
        :accept="selectedKind === 'pdf' ? '.pdf' : '.stp,.step'"
        @change="selectFiles"
      />
      <template v-if="canEdit">
        <p class="muted">
          每类最多一份，单文件不超过20MB。选中文件即上传并更新，另一类文件保持不变；PDF可预览，模型下载后查看。
        </p>
        <div v-if="saveFailed && dirty" class="retry-bar">
          <el-button
            class="drawing-action"
            size="default"
            type="primary"
            :loading="saving"
            @click="save"
            >重试更新</el-button
          >
        </div>
      </template>
      <el-collapse v-model="historyOpen" class="history">
        <el-collapse-item name="history" title="历史版本">
          <div v-loading="historyLoading">
            <el-alert
              v-if="historyError"
              :title="historyError"
              type="error"
              :closable="false"
              ><el-button link type="primary" @click="loadHistory(historyPage)"
                >重试</el-button
              ></el-alert
            >
            <p
              v-if="!history.length && !historyLoading && !historyError"
              class="muted"
            >
              暂无已归档修订
            </p>
            <article v-for="row in history" :key="row.id" class="history-row">
              <div class="heading">
                <strong
                  >V{{ row.revision_no
                  }}{{
                    row.revision_no === data.revision_no ? "（当前）" : ""
                  }}
                  · 图纸版次 {{ row.revision_label || "未标注" }}</strong
                >
                <span class="muted"
                  >{{ row.created_by_name }} ·
                  {{ formatMesDate(row.created_at) }}</span
                >
              </div>
              <p class="change-note">{{ row.change_note }}</p>
              <a
                v-for="file in row.items"
                :key="file.id"
                class="history-file"
                :href="file.url"
                target="_blank"
                rel="noopener noreferrer"
                >{{ file.file_name }}</a
              >
            </article>
            <ListPagination
              v-if="historyTotal > 5"
              small
              layout="prev, pager, next"
              :page-size="5"
              :total="historyTotal"
              :current-page="historyPage"
              @current-change="loadHistory"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>
  </section>
</template>
<style scoped>
.drawings {
  padding: 16px;
  margin: 24px 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.heading,
.title,
.file-row,
.retry-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.heading,
.retry-bar {
  justify-content: space-between;
}

h3 {
  margin: 0;
}

.drawing-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.drawing-group {
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.file-row {
  margin-top: 14px;
}

.file-row > a,
.file-row > span:first-child {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

a {
  color: var(--el-color-primary);
  overflow-wrap: anywhere;
}

.muted {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}

.drawing-action {
  min-width: 96px;
}

.retry-bar {
  margin: 14px 0;
}

.history-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.change-note {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.history-file {
  display: inline-block;
  margin: 0 16px 8px 0;
}

@media (width <= 760px) {
  .drawing-groups {
    grid-template-columns: 1fr;
  }
}
</style>
