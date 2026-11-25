<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import {
  listAssetItemOptions,
  type AssetItemOption
} from "@plugins/inv/web/src/api/invAssetManagement";

const props = defineProps<{
  modelValue: string;
  orgId: string;
  disabled?: boolean;
  selectedLabel?: string;
  permissionKey?: "asset_register:list" | "asset_register:create";
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [item: AssetItemOption];
}>();
const items = ref<AssetItemOption[]>([]);
const selected = ref<AssetItemOption>();
const loading = ref(false);
const failed = ref(false);
const keyword = ref("");
const page = ref(1);
const total = ref(0);
let request = 0;
const missingSelection = computed(
  () =>
    props.modelValue && !items.value.some(item => item.id === props.modelValue)
);
const itemLabel = (item: AssetItemOption) =>
  `${item.item_no} · ${item.item_name}${item.specification ? ` · ${item.specification}` : ""}`;

async function load(nextPage = 1) {
  const id = ++request;
  if (!props.orgId || props.disabled) {
    loading.value = false;
    return;
  }
  loading.value = true;
  failed.value = false;
  try {
    const result = await listAssetItemOptions({
      org_id: props.orgId,
      keyword: keyword.value || undefined,
      page: nextPage,
      page_size: 50,
      ...(props.permissionKey ? { permission_key: props.permissionKey } : {})
    });
    if (id !== request) return;
    if (result.code !== 0) throw new Error(result.message);
    items.value = result.data.items;
    page.value = nextPage;
    total.value = result.data.total;
  } catch (error) {
    if (id !== request) return;
    failed.value = true;
    items.value = [];
    total.value = 0;
    ElMessage.error(getHttpErrorMessage(error, "资产物品加载失败"));
  } finally {
    if (id === request) loading.value = false;
  }
}
function search(value: string) {
  keyword.value = value;
  items.value = [];
  void load();
}
function change(value: string) {
  const item = items.value.find(row => row.id === value) || selected.value;
  emit("update:modelValue", value);
  if (item?.id === value) {
    selected.value = item;
    emit("select", item);
  }
}
watch(
  () => [props.orgId, props.disabled],
  () => {
    keyword.value = "";
    items.value = [];
    selected.value = undefined;
    total.value = 0;
    void load();
  },
  { immediate: true }
);
</script>

<template>
  <el-select
    :model-value="modelValue"
    :disabled="disabled"
    filterable
    remote
    :remote-method="search"
    :loading="loading"
    placeholder="搜索物料编号、名称或规格"
    class="w-full"
    @change="change"
  >
    <el-option
      v-if="missingSelection"
      :value="modelValue"
      :label="
        selected?.id === modelValue
          ? itemLabel(selected)
          : selectedLabel || modelValue
      "
      hidden
    />
    <el-option
      v-for="item in items"
      :key="item.id"
      :value="item.id"
      :label="itemLabel(item)"
    >
      <span>{{ itemLabel(item) }}</span>
      <span v-if="item.category_name" class="ml-3 text-xs text-gray-500">{{
        item.category_name
      }}</span>
    </el-option>
    <template #empty>
      <div class="p-3 text-sm text-gray-500">
        {{
          failed
            ? "加载失败，请重新搜索"
            : "无匹配资产物品。请先在物资档案中开启“允许登记为资产”。"
        }}
      </div>
    </template>
    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <span class="text-xs text-gray-500">共 {{ total }} 项</span>
        <el-button
          data-action="neutral"
          size="small"
          :disabled="loading || page <= 1"
          @click.stop="load(page - 1)"
          >上一页</el-button
        >
        <el-button
          data-action="neutral"
          size="small"
          :disabled="loading || page * 50 >= total"
          @click.stop="load(page + 1)"
          >下一页</el-button
        >
      </div>
    </template>
  </el-select>
</template>
