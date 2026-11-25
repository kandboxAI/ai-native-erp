<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  addWorkflowComment,
  getWorkflowTimeline,
  resubmitWorkflow,
  type WorkflowTimelineItem
} from "@/api/workflowTask";
import { formatTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import { emitter } from "@/utils/mitt";
import { useRouter } from "vue-router";
import { buildWorkflowBusinessEditRoute } from "@/utils/workflowBusinessEditRegistry";
import WorkflowStarterSelector from "@/components/WorkflowStarterSelector/index.vue";

const router = useRouter();

const props = withDefaults(
  defineProps<{
    items?: WorkflowTimelineItem[];
    loading?: boolean;
    title?: string;
    businessType?: string;
    businessId?: string;
    showEditButton?: boolean;
  }>(),
  {
    loading: false,
    title: "审批进度",
    businessType: "",
    businessId: "",
    showEditButton: false
  }
);

const emit = defineEmits<{
  (e: "edit"): void;
}>();

const remoteItems = ref<WorkflowTimelineItem[]>([]);
const remoteLoading = ref(false);
const actionLoading = ref(false);
const loadError = ref("");
const commentText = ref("");
const canComment = ref(false);
const canResubmit = ref(false);
const requiresEditBeforeResubmit = ref(false);
const latestOrganizationId = ref<string | null>(null);
const workflowSelectorRef = ref<InstanceType<typeof WorkflowStarterSelector>>();
const registeredEditRoute = computed(() =>
  buildWorkflowBusinessEditRoute(props.businessType, props.businessId)
);
let requestSequence = 0;

const hasRemoteThread = computed(() =>
  Boolean(props.businessType && props.businessId)
);
const timelineItems = computed(() =>
  hasRemoteThread.value ? remoteItems.value : (props.items ?? [])
);
const isLoading = computed(() => props.loading || remoteLoading.value);
const shouldShow = computed(
  () =>
    props.items !== undefined ||
    hasRemoteThread.value ||
    isLoading.value ||
    timelineItems.value.length > 0 ||
    Boolean(loadError.value)
);

async function loadProgress() {
  const sequence = ++requestSequence;
  loadError.value = "";
  if (!hasRemoteThread.value && props.items !== undefined) {
    remoteItems.value = [];
    remoteLoading.value = false;
    return;
  }
  if (!props.businessType || !props.businessId) {
    remoteItems.value = [];
    remoteLoading.value = false;
    return;
  }
  remoteLoading.value = true;
  try {
    const res = await getWorkflowTimeline(props.businessType, props.businessId);
    if (sequence !== requestSequence) return;
    if (res.code !== 0) throw new Error(res.message || "审批进度加载失败");
    remoteItems.value = res.data?.items ?? [];
    canComment.value = Boolean(res.data?.can_comment);
    canResubmit.value = Boolean(res.data?.can_resubmit);
    requiresEditBeforeResubmit.value = Boolean(
      res.data?.requires_edit_before_resubmit
    );
    latestOrganizationId.value = res.data?.org_id || null;
  } catch (error: unknown) {
    if (sequence !== requestSequence) return;
    remoteItems.value = [];
    canComment.value = false;
    canResubmit.value = false;
    requiresEditBeforeResubmit.value = false;
    loadError.value = getHttpErrorMessage(error, "审批进度加载失败");
  } finally {
    if (sequence === requestSequence) remoteLoading.value = false;
  }
}

async function submitComment() {
  const comment = commentText.value.trim();
  if (!comment) {
    ElMessage.warning("请输入评论内容");
    return;
  }
  actionLoading.value = true;
  try {
    const res = await addWorkflowComment(
      props.businessType,
      props.businessId,
      comment
    );
    if (res.code !== 0) throw new Error(res.message || "评论失败");
    commentText.value = "";
    remoteItems.value = res.data?.items ?? [];
    canComment.value = Boolean(res.data?.can_comment);
    canResubmit.value = Boolean(res.data?.can_resubmit);
    requiresEditBeforeResubmit.value = Boolean(
      res.data?.requires_edit_before_resubmit
    );
    emitter.emit("workflowBusinessChanged", {
      business_type: props.businessType,
      business_id: props.businessId,
      instance_status: res.data?.latest_instance_status_code || undefined
    });
    ElMessage.success("评论已发布");
  } catch (error: unknown) {
    ElMessage.error(getHttpErrorMessage(error, "评论失败"));
  } finally {
    actionLoading.value = false;
  }
}

async function submitResubmit() {
  try {
    const { value } = await ElMessageBox.prompt(
      "请确认已经修改并保存原单据内容，再填写本次重新发起说明。",
      "重新发起审批",
      {
        inputType: "textarea",
        inputPlaceholder: "例如：已根据驳回意见修改金额并补充附件",
        inputValidator: value =>
          Boolean(String(value || "").trim()) || "请填写重新发起说明",
        confirmButtonText: "重新发起",
        cancelButtonText: "取消"
      }
    );
    const choices = await workflowSelectorRef.value?.collect(
      latestOrganizationId.value
    );
    if (choices === null) return;
    actionLoading.value = true;
    const res = await resubmitWorkflow(
      props.businessType,
      props.businessId,
      String(value || "").trim(),
      choices
    );
    if (res.code !== 0) throw new Error(res.message || "重新发起失败");
    remoteItems.value = res.data?.items ?? [];
    canComment.value = Boolean(res.data?.can_comment);
    canResubmit.value = Boolean(res.data?.can_resubmit);
    requiresEditBeforeResubmit.value = Boolean(
      res.data?.requires_edit_before_resubmit
    );
    emitter.emit("workflowBusinessChanged", {
      business_type: props.businessType,
      business_id: props.businessId,
      instance_status: res.data?.latest_instance_status_code || undefined
    });
    await loadProgress();
    ElMessage.success("已重新发起审批");
  } catch (error: unknown) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(getHttpErrorMessage(error, "重新发起失败"));
  } finally {
    actionLoading.value = false;
  }
}

function onWorkflowBusinessChanged(event: {
  business_type: string;
  business_id?: string;
}) {
  if (
    event.business_type === props.businessType &&
    (!event.business_id || event.business_id === props.businessId)
  ) {
    void loadProgress();
  }
}

function openBusinessEditor() {
  if (props.showEditButton) {
    emit("edit");
    return;
  }
  if (registeredEditRoute.value) {
    void router.push(registeredEditRoute.value);
  }
}

onMounted(() =>
  emitter.on("workflowBusinessChanged", onWorkflowBusinessChanged)
);
onBeforeUnmount(() =>
  emitter.off("workflowBusinessChanged", onWorkflowBusinessChanged)
);

watch(
  () => [props.items, props.businessType, props.businessId] as const,
  () => void loadProgress(),
  { immediate: true }
);

function timelineType(
  action: string
): "primary" | "success" | "warning" | "danger" | "info" {
  if (action === "approved") return "success";
  if (action === "rejected") return "danger";
  if (action === "comment") return "info";
  if (action === "resubmit") return "primary";
  if (action === "pending") return "warning";
  if (action === "not_started" || action === "cancelled") return "info";
  return "primary";
}

function statusTagType(
  action: string
): "primary" | "success" | "warning" | "danger" | "info" {
  return timelineType(action);
}

function itemTitle(item: WorkflowTimelineItem) {
  if (item.action_code === "submit") return "提交审批";
  if (item.action_code === "comment") return "沟通记录";
  if (item.action_code === "resubmit") return "重新发起审批";
  if (item.action_code === "withdraw") return "撤回申请";
  return item.task_name || item.task_key || "审批节点";
}

function participantText(item: WorkflowTimelineItem) {
  if (["submit", "resubmit", "withdraw"].includes(item.action_code)) {
    return item.actor_name ? `发起人：${item.actor_name}` : "";
  }
  if (item.action_code === "comment") {
    return item.actor_name ? `评论人：${item.actor_name}` : "";
  }
  if (item.action_code === "approved" || item.action_code === "rejected") {
    return item.actor_name ? `审批人：${item.actor_name}` : "审批人：—";
  }
  if (item.assignee_names?.length) {
    const prefix = item.action_code === "pending" ? "当前待审批" : "计划审批人";
    return `${prefix}：${item.assignee_names.join("、")}`;
  }
  if (item.assignee_label) {
    const prefix =
      item.action_code === "pending" ? "当前待审批" : "计划审批对象";
    return `${prefix}：${item.assignee_label}`;
  }
  return "";
}

function displayTime(value: string | null) {
  return value ? formatTime(value, "—") : "";
}
</script>

<template>
  <section v-if="shouldShow" class="approval-progress">
    <div class="approval-progress-title">{{ props.title }}</div>
    <div v-loading="isLoading" class="approval-progress-body">
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
      <el-empty
        v-else-if="!isLoading && !timelineItems.length"
        description="暂无审批进度"
        :image-size="64"
      />
      <el-timeline v-else class="approval-timeline">
        <el-timeline-item
          v-for="(item, index) in timelineItems"
          :key="`${item.instance_id || 'instance'}-${item.task_key || item.action_code}-${index}`"
          :type="timelineType(item.action_code)"
          :timestamp="displayTime(item.occurred_at)"
          placement="top"
          :hollow="item.action_code === 'not_started'"
        >
          <div class="approval-node-heading">
            <span class="approval-node-title">{{ itemTitle(item) }}</span>
            <el-tag
              :type="statusTagType(item.action_code)"
              size="small"
              effect="plain"
            >
              {{ item.action_label }}
            </el-tag>
          </div>
          <div v-if="participantText(item)" class="approval-node-meta">
            {{ participantText(item) }}
          </div>
          <div v-if="item.comment" class="approval-node-comment">
            {{
              item.action_code === "comment"
                ? "评论"
                : item.action_code === "rejected"
                  ? "驳回原因"
                  : "说明"
            }}：{{ item.comment }}
          </div>
        </el-timeline-item>
      </el-timeline>
      <div
        v-if="canComment || canResubmit || requiresEditBeforeResubmit"
        class="approval-actions"
      >
        <el-alert
          v-if="requiresEditBeforeResubmit"
          title="审批已驳回，请先编辑并保存原单据，保存后再重新发起审批。"
          type="warning"
          :closable="false"
          show-icon
        />
        <el-input
          v-if="canComment"
          v-model="commentText"
          type="textarea"
          :rows="2"
          maxlength="1000"
          show-word-limit
          placeholder="填写评论，与发起人或审批人沟通"
        />
        <div class="approval-action-buttons">
          <el-button
            data-action="edit"
            v-if="
              requiresEditBeforeResubmit &&
              (props.showEditButton || registeredEditRoute)
            "
            type="primary"
            plain
            @click="openBusinessEditor"
            >编辑原单据</el-button
          >
          <el-button
            data-action="neutral"
            v-if="requiresEditBeforeResubmit"
            :loading="remoteLoading"
            @click="loadProgress"
            >已保存，刷新状态</el-button
          >
          <el-button
            data-action="primary"
            v-if="canResubmit"
            type="primary"
            plain
            :loading="actionLoading"
            @click="submitResubmit"
            >重新发起</el-button
          >
          <el-button
            data-action="primary"
            v-if="canComment"
            type="primary"
            :loading="actionLoading"
            :disabled="!commentText.trim()"
            @click="submitComment"
            >发表评论</el-button
          >
        </div>
      </div>
    </div>
  </section>
  <WorkflowStarterSelector
    ref="workflowSelectorRef"
    :business-type="props.businessType"
  />
</template>

<style lang="scss" scoped>
.approval-progress {
  margin-top: 16px;
}

.approval-progress-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.approval-progress-body {
  min-height: 72px;
  padding: 16px 18px 2px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.approval-timeline {
  padding-left: 4px;
  margin: 0;
}

.approval-node-heading {
  display: flex;
  gap: 10px;
  align-items: center;
}

.approval-node-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.approval-node-meta,
.approval-node-comment {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.approval-node-comment {
  color: var(--el-text-color-secondary);
}

.approval-actions {
  padding: 12px 0 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.approval-action-buttons {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 10px;
}
</style>
