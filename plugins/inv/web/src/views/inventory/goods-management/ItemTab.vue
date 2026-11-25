<template>
  <div class="list-page">
    <ReListHeading data-list-key="material-catalog-v2" title="物料" />
    <section class="list-query-panel">
      <div class="tab-toolbar list-filters">
        <el-form inline class="tab-filter" @submit.prevent>
          <el-form-item>
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="请输入名称 / 编号 / 规格"
              @keyup.enter="search"
            />
          </el-form-item>
          <el-form-item>
            <el-select
              v-model="query.category_id"
              clearable
              filterable
              placeholder="请选择物料分类"
              style="width: 160px"
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
              v-model="query.applicable_warehouse_id"
              clearable filterable placeholder="当前仓库（可切换）" style="width: 180px" @change="onWarehouseChange"
            >
              <el-option v-for="warehouse in warehouseOptions" :key="warehouse.id" :label="warehouse.label" :value="warehouse.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-select
              v-model="query.is_active"
              clearable
              placeholder="请选择状态"
              style="width: 110px"
            >
              <el-option label="启用" :value="true" />
              <el-option label="停用" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-select
              v-model="query.is_asset_managed"
              clearable
              placeholder="请选择资产管理状态"
              style="width: 130px"
            >
              <el-option label="已纳入" :value="true" />
              <el-option label="未纳入" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button data-list-query="search" type="primary" @click="search"
              >搜索</el-button
            >
            <el-button data-list-query="reset" @click="resetQuery"
              >重置</el-button
            >
          </el-form-item>
        </el-form>
      </div>

      <ReListTable
        :list-heading="false"
        list-key="material-catalog-v2"

        :list-refresh="load"
        v-loading="loading"
        :data="rows"
        row-key="id"
        stripe
        class="data-table"
      >
        <el-table-column
          prop="item_no"
          label="物料编号"
          width="180"
          :list-hidden="true"
          show-overflow-tooltip
        />
        <el-table-column
          prop="item_name"
          label="物料信息"
          min-width="220"
          fixed="left"
        >
          <template #default="{ row }">
            <ReListIdentity :primary="row.item_name" :secondary="row.item_no" />
          </template>
        </el-table-column>
        <el-table-column
          prop="category_name"
          label="分类"
          width="110"
          show-overflow-tooltip
        />
        <el-table-column
          prop="specification"
          label="规格型号"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column prop="warehouses" label="适用仓库" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.warehouses?.map(w => w.warehouse_name).join('、') || '未配置' }}</template>
        </el-table-column>
        <el-table-column prop="unit_code" label="单位" width="70">
          <template #default="{ row }">{{ unitLabel(row.unit_code) }}</template>
        </el-table-column>
        <el-table-column
          prop="unit_price"
          label="单价（元/单位）"
          width="140"
          align="center"
        >
          <template #default="{ row }">{{
            formatMoney(row.unit_price)
          }}</template>
        </el-table-column>
        <el-table-column
          prop="default_supplier_name"
          label="默认供应商"
          width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="is_asset_managed"
          label="资产管理"
          width="90"
          align="center"
        >
          <template #default="{ row }">{{
            row.is_asset_managed ? "已纳入" : "未纳入"
          }}</template>
        </el-table-column>
        <el-table-column
          prop="is_lot_controlled"
          label="批次管理"
          width="90"
          align="center"
        >
          <template #default="{ row }">{{
            row.is_lot_controlled ? "是" : "否"
          }}</template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="remark"
          label="备注"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button
              data-list-action="edit"
              v-if="hasPerms('inventory_product:update')"
              link
              type="primary"
              @click="openDialog(row as Item)"
              >编辑</el-button
            >
            <el-button
              data-list-action="delete"
              v-if="hasPerms('inventory_product:delete')" :disabled="row.can_edit_base_fields === false"
              link
              type="danger"
              @click="remove(row as Item)"
              >删除</el-button
            >
          </template>
        </el-table-column>

        <template #list-actions
          ><div class="header-actions">
            <el-button
              data-list-action="export"
              v-if="hasPerms('inventory_product:import')"
              :loading="downloadingTemplate"
              :icon="Download"
              @click="downloadTemplate"
              >下载模板</el-button
            >
            <el-button
              data-list-action="import"
              v-if="hasPerms('inventory_product:import')"
              :icon="Upload"
              @click="importVisible = true"
              >导入物料</el-button
            >
            <el-button
              data-list-action="export"
              v-if="
                hasPerms('inventory_product:list') &&
                hasPerms('inventory_product:export')
              "
              :loading="exporting"
              :icon="Download"
              @click="exportItems"
              >导出物料</el-button
            >
            <el-button
              data-list-action="create"
              v-if="hasPerms('inventory_product:create')"
              type="primary"
              :icon="Plus"
              @click="openDialog()"
              >新增物料</el-button
            >
          </div></template
        >

        <template #list-pagination
          ><div class="table-footer">
            <ReListPagination
              v-model:current-page="query.page"
              v-model:page-size="query.page_size"
              :total="total"
              @current-change="load"
              @size-change="search"
            /></div
        ></template>
      </ReListTable>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑物料' : '新增物料'"
      width="720px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-alert v-if="warehouseOptionsError" :title="warehouseOptionsError" type="error" :closable="false" show-icon />
        <el-alert v-if="basicFieldsLocked" title="该物料已在多个仓库共用，基础信息由管理员统一维护；此处可调整本人管理仓库的适用关系。" type="info" :closable="false" show-icon />
        <el-row :gutter="12">
          <el-col :span="24">
            <el-form-item label="适用仓库" prop="warehouse_ids">
              <el-select v-model="form.warehouse_ids" multiple filterable clearable class="w-full"
                :loading="warehouseOptionsLoading" placeholder="选择允许该物料入库的仓库，可多选">
                <el-option v-for="warehouse in formWarehouseOptions" :key="warehouse.id"
                  :value="warehouse.id" :label="warehouse.label" :disabled="warehouse.disabled" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料编号" prop="item_no">
              <el-input v-model="form.item_no" :disabled="basicFieldsLocked" placeholder="不填自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料名称" prop="item_name">
              <el-input v-model="form.item_name" :disabled="basicFieldsLocked" maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料分类">
              <el-select
                v-model="form.category_id" :disabled="basicFieldsLocked"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="c in categories"
                  :key="c.id"
                  :label="c.category_name"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="规格型号">
              <el-input v-model="form.specification" :disabled="basicFieldsLocked" maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="基本单位" prop="unit_code">
              <el-select
                v-model="form.unit_code" :disabled="basicFieldsLocked"
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="o in meta.md_unit || []"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="辅助单位">
              <el-select
                v-model="form.sub_unit_code" :disabled="basicFieldsLocked"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="o in meta.md_unit || []"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="参考单价">
              <el-input-number
                v-model="form.unit_price" :disabled="basicFieldsLocked"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="默认供应商">
              <el-select
                v-model="form.default_supplier_id" :disabled="basicFieldsLocked"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="s in suppliers"
                  :key="s.id"
                  :label="s.supplier_name"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="允许登记为资产" label-width="120px">
              <el-switch v-model="form.is_asset_managed" :disabled="basicFieldsLocked" />
              <span class="ml-3 text-xs text-gray-500"
                >开启后确认新收货入库会同步登记并确认资产；逐件自动编号，责任部门默认取仓库配置，可在入库时调整。请先配置资产类型；资产统一逐件编号，批次号仅用于收货追溯。</span
              >
            </el-form-item>
          </el-col>
          <template v-if="form.is_asset_managed">
            <el-col :span="12">
              <el-form-item label="默认资产类型">
                <el-select
                  v-model="form.default_asset_type_code" :disabled="basicFieldsLocked"
                  clearable
                  class="w-full"
                  placeholder="收货入库前须配置"
                >
                  <el-option
                    v-for="o in meta.asset_type || []"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </template>
          <el-col :span="12">
            <el-form-item label="批次管理">
              <el-switch v-model="form.is_lot_controlled" :disabled="basicFieldsLocked" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="保质期（天）">
              <el-input-number
                v-model="form.shelf_life_days" :disabled="basicFieldsLocked"
                :min="0"
                :controls="false"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" :disabled="basicFieldsLocked" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" :disabled="basicFieldsLocked" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button data-action="neutral" @click="dialogVisible = false">取消</el-button>
        <el-button data-action="primary" type="primary" :loading="saving" :disabled="warehouseOptionsLoading || Boolean(warehouseOptionsError)" @click="save"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <GoodsImportDialog
      v-model="importVisible"
      kind="product"
      @success="search"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Download, Plus, Upload } from "@element-plus/icons-vue";
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules
} from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { formatMoney } from "@plugins/inv/web/src/api/inventoryManagement";
import {
  createItem,
  deleteItem,
  listItemCategoryOptions,
  listItems,
  listItemWarehouseOptions,
  listSupplierOptions,
  updateItem,
  type Item,
  type ItemBody,
  type ItemWarehouseOption,
  type SupplierOption
} from "@plugins/inv/web/src/api/invGoodsManagement";
import { useInventoryMeta } from "../components/common";
import GoodsImportDialog from "./GoodsImportDialog.vue";
import { preferredWarehouseId, rememberWarehouse } from "../components/warehouseContext";
import {
  downloadGoodsImportTemplate,
  exportGoodsTemplateData
} from "@plugins/inv/web/src/api/invGoodsImport";
import {
  omitEmptyParams,
  saveExcelBlob
} from "@plugins/inv/web/src/views/inventory/shared/utils/exportXlsxFromApi";

const { meta, loadMeta, unitLabel } = useInventoryMeta();
const loading = ref(false);
const saving = ref(false);
const downloadingTemplate = ref(false);
const exporting = ref(false);
const rows = ref<Item[]>([]);
const total = ref(0);
const categories = ref<{ id: string; category_name: string }[]>([]);
const suppliers = ref<SupplierOption[]>([]);
const warehouseOptions = ref<ItemWarehouseOption[]>([]);
const editableWarehouseOptions = ref<ItemWarehouseOption[]>([]);
const warehouseOptionsLoading = ref(false);
const warehouseOptionsError = ref("");
let warehouseRequest = 0;
const query = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  category_id: "",
  applicable_warehouse_id: "",
  is_asset_managed: undefined as boolean | undefined,
  is_active: undefined as boolean | undefined
});
const dialogVisible = ref(false);
const importVisible = ref(false);
const editing = ref<Item | null>(null);
const basicFieldsLocked = computed(() => editing.value?.can_edit_base_fields === false);
const formWarehouseOptions = computed(() => {
  const result = editableWarehouseOptions.value.map(row => ({ ...row, disabled: false }));
  for (const row of editing.value?.warehouses || []) {
    if (!result.some(option => option.id === row.id)) result.push({ ...row,
      label: `${row.org_name} / ${row.warehouse_name}（已失效或不在当前管理范围）`, disabled: row.is_available });
  }
  return result;
});
const formRef = ref<FormInstance>();

type ItemForm = Omit<ItemBody, "unit_price"> & {
  unit_price?: number | null;
};
const emptyForm = (): ItemForm => ({
  warehouse_ids: [],
  item_no: "",
  item_name: "",
  category_id: null,
  specification: "",
  unit_code: "piece",
  sub_unit_code: null,
  unit_price: null,
  default_supplier_id: null,
  is_asset_managed: false,
  default_asset_type_code: null,
  is_lot_controlled: false,
  shelf_life_days: null,
  is_active: true,
  remark: ""
});
const form = reactive<ItemForm>(emptyForm());
const rules: FormRules = {
  warehouse_ids: [{ required: true, type: "array", min: 1, message: "请选择至少一个适用仓库", trigger: "change" }],
  item_name: [{ required: true, message: "请输入物料名称", trigger: "blur" }],
  unit_code: [{ required: true, message: "请选择单位", trigger: "change" }]
};

async function load() {
  loading.value = true;
  try {
    const res = await listItems({
      page: query.page,
      page_size: query.page_size,
      keyword: query.keyword || undefined,
      category_id: query.category_id || undefined,
      applicable_warehouse_id: query.applicable_warehouse_id || undefined,
      is_asset_managed: query.is_asset_managed,
      is_active: query.is_active
    });
    if (res.code !== 0) throw new Error(res.message);
    rows.value = res.data.items;
    total.value = res.data.total;
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载物料失败"));
  } finally {
    loading.value = false;
  }
}
function search() {
  query.page = 1;
  load();
}

function onWarehouseChange() {
  rememberWarehouse(query.applicable_warehouse_id);
  search();
}

function resetQuery() {
  Object.assign(query, {
    page: 1,
    keyword: "",
    category_id: "",
    applicable_warehouse_id: warehouseOptions.value.length === 1 ? warehouseOptions.value[0].id : "",
    is_asset_managed: undefined,
    is_active: undefined
  });
  rememberWarehouse(query.applicable_warehouse_id);
  load();
}

async function downloadTemplate() {
  downloadingTemplate.value = true;
  try {
    await saveExcelBlob(
      await downloadGoodsImportTemplate("product"),
      "物料档案导入模板"
    );
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "模板下载失败"));
  } finally {
    downloadingTemplate.value = false;
  }
}

async function exportItems() {
  exporting.value = true;
  try {
    const { page, page_size, ...filters } = query;
    await saveExcelBlob(
      await exportGoodsTemplateData(omitEmptyParams(filters)),
      "物料档案"
    );
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "物料导出失败"));
  } finally {
    exporting.value = false;
  }
}

async function loadOptions() {
  const [c, s, w] = await Promise.all([
    listItemCategoryOptions(),
    listSupplierOptions(),
    listItemWarehouseOptions()
  ]);
  categories.value = c.code === 0 ? c.data.items : [];
  suppliers.value = s.code === 0 ? s.data.items : [];
  warehouseOptions.value = w.code === 0 ? w.data.items : [];
  if (!warehouseOptions.value.some(option => option.id === query.applicable_warehouse_id)) {
    query.applicable_warehouse_id = preferredWarehouseId(warehouseOptions.value);
  }
}

function openDialog(row?: Item) {
  editing.value = row ?? null;
  Object.assign(form, emptyForm());
  if (row) {
    Object.assign(form, {
      ...row,
      warehouse_ids: [...(row.warehouse_ids || [])],
      unit_price: row.unit_price == null ? null : Number(row.unit_price)
    });
  }
  dialogVisible.value = true;
  void loadEditableWarehouses();
}

async function loadEditableWarehouses() {
  const request = ++warehouseRequest;
  warehouseOptionsLoading.value = true;
  warehouseOptionsError.value = "";
  editableWarehouseOptions.value = [];
  try {
    const response = await listItemWarehouseOptions(editing.value ? "update" : "create");
    if (request !== warehouseRequest) return;
    if (response.code !== 0) throw new Error(response.message);
    editableWarehouseOptions.value = response.data.items;
    if (!editing.value && !form.warehouse_ids?.length) {
      const current = editableWarehouseOptions.value.some(option => option.id === query.applicable_warehouse_id)
        ? query.applicable_warehouse_id : preferredWarehouseId(editableWarehouseOptions.value);
      form.warehouse_ids = current ? [current] : [];
    }
  } catch (error) {
    if (request === warehouseRequest) warehouseOptionsError.value = getHttpErrorMessage(error, "加载适用仓库失败，请重新打开弹窗重试");
  } finally {
    if (request === warehouseRequest) warehouseOptionsLoading.value = false;
  }
}

async function save() {
  if (saving.value || warehouseOptionsLoading.value || warehouseOptionsError.value) return;
  if (!(await formRef.value?.validate().catch(() => false))) return;
  saving.value = true;
  try {
    const body: ItemBody = {
      warehouse_ids: [...(form.warehouse_ids || [])],
      ...(editing.value ? { expected_updated_at: editing.value.updated_at } : {}),
      item_no: form.item_no || null,
      item_name: form.item_name,
      category_id: form.category_id || null,
      specification: form.specification || null,
      unit_code: form.unit_code,
      sub_unit_code: form.sub_unit_code || null,
      unit_price: form.unit_price ?? null,
      default_supplier_id: form.default_supplier_id || null,
      is_asset_managed: form.is_asset_managed,
      default_asset_type_code: form.default_asset_type_code || null,
      is_lot_controlled: form.is_lot_controlled,
      shelf_life_days: form.shelf_life_days ?? null,
      is_active: form.is_active,
      remark: form.remark || null
    };
    if (!body.item_no) delete body.item_no;
    const res = editing.value
      ? await updateItem(editing.value.id, basicFieldsLocked.value
        ? { warehouse_ids: body.warehouse_ids, expected_updated_at: body.expected_updated_at } : body)
      : await createItem(body);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已保存");
    dialogVisible.value = false;
    load();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "保存失败"));
  } finally {
    saving.value = false;
  }
}

async function remove(row: Item) {
  try {
    await ElMessageBox.confirm(
      `确定删除物料「${row.item_name}」吗？已有库存或单据的物料只能停用。`,
      "删除",
      {
        confirmButtonClass: "app-button-danger",
        type: "warning"
      }
    );
  } catch {
    return;
  }
  try {
    const res = await deleteItem(row.id);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已删除");
    load();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "删除失败"));
  }
}

onMounted(async () => {
  await Promise.all([loadMeta(), loadOptions()]);
  load();
});

defineExpose({ reload: async () => { await loadOptions(); await load(); } });
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-filter {
  margin: 0;
}

.tab-filter :deep(.el-form-item) {
  margin-bottom: 8px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
