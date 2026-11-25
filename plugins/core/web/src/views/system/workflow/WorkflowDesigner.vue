<template>
  <div class="designer-shell">
    <div class="designer-toolbar list-filters" data-list-context="workflow-editor">
      <div class="toolbar-left">
        <el-input
          v-model="design.process_name"
          class="process-name"
          maxlength="128"
          placeholder="请输入流程名称"
        />
      </div>
      <div class="toolbar-actions">
        <el-button v-if="businessType === 'registration_change'" @click="loadBuiltinTemplate()">载入内置模板</el-button>
        <el-button data-action="primary" :loading="previewing" @click="onPreview">校验预览</el-button>
        <el-button data-action="primary" type="primary" :loading="saving" @click="onSave">
          保存并生成版本
        </el-button>
      </div>
    </div>

    <div class="canvas-wrap">
      <div class="zoom-tools">
        <el-button data-action="neutral" text :disabled="zoom <= 60" @click="changeZoom(-10)"
          >−</el-button
        >
        <span>{{ zoom }}%</span>
        <el-button data-action="neutral" text :disabled="zoom >= 140" @click="changeZoom(10)"
          >＋</el-button
        >
      </div>

      <div class="canvas-scroll">
        <div class="flow-stage" :style="{ transform: `scale(${zoom / 100})` }">
          <div class="start-card flow-card">
            <div class="card-head start-head">发起人</div>
            <div class="card-body">
              <span>提交业务单的当前用户</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>

          <FlowSequence
            :nodes="design.nodes"
            :condition-fields="conditionFields"
            :node-summary="nodeSummary"
            @add-node="addNode"
            @remove-node="removeNode"
            @edit-node="editNode"
            @add-branch="addBranch"
            @remove-branch="removeBranch"
            @reset-condition="resetCondition"
            @update-condition-value="updateConditionValue"
          />

          <div class="flow-end-dot" />
          <div class="flow-end-text">流程结束</div>
        </div>
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="activeNode?.type === 'cc' ? '设置抄送人' : '设置审批人'"
      size="440px"
      destroy-on-close
      append-to-body
    >
      <el-form v-if="activeNode" label-position="top">
        <el-form-item label="节点名称" required>
          <el-input v-model="activeNode.name" maxlength="128" />
        </el-form-item>

        <template v-if="activeNode.type === 'approval'">
          <el-form-item label="审批方式" required>
            <el-radio-group
              v-model="activeNode.approval_mode"
              @change="handleApprovalModeChange(activeNode)"
            >
              <el-radio-button value="single">单人审批</el-radio-button>
              <el-radio-button value="any">或签</el-radio-button>
              <el-radio-button value="all">会签</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <div class="recipient-title">
            <span>审批对象</span>
            <el-button
              data-action="primary"
              v-if="activeNode.approval_mode !== 'single'"
              type="primary"
              link
              @click="addApprover(activeNode)"
            >
              + 添加审批对象
            </el-button>
          </div>
          <div
            v-for="(assignee, index) in activeNode.assignees"
            :key="index"
            class="recipient-row"
          >
            <AssigneeFields
              v-model="activeNode.assignees[index]"
              :node-id="`${activeNode.id}_${index}`"
              :business-type="props.businessType"
              purpose="approval"
            />
            <el-button data-list-action="delete"
              v-if="activeNode.approval_mode !== 'single'"
              type="danger"
              link
              :disabled="activeNode.assignees.length <= 2"
              @click="activeNode.assignees.splice(index, 1)"
            >
              删除
            </el-button>
          </div>
          <div class="assignee-preview">
            <div class="assignee-preview__head">
              <span>实际审批人预览</span>
              <el-button
                data-action="primary"
                type="primary"
                link
                :loading="assigneePreviewLoading"
                @click="loadAssigneePreview"
              >
                刷新
              </el-button>
            </div>
            <div v-if="assigneePreviewError" class="preview-error">
              {{ assigneePreviewError }}
            </div>
            <template v-else-if="assigneePreview">
              <div class="preview-summary">
                {{ approvalPreviewSummary }}
              </div>
              <div
                v-for="(group, index) in assigneePreview.groups"
                :key="`${group.type}-${group.value}-${index}`"
                class="preview-group"
              >
                <span class="preview-group__label">
                  {{ assigneeSummary(activeNode.assignees[index]) }}：
                </span>
                <span v-if="group.dynamic">运行时确定</span>
                <span v-else-if="group.members.length">
                  {{ group.members.map(item => item.name).join("、") }}
                </span>
                <span v-else>未匹配到人员</span>
              </div>
              <div v-if="unactionableNames.length" class="preview-error">
                以下人员缺少待办办理权限：{{ unactionableNames.join("、") }}
              </div>
            </template>
            <div v-else class="preview-empty">正在计算实际审批人…</div>
          </div>
        </template>

        <template v-else>
          <div class="recipient-title">
            <span>抄送对象</span>
            <el-button data-action="primary" type="primary" link @click="addRecipient(activeNode)">
              + 添加抄送对象
            </el-button>
          </div>
          <div
            v-for="(recipient, index) in activeNode.recipients"
            :key="index"
            class="recipient-row"
          >
            <AssigneeFields
              v-model="activeNode.recipients[index]"
              :node-id="activeNode.id"
              :business-type="props.businessType"
              purpose="cc"
            />
            <el-button data-list-action="delete"
              type="danger"
              link
              :disabled="activeNode.recipients.length <= 1"
              @click="activeNode.recipients.splice(index, 1)"
            >
              删除
            </el-button>
          </div>
        </template>
      </el-form>
      <template #footer>
        <el-button data-action="success" type="primary" @click="drawerVisible = false"
          >完成</el-button
        >
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  provide,
  reactive,
  ref,
  watch
} from "vue";
import { ArrowRight } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import AssigneeFields from "./AssigneeFields.vue";
import FlowSequence from "./FlowSequence.vue";
import {
  emptyAssigneeOptions,
  workflowAssigneeOptionsKey,
  workflowAssigneeOptionsLoadingKey
} from "./workflowDesignerContext";
import {
  getDesignTemplate,
  getLatestDesign,
  getAssigneeOptions,
  listWorkflowConditionFields,
  previewFlowDesign,
  previewWorkflowAssignees,
  saveFlowDesign,
  type AssigneeConfig,
  type ApprovalNode,
  type AssigneeOptions,
  type AssigneePreviewResult,
  type CcNode,
  type ConditionBranch,
  type ConditionOperator,
  type ExclusiveGatewayNode,
  type FlowGatewayNode,
  type ParallelGatewayNode,
  type FlowDesignV3,
  type FlowNodeV3,
  type WorkflowConditionField
} from "@/api/workflowDefinition";

const props = defineProps<{
  definitionId: string;
  businessType: string;
}>();

const emit = defineEmits<{
  cancel: [];
  saved: [];
}>();

const saving = ref(false);
const previewing = ref(false);
const assigneeOptions = ref<AssigneeOptions>(emptyAssigneeOptions());
const optionsLoading = ref(false);
const conditionFields = ref<WorkflowConditionField[]>([]);
const drawerVisible = ref(false);
const activeNode = ref<ApprovalNode | CcNode | null>(null);
const zoom = ref(100);
const assigneePreview = ref<AssigneePreviewResult | null>(null);
const assigneePreviewLoading = ref(false);
const assigneePreviewError = ref("");
let assigneePreviewTimer: ReturnType<typeof setTimeout> | null = null;

const unactionableNames = computed(
  () =>
    assigneePreview.value?.groups
      .flatMap(group => group.members)
      .filter(member => !member.actionable)
      .map(member => member.name)
      .filter((name, index, names) => names.indexOf(name) === index) ?? []
);

const approvalPreviewSummary = computed(() => {
  if (!assigneePreview.value || activeNode.value?.type !== "approval")
    return "";
  const count = assigneePreview.value.candidate_count;
  if (activeNode.value.approval_mode === "all") {
    return `会签需要 ${count} 名实际审批人全部同意`;
  }
  if (activeNode.value.approval_mode === "any") {
    return `或签由 ${count} 名候选人中的任意一人处理`;
  }
  return count > 1
    ? `该审批对象匹配 ${count} 人，任意一人处理即可`
    : `实际审批人 ${count} 人`;
});

provide(workflowAssigneeOptionsKey, assigneeOptions);
provide(workflowAssigneeOptionsLoadingKey, optionsLoading);

/** 新增审批对象的默认值：业务负责人（如班主任）优先，否则发起人上级 */
function defaultAssignee(): AssigneeConfig {
  const owner = assigneeOptions.value.business_owners[0]?.value;
  return owner
    ? { type: "business_owner", value: owner }
    : { type: "initiator_leader", value: "initiator_leader" };
}

function newId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function emptyApproval(): ApprovalNode {
  const assignee: AssigneeConfig = defaultAssignee();
  return {
    type: "approval",
    id: newId("user_task"),
    name: "审批人",
    assignee,
    approval_mode: "single",
    assignees: [{ ...assignee }]
  };
}

function emptyCc(): CcNode {
  const id = newId("cc_node");
  return {
    type: "cc",
    id,
    name: "抄送人",
    recipients: [{ type: "starter_select", value: id }]
  };
}

const design = reactive<FlowDesignV3>({
  schema_version: 3,
  process_name: "审批流程",
  process_id: null,
  nodes: [emptyApproval()]
});

function approvalCount(nodes: FlowNodeV3[]): number {
  return nodes.reduce((total, node) => {
    if (node.type === "approval") return total + 1;
    if (node.type === "cc") return total;
    return (
      total +
      node.branches.reduce(
        (branchTotal, branch) => branchTotal + approvalCount(branch.nodes),
        0
      )
    );
  }, 0);
}

function assigneeSummary(assignee: AssigneeConfig) {
  if (assignee.type === "starter") return "发起人本人";
  if (assignee.type === "starter_select") return "发起人自选";
  if (assignee.type === "user") return "指定用户";
  if (assignee.type === "initiator_leader") return "发起人上级";
  if (assignee.type === "department_manager") {
    return `部门负责人（${assignee.value || "未配置"}）`;
  }
  if (assignee.type === "business_owner") {
    return (
      assigneeOptions.value.business_owners.find(
        item => item.value === assignee.value
      )?.label ||
      assignee.value ||
      "业务负责人"
    );
  }
  return (
    assigneeOptions.value.permissions.find(
      item => item.permission_key === assignee.value
    )?.permission_name ||
    assignee.value ||
    "未配置"
  );
}

function nodeSummary(node: ApprovalNode | CcNode) {
  if (node.type === "approval") {
    const modeLabel = { single: "单人", any: "或签", all: "会签" }[
      node.approval_mode || "single"
    ];
    return `${modeLabel}：${node.assignees.map(assigneeSummary).join("、")}`;
  }
  return node.recipients.map(assigneeSummary).join("、") || "未配置";
}

function makeGateway(): ExclusiveGatewayNode {
  const defaultBranchId = newId("branch_default");
  return {
    type: "exclusive_gateway",
    id: newId("gateway"),
    name: "条件分支",
    default_branch_id: defaultBranchId,
    branches: [
      {
        id: newId("branch"),
        name: "条件1",
        condition: defaultCondition(),
        nodes: [emptyApproval()]
      },
      {
        id: defaultBranchId,
        name: "其他情况",
        condition: null,
        nodes: [emptyApproval()]
      }
    ]
  };
}

function makeParallelGateway(): ParallelGatewayNode {
  return {
    type: "parallel_gateway",
    id: newId("parallel"),
    name: "并行审批",
    branches: [1, 2].map(index => ({
      id: newId("branch"),
      name: `并行分支${index}`,
      condition: null,
      nodes: [emptyApproval()]
    }))
  };
}

function addNode(
  nodes: FlowNodeV3[],
  index: number,
  type: "approval" | "cc" | "gateway" | "parallel"
) {
  if (type === "cc" && !canAddCcAt(nodes, index)) {
    ElMessage.warning("抄送节点必须放在审批节点之后");
    return;
  }
  if (type === "gateway" && !conditionFields.value.length) {
    ElMessage.warning("当前业务类型没有可用于条件判断的字段");
    return;
  }
  const node =
    type === "approval"
      ? emptyApproval()
      : type === "cc"
        ? emptyCc()
        : type === "parallel" ? makeParallelGateway() : makeGateway();
  nodes.splice(index, 0, node);
  if (node.type === "approval" || node.type === "cc") editNode(node);
}

function canAddCcAt(nodes: FlowNodeV3[], index: number): boolean {
  for (let current = index - 1; current >= 0; current -= 1) {
    const node = nodes[current];
    if (node.type === "approval") return true;
    if (node.type !== "cc") return false;
  }
  return false;
}

function removeNode(nodes: FlowNodeV3[], index: number) {
  const node = nodes[index];
  if (node.type === "approval" && approvalCount(nodes) <= 1) return;
  nodes.splice(index, 1);
}

function editNode(node: ApprovalNode | CcNode) {
  activeNode.value = node;
  drawerVisible.value = true;
  scheduleAssigneePreview();
}

async function loadAssigneePreview() {
  if (activeNode.value?.type !== "approval") return;
  assigneePreviewLoading.value = true;
  assigneePreviewError.value = "";
  try {
    const response = await previewWorkflowAssignees(
      props.definitionId,
      activeNode.value.assignees
    );
    if (response.code !== 0) throw new Error(response.message);
    assigneePreview.value = response.data;
  } catch (error: unknown) {
    assigneePreview.value = null;
    assigneePreviewError.value =
      error instanceof Error ? error.message : "审批人预览失败";
  } finally {
    assigneePreviewLoading.value = false;
  }
}

function scheduleAssigneePreview() {
  if (assigneePreviewTimer) clearTimeout(assigneePreviewTimer);
  assigneePreviewTimer = setTimeout(loadAssigneePreview, 300);
}

function addRecipient(node: CcNode) {
  node.recipients.push(defaultAssignee());
}

function addApprover(node: ApprovalNode) {
  if (node.assignees.length >= 20) return;
  node.assignees.push(defaultAssignee());
}

function handleApprovalModeChange(node: ApprovalNode) {
  if (node.approval_mode === "single") {
    node.assignees.splice(1);
  } else {
    while (node.assignees.length < 2) {
      addApprover(node);
    }
  }
  node.assignee = node.assignees[0];
}

function normalizeNodes(nodes: FlowNodeV3[]) {
  for (const node of nodes) {
    if (node.type === "approval") {
      node.approval_mode ||= "single";
      if (!node.assignees?.length) node.assignees = [{ ...node.assignee }];
      node.assignee = node.assignees[0];
    } else if (node.type !== "cc") {
      node.branches.forEach(branch => normalizeNodes(branch.nodes));
    }
  }
}

function defaultCondition() {
  const field = conditionFields.value[0];
  return {
    field: field?.key || "leave_days",
    operator: "lte" as ConditionOperator,
    value: 1
  };
}

function addBranch(gateway: FlowGatewayNode) {
  if (gateway.branches.length >= 8) return;
  const parallel = gateway.type === "parallel_gateway";
  gateway.branches.splice(gateway.branches.length - (parallel ? 0 : 1), 0, {
    id: newId("branch"),
    name: parallel ? `并行分支${gateway.branches.length + 1}` : `条件${gateway.branches.length}`,
    condition: parallel ? null : defaultCondition(),
    nodes: [emptyApproval()]
  });
}

function removeBranch(gateway: FlowGatewayNode, index: number) {
  if (gateway.branches.length <= 2) return;
  gateway.branches.splice(index, 1);
}

function fieldType(fieldKey: string) {
  return (
    conditionFields.value.find(field => field.key === fieldKey)?.field_type ||
    "string"
  );
}

function operatorsFor(fieldKey: string): ConditionOperator[] {
  return (
    conditionFields.value.find(field => field.key === fieldKey)?.operators || [
      "eq",
      "ne"
    ]
  );
}

function resetCondition(branch: ConditionBranch) {
  if (!branch.condition) return;
  branch.condition.operator = operatorsFor(branch.condition.field)[0];
  const type = fieldType(branch.condition.field);
  branch.condition.value =
    type === "number" ? 0 : type === "boolean" ? false : "";
}

function updateConditionValue(
  branch: ConditionBranch,
  value: string | number | boolean | undefined
) {
  if (branch.condition) branch.condition.value = value ?? "";
}

function changeZoom(delta: number) {
  zoom.value = Math.max(60, Math.min(140, zoom.value + delta));
}

async function loadOptions() {
  optionsLoading.value = true;
  try {
    const [optionResponse, fieldResponse] = await Promise.all([
      getAssigneeOptions(props.businessType),
      listWorkflowConditionFields(props.businessType)
    ]);
    if (optionResponse.code === 0) assigneeOptions.value = optionResponse.data;
    if (fieldResponse.code === 0) conditionFields.value = fieldResponse.data;
  } finally {
    optionsLoading.value = false;
  }
}

async function loadDesign() {
  const latest = await getLatestDesign(props.definitionId);
  if (latest.code === 0 && latest.data) {
    Object.assign(design, latest.data);
    normalizeNodes(design.nodes);
    return;
  }
  await loadBuiltinTemplate();
}

async function loadBuiltinTemplate() {
  const template = await getDesignTemplate(props.businessType);
  if (template.code === 0) {
    Object.assign(design, template.data);
    normalizeNodes(design.nodes);
  }
}

function validateLocal() {
  if (!design.process_name.trim()) throw new Error("请输入流程名称");
  validateNodes(design.nodes, "流程", false);
}

function validateNodes(
  nodes: FlowNodeV3[],
  label: string,
  approvalSeen: boolean
): boolean {
  if (!nodes.length) throw new Error(`${label}至少需要一个流程节点`);
  let everyPathHasApproval = approvalSeen;
  let canPlaceCc = false;
  for (const node of nodes) {
    if (!node.name.trim()) throw new Error("节点名称不能为空");
    if (node.type === "approval") {
      if (!node.assignees.length)
        throw new Error(`审批节点「${node.name}」未配置审批对象`);
      if (node.approval_mode !== "single" && node.assignees.length < 2)
        throw new Error(
          `审批节点「${node.name}」的或签/会签至少需要两个审批对象`
        );
      if (node.approval_mode === "single" && node.assignees.length !== 1)
        throw new Error(`审批节点「${node.name}」单人审批只能配置一个审批对象`);
      node.assignee = node.assignees[0];
      everyPathHasApproval = true;
      canPlaceCc = true;
      continue;
    }
    if (node.type === "cc") {
      if (!canPlaceCc)
        throw new Error(`抄送节点「${node.name}」必须放在审批节点之后`);
      if (!node.recipients.length)
        throw new Error(`抄送节点「${node.name}」未配置接收人`);
      continue;
    }
    if (node.type === "exclusive_gateway") {
      if (!conditionFields.value.length)
        throw new Error("当前业务类型没有可用于条件判断的字段");
      const branchIds = new Set(node.branches.map(branch => branch.id));
      if (!branchIds.has(node.default_branch_id))
        throw new Error(`条件分支「${node.name}」缺少默认分支`);
      for (const branch of node.branches) {
        if (branch.id === node.default_branch_id && branch.condition)
          throw new Error(`默认分支「${branch.name}」不能配置条件`);
        if (branch.id !== node.default_branch_id && !branch.condition)
          throw new Error(`分支「${branch.name}」必须配置条件`);
      }
    }
    everyPathHasApproval = node.branches.every(branch =>
      validateNodes(
        branch.nodes,
        `${label} / 分支「${branch.name}」`,
        everyPathHasApproval
      )
    );
    canPlaceCc = false;
  }
  if (!everyPathHasApproval) throw new Error(`${label}至少需要一个审批节点`);
  return everyPathHasApproval;
}

async function onPreview() {
  previewing.value = true;
  try {
    validateLocal();
    const response = await previewFlowDesign({ ...design }, props.businessType);
    if (response.code !== 0) throw new Error(response.message);
    ElMessage.success(
      `校验通过，共 ${response.data.user_tasks.length} 个审批节点`
    );
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : "校验失败");
  } finally {
    previewing.value = false;
  }
}

async function onSave() {
  saving.value = true;
  try {
    validateLocal();
    const response = await saveFlowDesign({
      definition_id: props.definitionId,
      design: { ...design, schema_version: 3 },
      remark: "钉钉式可视化流程设计"
    });
    if (response.code !== 0) throw new Error(response.message);
    ElMessage.success(
      `已保存为版本 v${response.data.version_no}，请在版本列表中发布`
    );
    emit("saved");
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败");
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await loadOptions();
  await loadDesign();
});

watch(
  () =>
    activeNode.value?.type === "approval"
      ? JSON.stringify(activeNode.value.assignees)
      : "",
  () => {
    if (drawerVisible.value) scheduleAssigneePreview();
  }
);

onBeforeUnmount(() => {
  if (assigneePreviewTimer) clearTimeout(assigneePreviewTimer);
});
</script>

<style scoped>
.designer-shell {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  overflow: hidden;
  background: #f5f6f8;
}

.designer-toolbar {
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
}

.toolbar-left,
.toolbar-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.process-name {
  width: 260px;
}

.canvas-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}

.canvas-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
}

.flow-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 1100px;
  min-height: 100%;
  padding: 72px 80px 100px;
  transform-origin: top center;
  transition: transform 0.15s ease;
}

.zoom-tools {
  position: absolute;
  top: 16px;
  right: 20px;
  z-index: 3;
  display: flex;
  align-items: center;
  padding: 3px 8px;
  font-size: 13px;
  background: rgb(255 255 255 / 92%);
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 5%);
}

.flow-card {
  width: 320px;
  overflow: hidden;
  cursor: pointer;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 38px;
  padding: 0 18px;
  font-size: 14px;
  color: #fff;
}

.start-head {
  background: #6079a7;
}

.approval-head {
  background: #ff943e;
}

.cc-head {
  background: #3296ed;
}

.card-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 74px;
  padding: 12px 18px;
  color: #303133;
}

.card-body .el-icon {
  color: #b7bdc6;
}

.node-name {
  font-size: 15px;
}

.node-summary {
  max-width: 250px;
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.delete-node {
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: 20px;
  color: rgb(255 255 255 / 82%);
}

.connector {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 88px;
}

:deep(.connector > span) {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #c8cdd5;
}

:deep(.connector > span::after) {
  position: absolute;
  bottom: -1px;
  left: -4px;
  width: 0;
  height: 0;
  content: "";
  border-top: 7px solid #c8cdd5;
  border-right: 5px solid transparent;
  border-left: 5px solid transparent;
}

.connector.simple {
  height: 54px;
}

:deep(.add-node-button) {
  position: relative;
  top: 24px;
  z-index: 3;
  width: 38px;
  height: 38px;
  font-size: 20px;
  box-shadow: 0 2px 5px rgb(50 150 237 / 35%);
}

.gateway-title {
  padding: 8px 20px;
  color: #fff;
  background: #8e72d8;
  border-radius: 16px;
}

.branch-board {
  display: flex;
  gap: 42px;
  align-items: flex-start;
  margin-top: 28px;
}

.branch-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 340px;
}

.branch-rule-card {
  width: 340px;
  padding: 14px;
  background: #fff;
  border-top: 3px solid #8e72d8;
  border-radius: 5px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 10%);
}

.branch-title-row,
.condition-row,
.recipient-title,
.recipient-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.branch-title-row .el-input {
  flex: 1;
}

.condition-row {
  margin-top: 12px;
}

.condition-row > * {
  flex: 1;
}

.assignee-preview {
  padding: 14px;
  margin-top: 14px;
  background: #f7f8fa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.assignee-preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.preview-summary {
  margin-top: 8px;
  color: #303133;
}

.preview-group {
  margin-top: 7px;
  font-size: 13px;
  line-height: 1.5;
  color: #606266;
}

.preview-group__label {
  color: #303133;
}

.preview-error {
  margin-top: 8px;
  font-size: 13px;
  color: #f56c6c;
}

.preview-empty {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}

.condition-row .operator-select {
  flex: 0 0 96px;
}

.default-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

.branch-node {
  width: 300px;
}

.add-branch {
  margin-top: 20px;
}

.flow-end-dot {
  width: 12px;
  height: 12px;
  margin-top: 4px;
  background: #c8cdd5;
  border-radius: 50%;
}

.flow-end-text {
  margin-top: 10px;
  color: #a8adb5;
}

.recipient-title {
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
}

.recipient-row {
  margin-bottom: 12px;
}

.recipient-row :deep(.assignee-row) {
  flex: 1;
}

:deep(.add-node-menu) {
  display: flex;
  flex-direction: column;
}

:deep(.add-node-menu .el-button) {
  justify-content: flex-start;
  margin: 0;
}

@media (width <= 900px) {
  .designer-toolbar {
    align-items: flex-start;
    padding: 12px;
  }

  .toolbar-left {
    align-items: flex-start;
  }

  .process-name {
    width: 190px;
  }
}
</style>
