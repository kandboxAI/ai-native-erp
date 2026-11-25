<template>
  <ReListPresentation>
    <div
      class="sys-module sys-page inv-query-page list-page list-presentation-container"
    >
      <section class="list-section">
        <ReMenuViews v-model="tab" class="list-tabs" @tab-change="search">
          <el-tab-pane
            v-if="hasPerms('inventory_item:list')"
            label="库存汇总"
            name="summary"
          />
          <el-tab-pane
            v-if="hasPerms('inventory_item:list')"
            label="余额明细"
            name="balance"
          />
          <el-tab-pane
            v-if="hasPerms('inventory_movement:list')"
            label="库存流水"
            name="transaction"
          />
        </ReMenuViews>

        <ReListHeading
          v-if="tab === 'summary'"
          data-list-key="stock-summary-v2"
        >
          <template #title>库存汇总</template>
        </ReListHeading>
        <ReListHeading
          v-else-if="tab === 'balance'"
          data-list-key="stock-balance-v2"
        >
          <template #title>余额明细</template>
        </ReListHeading>
        <ReListHeading v-else data-list-key="stock-transaction-v2">
          <template #title>库存流水</template>
        </ReListHeading>
        <section class="list-query-panel">
          <div class="tab-toolbar query-toolbar list-filters">
            <el-form inline class="tab-filter" @submit.prevent>
              <el-form-item>
                <el-input
                  v-model="filters.keyword"
                  clearable
                  placeholder="请输入名称 / 编号 / 规格"
                  class="filter-keyword"
                  @keyup.enter="search"
                />
              </el-form-item>
              <el-form-item>
                <el-select
                  v-model="filters.category_id"
                  clearable
                  filterable
                  placeholder="请选择物料分类"
                  class="filter-category"
                >
                  <el-option
                    v-for="c in categories"
                    :key="c.id"
                    :label="c.category_name"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-select
                  v-model="filters.org_id"
                  clearable
                  filterable
                  placeholder="请选择所属组织"
                  class="filter-org"
                >
                  <el-option
                    v-for="o in orgOptions"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-select
                  v-model="filters.warehouse_id"
                  clearable
                  filterable
                  placeholder="请选择仓库"
                  class="filter-warehouse"
                >
                  <el-option
                    v-for="l in warehouseOptions"
                    :key="l.id"
                    :label="l.label"
                    :value="l.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="tab === 'summary'">
                <el-select
                  v-model="filters.alert_status"
                  clearable
                  placeholder="请选择库存预警"
                  class="filter-alert"
                >
                  <el-option
                    label="需补货（缺货 + 不足）"
                    value="replenishment"
                  />
                  <el-option
                    v-for="(lbl, key) in ALERT_STATUS_LABELS"
                    :key="key"
                    :label="lbl"
                    :value="key"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="tab === 'balance'">
                <el-select
                  v-model="filters.stock_status_code"
                  clearable
                  placeholder="请选择库存状态"
                  class="filter-status"
                >
                  <el-option
                    v-for="o in meta.inv_stock_status || []"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="tab === 'transaction'">
                <el-date-picker
                  v-model="txRange"
                  type="daterange"
                  value-format="YYYY-MM-DD"
                  range-separator="-"
                  start-placeholder="发生日期开始"
                  end-placeholder="发生日期结束"
                  clearable
                  class="filter-date"
                />
              </el-form-item>
              <el-form-item v-if="tab !== 'transaction'" class="zero-filter">
                <el-switch
                  v-model="filters.include_zero"
                  active-text="显示零库存"
                />
              </el-form-item>
              <el-form-item class="toolbar-actions">
                <el-button
                  data-list-query="search"
                  type="primary"
                  @click="search"
                  >搜索</el-button
                >
                <el-button data-list-query="reset" @click="reset"
                  >重置</el-button
                >
              </el-form-item>
            </el-form>
          </div>

          <div>
            <ReListTable
              v-if="tab === 'summary'"
              v-loading="loading"
              :list-heading="false"
              list-key="stock-summary-v2"
              :list-refresh="load"
              :data="summaryRows"
              :row-key="(row) => `${row.item_id}:${row.warehouse_id}`"
              class="data-table"
            >
              <el-table-column
                prop="item_no"
                label="物料编号"
                width="140"
                :list-hidden="true"
                show-overflow-tooltip
              />
              <el-table-column
                prop="item_name"
                label="物料信息"
                min-width="220"
                fixed="left"
              >
                <template #default="{ row }"
                  ><ReListIdentity
                    :primary="row.item_name"
                    :secondary="row.item_no"
                /></template>
              </el-table-column>
              <el-table-column
                prop="category_name"
                label="分类"
                width="110"
                show-overflow-tooltip
              />
              <el-table-column
                prop="specification"
                label="规格"
                width="120"
                show-overflow-tooltip
              />
              <el-table-column
                prop="org_name"
                label="所属组织"
                min-width="110"
                show-overflow-tooltip
              />
              <el-table-column
                prop="warehouse_name"
                label="仓库"
                min-width="110"
                show-overflow-tooltip
              />
              <el-table-column prop="unit_code" label="单位" width="64">
                <template #default="{ row }">{{
                  unitLabel(row.unit_code)
                }}</template>
              </el-table-column>
              <el-table-column
                prop="quantity"
                label="账面"
                width="80"
                align="right"
              >
                <template #default="{ row }">{{
                  formatQuantity(row.quantity)
                }}</template>
              </el-table-column>
              <el-table-column
                prop="available_quantity"
                label="可用"
                width="80"
                align="right"
              >
                <template #default="{ row }">{{
                  formatQuantity(row.available_quantity)
                }}</template>
              </el-table-column>
              <el-table-column
                prop="lent_quantity"
                label="借出在外"
                width="90"
                align="right"
              >
                <template #default="{ row }">{{
                  formatQuantity(row.lent_quantity)
                }}</template>
              </el-table-column>
              <el-table-column
                prop="min_quantity"
                label="下限 / 上限"
                width="110"
                align="center"
              >
                <template #default="{ row }"
                  >{{
                    row.min_quantity == null
                      ? "—"
                      : formatQuantity(row.min_quantity)
                  }}
                  /
                  {{
                    row.max_quantity == null
                      ? "—"
                      : formatQuantity(row.max_quantity)
                  }}</template
                >
              </el-table-column>
              <el-table-column
                prop="stock_alert_label"
                label="预警"
                width="100"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="alertTagType(row.stock_alert_status)"
                    size="small"
                    >{{ row.stock_alert_label }}</el-tag
                  >
                </template>
              </el-table-column>
              <el-table-column
                prop="suggested_replenishment_quantity"
                label="建议补货"
                width="90"
                align="right"
              >
                <template #default="{ row }">{{
                  toNumber(row.suggested_replenishment_quantity)
                    ? formatQuantity(row.suggested_replenishment_quantity)
                    : "—"
                }}</template>
              </el-table-column>
              <el-table-column
                prop="inventory_value"
                label="库存价值"
                width="110"
                align="right"
              >
                <template #default="{ row }">{{
                  formatMoney(row.inventory_value)
                }}</template>
              </el-table-column>
              <el-table-column label="操作" width="130" fixed="right">
                <template #default="{ row }">
                  <el-button
                    data-action="view"
                    link
                    type="primary"
                    @click="openBalanceDetails(row as StockSummaryRow)"
                    >明细</el-button
                  >
                  <el-button
                    v-if="hasPerms('inventory_movement:list')"
                    data-action="view"
                    link
                    type="primary"
                    @click="openTransactionDetails(row as StockSummaryRow)"
                    >流水</el-button
                  >
                </template>
              </el-table-column>

              <template #list-pagination
                ><div class="table-footer">
                  <ReListPagination
                    v-model:current-page="page"
                    v-model:page-size="pageSize"
                    :total="total"
                    @current-change="load"
                    @size-change="search"
                  /></div
              ></template>
              <template #list-actions>
                <el-button
                  v-if="!warehouseScopeKey && hasPerms('inventory_item:import')"
                  data-list-action="import"
                  round
                  :icon="Upload"
                  @click="importVisible = true"
                  >导入盘点</el-button
                >
                <el-button
                  v-if="hasPerms('inventory_item:list')"
                  data-list-action="export"
                  round
                  :icon="Download"
                  :loading="exporting"
                  @click="exportCsv"
                  >导出库存汇总</el-button
                ></template
              ></ReListTable
            >

            <ReListTable
              v-else-if="tab === 'balance'"
              v-loading="loading"
              :list-heading="false"
              list-key="stock-balance-v2"
              :list-refresh="load"
              :data="balanceRows"
              row-key="id"
              class="data-table"
            >
              <el-table-column
                prop="item_no"
                label="物料编号"
                width="140"
                :list-hidden="true"
                show-overflow-tooltip
              />
              <el-table-column
                prop="item_name"
                label="物料信息"
                min-width="220"
                fixed="left"
              >
                <template #default="{ row }"
                  ><ReListIdentity
                    :primary="row.item_name"
                    :secondary="row.item_no"
                /></template>
              </el-table-column>
              <el-table-column
                prop="specification"
                label="规格"
                width="110"
                show-overflow-tooltip
              />
              <el-table-column
                prop="org_name"
                label="仓库"
                min-width="180"
                show-overflow-tooltip
              >
                <template #default="{ row }"
                  >{{ row.org_name }} / {{ row.warehouse_name }}</template
                >
              </el-table-column>
              <el-table-column
                prop="lot_no"
                label="批次"
                width="120"
                show-overflow-tooltip
              />
              <el-table-column
                prop="expiry_date"
                label="有效期至"
                width="110"
              />
              <el-table-column
                prop="stock_status_code"
                label="库存状态"
                width="90"
              >
                <template #default="{ row }">{{
                  label("inv_stock_status", row.stock_status_code)
                }}</template>
              </el-table-column>
              <el-table-column
                prop="quantity"
                label="数量"
                width="90"
                align="right"
              >
                <template #default="{ row }"
                  >{{ formatQuantity(row.quantity) }}
                  {{ unitLabel(row.unit_code) }}</template
                >
              </el-table-column>
              <el-table-column
                prop="updated_at"
                label="更新时间"
                min-width="150"
              >
                <template #default="{ row }">{{
                  formatDateTime(row.updated_at)
                }}</template>
              </el-table-column>

              <template #list-pagination
                ><div class="table-footer">
                  <ReListPagination
                    v-model:current-page="page"
                    v-model:page-size="pageSize"
                    :total="total"
                    @current-change="load"
                    @size-change="search"
                  /></div
              ></template>
              <template #list-actions>
                <el-button
                  v-if="!warehouseScopeKey && hasPerms('inventory_item:import')"
                  data-list-action="import"
                  round
                  :icon="Upload"
                  @click="importVisible = true"
                  >导入盘点</el-button
                >
                <el-button
                  v-if="hasPerms('inventory_item:list')"
                  data-list-action="export"
                  round
                  :icon="Download"
                  :loading="exporting"
                  @click="exportCsv"
                  >导出余额明细</el-button
                ></template
              ></ReListTable
            >

            <ReListTable
              v-else
              v-loading="loading"
              :list-heading="false"
              list-key="stock-transaction-v2"
              :list-refresh="load"
              :data="txRows"
              row-key="id"
              class="data-table"
            >
              <el-table-column
                prop="item_name"
                label="物料信息"
                min-width="220"
                fixed="left"
              >
                <template #default="{ row }"
                  ><ReListIdentity
                    :primary="row.item_name"
                    :secondary="row.item_no"
                /></template>
              </el-table-column>
              <el-table-column
                prop="transaction_no"
                label="流水号"
                min-width="180"
                show-overflow-tooltip
              />
              <el-table-column
                prop="occurred_at"
                label="发生时间"
                min-width="150"
              >
                <template #default="{ row }">{{
                  formatDateTime(row.occurred_at)
                }}</template>
              </el-table-column>
              <el-table-column prop="order_no" label="单据" min-width="170">
                <template #default="{ row }">
                  <el-button
                    data-action="view"
                    link
                    type="primary"
                    @click="openOrder(row.stock_order_id)"
                    >{{ row.order_no }}</el-button
                  >
                </template>
              </el-table-column>
              <el-table-column
                prop="order_type_name"
                label="单据类型"
                width="100"
              />
              <el-table-column
                prop="lot_no"
                label="批次"
                width="110"
                show-overflow-tooltip
              />
              <el-table-column
                prop="from_warehouse_label"
                label="来源"
                min-width="170"
                show-overflow-tooltip
              >
                <template #default="{ row }">{{
                  row.from_warehouse_label
                    ? `${row.from_warehouse_label}（${label("inv_stock_status", row.from_stock_status_code)}）`
                    : "—"
                }}</template>
              </el-table-column>
              <el-table-column
                prop="to_warehouse_label"
                label="目标"
                min-width="170"
                show-overflow-tooltip
              >
                <template #default="{ row }">{{
                  row.to_warehouse_label
                    ? `${row.to_warehouse_label}（${label("inv_stock_status", row.to_stock_status_code)}）`
                    : "—"
                }}</template>
              </el-table-column>
              <el-table-column
                prop="quantity"
                label="数量"
                width="90"
                align="right"
              >
                <template #default="{ row }"
                  >{{ formatQuantity(row.quantity) }}
                  {{ unitLabel(row.unit_code) }}</template
                >
              </el-table-column>

              <template #list-pagination
                ><div class="table-footer">
                  <ReListPagination
                    v-model:current-page="page"
                    v-model:page-size="pageSize"
                    :total="total"
                    @current-change="load"
                    @size-change="search"
                  /></div
              ></template>
              <template #list-actions>
                <el-button
                  v-if="hasPerms('inventory_item:list')"
                  data-list-action="export"
                  round
                  :icon="Download"
                  :loading="exporting"
                  @click="exportCsv"
                  >导出库存流水</el-button
                ></template
              ></ReListTable
            >
          </div>
        </section>
      </section>

      <GoodsImportDialog
        v-model="importVisible"
        kind="stock"
        @success="search"
      />
      <StockBalanceDrawer
        v-model="balanceDrawerVisible"
        :warehouse-scope-key="warehouseScopeKey"
        :summary="balanceDrawerSummary"
      />
      <StockTransactionDrawer
        v-model="transactionDrawerVisible"
        :warehouse-scope-key="warehouseScopeKey"
        :summary="transactionDrawerSummary"
        @open-order="openOrder"
      />
      <OrderDetailDialog v-model="orderVisible" :order-id="orderId" />
    </div>
  </ReListPresentation>
</template>

<script setup lang="ts">
import { useMenuView } from "@/utils/menuView";
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { Download, Upload } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  ALERT_STATUS_LABELS,
  formatMoney,
  formatQuantity,
  listWarehouseOptions,
  listStockBalances,
  listStockSummary,
  listStockTransactions,
  toNumber,
  type InventoryAlertFilter,
  type InventoryAlertStatus,
  type WarehouseOption,
  type StockBalanceRow,
  type StockSummaryRow,
  type StockTransactionRow,
} from "@plugins/inv/web/src/api/inventoryManagement";
import { listItemCategoryOptions } from "@plugins/inv/web/src/api/invGoodsManagement";
import GoodsImportDialog from "../goods-management/GoodsImportDialog.vue";
import OrderDetailDialog from "../components/OrderDetailDialog.vue";
import { useInventoryMeta, useOrgOptions } from "../components/common";
import StockBalanceDrawer from "./StockBalanceDrawer.vue";
import StockTransactionDrawer from "./StockTransactionDrawer.vue";
import type { InventoryQueryTab } from "./types";

defineOptions({ name: "LogisticsMaterialStock" });
const props = withDefaults(
  defineProps<{ initialTab?: InventoryQueryTab; warehouseScopeKey?: string }>(),
  {
    initialTab: "summary",
  },
);

const route = useRoute();
const warehouseScopeKey = computed(
  () =>
    props.warehouseScopeKey ||
    (typeof route.meta.warehouse_scope_key === "string"
      ? route.meta.warehouse_scope_key
      : undefined),
);
const { orgOptions, loadOrgOptions } = useOrgOptions();
const { meta, loadMeta, label, unitLabel } = useInventoryMeta();

const tab = useMenuView<InventoryQueryTab>(props.initialTab, [
  "summary",
  "balance",
  "transaction",
]);
const loading = ref(false);
const exporting = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const summaryRows = ref<StockSummaryRow[]>([]);
const balanceRows = ref<StockBalanceRow[]>([]);
const txRows = ref<StockTransactionRow[]>([]);
const categories = ref<{ id: string; category_name: string }[]>([]);
const warehouseOptions = ref<WarehouseOption[]>([]);
const txRange = ref<[string, string] | null>(null);
const importVisible = ref(false);
const orderVisible = ref(false);
const orderId = ref<string | null>(null);
const balanceDrawerVisible = ref(false);
const balanceDrawerSummary = ref<StockSummaryRow | null>(null);
const transactionDrawerVisible = ref(false);
const transactionDrawerSummary = ref<StockSummaryRow | null>(null);

const emptyFilters = () => ({
  keyword: "",
  item_id: "",
  category_id: "",
  org_id: "",
  warehouse_id: "",
  alert_status: "" as InventoryAlertFilter | "",
  stock_status_code: "",
  include_zero: false,
});
const filters = reactive(emptyFilters());

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

function common(p = page.value, size = pageSize.value) {
  return {
    warehouse_scope_key: warehouseScopeKey.value,
    page: p,
    page_size: size,
    keyword: filters.keyword || undefined,
    item_id: filters.item_id || undefined,
    org_id: filters.org_id || undefined,
    warehouse_id: filters.warehouse_id || undefined,
  };
}

async function fetchPage(p: number, size: number) {
  if (tab.value === "summary") {
    return listStockSummary({
      ...common(p, size),
      category_id: filters.category_id || undefined,
      alert_status: filters.alert_status || undefined,
      include_zero: filters.include_zero,
    });
  }
  if (tab.value === "balance") {
    return listStockBalances({
      ...common(p, size),
      stock_status_code: filters.stock_status_code || undefined,
      include_zero: filters.include_zero,
    });
  }
  return listStockTransactions({
    ...common(p, size),
    occurred_date_start: txRange.value?.[0],
    occurred_date_end: txRange.value?.[1],
  });
}

async function load() {
  loading.value = true;
  try {
    const res = await fetchPage(page.value, pageSize.value);
    if (res.code !== 0) throw new Error(res.message);
    total.value = res.data.total;
    if (tab.value === "summary")
      summaryRows.value = res.data.items as StockSummaryRow[];
    else if (tab.value === "balance")
      balanceRows.value = res.data.items as StockBalanceRow[];
    else txRows.value = res.data.items as StockTransactionRow[];
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载失败"));
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

function reset() {
  Object.assign(filters, emptyFilters());
  txRange.value = null;
  search();
}

function openBalanceDetails(row: StockSummaryRow) {
  if (!row.warehouse_id) {
    ElMessage.error("当前库存记录缺少仓库信息，无法查看余额明细");
    return;
  }
  balanceDrawerSummary.value = row;
  balanceDrawerVisible.value = true;
}

function openTransactionDetails(row: StockSummaryRow) {
  if (!row.warehouse_id) {
    ElMessage.error("当前库存记录缺少仓库信息，无法查看库存流水");
    return;
  }
  transactionDrawerSummary.value = row;
  transactionDrawerVisible.value = true;
}

function openOrder(id: string) {
  orderId.value = id;
  orderVisible.value = true;
}

async function exportCsv() {
  exporting.value = true;
  try {
    const items: Record<string, unknown>[] = [];
    for (let p = 1; p <= 50; p += 1) {
      const res = await fetchPage(p, 100);
      if (res.code !== 0) throw new Error(res.message);
      items.push(...(res.data.items as unknown as Record<string, unknown>[]));
      if (items.length >= res.data.total || !res.data.items.length) break;
    }
    const columns: [string, (r: Record<string, unknown>) => unknown][] =
      tab.value === "summary"
        ? [
            ["物料编号", (r) => r.item_no],
            ["物料名称", (r) => r.item_name],
            ["分类", (r) => r.category_name],
            ["规格", (r) => r.specification],
            ["所属组织", (r) => r.org_name],
            ["仓库", (r) => r.warehouse_name],
            ["单位", (r) => unitLabel(r.unit_code as string)],
            ["账面", (r) => r.quantity],
            ["可用", (r) => r.available_quantity],
            ["借出在外", (r) => r.lent_quantity],
            ["预警", (r) => r.stock_alert_label],
            ["库存价值", (r) => r.inventory_value],
          ]
        : tab.value === "balance"
          ? [
              ["物料编号", (r) => r.item_no],
              ["物料名称", (r) => r.item_name],
              ["仓库", (r) => r.warehouse_name],
              ["批次", (r) => r.lot_no],
              [
                "库存状态",
                (r) => label("inv_stock_status", r.stock_status_code as string),
              ],
              ["数量", (r) => r.quantity],
            ]
          : [
              ["流水号", (r) => r.transaction_no],
              ["发生时间", (r) => formatDateTime(r.occurred_at as string)],
              ["单号", (r) => r.order_no],
              ["单据类型", (r) => r.order_type_name],
              ["物料", (r) => r.item_name],
              ["批次", (r) => r.lot_no],
              ["来源", (r) => r.from_warehouse_label],
              ["目标", (r) => r.to_warehouse_label],
              ["数量", (r) => r.quantity],
            ];
    const XLSX = await import("xlsx");
    const data = items.map((row) =>
      Object.fromEntries(columns.map(([name, getter]) => [name, getter(row)])),
    );
    const workbook = XLSX.utils.book_new();
    const sheetName =
      tab.value === "summary"
        ? "库存汇总"
        : tab.value === "balance"
          ? "库存余额明细"
          : "出入库流水";
    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.json_to_sheet(data),
      sheetName,
    );
    XLSX.writeFile(
      workbook,
      `库存台账-${sheetName}-${new Date().toISOString().slice(0, 10)}.xlsx`,
    );
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "导出失败"));
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  if (typeof route.query.item_id === "string")
    filters.item_id = route.query.item_id;
  if (typeof route.query.org_id === "string")
    filters.org_id = route.query.org_id;
  await Promise.all([loadMeta(), loadOrgOptions()]);
  const [catRes, locRes] = await Promise.all([
    hasPerms("inventory_product:list") || hasPerms("inventory_item:list")
      ? listItemCategoryOptions()
      : Promise.resolve({ code: 0, data: { items: [] } }),
    listWarehouseOptions({ warehouse_scope_key: warehouseScopeKey.value }),
  ]);
  categories.value = catRes.code === 0 ? catRes.data.items : [];
  warehouseOptions.value = locRes.code === 0 ? locRes.data.items : [];
  load();
});
</script>

<style scoped lang="scss">
.query-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.tab-filter {
  display: flex;
  flex: 1 1 100%;
  flex-wrap: wrap;
  min-width: 0;
}

.tab-filter :deep(.el-form-item) {
  margin-right: 8px;
  margin-bottom: 8px;
}

.filter-keyword {
  width: 210px;
}

.filter-category {
  width: 160px;
}

.filter-warehouse {
  width: 180px;
}

.filter-alert {
  width: 170px;
}

.filter-status {
  width: 140px;
}

.filter-date {
  width: 240px;
}

.zero-filter :deep(.el-form-item__content) {
  min-height: 32px;
}

.toolbar-actions :deep(.el-form-item__content) {
  flex-wrap: wrap;
}

.data-table {
  width: 100%;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 0;
}

@media (width <= 560px) {
  .tab-filter :deep(.el-form-item),
  .filter-keyword,
  .filter-category,
  .filter-org,
  .filter-warehouse,
  .filter-alert,
  .filter-status,
  .filter-date {
    width: 100%;
    margin-right: 0;
  }
}
</style>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>
