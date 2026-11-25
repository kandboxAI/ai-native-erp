<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from "vue";
import ListPagination from "@/components/ListPagination/index.vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  listStockAssetBindings,
  type StockAssetBinding,
  type StockAssetTracking,
} from "../../../api/invAssetManagement";

const props = defineProps<{
  modelValue?: StockAssetTracking;
  itemId: string;
  warehouseId: string;
  itemName: string;
  unit: string;
  quantity: number;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: StockAssetTracking];
}>();
const loading = ref(false);
const error = ref("");
const bindings = ref<StockAssetBinding[]>([]);
const known = ref<Record<string, StockAssetBinding>>({});
const page = ref(1);
const total = ref(0);
const keyword = ref("");
const opened = ref(false);
let request = 0;
const canTransfer = computed(() => hasPerms("asset_register:transfer"));
const selections = computed(() => props.modelValue?.selections || []);
const selectedQuantity = computed(
  () =>
    Math.round(
      selections.value.reduce((sum, row) => sum + Number(row.quantity), 0) *
        1000,
    ) / 1000,
);
const selectedIds = computed({
  get: () => selections.value.map((row) => row.binding_id),
  set: (ids: string[]) => select(ids),
});
const optionRows = computed(() => [
  ...selections.value
    .map((row) => known.value[row.binding_id])
    .filter((row): row is StockAssetBinding => Boolean(row)),
  ...bindings.value.filter((row) => !selectedIds.value.includes(row.id)),
]);
const mismatch = computed(
  () =>
    selections.value.length > 0 &&
    Math.abs(selectedQuantity.value - props.quantity) > 0.000001,
);

function number(value: string | number) {
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 3 });
}
function shortNo(value: string | null) {
  if (!value) return "历史数量资产";
  return value.length > 28 ? `${value.slice(0, 11)}…${value.slice(-8)}` : value;
}
function label(row: StockAssetBinding) {
  return `${props.itemName} · ${shortNo(row.asset_no)}`;
}
function available(row: StockAssetBinding) {
  return (
    row.stock_status_code === "available" &&
    row.registration_status_code === "confirmed" &&
    ["idle", "in_use"].includes(row.status_code) &&
    Number(row.quantity) > 0
  );
}
function status(row: StockAssetBinding) {
  return available(row) ? "可发放" : "暂不可发放";
}
function disabledOption(row: StockAssetBinding) {
  return (
    !selectedIds.value.includes(row.id) &&
    (!available(row) || selectedQuantity.value >= props.quantity)
  );
}
async function load() {
  if (!props.itemId || !props.warehouseId || !canTransfer.value) return;
  const token = ++request;
  loading.value = true;
  error.value = "";
  try {
    const response = await listStockAssetBindings({
      item_id: props.itemId,
      warehouse_id: props.warehouseId,
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: 20,
    });
    if (token !== request) return;
    bindings.value = response.data.items;
    total.value = response.data.total;
    known.value = {
      ...known.value,
      ...Object.fromEntries(bindings.value.map((row) => [row.id, row])),
    };
  } catch (cause) {
    if (token === request) {
      bindings.value = [];
      error.value = getHttpErrorMessage(cause, "资产加载失败，请重试");
    }
  } finally {
    if (token === request) loading.value = false;
  }
}
function visible(value: boolean) {
  opened.value = value;
  if (value) {
    keyword.value = "";
    page.value = 1;
    bindings.value = [];
    void load();
  }
}
function search(value: string) {
  keyword.value = value.trim();
  page.value = 1;
  void load();
}
function select(ids: string[]) {
  if (props.disabled) return;
  const kept = selections.value.filter((row) => ids.includes(row.binding_id));
  let remaining =
    Math.round(
      (props.quantity -
        kept.reduce((sum, row) => sum + Number(row.quantity), 0)) *
        1000,
    ) / 1000;
  for (const id of ids) {
    if (kept.some((row) => row.binding_id === id)) continue;
    const binding = known.value[id];
    if (!binding || !available(binding) || remaining <= 0) continue;
    const quantity =
      binding.management_mode === "individual"
        ? 1
        : Math.min(Number(binding.quantity), remaining);
    if (quantity > remaining) continue;
    kept.push({ binding_id: id, quantity: String(quantity) });
    remaining = Math.round((remaining - quantity) * 1000) / 1000;
  }
  emit("update:modelValue", { selections: kept });
}
function updateQuantity(id: string, quantity: number | undefined) {
  if (props.disabled || quantity === undefined || quantity <= 0) return;
  emit("update:modelValue", {
    selections: selections.value.map((row) =>
      row.binding_id === id ? { ...row, quantity: String(quantity) } : row,
    ),
  });
}
watch(
  () => [props.itemId, props.warehouseId],
  () => {
    request++;
    bindings.value = [];
    known.value = {};
    loading.value = false;
    error.value = "";
    page.value = 1;
    total.value = 0;
    keyword.value = "";
    emit("update:modelValue", { selections: [] });
    if (opened.value) void load();
  },
);
onScopeDispose(() => {
  request++;
});
</script>

<template>
  <div class="requisition-asset-select">
    <el-select
      v-if="canTransfer"
      v-model="selectedIds"
      multiple
      filterable
      remote
      clearable
      collapse-tags
      collapse-tags-tooltip
      :max-collapse-tags="2"
      :disabled="disabled"
      :loading="loading"
      :remote-method="search"
      :reserve-keyword="false"
      placeholder="下拉选择，可搜索编号或序列号"
      popper-class="requisition-asset-popper"
      :fit-input-width="false"
      @visible-change="visible"
    >
      <el-option
        v-for="binding in optionRows"
        :key="binding.id"
        :value="binding.id"
        :label="label(binding)"
        :disabled="disabledOption(binding)"
      >
        <div class="requisition-asset-option">
          <div class="requisition-asset-option__heading">
            <strong>{{ itemName }}</strong>
            <span
              >{{ status(binding) }} · {{ number(binding.quantity) }}
              {{ unit }}</span
            >
          </div>
          <div
            class="requisition-asset-option__number"
            :title="binding.asset_no || undefined"
          >
            {{ binding.asset_no || "历史数量资产" }}
          </div>
          <div
            v-if="binding.serial_no"
            class="requisition-asset-option__serial"
          >
            序列号：{{ binding.serial_no }}
          </div>
        </div>
      </el-option>
      <template #empty>
        <div class="requisition-asset-empty">
          <template v-if="error"
            ><span>{{ error }}</span
            ><el-button link type="primary" @click.stop="load"
              >重试</el-button
            ></template
          >
          <span v-else>{{
            loading
              ? "正在加载资产…"
              : keyword
                ? "没有匹配资产，请更换关键词"
                : "本仓库暂无可关联资产，普通耗材可直接发放"
          }}</span>
        </div>
      </template>
      <template #footer>
        <ListPagination
          v-if="total > 20"
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          :disabled="loading"
          layout="total, prev, pager, next"
          :pager-count="5"
          small
          @current-change="load"
        />
      </template>
    </el-select>
    <div
      v-if="error && selections.length"
      class="requisition-asset-select__hint"
    >
      {{ error }}
      <el-button
        link
        type="primary"
        :disabled="loading || disabled"
        @click="load"
        >重试</el-button
      >
    </div>
    <span v-if="!canTransfer" class="requisition-asset-select__hint"
      >关联资产需资产流转权限；普通耗材可直接发放</span
    >
    <div
      v-if="selections.length"
      class="requisition-asset-select__summary"
      :class="{ 'is-mismatch': mismatch }"
      :title="
        selections
          .map((row) => known[row.binding_id]?.asset_no || '历史数量资产')
          .join('\n')
      "
    >
      已选 {{ number(selectedQuantity) }} / {{ number(quantity) }} {{ unit }}
      <span v-if="mismatch">，请调整为实际发放数量</span>
    </div>
    <div
      v-for="selection in selections.filter(
        (row) => known[row.binding_id]?.management_mode === 'batch',
      )"
      :key="selection.binding_id"
      class="requisition-asset-select__batch"
    >
      <span>历史数量资产 · 本次发放</span>
      <el-input-number
        :model-value="Number(selection.quantity)"
        :min="0.001"
        :precision="3"
        :max="Math.min(Number(known[selection.binding_id].quantity), quantity)"
        :disabled="disabled"
        controls-position="right"
        size="small"
        @update:model-value="
          (value) => updateQuantity(selection.binding_id, value)
        "
      />
      <span>{{ unit }}</span>
    </div>
  </div>
</template>

<style scoped>
.requisition-asset-select {
  display: grid;
  gap: 6px;
  padding: 4px 0;
}
.requisition-asset-select :deep(.el-select) {
  width: 100%;
}
.requisition-asset-select__summary,
.requisition-asset-select__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.requisition-asset-select__summary {
  color: var(--el-color-success);
}
.requisition-asset-select__summary.is-mismatch {
  color: var(--el-color-warning);
}
.requisition-asset-select__batch {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
:global(.el-select__popper.requisition-asset-popper) {
  width: min(520px, calc(100vw - 40px));
}
:global(.el-select__popper.requisition-asset-popper .el-select-dropdown) {
  min-width: 0 !important;
  width: 100%;
}
:global(.requisition-asset-popper .el-select-dropdown__item) {
  height: auto;
  padding: 10px 14px;
  line-height: 1.5;
  white-space: normal;
}
:global(.requisition-asset-option__heading) {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
:global(.requisition-asset-option__heading span) {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: normal;
}
:global(.requisition-asset-option__number),
:global(.requisition-asset-option__serial) {
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: normal;
}
:global(.requisition-asset-option__number) {
  font-family: var(--el-font-family);
  font-variant-numeric: tabular-nums;
}
:global(.requisition-asset-empty) {
  display: grid;
  gap: 8px;
  padding: 18px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
