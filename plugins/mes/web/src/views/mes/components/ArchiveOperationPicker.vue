<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import {
  archiveOptions,
  type ArchiveOption,
} from "@plugins/mes/web/src/api/mesArchives";
import RemoteSelect from "./RemoteSelect.vue";
export type ArchiveSelection = {
  process_id?: string | null;
  equipment_id?: string | null;
  requirement_id?: string | null;
  operation_name?: string;
  operation_description?: string | null;
  work_center_name?: string | null;
  workstation_name?: string | null;
  is_quality_required?: boolean;
};
const props = defineProps<{
  orgId: string;
  modelValue: ArchiveSelection;
  disabled?: boolean;
  loadOptions?: typeof archiveOptions;
}>();
const emit = defineEmits<{ "update:modelValue": [value: ArchiveSelection] }>();
const processInfo = ref<{ id: string; org: string; previous: string }>();
const previousNames = computed(() =>
  processInfo.value?.id === props.modelValue.process_id &&
  processInfo.value?.org === props.orgId
    ? processInfo.value.previous
    : "",
);
let request = 0;
watch(
  [() => props.orgId, () => props.modelValue.process_id],
  async ([org, id]) => {
    const current = ++request;
    if (!org || !id) {
      processInfo.value = undefined;
      return;
    }
    if (processInfo.value?.id === id && processInfo.value?.org === org) return;
    processInfo.value = undefined;
    try {
      const choices = await (props.loadOptions || archiveOptions)(
        "processes",
        org,
        props.modelValue.operation_name || "",
      );
      const option = choices.find((row) => row.value === id);
      if (current === request && option)
        processInfo.value = {
          id,
          org,
          previous: option.previous_process_names || "",
        };
    } catch {
      /* 选择器仍可重试；实际发布始终由服务端校验。 */
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  ++request;
});
function set(
  field: "process_id" | "equipment_id" | "requirement_id",
  option?: ArchiveOption,
) {
  const value: ArchiveSelection = { [field]: option?.value || null };
  if (field === "process_id") {
    ++request;
    processInfo.value = option
      ? {
          id: option.value,
          org: props.orgId,
          previous: option.previous_process_names || "",
        }
      : undefined;
    Object.assign(value, {
      equipment_id: null,
      requirement_id: option?.requirement_id || null,
    });
    if (option)
      Object.assign(value, {
        operation_name: option.record_name,
        operation_description: option.description || "",
        is_quality_required:
          props.modelValue.is_quality_required ||
          option.is_quality_required ||
          false,
      });
  }
  if (field === "equipment_id" && option)
    Object.assign(value, {
      workstation_name: option.record_no,
      work_center_name:
        option.work_center_name || props.modelValue.work_center_name,
    });
  if (field === "requirement_id" && option?.description)
    value.operation_description = [
      props.modelValue.operation_description,
      option.description,
    ]
      .filter(Boolean)
      .join("\n");
  emit("update:modelValue", value);
}
async function equipment(value: string) {
  return (
    await (props.loadOptions || archiveOptions)(
      "equipment",
      props.orgId,
      value,
      props.modelValue.process_id
        ? { applicable_process_id: props.modelValue.process_id }
        : { generic_equipment_only: true },
    )
  ).filter((row) => {
    const processes =
      row.process_ids || (row.process_id ? [row.process_id] : []);
    return !processes.length || processes.includes(props.modelValue.process_id);
  });
}
</script>
<template>
  <div class="archive-pickers">
    <el-form-item label="选用工艺档案"
      ><RemoteSelect
        :model-value="modelValue.process_id || ''"
        :disabled="disabled || !orgId"
        :context-key="orgId"
        :load-options="
          (value) => (loadOptions || archiveOptions)('processes', orgId, value)
        "
        :initial-option="
          modelValue.process_id
            ? {
                value: modelValue.process_id,
                label: modelValue.operation_name || '已选工艺',
              }
            : undefined
        "
        placeholder="可选，保留手工配置"
        @select="
          (option) => set('process_id', option as ArchiveOption | undefined)
        "
    /></el-form-item>
    <el-form-item label="生产设备"
      ><RemoteSelect
        :model-value="modelValue.equipment_id || ''"
        :disabled="disabled || !orgId"
        :context-key="`${orgId}:${modelValue.process_id}`"
        :load-options="equipment"
        :initial-option="
          modelValue.equipment_id
            ? {
                value: modelValue.equipment_id,
                label: modelValue.workstation_name || '已选设备',
              }
            : undefined
        "
        placeholder="可选，按所属工艺筛选"
        @select="
          (option) => set('equipment_id', option as ArchiveOption | undefined)
        "
    /></el-form-item>
    <el-form-item label="工艺要求"
      ><RemoteSelect
        :model-value="modelValue.requirement_id || ''"
        :disabled="disabled || !orgId"
        :context-key="`${orgId}:${modelValue.process_id}`"
        :load-options="
          (value) =>
            (loadOptions || archiveOptions)('requirements', orgId, value)
        "
        :initial-option="
          modelValue.requirement_id
            ? { value: modelValue.requirement_id, label: '已选工艺要求' }
            : undefined
        "
        placeholder="可选"
        @select="
          (option) => set('requirement_id', option as ArchiveOption | undefined)
        "
    /></el-form-item>
    <el-alert
      v-if="previousNames"
      class="predecessor-hint"
      :title="`前置工艺：${previousNames}`"
      description="须在本工序之前添加这些工艺；也可直接选用完整的工艺路线。"
      type="info"
      :closable="false"
      show-icon
    />
  </div>
</template>
<style scoped>
.archive-pickers {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.predecessor-hint {
  grid-column: 1 / -1;
}

@media (width <= 800px) {
  .archive-pickers {
    grid-template-columns: 1fr;
  }
}
</style>
