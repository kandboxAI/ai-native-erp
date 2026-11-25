<template>
  <AddConnector
    :allow-cc="false"
    :allow-gateway="conditionFields.length > 0"
    @add="type => emit('add-node', nodes, 0, type)"
  />

  <template v-for="(node, index) in nodes" :key="node.id">
    <template v-if="node.type === 'exclusive_gateway' || node.type === 'parallel_gateway'">
      <div class="gateway-node">
        <div class="gateway-title">
          <el-input v-model="node.name" maxlength="128" />
          <el-button
            data-action="neutral"
            text
            class="delete-gateway"
            :disabled="pathApprovalCount(nodes) <= pathApprovalCount([node])"
            @click="emit('remove-node', nodes, index)"
          >
            ×
          </el-button>
        </div>
        <div class="branch-board">
          <div
            v-for="(branch, branchIndex) in node.branches"
            :key="branch.id"
            class="branch-column"
          >
            <div class="branch-rule-card">
              <div class="branch-title-row">
                <el-input v-model="branch.name" maxlength="128" />
                <el-tag
                  v-if="node.type === 'exclusive_gateway' && node.default_branch_id === branch.id"
                  type="info"
                  size="small"
                >
                  默认
                </el-tag>
                <el-button data-list-action="delete"
                  v-else
                  type="danger"
                  link
                  :disabled="node.branches.length <= 2"
                  @click="emit('remove-branch', node, branchIndex)"
                >
                  删除
                </el-button>
              </div>
              <div
                v-if="node.type === 'exclusive_gateway' && node.default_branch_id !== branch.id && branch.condition"
                class="condition-row"
              >
                <el-select
                  v-model="branch.condition.field"
                  placeholder="条件字段"
                  @change="emit('reset-condition', branch)"
                >
                  <el-option
                    v-for="field in conditionFields"
                    :key="field.key"
                    :label="field.label"
                    :value="field.key"
                  />
                </el-select>
                <el-select
                  v-model="branch.condition.operator"
                  class="operator-select"
                >
                  <el-option
                    v-for="operator in operatorsFor(branch.condition.field)"
                    :key="operator"
                    :label="operatorLabels[operator]"
                    :value="operator"
                  />
                </el-select>
                <el-input-number
                  v-if="fieldType(branch.condition.field) === 'number'"
                  :model-value="Number(branch.condition.value)"
                  :controls="false"
                  @update:model-value="
                    value => emit('update-condition-value', branch, value)
                  "
                />
                <el-select
                  v-else-if="fieldType(branch.condition.field) === 'boolean'"
                  :model-value="Boolean(branch.condition.value)"
                  @update:model-value="
                    value => emit('update-condition-value', branch, value)
                  "
                >
                  <el-option label="是" :value="true" />
                  <el-option label="否" :value="false" />
                </el-select>
                <el-input
                  v-else
                  :model-value="String(branch.condition.value)"
                  placeholder="条件值"
                  @update:model-value="
                    value => emit('update-condition-value', branch, value)
                  "
                />
              </div>
              <div v-else class="default-hint">
                {{ node.type === "parallel_gateway" ? "并行办理，所有分支通过后继续" : "其他条件均不满足时进入此分支" }}
              </div>
            </div>

            <FlowSequence
              :nodes="branch.nodes"
              :condition-fields="conditionFields"
              :node-summary="nodeSummary"
              @add-node="forwardAddNode"
              @remove-node="forwardRemoveNode"
              @edit-node="forwardEditNode"
              @add-branch="forwardAddBranch"
              @remove-branch="forwardRemoveBranch"
              @reset-condition="forwardResetCondition"
              @update-condition-value="forwardUpdateConditionValue"
            />
          </div>
        </div>
        <el-button
          data-action="primary"
          class="add-branch"
          :disabled="node.branches.length >= branchLimit"
          @click="emit('add-branch', node)"
        >
          {{ node.type === "parallel_gateway" ? "+ 添加并行分支" : "+ 添加条件分支" }}
        </el-button>
      </div>
    </template>

    <template v-else>
      <div
        class="flow-card node-card"
        :class="node.type"
        @click="emit('edit-node', node)"
      >
        <div class="card-head" :class="`${node.type}-head`">
          <span>{{ node.type === "approval" ? "审批人" : "抄送人" }}</span>
          <el-button
            data-action="neutral"
            text
            class="delete-node"
            :disabled="
              node.type === 'approval' && pathApprovalCount(nodes) <= 1
            "
            @click.stop="emit('remove-node', nodes, index)"
          >
            ×
          </el-button>
        </div>
        <div class="card-body">
          <div>
            <div class="node-name">{{ node.name }}</div>
            <div class="node-summary">{{ nodeSummary(node) }}</div>
          </div>
          <el-icon><ArrowRight /></el-icon>
        </div>
      </div>
    </template>

    <AddConnector
      :allow-cc="canAddCcAt(nodes, index + 1)"
      :allow-gateway="conditionFields.length > 0"
      @add="type => emit('add-node', nodes, index + 1, type)"
    />
  </template>
</template>

<script setup lang="ts">
import { defineComponent, h } from "vue";
import { ArrowRight, Plus } from "@element-plus/icons-vue";
import { ElButton, ElPopover } from "element-plus";
import {
  type ApprovalNode,
  type CcNode,
  type ConditionBranch,
  type ConditionOperator,
  type FlowGatewayNode,
  type FlowNodeV3,
  type WorkflowConditionField
} from "@/api/workflowDefinition";

defineOptions({ name: "FlowSequence" });

type AddNodeType = "approval" | "cc" | "gateway" | "parallel";
type EditableNode = ApprovalNode | CcNode;

const props = withDefaults(
  defineProps<{
    nodes: FlowNodeV3[];
    conditionFields: WorkflowConditionField[];
    nodeSummary: (node: EditableNode) => string;
    branchLimit?: number;
  }>(),
  { branchLimit: 8 }
);

const emit = defineEmits<{
  "add-node": [nodes: FlowNodeV3[], index: number, type: AddNodeType];
  "remove-node": [nodes: FlowNodeV3[], index: number];
  "edit-node": [node: EditableNode];
  "add-branch": [gateway: FlowGatewayNode];
  "remove-branch": [gateway: FlowGatewayNode, index: number];
  "reset-condition": [branch: ConditionBranch];
  "update-condition-value": [
    branch: ConditionBranch,
    value: string | number | boolean | undefined
  ];
}>();

const AddConnector = defineComponent({
  name: "AddConnector",
  props: {
    allowCc: { type: Boolean, default: true },
    allowGateway: { type: Boolean, default: true }
  },
  emits: ["add"],
  setup(componentProps, { emit: componentEmit }) {
    return () =>
      h("div", { class: "connector" }, [
        h("span"),
        h(
          ElPopover,
          { placement: "right", trigger: "click", width: 160 },
          {
            reference: () =>
              h(
                ElButton,
                { class: "add-node-button", type: "primary", circle: true, "data-action": "primary" },
                { icon: () => h(Plus) }
              ),
            default: () =>
              h("div", { class: "add-node-menu" }, [
                h(
                  ElButton,
                  {
                    "data-action": "primary",
                    text: true,
                    onClick: () => componentEmit("add", "approval")
                  },
                  () => "添加审批人"
                ),
                h(
                  ElButton,
                  {
                    "data-action": "primary",
                    text: true,
                    disabled: !componentProps.allowCc,
                    onClick: () => componentEmit("add", "cc")
                  },
                  () => "添加抄送人"
                ),
                h(
                  ElButton,
                  {
                    "data-action": "primary",
                    text: true,
                    disabled: !componentProps.allowGateway,
                    onClick: () => componentEmit("add", "gateway")
                  },
                  () => "添加条件分支"
                ),
                h(
                  ElButton,
                  { text: true, onClick: () => componentEmit("add", "parallel") },
                  () => "添加并行审批"
                )
              ])
          }
        )
      ]);
  }
});

const operatorLabels: Record<ConditionOperator, string> = {
  eq: "等于",
  ne: "不等于",
  gt: "大于",
  gte: "大于等于",
  lt: "小于",
  lte: "小于等于"
};

function pathApprovalCount(nodes: FlowNodeV3[]): number {
  return nodes.reduce((total, node) => {
    if (node.type === "approval") return total + 1;
    if (node.type === "cc") return total;
    return (
      total +
      node.branches.reduce(
        (branchTotal, branch) => branchTotal + pathApprovalCount(branch.nodes),
        0
      )
    );
  }, 0);
}

function canAddCcAt(nodes: FlowNodeV3[], index: number): boolean {
  for (let current = index - 1; current >= 0; current -= 1) {
    const node = nodes[current];
    if (node.type === "approval") return true;
    if (node.type !== "cc") return false;
  }
  return false;
}

function fieldType(fieldKey: string) {
  return (
    props.conditionFields.find(field => field.key === fieldKey)?.field_type ||
    "string"
  );
}

function operatorsFor(fieldKey: string): ConditionOperator[] {
  return (
    props.conditionFields.find(field => field.key === fieldKey)?.operators || [
      "eq",
      "ne"
    ]
  );
}

function forwardAddNode(nodes: FlowNodeV3[], index: number, type: AddNodeType) {
  emit("add-node", nodes, index, type);
}

function forwardRemoveNode(nodes: FlowNodeV3[], index: number) {
  emit("remove-node", nodes, index);
}

function forwardEditNode(node: EditableNode) {
  emit("edit-node", node);
}

function forwardAddBranch(gateway: FlowGatewayNode) {
  emit("add-branch", gateway);
}

function forwardRemoveBranch(gateway: FlowGatewayNode, index: number) {
  emit("remove-branch", gateway, index);
}

function forwardResetCondition(branch: ConditionBranch) {
  emit("reset-condition", branch);
}

function forwardUpdateConditionValue(
  branch: ConditionBranch,
  value: string | number | boolean | undefined
) {
  emit("update-condition-value", branch, value);
}
</script>

<style scoped>
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

.delete-node,
.delete-gateway {
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: 20px;
}

.delete-node {
  color: rgb(255 255 255 / 82%);
}

.delete-gateway {
  color: #8e72d8;
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

:deep(.add-node-button) {
  position: relative;
  top: 24px;
  z-index: 3;
  width: 38px;
  height: 38px;
  font-size: 20px;
  box-shadow: 0 2px 5px rgb(50 150 237 / 35%);
}

.gateway-node {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.gateway-title {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 320px;
  padding: 8px 12px;
  background: #fff;
  border-top: 3px solid #8e72d8;
  border-radius: 5px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 10%);
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
.condition-row {
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

.condition-row .operator-select {
  flex: 0 0 96px;
}

.default-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

.add-branch {
  margin-top: 20px;
}

:deep(.add-node-menu) {
  display: flex;
  flex-direction: column;
}

:deep(.add-node-menu .el-button) {
  justify-content: flex-start;
  margin: 0;
}
</style>
