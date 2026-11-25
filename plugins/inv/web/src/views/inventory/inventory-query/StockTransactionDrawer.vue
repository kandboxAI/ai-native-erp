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
        <el-descriptions-item label="当前可用">
          <strong>{{ quantityWithUnit(summary.available_quantity) }}</strong>
        </el-descriptions-item>
      </el-descriptions>

      <div class="section-title">出入库记录</div>
      <ReListTable list-key="StockTransactionDrawer-0" :list-controls="false" :list-refresh="load"
        v-loading="loading"
        :data="rows"
        row-key="id"
        table-layout="fixed"
        class="drawer-table"
      >
        <el-table-column prop="occurred_at" label="发生时间" width="165">
          <template #default="{ row }">{{
            formatDateTime(row.occurred_at)
          }}</template>
        </el-table-column>
        <el-table-column prop="order_no" label="单据信息" min-width="205">
          <template #default="{ row }">
            <el-button
              data-action="view"
              link
              type="primary"
              class="order-link"
              @click="emit('open-order', row.stock_order_id)"
            >
              {{ row.order_no }}
            </el-button>
            <div class="cell-sub">{{ row.order_type_name || "—" }}</div>
          </template>
        </el-table-column>
        <el-table-column
          prop="lot_no"
          label="批次"
          width="105"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.lot_no || "—" }}</template>
        </el-table-column>
        <el-table-column prop="from_warehouse_label" label="流转路径" min-width="300">
          <template #default="{ row }">
            <div class="movement-route">
              <div>
                <span class="route-label">来源</span>
                <span>{{
                  warehouseWithStatus(
                    row.from_warehouse_label,
                    row.from_stock_status_code,
                  )
                }}</span>
              </div>
              <div>
                <span class="route-label">目标</span>
                <span>{{
                  warehouseWithStatus(
                    row.to_warehouse_label,
                    row.to_stock_status_code,
                  )
                }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="110" align="right">
          <template #default="{ row }">
            <strong>{{ quantityWithUnit(row.quantity) }}</strong>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="当前物料在该仓库暂无库存流水" />
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
  listStockTransactions,
  type StockSummaryRow,
  type StockTransactionRow,
} from "@plugins/inv/web/src/api/inventoryManagement";
import { useInventoryMeta } from "../components/common";

const props = defineProps<{
  modelValue: boolean;
  summary: StockSummaryRow | null;
  warehouseScopeKey?: string;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
  (event: "open-order", orderId: string): void;
}>();

const { label, unitLabel, loadMeta } = useInventoryMeta();
const loading = ref(false);
const rows = ref<StockTransactionRow[]>([]);
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
    ? `${props.summary.item_name} · ${props.summary.warehouse_name || "仓库"}库存流水`
    : "库存流水",
);

function quantityWithUnit(value: StockTransactionRow["quantity"]) {
  if (!props.summary) return formatQuantity(value);
  return `${formatQuantity(value)} ${unitLabel(props.summary.unit_code)}`;
}

function warehouseWithStatus(
  warehouse: string | null | undefined,
  status: string | null | undefined,
) {
  if (!warehouse) return "—";
  const statusLabel = status ? label("inv_stock_status", status) : "";
  return statusLabel ? `${warehouse}（${statusLabel}）` : warehouse;
}

async function load() {
  const summary = props.summary;
  if (!props.modelValue || !summary?.warehouse_id) return;
  const currentRequest = ++requestSequence;
  loading.value = true;
  try {
    const res = await listStockTransactions({
      page: page.value,
      page_size: pageSize.value,
      item_id: summary.item_id,
      org_id: summary.org_id,
      warehouse_id: summary.warehouse_id,
      warehouse_scope_key: props.warehouseScopeKey,
    });
    if (res.code !== 0) throw new Error(res.message);
    if (currentRequest !== requestSequence) return;
    rows.value = res.data.items;
    total.value = res.data.total;
  } catch (error) {
    if (currentRequest === requestSequence)
      ElMessage.error(getHttpErrorMessage(error, "库存流水加载失败"));
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

.order-link {
  max-width: 100%;
  height: auto;
  padding: 0;
  vertical-align: top;
}

.order-link :deep(span) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-sub {
  margin-top: 3px;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-text-color-secondary);
}

.movement-route {
  display: grid;
  gap: 3px;
  line-height: 20px;
}

.movement-route > div {
  display: flex;
  min-width: 0;
}

.movement-route > div > span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-label {
  flex: 0 0 auto;
  margin-right: 8px;
  color: var(--el-text-color-secondary);
}

.drawer-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
