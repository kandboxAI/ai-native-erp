<script setup lang="ts">
import { watch } from "vue";
import { useBusinessContext } from "@plugins/sample_app/web/src/api/sample_appContext";
const props = defineProps<{
  modelValue?: string | null;
  disabled?: boolean;
  label?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const context = useBusinessContext();
watch(
  () => context?.organizations.value,
  (rows) => {
    if (!props.modelValue && rows?.length === 1)
      emit("update:modelValue", rows[0].id);
  },
  { immediate: true },
);
</script>
<template>
  <el-form-item :label="label || '所属组织'" required
    ><el-select
      :model-value="modelValue || ''"
      :disabled="disabled"
      filterable
      placeholder="请选择所属组织"
      style="width: 220px"
      @update:model-value="(value) => emit('update:modelValue', value)"
      ><el-option
        v-for="item in context?.organizations.value || []"
        :key="item.id"
        :label="item.org_name"
        :value="item.id" /></el-select
  ></el-form-item>
</template>
