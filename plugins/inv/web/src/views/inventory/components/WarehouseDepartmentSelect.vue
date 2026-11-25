<template>
  <el-select
    :model-value="modelValue"
    filterable
    clearable
    class="w-full"
    :disabled="!orgId"
    :loading="loading"
    :placeholder="orgId ? placeholder || '请选择责任部门' : '请先选择所属组织或仓库'"
    @update:model-value="(value) => emit('update:modelValue', value || null)"
  >
    <el-option
      v-for="option in options"
      :key="option.value"
      :label="option.label"
      :value="option.value"
    />
    <template #empty>
      <div class="department-empty">
        <span>{{
          loading ? "正在加载责任部门…" : error || "本组织及下级组织暂无可选部门"
        }}</span>
        <el-button v-if="error" link type="primary" @click.stop="load"
          >重试</el-button
        >
      </div>
    </template>
  </el-select>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { getHttpErrorMessage } from "@/utils/http";
import { listWarehouseAssetDepartmentOptions } from "../../../api/inventoryManagement";

const props = defineProps<{
  modelValue?: string | null;
  orgId?: string | null;
  permissionKey: string;
  placeholder?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>();
const options = ref<{ value: string; label: string; org_id: string }[]>([]);
const loading = ref(false);
const error = ref("");
let request = 0;
let disposed = false;

async function load() {
  const token = ++request;
  options.value = [];
  error.value = "";
  loading.value = false;
  if (!props.orgId) return;
  loading.value = true;
  try {
    const response = await listWarehouseAssetDepartmentOptions({
      org_id: props.orgId,
      permission_key: props.permissionKey,
    });
    if (disposed || token !== request) return;
    if (response.code !== 0)
      throw new Error(response.message || "加载责任部门失败");
    options.value = response.data.items;
  } catch (cause) {
    if (!disposed && token === request)
      error.value = getHttpErrorMessage(cause, "加载责任部门失败");
  } finally {
    if (!disposed && token === request) loading.value = false;
  }
}
watch(() => [props.orgId, props.permissionKey], load, { immediate: true });
onBeforeUnmount(() => {
  disposed = true;
  request++;
});
</script>

<style scoped>
.department-empty {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: var(--el-text-color-secondary);
}
</style>
