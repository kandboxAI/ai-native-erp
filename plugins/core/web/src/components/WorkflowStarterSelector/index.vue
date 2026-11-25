<template>
  <el-dialog
    v-model="visible"
    title="选择审批流程人员"
    width="520px"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="finish(null)"
  >
    <el-alert
      title="当前流程包含“发起人自选”节点，请完成选择后再提交业务单。"
      type="info"
      :closable="false"
      class="selection-alert"
    />
    <el-form label-position="top">
      <el-form-item
        v-for="node in selectionNodes"
        :key="node.key"
        :label="`${node.kind === 'approval' ? '审批人' : '抄送人'} · ${node.name}`"
        required
      >
        <el-select
          v-model="choices[node.key]"
          multiple
          filterable
          remote
          reserve-keyword
          :remote-method="searchCandidates"
          :loading="loadingCandidates"
          placeholder="搜索姓名或邮箱"
          style="width: 100%"
        >
          <el-option
            v-for="candidate in candidates"
            :key="candidate.id"
            :value="candidate.id"
            :label="candidateLabel(candidate)"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button data-action="neutral" @click="finish(null)">取消</el-button>
      <el-button data-action="primary" type="primary" @click="confirm">确认并继续提交</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getWorkflowStartRequirements,
  searchWorkflowStarterCandidates,
  type WorkflowSelectionNode,
  type WorkflowStarterCandidate,
  type WorkflowStarterChoices
} from "@/api/workflowRuntime";
import type { WorkflowStartRequirements } from "@/api/workflowRuntime";

const props = defineProps<{
  businessType: string;
  requirements?: WorkflowStartRequirements;
}>();

const visible = ref(false);
const selectionNodes = ref<WorkflowSelectionNode[]>([]);
const candidates = ref<WorkflowStarterCandidate[]>([]);
const loadingCandidates = ref(false);
const choices = reactive<WorkflowStarterChoices>({});
const activeOrganizationId = ref<string | null>(null);
let resolver: ((value: WorkflowStarterChoices | null) => void) | null = null;

function isOrganizationForbidden(error: unknown) {
  if (!error || typeof error !== "object") return false;
  const err = error as {
    response?: { status?: number; data?: { message?: string } };
    message?: string;
  };
  const message = err.response?.data?.message || err.message || "";
  return err.response?.status === 403 && message.includes("无权访问该组织");
}

function candidateLabel(candidate: WorkflowStarterCandidate) {
  return candidate.display_name || candidate.id;
}

async function searchCandidates(keyword = "") {
  loadingCandidates.value = true;
  try {
    const response = await searchWorkflowStarterCandidates(
      props.businessType,
      activeOrganizationId.value,
      keyword.trim() || undefined
    );
    if (response.code !== 0) throw new Error(response.message);
    const selectedIds = new Set(Object.values(choices).flat());
    const selectedExisting = candidates.value.filter(candidate =>
      selectedIds.has(candidate.id)
    );
    const merged = [...selectedExisting, ...response.data];
    candidates.value = Array.from(
      new Map(merged.map(item => [item.id, item])).values()
    );
  } finally {
    loadingCandidates.value = false;
  }
}

function finish(value: WorkflowStarterChoices | null) {
  if (!resolver) return;
  const resolve = resolver;
  resolver = null;
  visible.value = false;
  resolve(value);
}

function confirm() {
  const missing = selectionNodes.value.find(
    node => !(choices[node.key]?.length > 0)
  );
  if (missing) {
    ElMessage.warning(`请选择「${missing.name}」`);
    return;
  }
  finish(
    Object.fromEntries(
      selectionNodes.value.map(node => [node.key, [...choices[node.key]]])
    )
  );
}

async function collect(
  organizationId?: string | null
): Promise<WorkflowStarterChoices | null> {
  activeOrganizationId.value = organizationId || null;
  let response;
  try {
    response = props.requirements
      ? { code: 0, message: "", data: props.requirements }
      : await getWorkflowStartRequirements(props.businessType, organizationId);
  } catch (e) {
    if (!organizationId || !isOrganizationForbidden(e)) throw e;
    activeOrganizationId.value = null;
    response = await getWorkflowStartRequirements(props.businessType, null);
  }
  if (response.code !== 0) throw new Error(response.message);
  if (!response.data.selection_nodes.length) return {};

  selectionNodes.value = response.data.selection_nodes;
  for (const key of Object.keys(choices)) delete choices[key];
  for (const node of selectionNodes.value) choices[node.key] = [];
  await searchCandidates();
  visible.value = true;
  return new Promise(resolve => {
    resolver = resolve;
  });
}

defineExpose({ collect });
</script>

<style scoped>
.selection-alert {
  margin-bottom: 18px;
}
</style>
