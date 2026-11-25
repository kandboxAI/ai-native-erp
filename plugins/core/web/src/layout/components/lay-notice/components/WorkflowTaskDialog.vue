<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getFileUrl } from "@/api/systemFile";
import {
  completeWorkflowTask,
  getWorkflowTaskDetail,
  rejectWorkflowTask,
  type WorkflowBusinessDetailTable,
  type WorkflowTaskDetail
} from "@/api/workflowTask";
import { getHttpErrorMessage } from "@/utils/http";
import {
  isWorkflowActionTimeout,
  workflowActionErrorMessage
} from "@/utils/workflowAction";
import { emitter } from "@/utils/mitt";
import WorkflowApprovalProgress from "@/components/workflow/WorkflowApprovalProgress.vue";
import WorkflowContractPreview from "@/components/workflow/WorkflowContractPreview.vue";
import MarkdownPreview from "@/components/MarkdownPreview/index.vue";
import MarkdownComparison from "@/components/MarkdownComparison/index.vue";

export type WorkflowTaskDialogFallback = {
  id?: string | null;
  task_id?: string | null;
  task_key?: string | null;
  task_name?: string | null;
  business_type?: string | null;
  business_summary?: string | null;
  text?: string | null;
  arrived_at?: string | null;
  time?: string | null;
  route?: string | null;
};

type WorkflowAttachmentCellItem = {
  name?: string | null;
  url?: string | null;
  content_type?: string | null;
};

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    taskId?: string | null;
    fallbackTask?: WorkflowTaskDialogFallback | null;
    requireComment?: boolean;
    secondaryActionLabel?: string;
  }>(),
  {
    taskId: null,
    fallbackTask: null,
    requireComment: false,
    secondaryActionLabel: ""
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "success"): void;
  (
    e: "secondary",
    query?: Record<string, string>,
    task?: WorkflowTaskDetail
  ): void;
  (e: "closed"): void;
}>();

const todoDetailLoading = ref(false);
const todoActionLoading = ref(false);
const todoDetail = ref<WorkflowTaskDetail | null>(null);
const approvalComment = ref("");

async function openOriginal(fileId: string) {
  try {
    const result = await getFileUrl(fileId);
    window.open(result.data.url, "_blank", "noopener,noreferrer");
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "无法打开原件"));
  }
}

const resolvedTaskId = computed(
  () =>
    props.taskId || props.fallbackTask?.id || props.fallbackTask?.task_id || ""
);
const todoBusinessFields = computed(() =>
  (todoDetail.value?.business_detail?.fields ?? []).map(field => ({
    ...field,
    value:
      field.type === "markdown" || field.type === "markdown_diff"
        ? field.value
        : ["avatar", "image"].includes(field.type || "")
          ? displayValue(field.value)
          : formatBusinessValue(field.label, field.value)
  }))
);
const todoMarkdownFields = computed(() =>
  todoBusinessFields.value.filter(
    field => field.type === "markdown" || field.type === "markdown_diff"
  )
);
const hasMarkdown = computed(() => todoMarkdownFields.value.length > 0);
const todoSummary = computed(
  () =>
    todoDetail.value?.business_summary ||
    props.fallbackTask?.business_summary ||
    props.fallbackTask?.text
);
const todoMetadataFields = computed(() =>
  todoBusinessFields.value.filter(
    field =>
      !todoMarkdownFields.value.includes(field) &&
      (!hasMarkdown.value || field.label !== "冻结内容哈希")
  )
);
const todoContentHash = computed(() =>
  todoBusinessFields.value.find(field => field.label === "冻结内容哈希")
);
const todoBusinessTables = computed(
  () =>
    (todoDetail.value?.business_detail?.tables ??
      []) as WorkflowBusinessDetailTable[]
);
const todoBusinessContract = computed(
  () => todoDetail.value?.business_detail?.contract ?? null
);
const todoBusinessTypeDisplay = computed(() =>
  businessTypeLabel(
    todoDetail.value?.business_type_code || props.fallbackTask?.business_type
  )
);
const dialogWidth = computed(() =>
  todoBusinessTables.value.length || hasMarkdown.value
    ? "min(960px, 94vw)"
    : todoBusinessContract.value
      ? "920px"
      : "720px"
);

function businessTypeLabel(type?: string | null) {
  if (!type) return "—";
  return type;
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function formatBusinessValue(_label: string, value: unknown) {
  const raw = displayValue(value);
  if (raw === "—") return raw;
  return raw;
}

function formatDetailTime(value?: string | null) {
  return value ? value.replace("T", " ").slice(0, 19) : "—";
}

function isAttachmentCell(label: string, value: unknown) {
  return label === "附件" && Array.isArray(value);
}

function attachmentItems(value: unknown): WorkflowAttachmentCellItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is WorkflowAttachmentCellItem =>
        Boolean(item) &&
        typeof item === "object" &&
        typeof (item as WorkflowAttachmentCellItem).url === "string" &&
        Boolean((item as WorkflowAttachmentCellItem).url?.trim())
    )
    .map(item => ({
      ...item,
      name: item.name?.trim() || "附件",
      url: item.url?.trim() || ""
    }));
}

function isImageAttachment(file: WorkflowAttachmentCellItem) {
  const contentType = String(file.content_type || "").toLowerCase();
  if (contentType.startsWith("image/")) return true;
  const url = String(file.url || "")
    .split("?", 1)[0]
    .toLowerCase();
  const name = String(file.name || "").toLowerCase();
  return (
    /\.(jpe?g|png|webp|gif|bmp|svg)$/.test(url) ||
    /\.(jpe?g|png|webp|gif|bmp|svg)$/.test(name)
  );
}

function attachmentImageUrls(value: unknown) {
  return attachmentItems(value)
    .filter(file => file.url && isImageAttachment(file))
    .map(file => file.url as string);
}

function attachmentImageIndex(
  value: unknown,
  file: WorkflowAttachmentCellItem
) {
  return Math.max(0, attachmentImageUrls(value).indexOf(file.url || ""));
}

async function loadDetail() {
  const taskId = resolvedTaskId.value;
  if (!taskId) {
    ElMessage.warning("无法打开该待办详情");
    emit("update:modelValue", false);
    return;
  }
  todoDetail.value = null;
  approvalComment.value = "";
  todoDetailLoading.value = true;
  try {
    const res = await getWorkflowTaskDetail(taskId);
    if (res.code !== 0) throw new Error(res.message || "加载待办详情失败");
    todoDetail.value = res.data;
  } catch (e: unknown) {
    ElMessage.error(getHttpErrorMessage(e, "加载待办详情失败"));
    emit("update:modelValue", false);
  } finally {
    todoDetailLoading.value = false;
  }
}

function onClosed() {
  todoDetail.value = null;
  approvalComment.value = "";
  emit("closed");
}

function actionComment(action: "complete" | "reject") {
  const text = approvalComment.value.trim();
  if ((props.requireComment || action === "reject") && !text) {
    ElMessage.warning(
      action === "reject" ? "请填写驳回原因" : "请填写审批意见"
    );
    return null;
  }
  return text || undefined;
}

async function handleTodoAction(action: "complete" | "reject") {
  if (todoActionLoading.value) return;
  const taskId = todoDetail.value?.id || resolvedTaskId.value;
  if (!taskId) return;
  const comment = actionComment(action);
  if (comment === null) return;

  todoActionLoading.value = true;
  try {
    const res =
      action === "complete"
        ? await completeWorkflowTask(taskId, comment)
        : await rejectWorkflowTask(taskId, comment);
    if (res.code !== 0) throw new Error(res.message || "操作失败");
    ElMessage.success(action === "complete" ? "已同意" : "已驳回");
    emitter.emit("workflowBusinessChanged", {
      business_type:
        todoDetail.value?.business_type_code ||
        props.fallbackTask?.business_type ||
        "",
      business_id: todoDetail.value?.business_id || undefined,
      instance_status:
        typeof res.data?.instance_status_code === "string"
          ? res.data.instance_status_code
          : undefined
    });
    emit("update:modelValue", false);
    emit("success");
  } catch (e: unknown) {
    ElMessage.error(workflowActionErrorMessage(e));
    if (isWorkflowActionTimeout(e)) await loadDetail();
  } finally {
    todoActionLoading.value = false;
  }
}

watch(
  () => [props.modelValue, resolvedTaskId.value] as const,
  ([visible]) => {
    if (visible) void loadDetail();
  },
  // 待办链接进入页面时，弹窗首次挂载就可能已经打开。
  { immediate: true }
);
</script>

<template>
  <el-dialog
    :model-value="props.modelValue"
    :title="hasMarkdown && todoSummary ? `${todoSummary} 审核` : '待办审批'"
    :width="dialogWidth"
    :top="hasMarkdown ? '5vh' : undefined"
    :class="{ 'markdown-review-dialog': hasMarkdown }"
    class="todo-detail-dialog"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <div v-loading="todoDetailLoading">
      <template v-if="todoDetail || props.fallbackTask">
        <component
          :is="hasMarkdown ? 'details' : 'div'"
          class="todo-detail-section"
        >
          <summary v-if="hasMarkdown" class="todo-detail-section-title">
            流程详情
          </summary>
          <div v-else class="todo-detail-section-title">流程信息</div>
          <el-descriptions
            :column="2"
            border
            size="small"
            class="todo-detail-desc"
          >
            <el-descriptions-item label="业务类型">
              {{ todoBusinessTypeDisplay }}
            </el-descriptions-item>
            <el-descriptions-item label="审批节点">
              {{
                todoDetail?.task_name ||
                props.fallbackTask?.task_name ||
                todoDetail?.task_key ||
                props.fallbackTask?.task_key ||
                "—"
              }}
            </el-descriptions-item>
            <el-descriptions-item label="到达时间">
              {{
                formatDetailTime(
                  props.fallbackTask?.arrived_at || props.fallbackTask?.time
                )
              }}
            </el-descriptions-item>
            <el-descriptions-item label="任务状态">
              {{
                todoDetail?.status_code === "pending"
                  ? "待处理"
                  : todoDetail?.status_code || "—"
              }}
            </el-descriptions-item>
            <el-descriptions-item :span="2" label="业务摘要">
              {{ todoSummary || "—" }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="hasMarkdown && todoContentHash"
              :span="2"
              :label="todoContentHash.label"
            >
              <span class="content-hash">{{ todoContentHash.value }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </component>

        <div v-if="todoMetadataFields.length" class="todo-detail-section">
          <div class="todo-detail-section-title">业务详情</div>
          <el-descriptions
            :column="2"
            border
            size="small"
            class="todo-detail-desc"
          >
            <el-descriptions-item
              v-for="field in todoMetadataFields"
              :key="field.label"
              :label="field.label"
              :span="
                hasMarkdown &&
                [
                  '审核说明',
                  '变更原因',
                  '当前读取许可对象',
                  '读取范围说明'
                ].includes(field.label)
                  ? 2
                  : 1
              "
            >
              <el-avatar v-if="field.type === 'avatar'" :src="field.value === '—' ? undefined : field.value" :size="56" />
              <el-image
                v-else-if="field.type === 'image' && field.value !== '—'"
                :src="field.value"
                :preview-src-list="[field.value]"
                fit="cover"
                class="todo-field-photo"
              />
              <template v-else-if="field.file_id">
                <span>{{ field.value }}</span>
                <el-button
                  link
                  type="primary"
                  @click="openOriginal(field.file_id)"
                >
                  下载查看原件
                </el-button>
              </template>
              <span v-else>{{ field.value }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <section
          v-for="field in todoMarkdownFields"
          :key="field.label"
          class="todo-detail-section"
        >
          <h3 class="todo-detail-section-title">{{ field.label }}</h3>
          <MarkdownComparison
            v-if="field.type === 'markdown_diff'"
            :old-content="field.old_value ?? null"
            :new-content="field.value"
            :old-label="field.old_label"
            :new-label="field.label"
            :unavailable-reason="field.unavailable_reason"
            review
          />
          <MarkdownPreview v-else :content="field.value || ''" />
        </section>

        <div v-if="todoBusinessContract" class="todo-detail-section">
          <WorkflowContractPreview :contract="todoBusinessContract" />
        </div>

        <div
          v-for="(table, idx) in todoBusinessTables"
          :key="idx"
          class="todo-detail-section"
        >
          <div class="todo-detail-section-title">{{ table.title }}</div>
          <el-table
            :data="table.rows"
            border
            size="small"
            max-height="240"
            class="todo-detail-table"
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
                <template v-if="isAttachmentCell(col.label, row[col.prop])">
                  <div
                    v-if="attachmentItems(row[col.prop]).length"
                    class="todo-attachment-list"
                  >
                    <template
                      v-for="(file, index) in attachmentItems(row[col.prop])"
                      :key="`${file.url}-${index}`"
                    >
                      <el-image
                        v-if="isImageAttachment(file)"
                        class="todo-attachment-thumb"
                        :src="file.url || ''"
                        fit="cover"
                        :preview-src-list="attachmentImageUrls(row[col.prop])"
                        :initial-index="
                          attachmentImageIndex(row[col.prop], file)
                        "
                        preview-teleported
                        hide-on-click-modal
                      />
                      <el-link
                        v-else
                        :href="file.url || undefined"
                        target="_blank"
                        type="primary"
                      >
                        {{ file.name || "附件" }}
                      </el-link>
                    </template>
                  </div>
                  <span v-else>—</span>
                </template>
                <template v-else>
                  {{ formatBusinessValue(col.label, row[col.prop]) }}
                </template>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <WorkflowApprovalProgress
          class="todo-detail-section"
          :items="todoDetail?.timeline ?? []"
          :business-type="todoDetail?.business_type_code || ''"
          :business-id="todoDetail?.business_id || ''"
        />

        <div
          v-if="todoDetail?.status_code === 'pending'"
          class="todo-detail-section"
        >
          <div class="todo-detail-section-title">
            审批意见
            <span v-if="props.requireComment" class="required-mark">*</span>
          </div>
          <el-input
            v-model="approvalComment"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            :placeholder="
              props.requireComment
                ? '请填写审批意见（同意或驳回前必填）'
                : '同意意见可选，驳回原因必填'
            "
          />
        </div>
      </template>
    </div>
    <template #footer>
      <div v-if="todoActionLoading" role="status">
        正在完成审批及业务校验，请稍候，不要重复提交。
      </div>
      <div class="todo-detail-footer">
        <el-button
          data-action="neutral"
          @click="emit('update:modelValue', false)"
          >关闭</el-button
        >
        <el-button
          data-action="view"
          v-if="props.secondaryActionLabel"
          link
          type="primary"
          :disabled="todoDetailLoading || !todoDetail"
          @click="
            emit(
              'secondary',
              todoDetail?.business_detail?.business_page_query,
              todoDetail ?? undefined
            )
          "
        >
          {{ props.secondaryActionLabel }}
        </el-button>
        <template v-if="todoDetail?.status_code === 'pending'">
          <el-button
            data-action="warning"
            type="danger"
            :loading="todoActionLoading"
            @click="handleTodoAction('reject')"
          >
            驳回
          </el-button>
          <el-button
            data-action="success"
            type="primary"
            :loading="todoActionLoading"
            @click="handleTodoAction('complete')"
          >
            同意
          </el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<style lang="scss" scoped>
:global(.markdown-review-dialog.el-dialog) {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  margin-bottom: 0;
}

:global(.markdown-review-dialog > .el-dialog__body) {
  min-height: 0;
  overflow: auto;
}

:global(.markdown-review-dialog > .el-dialog__header),
:global(.markdown-review-dialog > .el-dialog__footer) {
  flex: none;
}

.markdown-review-dialog .todo-detail-footer {
  flex-wrap: wrap;
}

summary.todo-detail-section-title {
  cursor: pointer;
}

.content-hash {
  overflow-wrap: anywhere;
}

.todo-detail-section + .todo-detail-section {
  margin-top: 16px;
}

.todo-detail-section-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.required-mark {
  color: var(--el-color-danger);
}

.todo-field-photo {
  width: 40px;
  height: 40px;
  border-radius: 6px;
}

.todo-detail-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.todo-attachment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.todo-attachment-thumb {
  width: 48px;
  height: 48px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}
</style>
