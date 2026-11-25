<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import type { MesOption } from "@plugins/mes/web/src/api/mes";

const props = defineProps<{
  modelValue?: string;
  loadOptions: (keyword: string) => Promise<MesOption[]>;
  placeholder: string;
  disabled?: boolean;
  contextKey?: string;
  autoSelectSingle?: boolean;
  initialOption?: MesOption;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [option?: MesOption];
}>();
const options = ref<MesOption[]>([]);
const selected = ref<MesOption>();
const loading = ref(false);
const error = ref("");
let request = 0;
async function search(keyword = "") {
  const current = ++request;
  if (props.disabled) return;
  loading.value = true;
  error.value = "";
  try {
    const result = await props.loadOptions(keyword);
    if (current !== request) return;
    options.value =
      selected.value &&
      !result.some((item) => item.value === selected.value.value)
        ? [selected.value, ...result]
        : result;
    if (
      props.autoSelectSingle &&
      !props.modelValue &&
      !keyword &&
      result.length === 1
    )
      change(result[0].value);
  } catch (cause: any) {
    if (current === request) {
      options.value = selected.value ? [selected.value] : [];
      error.value = cause?.message || "选项加载失败，请重试";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function change(value: string) {
  selected.value = options.value.find((item) => item.value === value);
  emit("update:modelValue", value || "");
  emit("select", selected.value);
}
watch(
  () => [props.modelValue, props.initialOption],
  () => {
    const option =
      props.initialOption?.value === props.modelValue
        ? props.initialOption
        : options.value.find((item) => item.value === props.modelValue);
    selected.value = option;
    if (option && !options.value.some((item) => item.value === option.value))
      options.value = [option, ...options.value];
  },
);
watch(
  () => [props.contextKey, props.disabled],
  () => {
    ++request;
    selected.value =
      props.initialOption?.value === props.modelValue
        ? props.initialOption
        : undefined;
    options.value = selected.value ? [selected.value] : [];
    loading.value = false;
    error.value = "";
    if (!props.disabled) search();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  ++request;
});
</script>

<template>
  <div class="remote-select">
    <el-select
      :model-value="modelValue"
      filterable
      remote
      clearable
      :disabled="disabled"
      :remote-method="search"
      :loading="loading"
      :placeholder="placeholder"
      @change="change"
      @visible-change="(visible) => visible && search()"
    >
      <el-option
        v-for="item in options"
        :key="item.value"
        :label="item.label"
        :value="item.value"
      />
      <template #footer
        ><small>最多显示 50 项，可输入关键字查找</small></template
      >
    </el-select>
    <div v-if="error" class="option-error" role="alert">
      {{ error }}
      <el-button link type="primary" @click="search()">重试</el-button>
    </div>
  </div>
</template>

<style scoped>
.remote-select {
  width: 100%;
}

.option-error {
  font-size: 12px;
  color: var(--el-color-danger);
}

small {
  color: var(--el-text-color-secondary);
}
</style>
