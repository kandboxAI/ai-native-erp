<template>
  <el-drawer
    v-model="visible"
    :title="title"
    size="min(980px, 96vw)"
    class="ledger-detail-drawer"
    destroy-on-close
    @closed="clear"
  >
    <template v-if="summary">
      <el-descriptions :column="2" border class="drawer-summary">
        <el-descriptions-item label="物料编号">
          {{ summary.item_no }}
        </el-descriptions-item>
        <el-descriptions-item label="物料名称">
          {{ summary.item_name }}
        </el-descriptions-item>
        <el-descriptions-item label="规格型号">
          {{ summary.specification || "—" }}
        </el-descriptions-item>
        <el-descriptions-item label="所属组织">
          {{ summary.org_name }}
        </el-descriptions-item>
        <el-descriptions-item label="仓库">
          <strong>{{ summary.warehouse_name || "—" }}</strong>
        </el-descriptions-item>
        <el-descriptions-item label="库存状态">
          <el-tag :type="alertTagType(summary.stock_alert_status)" size="small">
            {{ summary.stock_alert_label }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="账面库存">
          {{ quantityWithUnit(summary.quantity) }}
        </el-descriptions-item>
        <el-descriptions-item label="当前可用">
          <strong>{{ quantityWithUnit(summary.available_quantity) }}</strong>
        </el-descriptions-item>
        <el-descriptions-item label="占用数量">
          {{ quantityWithUnit(summary.reserved_quantity) }}
        </el-descriptions-item>
        <el-descriptions-item label="借出在外">
          {{ quantityWithUnit(summary.lent_quantity) }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="section-title">余额构成</div>
      <ReListTable list-key="StockBalanceDrawer-0" :list-controls="false" :list-refresh="load"
        v-loading="loading"
        :data="rows"
        row-key="id"
        table-layout="fixed"
        class="drawer-table"
      >
        <el-table-column prop="lot_no" label="批次信息" min-width="210">
          <template #default="{ row }">
            <div class="cell-main">{{ row.lot_no || "无批次" }}</div>
            <div class="cell-sub">
              {{ batchDateText(row as StockBalanceRow) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="stock_status_code" label="库存状态" width="100">
          <template #default="{ row }">
            {{ label("inv_stock_status", row.stock_status_code) }}
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="账面数量" width="115" align="right">
          <template #default="{ row }">
            {{ quantityWithUnit(row.quantity) }}
          </template>
        </el-table-column>
        <el-table-column prop="reserved_quantity" label="占用数量" width="115" align="right">
          <template #default="{ row }">
            {{ quantityWithUnit(row.reserved_quantity) }}
          </template>
        </el-table-column>
        <el-table-column prop="available_quantity" label="可用数量" width="115" align="right">
          <template #default="{ row }">
            <strong>{{ quantityWithUnit(row.available_quantity) }}</strong>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="155">
          <template #default="{ row }">{{
            formatDateTime(row.updated_at)
          }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="当前物料在该仓库暂无余额记录" />
        </template>
      </ReListTable>

      <div  class="drawer-pagination">
        <ReListPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          @current-change="load"
          @size-change="changePageSize"
        />
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  formatQuantity,
  listStockBalances,
  type InventoryAlertStatus,
  type StockBalanceRow,
  type StockSummaryRow,
} from "@plugins/inv/web/src/api/inventoryManagement";
import { useInventoryMeta } from "../components/common";

const props = defineProps<{
  modelValue: boolean;
  summary: StockSummaryRow | null;
  warehouseScopeKey?: string;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
}>();

const { label, unitLabel, loadMeta } = useInventoryMeta();
const loading = ref(false);
const rows = ref<StockBalanceRow[]>([]);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
let requestSequence = 0;

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const title = computed(() =>
  props.summary
    ? `${props.summary.item_name} · ${props.summary.warehouse_name || "仓库"}余额明细`
    : "物料余额明细",
);

function alertTagType(status: InventoryAlertStatus) {
  return (
    (
      {
        out_of_stock: "danger",
        low_stock: "warning",
        overstock: "primary",
        normal: "success",
        unconfigured: "info",
      } as const
    )[status] ?? "info"
  );
}

function quantityWithUnit(value: StockBalanceRow["quantity"]) {
  if (!props.summary) return formatQuantity(value);
  return `${formatQuantity(value)} ${unitLabel(props.summary.unit_code)}`;
}

function batchDateText(row: StockBalanceRow) {
  const dates = [
    row.production_date ? `生产 ${row.production_date}` : "",
    row.expiry_date ? `有效期 ${row.expiry_date}` : "",
  ].filter(Boolean);
  return dates.join(" · ") || "未维护生产及有效期";
}

async function load() {
  const summary = props.summary;
  if (!props.modelValue || !summary?.warehouse_id) return;
  const currentRequest = ++requestSequence;
  loading.value = true;
  try {
    const res = await listStockBalances({
      page: page.value,
      page_size: pageSize.value,
      item_id: summary.item_id,
      org_id: summary.org_id,
      warehouse_id: summary.warehouse_id,
      warehouse_scope_key: props.warehouseScopeKey,
      include_zero: true,
    });
    if (res.code !== 0) throw new Error(res.message);
    if (currentRequest !== requestSequence) return;
    rows.value = res.data.items;
    total.value = res.data.total;
  } catch (error) {
    if (currentRequest === requestSequence)
      ElMessage.error(getHttpErrorMessage(error, "余额明细加载失败"));
  } finally {
    if (currentRequest === requestSequence) loading.value = false;
  }
}

function changePageSize() {
  page.value = 1;
  load();
}

function clear() {
  requestSequence += 1;
  loading.value = false;
  rows.value = [];
  total.value = 0;
  page.value = 1;
}

watch(
  () => props.modelValue,
  (isVisible) => {
    if (!isVisible) return;
    page.value = 1;
    loadMeta();
    load();
  },
);
</script>

<style scoped lang="scss">
.drawer-summary {
  margin-bottom: 20px;
}

.section-title {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.drawer-table {
  width: 100%;
}

.cell-main {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.cell-sub {
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.drawer-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
