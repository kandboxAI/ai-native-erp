<template>
  <ReListPresentation>
  <div class="sys-module sys-page stock-alert-page list-page list-presentation-container">
    <section class="list-section">
      <ReListHeading data-list-key="stock-alerts-v2">
        <template #title>低库存补货预警</template>
      </ReListHeading>
      <section class="list-query-panel">
        <el-form inline class="filter-form list-filters" @submit.prevent>
          <el-form-item>
            <el-select
              v-model="filters.warehouse_id"
              clearable
              placeholder="请选择仓库"
              class="filter-select"
            >
              <el-option
                v-for="warehouse in warehouses"
                :key="warehouse.id"
                :label="warehouse.label"
                :value="warehouse.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="filters.keyword"
              clearable
              placeholder="请输入物料名称 / 编号 / 规格"
              class="filter-keyword"
              @keyup.enter="search"
            />
          </el-form-item>
          <el-form-item>
            <el-select
              v-model="filters.status_code"
              placeholder="请选择预警状态"
              class="filter-select"
            >
              <el-option label="全部待补货" value="replenishment" />
              <el-option label="缺货" value="out_of_stock" />
              <el-option label="库存不足" value="low_stock" />
              <el-option label="未配置阈值" value="unconfigured" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button data-list-query="search" type="primary" @click="search"
              >搜索</el-button
            >
            <el-button data-list-query="reset" @click="reset">重置</el-button>
          </el-form-item>
        </el-form>

        <ReListTable
          :list-heading="false"
          list-key="stock-alerts-v2"
          :list-refresh="load"
          v-loading="loading"
          :data="rows"
          :row-key="(row) => `${row.item_id}:${row.warehouse_id}`"
          class="data-table"
        >
          <el-table-column prop="item_name" label="物料信息" min-width="220" fixed="left">
            <template #default="{ row }"><ReListIdentity :primary="row.item_name" :secondary="row.item_no" /></template>
          </el-table-column>
          <el-table-column
            prop="stock_alert_label"
            label="预警"
            width="96"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="
                  row.stock_alert_status === 'out_of_stock'
                    ? 'danger'
                    : row.stock_alert_status === 'unconfigured'
                      ? 'info'
                      : 'warning'
                "
                effect="dark"
                size="small"
              >
                {{ row.stock_alert_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="item_no" label="物料编号" width="140" :list-hidden="true" />
          <el-table-column
            prop="specification"
            label="规格"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="category_name"
            label="分类"
            width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="org_name"
            label="组织"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="warehouse_name"
            label="仓库"
            min-width="120"
            show-overflow-tooltip
          />
          <el-table-column
            prop="available_quantity"
            label="当前可用"
            width="110"
            align="right"
          >
            <template #default="{ row }">
              <span class="quantity-danger">
                {{ formatQuantity(row.available_quantity) }}
                {{ unitLabel(row.unit_code) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            prop="min_quantity"
            label="安全库存"
            width="105"
            align="right"
          >
            <template #default="{ row }">
              {{ optionalQuantity(row.min_quantity) }}
              <template v-if="row.min_quantity != null">
                {{ unitLabel(row.unit_code) }}
              </template>
            </template>
          </el-table-column>
          <el-table-column
            prop="suggested_replenishment_quantity"
            label="建议补货"
            width="115"
            align="right"
          >
            <template #default="{ row }">
              <strong v-if="row.stock_alert_status !== 'unconfigured'">
                {{ formatQuantity(row.suggested_replenishment_quantity) }}
                {{ unitLabel(row.unit_code) }}
              </strong>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" width="160">
            <template #default="{ row }">{{
              formatDateTime(row.updated_at)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <el-button
                data-action="view"
                link
                type="primary"
                @click="openStockDetails(row as LowStockAlertRow)"
              >
                查看详情
              </el-button>
              <el-button
                data-action="edit"
                v-if="hasPerms('inventory_product:update')"
                link
                type="primary"
                @click="openThresholdDialog(row as LowStockAlertRow)"
              >
                {{
                  row.stock_alert_status === "unconfigured"
                    ? "配置阈值"
                    : "调整阈值"
                }}
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="当前没有需要补货的物资" />
          </template>

          <template #list-actions
            ><div class="header-actions">
              <el-button
                data-action="edit"
                v-if="hasPerms('inventory_item:list')"
                @click="openStockSettings"
              >
                安全库存设置
              </el-button>
              <el-tag type="danger" effect="light">{{ total }} 项待处理</el-tag>
            </div></template
          >

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
        </ReListTable>
      </section>
    </section>

    <el-drawer
      v-model="detailVisible"
      :title="detailTitle"
      size="min(820px, 92vw)"
      destroy-on-close
      @closed="clearStockDetails"
    >
      <template v-if="selectedAlert">
        <el-descriptions :column="2" border class="detail-summary">
          <el-descriptions-item label="物料编号">
            {{ selectedAlert.item_no }}
          </el-descriptions-item>
          <el-descriptions-item label="物料名称">
            {{ selectedAlert.item_name }}
          </el-descriptions-item>
          <el-descriptions-item label="规格型号">
            {{ selectedAlert.specification || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="物料分类">
            {{ selectedAlert.category_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="所属组织">
            {{ selectedAlert.org_name }}
          </el-descriptions-item>
          <el-descriptions-item label="预警仓库">
            <strong>{{ selectedAlert.warehouse_name || "—" }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="预警状态">
            <el-tag
              :type="
                selectedAlert.stock_alert_status === 'out_of_stock'
                  ? 'danger'
                  : 'warning'
              "
              effect="dark"
              size="small"
            >
              {{ selectedAlert.stock_alert_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="当前可用">
            <span class="quantity-danger">
              {{ formatQuantity(selectedAlert.available_quantity) }}
              {{ unitLabel(selectedAlert.unit_code) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="安全库存">
            {{ optionalQuantity(selectedAlert.min_quantity) }}
            {{ unitLabel(selectedAlert.unit_code) }}
          </el-descriptions-item>
          <el-descriptions-item label="库存上限">
            {{ optionalQuantity(selectedAlert.max_quantity) }}
            {{ unitLabel(selectedAlert.unit_code) }}
          </el-descriptions-item>
          <el-descriptions-item label="建议补货">
            <strong>
              {{
                formatQuantity(selectedAlert.suggested_replenishment_quantity)
              }}
              {{ unitLabel(selectedAlert.unit_code) }}
            </strong>
          </el-descriptions-item>
          <el-descriptions-item label="库存更新时间" :span="2">
            {{ formatDateTime(selectedAlert.updated_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          title="预警按当前仓库独立计算：可用库存 ≤ 安全库存下限时提醒，并建议补至补货目标。"
          type="info"
          :closable="false"
          show-icon
          class="detail-rule"
        />
      </template>
    </el-drawer>

    <el-dialog
      v-model="thresholdVisible"
      title="配置仓库安全库存"
      width="460px"
      destroy-on-close
    >
      <el-alert
        v-if="thresholdRow"
        :title="`${thresholdRow.item_name} · ${thresholdRow.warehouse_name || thresholdRow.org_name}`"
        type="info"
        :closable="false"
        class="threshold-tip"
      />
      <el-form label-width="130px">
        <el-form-item label="安全库存下限" required>
          <el-input-number
            v-model="thresholdForm.min_quantity"
            :min="0"
            :precision="3"
            :step="1"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="补货目标/上限" required>
          <el-input-number
            v-model="thresholdForm.max_quantity"
            :min="0.001"
            :precision="3"
            :step="1"
            controls-position="right"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="neutral" @click="thresholdVisible = false">取消</el-button>
        <el-button
          data-action="primary"
          type="primary"
          :loading="thresholdSaving"
          @click="saveThreshold"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  formatQuantity,
  configureStockThreshold,
  listLowStockAlerts,
  listWarehouseOptions,
  type LowStockAlertRow,
  type StockAlertParams,
  type WarehouseOption
} from "@plugins/inv/web/src/api/inventoryManagement";
import { useInventoryMeta } from "../components/common";

defineOptions({ name: "LogisticsWarehouseStockAlerts" });

const route = useRoute();
const router = useRouter();
const { loadMeta, unitLabel } = useInventoryMeta();

const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const rows = ref<LowStockAlertRow[]>([]);
const warehouses = ref<WarehouseOption[]>([]);
const detailVisible = ref(false);
const selectedAlert = ref<LowStockAlertRow | null>(null);
const thresholdVisible = ref(false);
const thresholdSaving = ref(false);
const thresholdRow = ref<LowStockAlertRow | null>(null);
const thresholdForm = reactive<{
  min_quantity: number | null;
  max_quantity: number | null;
}>({ min_quantity: null, max_quantity: null });
const detailTitle = computed(() => {
  const row = selectedAlert.value;
  return row
    ? `${row.item_name} · ${row.warehouse_name || row.org_name}补货预警详情`
    : "补货预警详情";
});

const initialFilters = () => ({
  keyword: "",
  item_id: "",
  warehouse_id: "",
  status_code: "replenishment" as NonNullable<StockAlertParams["status_code"]>
});
const filters = reactive(initialFilters());

async function load() {
  loading.value = true;
  try {
    const result = await listLowStockAlerts({
      page: page.value,
      page_size: pageSize.value,
      keyword: filters.keyword || undefined,
      item_id: filters.item_id || undefined,
      warehouse_id: filters.warehouse_id || undefined,
      status_code: filters.status_code
    });
    if (result.code !== 0) throw new Error(result.message);
    rows.value = result.data.items;
    total.value = result.data.total;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "加载低库存预警失败"));
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

function reset() {
  Object.assign(filters, initialFilters());
  search();
}

function openStockSettings() {
  return router.push("/inventory/stock-settings");
}

function optionalQuantity(value: LowStockAlertRow["min_quantity"]) {
  return value == null ? "—" : formatQuantity(value);
}

function openStockDetails(row: LowStockAlertRow) {
  selectedAlert.value = row;
  detailVisible.value = true;
}

function clearStockDetails() {
  selectedAlert.value = null;
}

function openThresholdDialog(row: LowStockAlertRow) {
  thresholdRow.value = row;
  thresholdForm.min_quantity =
    row.min_quantity == null ? null : Number(row.min_quantity);
  thresholdForm.max_quantity =
    row.max_quantity == null ? null : Number(row.max_quantity);
  thresholdVisible.value = true;
}

async function saveThreshold() {
  const row = thresholdRow.value;
  if (!row?.warehouse_id) return;
  if (
    thresholdForm.min_quantity == null ||
    thresholdForm.max_quantity == null
  ) {
    ElMessage.warning("请填写安全库存下限和补货目标");
    return;
  }
  if (thresholdForm.max_quantity <= thresholdForm.min_quantity) {
    ElMessage.warning("补货目标/库存上限必须大于安全库存下限");
    return;
  }
  thresholdSaving.value = true;
  try {
    const result = await configureStockThreshold(
      row.item_id,
      row.warehouse_id,
      {
        min_quantity: thresholdForm.min_quantity,
        max_quantity: thresholdForm.max_quantity
      }
    );
    if (result.code !== 0) throw new Error(result.message);
    ElMessage.success("仓库安全库存配置已保存");
    thresholdVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "保存安全库存配置失败"));
  } finally {
    thresholdSaving.value = false;
  }
}

onMounted(async () => {
  if (typeof route.query.item_id === "string")
    filters.item_id = route.query.item_id;
  if (typeof route.query.warehouse_id === "string")
    filters.warehouse_id = route.query.warehouse_id;
  await loadMeta();
  try {
    const result = await listWarehouseOptions({ all_orgs: true });
    warehouses.value = result.code === 0 ? result.data.items : [];
  } catch {
    warehouses.value = [];
  }
  load();
});
</script>

<style scoped lang="scss">
.page-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.page-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.rule-alert {
  margin-bottom: 16px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.filter-keyword {
  width: 220px;
}

.filter-select {
  width: 160px;
}

.data-table {
  width: 100%;
}

.quantity-danger {
  font-weight: 600;
  color: var(--el-color-danger);
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.detail-summary {
  margin-bottom: 16px;
}

.detail-rule {
  margin-bottom: 16px;
}

.threshold-tip {
  margin-bottom: 18px;
}

@media (width <= 680px) {
  .page-header {
    align-items: flex-start;
  }

  .filter-form :deep(.el-form-item),
  .filter-keyword,
  .filter-select {
    width: 100%;
    margin-right: 0;
  }

  .detail-summary {
    --el-descriptions-item-bordered-label-background: var(
      --el-fill-color-light
    );
  }
}
</style>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>
