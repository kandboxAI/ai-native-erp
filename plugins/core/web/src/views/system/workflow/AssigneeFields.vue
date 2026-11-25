<template>
  <div class="assignee-row">
    <el-select v-model="model.type" style="width: 140px">
      <el-option label="拥有权限的用户" value="permission" />
      <el-option label="业务负责人" value="business_owner" />
      <el-option label="指定用户" value="user" />
      <el-option label="部门负责人" value="department_manager" />
      <el-option label="发起人上级" value="initiator_leader" />
      <el-option label="发起人本人" value="starter" />
      <el-option label="发起人自选" value="starter_select" />
    </el-select>
    <el-select
      v-if="model.type === 'permission'"
      v-model="model.value"
      filterable
      :loading="optionsLoading"
      placeholder="选择权限（如：审批学生请假）"
      style="flex: 1"
    >
      <el-option
        v-for="p in assigneeOptions.permissions"
        :key="p.permission_key"
        :label="`${p.permission_name} (${p.permission_key})`"
        :value="p.permission_key"
      />
    </el-select>
    <el-select
      v-else-if="model.type === 'business_owner'"
      v-model="model.value"
      :disabled="assigneeOptions.business_owners.length === 0"
      :placeholder="
        assigneeOptions.business_owners.length
          ? '选择业务关系（如：班主任）'
          : '该业务类型未登记业务负责人'
      "
      style="flex: 1"
    >
      <el-option
        v-for="item in assigneeOptions.business_owners"
        :key="item.value"
        :label="item.label"
        :value="item.value"
      />
    </el-select>
    <el-select
      v-else-if="model.type === 'user'"
      v-model="model.value"
      filterable
      remote
      :remote-method="searchUsers"
      :loading="usersLoading"
      placeholder="搜索用户"
      style="flex: 1"
    >
      <el-option
        v-for="u in userOptions"
        :key="u.id"
        :label="u.label"
        :value="u.id"
      />
    </el-select>
    <el-input
      v-else-if="model.type === 'department_manager'"
      v-model="model.value"
      placeholder="部门编号（department_no）"
      style="flex: 1"
    />
    <el-input
      v-else-if="model.type === 'initiator_leader'"
      model-value="发起人所在部门的负责人"
      disabled
      style="flex: 1"
    />
    <el-input
      v-else-if="model.type === 'starter'"
      model-value="流程实际发起人"
      disabled
      style="flex: 1"
    />
    <el-input
      v-else
      :model-value="starterSelectText"
      disabled
      style="flex: 1"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from "vue";
import type { AssigneeConfig } from "@/api/workflowDefinition";
import { searchAssigneeUsers } from "@/api/workflowDefinition";
import {
  emptyAssigneeOptions,
  workflowAssigneeOptionsKey,
  workflowAssigneeOptionsLoadingKey
} from "./workflowDesignerContext";

const model = defineModel<AssigneeConfig>({ required: true });
const props = defineProps<{
  nodeId?: string;
  purpose?: "approval" | "cc";
  businessType?: string;
}>();

const starterSelectText = computed(() =>
  props.purpose === "cc"
    ? "提交时由发起人选择抄送人"
    : "提交时由发起人选择审批人"
);

const assigneeOptions = inject(
  workflowAssigneeOptionsKey,
  ref(emptyAssigneeOptions())
);
const optionsLoading = inject(workflowAssigneeOptionsLoadingKey, ref(false));

const usersLoading = ref(false);
const userOptions = ref<Array<{ id: string; label: string }>>([]);

async function searchUsers(keyword: string) {
  usersLoading.value = true;
  try {
    const res = await searchAssigneeUsers(keyword?.trim() || undefined);
    if (res.code === 0) {
      userOptions.value = res.data.map(u => ({
        id: u.id,
        label: u.display_name || u.id
      }));
      if (
        model.value.type === "user" &&
        model.value.value &&
        !userOptions.value.some(u => u.id === model.value.value)
      ) {
        userOptions.value.unshift({
          id: model.value.value,
          label: `${model.value.value.slice(0, 8)}…（已配置）`
        });
      }
    }
  } finally {
    usersLoading.value = false;
  }
}

watch(
  () => model.value.type,
  t => {
    if (t === "starter") {
      model.value.value = "starter";
    } else if (t === "initiator_leader") {
      model.value.value = "initiator_leader";
    } else if (t === "starter_select") {
      model.value.value =
        props.nodeId || model.value.value || "starter_selection";
    } else if (t === "business_owner") {
      model.value.value =
        model.value.value || assigneeOptions.value.business_owners[0]?.value;
    } else if (t === "user" && userOptions.value.length === 0) {
      searchUsers("");
    }
  },
  { immediate: true }
);
</script>

<style scoped>
.assignee-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
</style>
