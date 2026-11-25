<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import { locationOptions, type LocationOption } from "../api/invLocation";
const props = withDefaults(
  defineProps<{
    modelValue?: string | null;
    orgId?: string | null;
    permissionKey: string;
    selectedLabel?: string;
    disabled?: boolean;
  }>(),
  { modelValue: null, orgId: null, selectedLabel: "", disabled: false },
);
const emit = defineEmits<{
  "update:modelValue": [value: string | null];
  select: [row: LocationOption | null];
}>();
const items = ref<LocationOption[]>([]);
const loading = ref(false);
const loaded = ref(false);
const error = ref("");
const missingSelection = computed(
  () =>
    props.modelValue &&
    !items.value.some((item) => item.id === props.modelValue),
);
const selectionLabel = computed(() => {
  if (loading.value || !loaded.value)
    return props.selectedLabel || "正在加载位置…";
  if (error.value) return props.selectedLabel || "位置选项加载失败";
  return props.selectedLabel
    ? `${props.selectedLabel}（当前不可选）`
    : "原位置不可选，请重新选择";
});
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await locationOptions(
      props.permissionKey,
      props.orgId || undefined,
    );
    if (current !== request) return;
    if (result.code !== 0) throw new Error(result.message);
    items.value = result.data.items;
  } catch (cause) {
    if (current === request) {
      items.value = [];
      error.value = getHttpErrorMessage(cause, "位置选项加载失败");
      ElMessage.error(error.value);
    }
  } finally {
    if (current === request) {
      loading.value = false;
      loaded.value = true;
    }
  }
}
function select(value: string) {
  const row = items.value.find((item) => item.id === value) || null;
  emit("update:modelValue", row?.id || null);
  emit("select", row);
}
watch(
  () => [props.orgId, props.permissionKey],
  () => {
    items.value = [];
    loaded.value = false;
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  request++;
});
</script>
<template>
  <el-select
    :model-value="modelValue"
    filterable
    clearable
    :loading="loading"
    :disabled="disabled"
    placeholder="搜索并选择位置名称"
    class="location-select"
    @change="select"
    @visible-change="(value) => value && load()"
  >
    <el-option
      v-if="missingSelection"
      :value="modelValue"
      :label="selectionLabel"
      disabled
    />
    <el-option
      v-for="item in items"
      :key="item.id"
      :value="item.id"
      :label="item.location_name"
    >
      <span>{{ item.location_name }}</span>
    </el-option>
    <template #empty>
      <div class="location-select-empty">
        {{
          loading
            ? "正在加载位置…"
            : error
              ? "位置加载失败，请重试"
              : items.length
                ? "没有匹配的位置"
                : "该组织暂无可选位置"
        }}
      </div>
    </template>
  </el-select>
  <div
    v-if="!loading && loaded && error"
    class="location-select-status is-error"
  >
    {{ error }}
    <el-button link type="primary" @click="load">重新加载</el-button>
  </div>
  <div
    v-else-if="!loading && loaded && !items.length"
    class="location-select-status"
  >
    该组织暂无可选位置，请核对位置的组织归属、启用状态及当前权限范围。
  </div>
</template>
<style scoped>
.location-select {
  width: 100%;
}
.location-select-empty {
  padding: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
.location-select-status {
  margin-top: 6px;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-text-color-secondary);
}
.location-select-status.is-error {
  color: var(--el-color-danger);
}
</style>
