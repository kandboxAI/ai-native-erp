<template>
  <ReListPresentation>
    <div
      class="sys-module sys-page stock-setting-page list-page list-presentation-container"
    >
      <section class="list-section">
        <ReListHeading data-list-key="stock-settings-v2">
          <template #title>安全库存设置</template>
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
                  :label="warehouseLabel(warehouse)"
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
                placeholder="请选择配置状态"
                class="filter-select"
              >
                <el-option label="全部状态" value="all" />
                <el-option label="已配置" value="configured" />
                <el-option label="未配置" value="unconfigured" />
                <el-option label="正常" value="normal" />
                <el-option label="库存不足" value="low_stock" />
                <el-option label="缺货" value="out_of_stock" />
                <el-option label="库存积压" value="overstock" />
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
            v-loading="loading"
            :list-heading="false"
            list-key="stock-settings-v2"
            :list-refresh="load"
            :data="rows"
            :row-key="(row) => `${row.item_id}:${row.warehouse_id}`"
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
              prop="stock_alert_label"
              label="状态"
              width="96"
              align="center"
            >
              <template #default="{ row }">
                <el-tag
                  :type="statusTagType(row.stock_alert_status)"
                  size="small"
                >
                  {{ row.stock_alert_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="item_no"
              label="物料编号"
              width="140"
              :list-hidden="true"
            />
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
            <el-table-column prop="org_name" label="组织" min-width="110" />
            <el-table-column
              prop="warehouse_name"
              label="仓库"
              min-width="120"
            />
            <el-table-column
              prop="available_quantity"
              label="当前可用"
              width="115"
              align="right"
            >
              <template #default="{ row }">
                {{ formatQuantity(row.available_quantity) }}
                {{ unitLabel(row.unit_code) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="min_quantity"
              label="安全库存下限"
              width="135"
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
              prop="max_quantity"
              label="补货目标/上限"
              width="140"
              align="right"
            >
              <template #default="{ row }">
                {{ optionalQuantity(row.max_quantity) }}
                <template v-if="row.max_quantity != null">
                  {{ unitLabel(row.unit_code) }}
                </template>
              </template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" width="165">
              <template #default="{ row }">
                {{ row.updated_at ? formatDateTime(row.updated_at) : "—" }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPerms('inventory_product:update')"
              label="操作"
              width="100"
              fixed="right"
            >
              <template #default="{ row }">
                <el-button
                  data-action="edit"
                  link
                  type="primary"
                  @click="openEditDialog(row.item_id, row.warehouse_id)"
                >
                  {{ row.min_quantity == null ? "配置" : "调整" }}
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无可维护的物料仓库组合" />
            </template>

            <template #list-actions
              ><el-button
                v-if="hasPerms('inventory_product:update')"
                data-list-action="create"
                type="primary"
                @click="openCreateDialog"
              >
                新增配置
              </el-button></template
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

      <el-dialog
        v-model="dialogVisible"
        :title="editing ? '调整安全库存' : '新增安全库存配置'"
        width="520px"
        destroy-on-close
      >
        <el-alert
          v-if="!editing"
          title="适用于新物料启用、首次采购或开仓备货前预先确定补货规则。保存后立即纳入预警；当前库存为 0 且下限大于 0 时会进入缺货状态。"
          type="warning"
          :closable="false"
          show-icon
          class="dialog-tip"
        />
        <el-form label-width="135px">
          <el-form-item label="仓库" required>
            <el-select
              v-model="form.warehouse_id"
              :disabled="editing"
              placeholder="请选择仓库"
              style="width: 100%"
              @change="handleWarehouseChange"
            >
              <el-option
                v-for="warehouse in warehouses"
                :key="warehouse.id"
                :label="warehouseLabel(warehouse)"
                :value="warehouse.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="!editing" label="物料分类">
            <el-select
              v-model="itemCategoryId"
              clearable
              filterable
              placeholder="全部物料分类"
              style="width: 100%"
              @change="handleCategoryChange"
            >
              <el-option
                v-for="category in itemCategories"
                :key="category.id"
                :label="category.category_name"
                :value="category.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="物料" required>
            <el-select
              v-model="form.item_id"
              :disabled="editing || !form.warehouse_id"
              filterable
              remote
              reserve-keyword
              :remote-method="searchItems"
              :loading="itemLoading"
              placeholder="输入物料名称、编号或规格"
              style="width: 100%"
            >
              <el-option
                v-for="item in itemOptions"
                :key="item.id"
                :label="itemLabel(item)"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="安全库存下限" required>
            <el-input-number
              v-model="form.min_quantity"
              :min="0"
              :precision="3"
              :step="1"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="补货目标/上限" required>
            <el-input-number
              v-model="form.max_quantity"
              :min="0.001"
              :precision="3"
              :step="1"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button data-action="neutral" @click="dialogVisible = false"
            >取消</el-button
          >
          <el-button
            data-action="primary"
            type="primary"
            :loading="saving"
            @click="save"
          >
            保存
          </el-button>
        </template>
      </el-dialog>
    </div>
  </ReListPresentation>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  formatQuantity,
  listItemOptions,
  listStockSettings,
  listWarehouseOptions,
  saveStockSetting,
  type InventoryAlertStatus,
  type ItemOption,
  type StockSettingParams,
  type StockSettingRow,
  type WarehouseOption,
} from "@plugins/inv/web/src/api/inventoryManagement";
import { useInventoryMeta } from "../components/common";
import { listItemCategoryOptions } from "@plugins/inv/web/src/api/invGoodsManagement";

defineOptions({ name: "LogisticsWarehouseStockSettings" });
const route = useRoute();
const warehouseScopeKey =
  typeof route.meta.warehouse_scope_key === "string"
    ? route.meta.warehouse_scope_key
    : undefined;

const { loadMeta, unitLabel } = useInventoryMeta();
const loading = ref(false);
const saving = ref(false);
const itemLoading = ref(false);
const dialogVisible = ref(false);
const editing = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const rows = ref<StockSettingRow[]>([]);
const warehouses = ref<WarehouseOption[]>([]);
const itemOptions = ref<ItemOption[]>([]);
const itemCategories = ref<{ id: string; category_name: string }[]>([]);
const itemCategoryId = ref("");

const initialFilters = () => ({
  warehouse_id: "",
  keyword: "",
  status_code: "all" as NonNullable<StockSettingParams["status_code"]>,
});
const filters = reactive(initialFilters());
const form = reactive<{
  item_id: string;
  warehouse_id: string;
  min_quantity: number | null;
  max_quantity: number | null;
}>({ item_id: "", warehouse_id: "", min_quantity: null, max_quantity: null });

async function load() {
  loading.value = true;
  try {
    const result = await listStockSettings({
      warehouse_scope_key: warehouseScopeKey,
      page: page.value,
      page_size: pageSize.value,
      warehouse_id: filters.warehouse_id || undefined,
      keyword: filters.keyword || undefined,
      status_code: filters.status_code,
    });
    if (result.code !== 0) throw new Error(result.message);
    rows.value = result.data.items;
    total.value = result.data.total;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "加载安全库存设置失败"));
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

function warehouseLabel(warehouse: WarehouseOption) {
  return warehouse.org_name
    ? `${warehouse.org_name} / ${warehouse.warehouse_name}`
    : warehouse.warehouse_name;
}

function itemLabel(item: ItemOption) {
  const specification = item.specification ? ` · ${item.specification}` : "";
  const category = item.category_name ? ` · ${item.category_name}` : "";
  return `${item.item_name}（${item.item_no}${specification}${category}）`;
}

function optionalQuantity(value: StockSettingRow["min_quantity"]) {
  return value == null ? "—" : formatQuantity(value);
}

function statusTagType(
  status: InventoryAlertStatus,
): "success" | "warning" | "info" | "danger" {
  if (status === "normal") return "success";
  if (status === "unconfigured") return "info";
  if (status === "out_of_stock") return "danger";
  return "warning";
}

async function searchItems(keyword = "") {
  if (!form.warehouse_id) {
    itemOptions.value = [];
    return;
  }
  itemLoading.value = true;
  try {
    const result = await listItemOptions({
      keyword: keyword || undefined,
      warehouse_id: form.warehouse_id,
      category_id: itemCategoryId.value || undefined,
      limit: 100,
    });
    if (result.code !== 0) throw new Error(result.message);
    itemOptions.value = result.data.items;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "加载物料选项失败"));
  } finally {
    itemLoading.value = false;
  }
}

function resetForm() {
  itemCategoryId.value = "";
  itemOptions.value = [];
  Object.assign(form, {
    item_id: "",
    warehouse_id: "",
    min_quantity: null,
    max_quantity: null,
  });
}

function handleWarehouseChange() {
  if (editing.value) return;
  form.item_id = "";
  itemOptions.value = [];
  void searchItems();
}

function handleCategoryChange() {
  form.item_id = "";
  itemOptions.value = [];
  void searchItems();
}

function openCreateDialog() {
  editing.value = false;
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(itemId: string, warehouseId: string | null) {
  const row = rows.value.find(
    (item) => item.item_id === itemId && item.warehouse_id === warehouseId,
  );
  if (!row) return;
  editing.value = true;
  itemOptions.value = [
    {
      id: row.item_id,
      item_no: row.item_no,
      item_name: row.item_name,
      category_id: row.category_id,
      category_name: row.category_name,
      specification: row.specification,
      unit_code: row.unit_code,
      is_lot_controlled: false,
    },
  ];
  Object.assign(form, {
    item_id: row.item_id,
    warehouse_id: row.warehouse_id || "",
    min_quantity: row.min_quantity == null ? null : Number(row.min_quantity),
    max_quantity: row.max_quantity == null ? null : Number(row.max_quantity),
  });
  dialogVisible.value = true;
}

async function save() {
  if (!form.item_id || !form.warehouse_id) {
    ElMessage.warning("请选择物料和仓库");
    return;
  }
  if (form.min_quantity == null || form.max_quantity == null) {
    ElMessage.warning("请填写安全库存下限和补货目标");
    return;
  }
  if (form.max_quantity <= form.min_quantity) {
    ElMessage.warning("补货目标/库存上限必须大于安全库存下限");
    return;
  }
  saving.value = true;
  try {
    const result = await saveStockSetting(form.item_id, form.warehouse_id, {
      min_quantity: form.min_quantity,
      max_quantity: form.max_quantity,
    });
    if (result.code !== 0) throw new Error(result.message);
    ElMessage.success(
      editing.value ? "安全库存设置已更新" : "安全库存配置已新增",
    );
    dialogVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "保存安全库存设置失败"));
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  const [warehouseResult, categoryResult] = await Promise.all([
    listWarehouseOptions({ warehouse_scope_key: warehouseScopeKey }),
    listItemCategoryOptions(),
    loadMeta(),
  ]);
  if (categoryResult.code === 0)
    itemCategories.value = categoryResult.data.items;
  if (warehouseResult.code === 0) warehouses.value = warehouseResult.data.items;
  await load();
});
</script>

<style scoped>
.page-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.page-subtitle {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}

.rule-alert {
  margin-bottom: 16px;
}

.filter-form {
  margin-bottom: 4px;
}

.filter-select {
  width: 220px;
}

.filter-keyword {
  width: 250px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.dialog-tip {
  margin-bottom: 18px;
}

@media (width <= 680px) {
  .page-header {
    align-items: flex-start;
  }

  .filter-select,
  .filter-keyword {
    width: 100%;
  }
}
</style>
