<template>
  <ReListPresentation>
    <div
      class="sys-module sys-page goods-mgmt-page list-page list-presentation-container"
    >
      <section v-loading="permissionsLoading" class="list-section">
        <h2 v-if="title">{{ title }}</h2>
        <el-alert
          v-if="permissionError"
          :title="permissionError"
          type="error"
          show-icon
          :closable="false"
        />
        <el-empty
          v-if="
            !permissionsLoading &&
            (availableTabs.length === 0 || (menuView && !activeTab))
          "
          description="暂无可查看的物资资料，请联系管理员分配查询权限"
        >
          <el-button
            data-action="primary"
            :loading="permissionsLoading"
            @click="refreshPermissions"
            >刷新权限</el-button
          >
        </el-empty>
        <ReMenuViews
          v-else-if="!permissionsLoading"
          v-model="activeTab"
          class="goods-tabs list-tabs"
        >
          <el-tab-pane
            v-if="availableTabs.includes('items')"
            label="物料"
            name="items"
            lazy
          >
            <ItemTab ref="itemTabRef" />
          </el-tab-pane>
          <el-tab-pane
            v-if="availableTabs.includes('categories')"
            label="物料分类"
            name="categories"
            lazy
          >
            <SimpleCrudTab
              noun="物料分类"
              permission="inventory_product_category"
              :api="itemCategoryApi"
              :columns="[
                { prop: 'category_name', label: '分类名称', width: 160 },
                {
                  prop: 'parent_name',
                  label: '上级分类',
                  width: 140,
                  format: (r) => categoryName(r.parent_id),
                },
                { prop: 'description', label: '说明', width: 240 },
              ]"
              :fields="[
                { prop: 'category_name', label: '分类名称', required: true },
                {
                  prop: 'parent_id',
                  label: '上级分类',
                  type: 'select',
                  options: () => categoryOptions,
                },
                { prop: 'description', label: '说明', type: 'textarea' },
              ]"
              @changed="loadCategories"
            >
              <template #toolbar>
                <el-button
                  v-if="hasPerms('inventory_product_category:import')"
                  data-list-action="import"
                  round
                  :icon="Upload"
                  @click="categoryImportVisible = true"
                  >导入分类</el-button
                >
              </template>
            </SimpleCrudTab>
          </el-tab-pane>
          <el-tab-pane
            v-if="availableTabs.includes('warehouses')"
            label="仓库"
            name="warehouses"
            lazy
          >
            <SimpleCrudTab
              noun="仓库"
              permission="inventory_warehouse"
              :api="warehouseApi"
              :action-width="320"
              delete-confirm-message="确认删除该仓库？仓库须无库存、无预留且无待处理业务。删除后历史单据和流水仍保留。"
              :columns="[
                {
                  prop: 'warehouse_name',
                  label: '仓库信息',
                  width: 220,
                  type: 'identity',
                  secondaryProp: 'warehouse_no',
                },
                {
                  prop: 'warehouse_no',
                  label: '仓库编号',
                  width: 120,
                  hidden: true,
                },
                { prop: 'org_name', label: '所属组织', width: 140 },
                { prop: 'requisition_approval_department_name', label: '领用审批部门', width: 160 },
                { prop: 'default_asset_department_name', label: '责任部门', width: 160 },
                { prop: 'default_asset_custodian_name', label: '资产保管人', width: 140 },
                {
                  prop: 'location_name',
                  label: '仓库位置',
                  width: 220,
                },
                {
                  prop: 'is_active',
                  label: '状态',
                  type: 'bool',
                  trueText: '启用',
                  falseText: '停用',
                  width: 80,
                },
              ]"
              :fields="[
                {
                  prop: 'org_id',
                  label: '所属组织',
                  type: 'select',
                  required: true,
                  readonlyOnEdit: true,
                  createOnly: true,
                  options: () => orgOptions,
                },
                {
                  prop: 'warehouse_no',
                  label: '仓库编号',
                  required: true,
                  readonlyOnEdit: true,
                },
                { prop: 'warehouse_name', label: '仓库名称', required: true },
                { prop: 'requisition_approval_department_id', label: '领用审批部门', type: 'warehouse_department', placeholder: '请选择领用审批部门', hint: '用于领用申请和详情的审批部门展示；办理账号仍须配置仓库管理授权和审批权限。', resetOnOrgChange: true },
                { prop: 'default_asset_department_id', label: '责任部门', type: 'warehouse_department', resetOnOrgChange: true },
                { prop: 'default_asset_custodian_user_id', label: '资产保管人', type: 'warehouse_custodian', resetOnOrgChange: true },
                { prop: 'location_id', label: '统一位置', type: 'location', required: true },
              ]"
            >
              <template #actions="{ row }">
                <el-button v-if="hasPerms('inventory_warehouse:authorize')" link type="primary"
                  :disabled="!row.is_active" @click="accessWarehouseId = row.id; accessVisible = true">管理账号</el-button>
                <el-button
                  v-if="hasPerms('inventory_warehouse:requisition_scope')"
                  data-list-action="configure"
                  link
                  type="primary"
                  :disabled="!row.is_active"
                  @click="openRequisitionScope(row.id)"
                  >申领范围</el-button
                >
              </template>
            </SimpleCrudTab>
          </el-tab-pane>
          <el-tab-pane
            v-if="availableTabs.includes('suppliers')"
            label="供应商"
            name="suppliers"
            lazy
          >
            <SimpleCrudTab
              noun="供应商"
              permission="supplier"
              :api="supplierApi"
              :action-width="200"
              :filters="[
                {
                  prop: 'category_id',
                  label: '供应商分类',
                  options: () => supplierCategoryOptions,
                },
              ]"
              :columns="[
                {
                  prop: 'supplier_name',
                  label: '供应商信息',
                  width: 220,
                  type: 'identity',
                  secondaryProp: 'supplier_no',
                },
                {
                  prop: 'supplier_no',
                  label: '编号',
                  width: 130,
                  hidden: true,
                },
                { prop: 'category_name', label: '分类', width: 110 },
                { prop: 'contact_name', label: '联系人', width: 90 },
                { prop: 'contact_phone', label: '联系电话', width: 120 },
                {
                  prop: 'settlement_method_code',
                  label: '结算方式',
                  width: 100,
                  format: (r) =>
                    label('md_settlement_method', r.settlement_method_code),
                },
                {
                  prop: 'settlement_cycle_code',
                  label: '结算周期',
                  width: 90,
                  format: (r) =>
                    label('md_settlement_cycle', r.settlement_cycle_code),
                },
                {
                  prop: 'is_active',
                  label: '状态',
                  type: 'bool',
                  trueText: '启用',
                  falseText: '停用',
                  width: 80,
                },
              ]"
              :fields="[
                {
                  prop: 'supplier_no',
                  label: '供应商编号',
                  placeholder: '不填自动生成',
                  readonlyOnEdit: true,
                },
                { prop: 'supplier_name', label: '供应商名称', required: true },
                {
                  prop: 'category_id',
                  label: '分类',
                  type: 'select',
                  options: () => supplierCategoryOptions,
                },
                {
                  prop: 'party_type_code',
                  label: '主体类型',
                  type: 'select',
                  required: true,
                  default: 'organization',
                  options: () => dictOptions('md_party_type'),
                },
                { prop: 'contact_name', label: '联系人' },
                { prop: 'contact_phone', label: '联系电话' },
                {
                  prop: 'settlement_method_code',
                  label: '结算方式',
                  type: 'select',
                  options: () => dictOptions('md_settlement_method'),
                },
                {
                  prop: 'settlement_cycle_code',
                  label: '结算周期',
                  type: 'select',
                  options: () => dictOptions('md_settlement_cycle'),
                },
                {
                  prop: 'is_active',
                  label: '启用',
                  type: 'switch',
                  default: true,
                },
              ]"
            >
              <template #actions="{ row }">
                <el-button
                  v-if="hasPerms('supplier_bank_account:list')"
                  data-action="edit"
                  link
                  type="success"
                  @click="openAccounts(row as Supplier)"
                  >收款账户</el-button
                >
              </template>
            </SimpleCrudTab>
          </el-tab-pane>
          <el-tab-pane
            v-if="availableTabs.includes('supplierCategories')"
            label="供应商分类"
            name="supplierCategories"
            lazy
          >
            <SimpleCrudTab
              noun="供应商分类"
              permission="supplier_category"
              :api="supplierCategoryApi"
              :columns="[
                { prop: 'category_name', label: '分类名称', width: 200 },
                {
                  prop: 'is_active',
                  label: '状态',
                  type: 'bool',
                  trueText: '启用',
                  falseText: '停用',
                  width: 80,
                },
              ]"
              :fields="[
                { prop: 'category_name', label: '分类名称', required: true },
                {
                  prop: 'is_active',
                  label: '启用',
                  type: 'switch',
                  default: true,
                },
              ]"
              @changed="loadSupplierCategories"
            />
          </el-tab-pane>
        </ReMenuViews>
      </section>

      <GoodsImportDialog
        v-model="categoryImportVisible"
        kind="category"
        @success="loadCategories"
      />

      <WarehouseRequisitionScopeDialog
        v-if="scopeWarehouseId"
        v-model="scopeVisible"
        :warehouse-id="scopeWarehouseId"
      />
      <WarehouseAccessDialog v-if="accessWarehouseId" v-model="accessVisible" :warehouse-id="accessWarehouseId" />
      <el-dialog
        v-model="accountsVisible"
        :title="`收款账户 - ${accountSupplier?.supplier_name ?? ''}`"
        width="760px"
        destroy-on-close
      >
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="收款账号属于商业机密：加密保存，列表只显示脱敏账号；修改时需重新输入完整账号。"
          class="mb-3"
        />
        <ReListTable
          v-loading="accountsLoading"
          list-key="index-0"
          :list-controls="false"
          :list-refresh="loadAccounts"
          :data="accounts"
          border
          size="small"
        >
          <el-table-column prop="account_name" label="户名" min-width="140" />
          <el-table-column
            prop="account_no_masked"
            label="账号"
            min-width="170"
          />
          <el-table-column prop="bank_name" label="开户行" min-width="140" />
          <el-table-column
            prop="is_primary"
            label="主要"
            width="60"
            align="center"
          >
            <template #default="{ row }">{{
              row.is_primary ? "是" : ""
            }}</template>
          </el-table-column>
          <el-table-column
            v-if="hasPerms('supplier_bank_account:update')"
            label="操作"
            width="120"
          >
            <template #default="{ row }">
              <el-button
                data-list-action="edit"
                link
                type="primary"
                @click="editAccount(row as SupplierBankAccount)"
                >修改</el-button
              >
              <el-button
                data-list-action="delete"
                link
                type="danger"
                @click="removeAccount(row as SupplierBankAccount)"
                >删除</el-button
              >
            </template>
          </el-table-column>
        </ReListTable>
        <el-form
          v-if="hasPerms('supplier_bank_account:update')"
          :model="accountForm"
          label-width="80px"
          class="account-form"
        >
          <div class="section-title">
            {{ accountForm.id ? "修改账户" : "新增账户" }}
          </div>
          <el-row :gutter="12">
            <el-col :span="12"
              ><el-form-item label="户名" required
                ><el-input v-model="accountForm.account_name" /></el-form-item
            ></el-col>
            <el-col :span="12"
              ><el-form-item label="账号" required
                ><el-input
                  v-model="accountForm.account_no"
                  placeholder="完整账号" /></el-form-item
            ></el-col>
            <el-col :span="12"
              ><el-form-item label="开户行"
                ><el-input v-model="accountForm.bank_name" /></el-form-item
            ></el-col>
            <el-col :span="12"
              ><el-form-item label="主要账户"
                ><el-switch v-model="accountForm.is_primary" /></el-form-item
            ></el-col>
          </el-row>
          <div class="account-actions">
            <el-button
              v-if="accountForm.id"
              data-action="neutral"
              @click="resetAccountForm"
              >取消修改</el-button
            >
            <el-button
              data-action="primary"
              type="primary"
              :loading="accountSaving"
              @click="saveAccount"
              >保存账户</el-button
            >
          </div>
        </el-form>
      </el-dialog>
    </div>
  </ReListPresentation>
</template>

<script setup lang="ts">
import { useMenuView } from "@/utils/menuView";
import { useRoute } from "vue-router";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Upload } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { useUserStoreHook } from "@/store/modules/user";
import { getHttpErrorMessage } from "@/utils/http";
import {
  createWarehouse,
  deleteWarehouse,
  listWarehouses,
  listWarehouseCreateOrgOptions,
  updateWarehouse,
} from "@plugins/inv/web/src/api/inventoryManagement";
import {
  createItemCategory,
  createSupplier,
  createSupplierBankAccount,
  createSupplierCategory,
  deleteItemCategory,
  deleteSupplier,
  deleteSupplierBankAccount,
  deleteSupplierCategory,
  listItemCategories,
  listItemCategoryOptions,
  listSupplierBankAccounts,
  listSupplierCategories,
  listSuppliers,
  updateItemCategory,
  updateSupplier,
  updateSupplierBankAccount,
  updateSupplierCategory,
  type Supplier,
  type SupplierBankAccount,
} from "@plugins/inv/web/src/api/invGoodsManagement";
import { useInventoryMeta } from "../components/common";
import GoodsImportDialog from "./GoodsImportDialog.vue";
import ItemTab from "./ItemTab.vue";
import SimpleCrudTab, { type CrudApi } from "./SimpleCrudTab.vue";
import WarehouseRequisitionScopeDialog from "./WarehouseRequisitionScopeDialog.vue";
import WarehouseAccessDialog from "./WarehouseAccessDialog.vue";
import { accessibleMaterialTabs, selectMaterialTab } from "./tabAccess";

defineOptions({ name: "LogisticsMaterialProducts" });
const props = defineProps<{
  onlyTab?: "items" | "suppliers";
  title?: string;
}>();

const activeTab = props.onlyTab
  ? ref<string>(props.onlyTab)
  : useMenuView<string>("items", [
      "items",
      "categories",
      "warehouses",
      "suppliers",
      "supplierCategories",
    ]);
const menuView = props.onlyTab || useRoute().meta.menuView;
const availableTabs = computed(() =>
  accessibleMaterialTabs(hasPerms).filter(
    (tab) => !props.onlyTab || tab === props.onlyTab,
  ),
);
watch(
  availableTabs,
  (tabs) => {
    activeTab.value =
      typeof menuView === "string"
        ? tabs.includes(menuView as any)
          ? menuView
          : ""
        : selectMaterialTab(activeTab.value, tabs);
  },
  { immediate: true },
);
const permissionsLoading = ref(true);
const permissionError = ref("");
const accessWarehouseId = ref("");
const accessVisible = ref(false);
const itemTabRef = ref<InstanceType<typeof ItemTab>>();
const categoryImportVisible = ref(false);
const orgOptions = ref<{ label: string; value: string }[]>([]);
const scopeVisible = ref(false);
const scopeWarehouseId = ref("");
function openRequisitionScope(id: string) {
  scopeWarehouseId.value = id;
  scopeVisible.value = true;
}
async function loadOrgOptions() {
  if (!hasPerms("inventory_warehouse:create")) {
    orgOptions.value = [];
    return;
  }
  const response = await listWarehouseCreateOrgOptions();
  if (response.code !== 0) throw new Error(response.message);
  orgOptions.value = response.data.items;
}
const { meta, loadMeta, label } = useInventoryMeta();
const dictOptions = (code: string) =>
  (meta.value[code] ?? []).map((o) => ({ label: o.label, value: o.value }));

const categories = ref<{ id: string; category_name: string }[]>([]);
const categoryOptions = computed(() =>
  categories.value.map((c) => ({ label: c.category_name, value: c.id })),
);
const categoryName = (id?: string | null) =>
  categories.value.find((c) => c.id === id)?.category_name ?? "—";
async function loadCategories() {
  const res = await listItemCategoryOptions();
  categories.value = res.code === 0 ? res.data.items : [];
  itemTabRef.value?.reload();
}

const supplierCategoryOptions = ref<{ label: string; value: string }[]>([]);
async function loadSupplierCategories() {
  const res = await listSupplierCategories({ page: 1, page_size: 100 });
  supplierCategoryOptions.value =
    res.code === 0
      ? res.data.items.map((c) => ({ label: c.category_name, value: c.id }))
      : [];
}

const asApi = (api: Record<string, any>) => api as CrudApi;
const itemCategoryApi = asApi({
  list: listItemCategories,
  create: createItemCategory,
  update: updateItemCategory,
  remove: deleteItemCategory,
});
const warehouseApi = asApi({
  list: listWarehouses,
  create: createWarehouse,
  update: updateWarehouse,
  remove: deleteWarehouse,
});
const supplierApi = asApi({
  list: listSuppliers,
  create: createSupplier,
  update: updateSupplier,
  remove: deleteSupplier,
});
const supplierCategoryApi = asApi({
  list: listSupplierCategories,
  create: createSupplierCategory,
  update: updateSupplierCategory,
  remove: deleteSupplierCategory,
});

// ───────── 收款账户 ─────────
const accountsVisible = ref(false);
const accountsLoading = ref(false);
const accountSaving = ref(false);
const accountSupplier = ref<Supplier | null>(null);
const accounts = ref<SupplierBankAccount[]>([]);
const accountForm = reactive({
  id: "",
  account_name: "",
  account_no: "",
  bank_name: "",
  is_primary: false,
});

function resetAccountForm() {
  Object.assign(accountForm, {
    id: "",
    account_name: "",
    account_no: "",
    bank_name: "",
    is_primary: false,
  });
}

async function loadAccounts() {
  if (!accountSupplier.value) return;
  accountsLoading.value = true;
  try {
    const res = await listSupplierBankAccounts(accountSupplier.value.id);
    if (res.code !== 0) throw new Error(res.message);
    accounts.value = res.data.items;
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载收款账户失败"));
  } finally {
    accountsLoading.value = false;
  }
}

function openAccounts(row: Supplier) {
  accountSupplier.value = row;
  resetAccountForm();
  accountForm.account_name = row.supplier_name;
  accountsVisible.value = true;
  loadAccounts();
}

function editAccount(row: SupplierBankAccount) {
  Object.assign(accountForm, {
    id: row.id,
    account_name: row.account_name,
    account_no: "",
    bank_name: row.bank_name ?? "",
    is_primary: row.is_primary,
  });
}

async function saveAccount() {
  if (!accountSupplier.value) return;
  if (!accountForm.account_name || accountForm.account_no.length < 4)
    return ElMessage.warning("请填写户名和完整账号");
  accountSaving.value = true;
  try {
    const body = {
      account_name: accountForm.account_name,
      account_no: accountForm.account_no,
      bank_name: accountForm.bank_name || null,
      is_primary: accountForm.is_primary,
    };
    const res = accountForm.id
      ? await updateSupplierBankAccount(
          accountSupplier.value.id,
          accountForm.id,
          body,
        )
      : await createSupplierBankAccount(accountSupplier.value.id, body);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已保存");
    resetAccountForm();
    loadAccounts();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "保存失败"));
  } finally {
    accountSaving.value = false;
  }
}

async function removeAccount(row: SupplierBankAccount) {
  if (!accountSupplier.value) return;
  try {
    await ElMessageBox.confirm(
      `确定删除收款账户 ${row.account_no_masked ?? ""} 吗？`,
      "删除",
      {
        confirmButtonClass: "app-button-danger",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  try {
    const res = await deleteSupplierBankAccount(
      accountSupplier.value.id,
      row.id,
    );
    if (res.code !== 0) throw new Error(res.message);
    loadAccounts();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "删除失败"));
  }
}

async function refreshPermissions() {
  permissionsLoading.value = true;
  permissionError.value = "";
  try {
    await useUserStoreHook().refreshCurrentUser();
    if (!availableTabs.value.length) return;
    await Promise.all([loadMeta(), loadOrgOptions()]);
    await Promise.all([
      hasPerms("inventory_product_category:list") ||
      hasPerms("inventory_product:list")
        ? loadCategories()
        : Promise.resolve(),
      hasPerms("supplier_category:list")
        ? loadSupplierCategories()
        : Promise.resolve(),
    ]);
  } catch (error) {
    permissionError.value = getHttpErrorMessage(
      error,
      "加载物资资料权限失败，请重试",
    );
  } finally {
    permissionsLoading.value = false;
  }
}
onMounted(refreshPermissions);
</script>

<style scoped lang="scss">
.goods-mgmt-page > .list-section {
  min-height: 128px;
}

.goods-mgmt-page :deep(.tab-toolbar) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.goods-mgmt-page :deep(.tab-filter .el-form-item) {
  margin-right: 8px;
  margin-bottom: 8px;
}

.goods-mgmt-page :deep(.data-table) {
  width: 100%;
}

.goods-mgmt-page :deep(.table-footer) {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 0;
}

.mb-3 {
  margin-bottom: 12px;
}

.section-title {
  margin: 16px 0 8px;
  font-weight: 600;
  color: #334155;
}

.account-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>
