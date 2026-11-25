<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import { Document, Paperclip } from "@element-plus/icons-vue";
import {
  getMesReportingTask,
  actMesReportingTask,
  submitMesWebReport,
  type MesTaskDetail,
  type MesReportBody,
} from "@plugins/mes/web/src/api/mes";
import { uploadFile, discardFile } from "@/api/systemFile";
import { message, actionMessage } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { formatMesDate, mesDispatchPersonLabel } from "../shared";
const props = defineProps<{ taskId?: string }>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ changed: [] }>();
const detail = ref<MesTaskDetail>(),
  loading = ref(false),
  busy = ref(false),
  error = ref("");
const form = reactive({
  good_quantity: 0,
  scrap_quantity: 0,
  rework_quantity: 0,
  labor_minutes: undefined as number | undefined,
  machine_minutes: undefined as number | undefined,
  exception_type_code: "",
  note: "",
});
const countUnits = new Set([
  "piece", "branch", "box", "pack", "set", "ream", "bottle",
]);
const maxFiles = 20;
const maxFileBytes = 2 * 1024 * 1024;
const attachmentExtensions = [
  "jpg", "jpeg", "png", "webp", "pdf", "doc", "docx", "xls", "xlsx",
];
const attachmentAccept = attachmentExtensions
  .map((extension) => `.${extension}`)
  .join(",");
const imageExtensions = new Set(["jpg", "jpeg", "png", "webp"]);
const attachmentInput = ref<HTMLInputElement>();
const isDragging = ref(false);
const attachments = ref<
  {
    key: number;
    raw: File;
    id?: string;
    previewUrl?: string;
    status: "ready" | "uploading" | "uploaded" | "failed";
  }[]
>([]);
let nextAttachmentKey = 0;
let request = 0,
  lastPayload = "",
  idempotencyKey = "";
const canExecute = computed(
  () =>
    detail.value &&
    ["released", "in_progress"].includes(detail.value.work_order_status_code),
);
const remaining = computed(() =>
  detail.value?.schedule_context
    ? detail.value.schedule_context.remaining_quantity
    : detail.value
      ? Math.max(
          0,
          detail.value.planned_quantity -
            detail.value.good_quantity -
            detail.value.scrap_quantity -
            detail.value.rework_quantity,
        )
      : 0,
);
const wholeQuantity = computed(
  () =>
    countUnits.has(detail.value?.unit_name ?? "") &&
    Number.isInteger(remaining.value),
);
const cannotAddFiles = computed(
  () => busy.value || attachments.value.length >= maxFiles,
);
const attachmentStatusLabels = {
  ready: "待上传",
  uploading: "上传中",
  uploaded: "已上传",
  failed: "上传失败",
} as const;

function reset({ discardAttachments = true } = {}) {
  for (const file of attachments.value) {
    if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
    if (discardAttachments && file.id)
      discardFile(file.id).catch(() => undefined);
  }
  attachments.value = [];
  isDragging.value = false;
  Object.assign(form, {
    good_quantity: 0,
    scrap_quantity: 0,
    rework_quantity: 0,
    labor_minutes: undefined,
    machine_minutes: undefined,
    exception_type_code: "",
    note: "",
  });
  lastPayload = "";
  idempotencyKey = "";
}
async function load() {
  const current = ++request;
  error.value = "";
  loading.value = true;
  try {
    const result = await getMesReportingTask(props.taskId);
    if (current === request) detail.value = result.data;
  } catch (cause: any) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "任务读取失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  addAttachments(Array.from(input.files ?? []));
  input.value = "";
}
function addAttachments(incoming: File[]) {
  if (busy.value || !incoming.length) return;
  const before = attachments.value.length;
  let firstIssue = "";
  for (const raw of incoming) {
    if (attachments.value.length >= maxFiles) {
      firstIssue ||= `最多添加 ${maxFiles} 个附件`;
      break;
    }
    const extension = raw.name.split(".").pop()?.toLowerCase() ?? "";
    if (!raw.name.includes(".") || !attachmentExtensions.includes(extension)) {
      firstIssue ||= `「${raw.name}」的格式不支持`;
      continue;
    }
    if (!raw.size || raw.size > maxFileBytes) {
      firstIssue ||= `「${raw.name}」为空文件或超过 2 MB`;
      continue;
    }
    attachments.value.push({
      key: ++nextAttachmentKey,
      raw,
      previewUrl: imageExtensions.has(extension)
        ? URL.createObjectURL(raw)
        : undefined,
      status: "ready",
    });
  }
  if (firstIssue) {
    const rejected = incoming.length - (attachments.value.length - before);
    message(`有 ${rejected} 个附件未添加。${firstIssue}`, { type: "warning" });
  }
}
function dragAttachments(event: DragEvent) {
  if (!event.dataTransfer?.types.includes("Files")) return;
  isDragging.value = !cannotAddFiles.value;
  event.dataTransfer.dropEffect = isDragging.value ? "copy" : "none";
}
function leaveAttachmentZone(event: DragEvent) {
  const zone = event.currentTarget as HTMLElement;
  if (!(event.relatedTarget instanceof Node && zone.contains(event.relatedTarget))) {
    isDragging.value = false;
  }
}
function dropAttachments(event: DragEvent) {
  isDragging.value = false;
  addAttachments(Array.from(event.dataTransfer?.files ?? []));
}
function removeAttachment(index: number) {
  if (busy.value) return;
  const [file] = attachments.value.splice(index, 1);
  if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
  if (file.id) discardFile(file.id).catch(() => undefined);
}
async function action(action: "track-in" | "hold" | "release" | "track-out") {
  if (busy.value || !detail.value) return;
  busy.value = true;
  const current = request;
  try {
    if (action === "track-out")
      await ElMessageBox.confirm(
        "确认结束本次执行？数量未达到计划时，任务会回到待执行；需要检验的任务会进入待检验。",
        "结束执行",
        {
          type: "warning",
          confirmButtonText: "确认结束",
          cancelButtonText: "取消",
        },
      );
    const result = await actMesReportingTask(detail.value.id, action, {
      version_no: detail.value.version_no,
      execution_id: detail.value.current_execution?.id,
      production_phase_code:
        detail.value.schedule_context?.production_phase_code,
      production_person_id:
        detail.value.schedule_context?.production_person_id || undefined,
    });
    if (current === request) {
      detail.value = result.data;
      emit("changed");
    }
  } catch (cause: any) {
    if (!["cancel", "close"].includes(cause))
      actionMessage(getHttpErrorMessage(cause, "操作失败，请刷新任务后重试"));
  } finally {
    busy.value = false;
  }
}
async function changeStage(
  stage: "load" | "run" | "unload" | "external_return",
) {
  if (!detail.value || !detail.value.current_execution || busy.value) return;
  busy.value = true;
  try {
    const result = await actMesReportingTask(detail.value.id, "stage", {
      version_no: detail.value.version_no,
      execution_id: detail.value.current_execution.id,
      segment_type_code: stage,
    });
    detail.value = result.data;
    emit("changed");
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "实际阶段切换失败"));
  } finally {
    busy.value = false;
  }
}
async function submit() {
  if (
    busy.value ||
    !detail.value ||
    !canExecute.value ||
    detail.value.status_code !== "in_progress"
  )
    return;
  const quantities = {
    good_quantity: form.good_quantity ?? 0,
    scrap_quantity: form.scrap_quantity ?? 0,
    rework_quantity: form.rework_quantity ?? 0,
  };
  const { good_quantity, scrap_quantity, rework_quantity } = quantities;
  if (wholeQuantity.value && !Object.values(quantities).every(Number.isInteger)) {
    message("请填写整数报工数量", { type: "warning" });
    return;
  }
  const quantity = good_quantity + scrap_quantity + rework_quantity;
  const previousAttempt =
    JSON.stringify({
      ...form,
      ...quantities,
      execution_id: detail.value.current_execution?.id,
      attachment_ids: attachments.value.map((file) => file.id),
    }) === lastPayload && !!idempotencyKey;
  const isRework = !!detail.value.schedule_context?.is_rework;
  if (isRework && quantity === 0) {
    if (!(Number(form.labor_minutes) > 0 || Number(form.machine_minutes) > 0)) {
      message("请填写本次返工的实际人工工时或机器工时（分钟）", {
        type: "warning",
      });
      return;
    }
  } else if (
    isRework ||
    !(quantity > 0) ||
    (quantity > remaining.value && !previousAttempt)
  ) {
    message("请填写大于零且不超过工序剩余数量的报工数量", { type: "warning" });
    return;
  }
  busy.value = true;
  const current = request;
  try {
    for (const file of attachments.value) {
      if (file.id) continue;
      file.status = "uploading";
      try {
        file.id = (await uploadFile(file.raw, "production_report")).id;
      } catch (cause) {
        if (current === request) {
          file.status = "failed";
          const reason = getHttpErrorMessage(cause, "请重试，或移除该附件后提交");
          actionMessage(`无法上传「${file.raw.name}」。${reason}`);
        }
        return;
      }
      if (current !== request) {
        discardFile(file.id).catch(() => undefined);
        return;
      }
      file.status = "uploaded";
    }
    const facts = {
      ...form,
      ...quantities,
      execution_id: detail.value.current_execution?.id,
      attachment_ids: attachments.value.map((file) => file.id),
    };
    const fingerprint = JSON.stringify(facts);
    if (lastPayload !== fingerprint) {
      lastPayload = fingerprint;
      idempotencyKey = crypto.randomUUID();
    }
    const result = await submitMesWebReport(detail.value.id, {
      ...facts,
      version_no: detail.value.version_no,
      idempotency_key: idempotencyKey,
    } as MesReportBody);
    if (current !== request) return;
    detail.value = result.data;
    reset({ discardAttachments: false });
    message("报工已提交", { type: "success" });
    emit("changed");
  } catch (cause: any) {
    actionMessage(getHttpErrorMessage(cause, "报工提交失败，内容已保留，可使用同一请求重试"));
  } finally {
    busy.value = false;
  }
}
watch(
  () => [visible.value, props.taskId],
  () => {
    ++request;
    detail.value = undefined;
    reset();
    if (visible.value && props.taskId) load();
  },
);
onBeforeUnmount(() => {
  ++request;
  reset();
});
</script>
<template>
  <el-drawer
    v-model="visible"
    title="手动报工 / 生产执行"
    size="min(820px, 97vw)"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    append-to-body
    destroy-on-close
  >
    <section v-loading="loading">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      /><el-button :disabled="busy" @click="load">刷新任务</el-button>
      <template v-if="detail"
        ><h2>{{ detail.work_order_no }} · {{ detail.operation_name }}</h2>
        <p>{{ detail.product_item_name }} · {{ detail.status_label }}</p>
        <p v-if="detail.assigned_production_person_id && !detail.schedule_plan_id">
          派工人员：{{ mesDispatchPersonLabel(detail) }}
        </p>
        <el-alert
          v-if="detail.schedule_context"
          :closable="false"
          :type="detail.schedule_context.reason ? 'warning' : 'info'"
          :title="`${detail.schedule_context.phase_label} · 本批次${detail.schedule_context.planned_quantity}${detail.unit_name}${detail.schedule_context.production_person_id ? ' · 安排人员：' + (detail.schedule_context.production_person_name || '姓名未维护') : ''}`"
        >
          <p>
            {{
              detail.schedule_context.reason ||
              `方案：${detail.schedule_context.plan_no}，按首件及剩余批量分别报工。`
            }}
          </p>
          <p v-if="detail.schedule_context.planned_start_at">
            本批次计划开始：{{
              formatMesDate(detail.schedule_context.planned_start_at)
            }}
          </p>
          <p v-if="detail.schedule_context.is_rework">
            当前为返工复作，保留原数量，不重复计产；完成后重新提交检验。
          </p>
        </el-alert>
        <el-descriptions :column="2" border
          ><el-descriptions-item label="计划"
            >{{ detail.planned_quantity }}
            {{ detail.unit_name }}</el-descriptions-item
          ><el-descriptions-item label="剩余可报"
            >{{ remaining }} {{ detail.unit_name }}</el-descriptions-item
          ><el-descriptions-item label="合格 / 报废 / 返工"
            >{{ detail.good_quantity }} / {{ detail.scrap_quantity }} /
            {{ detail.rework_quantity }}</el-descriptions-item
          ><el-descriptions-item label="本次开工">{{
            formatMesDate(detail.current_execution?.tracked_in_at)
          }}</el-descriptions-item></el-descriptions
        >
        <p>{{ detail.operation_description || "暂无工艺说明" }}</p>
        <div v-if="canExecute" class="actions">
          <el-button
            v-if="['pending', 'dispatched'].includes(detail.status_code)"
            type="primary"
            :loading="busy"
            :disabled="
              !!detail.schedule_context && !detail.schedule_context.can_start
            "
            @click="action('track-in')"
            >{{
              detail.schedule_context?.execution_kind_code === "external"
                ? "登记委外发出"
                : "开始生产"
            }}</el-button
          ><el-button
            v-if="detail.status_code === 'in_progress'"
            :disabled="busy"
            @click="action('hold')"
            >暂停</el-button
          ><el-button
            v-if="detail.status_code === 'paused' && detail.current_execution"
            :loading="busy"
            @click="action('release')"
            >恢复生产</el-button
          ><el-button
            v-if="
              ['in_progress', 'paused'].includes(detail.status_code) &&
              detail.current_execution
            "
            :disabled="busy"
            @click="action('track-out')"
            >结束本次执行</el-button
          >
        </div>
        <div
          v-if="
            detail.schedule_context?.execution_kind_code === 'external' &&
            detail.status_code === 'in_progress' &&
            detail.current_execution
          "
          class="actions"
        >
          <el-tag type="warning">{{
            detail.current_execution.segment_type_code === "external_wait"
              ? "委外待回厂"
              : "已回厂，填写产量后结束并提交检验"
          }}</el-tag
          ><el-button
            v-if="
              detail.current_execution.segment_type_code === 'external_wait'
            "
            type="primary"
            :loading="busy"
            @click="changeStage('external_return')"
            >确认实际回厂</el-button
          >
        </div>
        <div
          v-if="
            detail.schedule_context?.execution_kind_code === 'machine' &&
            detail.status_code === 'in_progress' &&
            detail.current_execution
          "
          class="actions"
        >
          <el-tag
            >实际阶段：{{
              detail.current_execution.segment_type_code === "load"
                ? "装料/人工操作"
                : detail.current_execution.segment_type_code === "run"
                  ? "自动加工"
                  : "卸料"
            }}</el-tag
          >
          <el-button
            v-if="detail.current_execution.segment_type_code === 'load'"
            type="primary"
            :disabled="busy"
            @click="changeStage('run')"
            >进入自动加工</el-button
          >
          <el-button
            v-if="
              detail.current_execution.segment_type_code === 'run' &&
              detail.schedule_context.unload_minutes > 0
            "
            :disabled="busy"
            @click="changeStage('unload')"
            >开始卸料</el-button
          >
          <el-button
            v-if="
              detail.current_execution.segment_type_code === 'unload' &&
              detail.schedule_context.planned_quantity > 1 &&
              remaining > 0
            "
            :disabled="busy"
            @click="
              changeStage(detail.schedule_context.load_minutes ? 'load' : 'run')
            "
            >开始下一件</el-button
          >
        </div>
        <el-form
          v-if="
            canExecute &&
            detail.status_code === 'in_progress' &&
            detail.current_execution?.segment_type_code !== 'external_wait' &&
            (remaining > 0 || detail.schedule_context?.is_rework)
          "
          :disabled="busy"
          label-position="top"
          ><h3>提交现场报工</h3>
          <div class="grid">
            <el-form-item
              v-for="item in [
                { key: 'good_quantity', label: '合格数量' },
                { key: 'scrap_quantity', label: '报废数量' },
                { key: 'rework_quantity', label: '返工数量' },
              ]"
              :key="item.key"
              :label="item.label"
              ><el-input-number
                v-model="form[item.key]"
                :disabled="!!detail.schedule_context?.is_rework"
                :min="0"
                :step="wholeQuantity ? 1 : 0.001"
                :precision="wholeQuantity ? 0 : 3"
                :step-strictly="wholeQuantity"
                :inputmode="wholeQuantity ? 'numeric' : 'decimal'"
                :value-on-clear="0" /></el-form-item
            ><el-form-item label="人工工时（分钟）"
              ><el-input-number
                v-model="form.labor_minutes"
                :min="0"
                :precision="3"
                :controls="false" /></el-form-item
            ><el-form-item label="机器工时（分钟）"
              ><el-input-number
                v-model="form.machine_minutes"
                :min="0"
                :precision="3"
                :controls="false" /></el-form-item
            ><el-form-item label="异常类型"
              ><el-select v-model="form.exception_type_code" clearable
                ><el-option label="缺料" value="material_shortage" /><el-option
                  label="设备故障"
                  value="equipment_failure" /><el-option
                  label="质量异常"
                  value="quality_abnormal" /><el-option
                  label="换型"
                  value="changeover" /><el-option
                  label="其他"
                  value="other" /></el-select
            ></el-form-item>
          </div>
          <el-form-item label="现场说明"
            ><el-input
              v-model="form.note"
              type="textarea"
              :rows="2"
              maxlength="1000" />
          </el-form-item>
          <el-form-item label="现场附件" class="attachment-form-item">
            <div class="attachment-field">
              <input
                ref="attachmentInput"
                hidden
                type="file"
                multiple
                :disabled="cannotAddFiles"
                :accept="attachmentAccept"
                @change="selectFiles"
              />
              <div
                class="attachment-dropzone"
                :class="{ 'is-dragging': isDragging }"
                @dragover.prevent="dragAttachments"
                @dragleave="leaveAttachmentZone"
                @drop.prevent="dropAttachments"
              >
                <button
                  type="button"
                  class="attachment-picker"
                  :disabled="cannotAddFiles"
                  @click="attachmentInput?.click()"
                >
                  <el-icon aria-hidden="true"><Paperclip /></el-icon>
                  <span class="attachment-picker-label">添加照片或文档</span>
                  <span class="attachment-drag-hint">支持拖拽</span>
                </button>
              </div>
              <div class="attachment-meta">
                <span>JPG、PNG、WebP、PDF、Word、Excel · 单个最多 2 MB</span>
                <span aria-live="polite">{{ attachments.length ? `已选 ${attachments.length} / ${maxFiles} 个` : `最多 ${maxFiles} 个` }}</span>
              </div>
              <ul v-if="attachments.length" class="attachment-list">
                <li v-for="(file, index) in attachments" :key="file.key" class="attachment-row">
                  <img v-if="file.previewUrl" class="attachment-thumbnail" :src="file.previewUrl" alt="" />
                  <span v-else class="attachment-document-icon" aria-hidden="true">
                    <el-icon><Document /></el-icon>
                  </span>
                  <div class="attachment-file">
                    <span class="attachment-name" :title="file.raw.name">{{ file.raw.name }}</span>
                    <span class="attachment-size">
                      {{ file.raw.size >= 1024 * 1024 ? `${(file.raw.size / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(file.raw.size / 1024)} KB` }}
                    </span>
                  </div>
                  <el-tag
                    size="small"
                    :type="file.status === 'failed' ? 'danger' : file.status === 'uploaded' ? 'success' : file.status === 'uploading' ? 'primary' : 'info'"
                    aria-live="polite"
                  >{{ attachmentStatusLabels[file.status] }}</el-tag>
                  <el-button
                    type="danger"
                    plain
                    size="small"
                    :aria-label="`移除附件 ${file.raw.name}`"
                    @click="removeAttachment(index)"
                  >移除</el-button>
                </li>
              </ul>
            </div>
          </el-form-item>
          <div class="erp-form-actions">
            <el-button type="primary" :loading="busy" @click="submit">提交报工</el-button>
          </div>
        </el-form
        >
        <el-alert
          v-else
          :title="
            canExecute
              ? remaining <= 0 &&
                detail.is_quality_required &&
                detail.status_code === 'in_progress'
                ? '已报足计划数量。返工不重复提交产量；完成复作后结束本次执行，再到工序检验提交复检。'
                : '请先开始生产；待检验任务请到执行与报工 → 工序检验处理。'
              : '工单未发布、已暂停或已结束，当前不能报工。'
          "
          type="info"
          :closable="false"
      /></template>
    </section>
  </el-drawer>
</template>
<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 20px 0;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0 16px;
}

.el-input-number {
  width: 100%;
}

.attachment-form-item {
  margin-bottom: 0;
}

.attachment-field {
  width: 100%;
  min-width: 0;
  line-height: 1.45;
}

.attachment-dropzone {
  border-radius: var(--el-border-radius-base);
}

.attachment-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  width: 100%;
  min-height: 44px;
  padding: 9px 12px;
  border: 1px dashed var(--el-border-color);
  border-radius: inherit;
  background: var(--el-fill-color-blank);
  color: var(--el-color-primary);
  text-align: left;
}

.attachment-picker:not(:disabled) {
  cursor: pointer;
}

.attachment-picker:not(:disabled):hover,
.attachment-dropzone.is-dragging .attachment-picker {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.attachment-picker:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.attachment-picker:disabled {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-disabled);
  pointer-events: none;
}

.attachment-picker-label {
  flex: 1;
  font-weight: 500;
}

.attachment-picker .el-icon {
  font-size: 16px;
}

.attachment-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 2px 12px;
  margin-top: 6px;
}

.attachment-meta,
.attachment-drag-hint,
.attachment-size {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.attachment-list {
  padding: 0;
  margin: 8px 0 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  list-style: none;
}

.attachment-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  padding: 8px;
}

.attachment-row + .attachment-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

.attachment-document-icon,
.attachment-thumbnail {
  width: 32px;
  height: 32px;
  border-radius: var(--el-border-radius-base);
}

.attachment-document-icon {
  display: grid;
  place-items: center;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 16px;
}

.attachment-thumbnail {
  object-fit: cover;
}

.attachment-file {
  display: grid;
  gap: 2px;
}

.attachment-name {
  overflow: hidden;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
