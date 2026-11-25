<script setup lang="ts">
import {
  findAssetLocation,
  assetLocationOptions,
} from "../../utils/assetLocationAliases";
import { formatQuantity } from "@/utils/quantity";
import ReListMoreFilters from "@/components/ReListMoreFilters/index.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  adjustLocationAsset,
  confirmAssetRegistration,
  getAssetOptions,
  getAssetSummary,
  listAssetEvents,
  listAssetLedger,
  transferAssetRegister,
  transferLocationAsset,
  updateAssetRegister,
  updateLocationAsset,
  voidAssetRegistration,
  type AssetEvent,
  type AssetLedger,
  type AssetOptions,
  type AssetSummary,
  type LocationAsset,
} from "@plugins/inv/web/src/api/invAssetManagement";

import AssetItemSelect from "./AssetItemSelect.vue";
import AssetRegistrationForm from "./AssetRegistrationForm.vue";

defineOptions({ name: "AssetManagementLedger" });

const loading = ref(false);
const options = ref<AssetOptions>({
  org_id: "",
  organizations: [],
  items: [],
  locations: [],
  departments: [],
  users: [],
  asset_type: [],
  asset_status: [],
  asset_location_type: [],
  asset_change_event_type: [],
  md_unit: [],
});
const summary = ref<AssetSummary | null>(null);
const assistantFilters = ref<Record<string, string | null>>({});
const rows = ref<AssetLedger[]>([]);
const total = ref(0);
const query = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  is_asset_managed: undefined as boolean | undefined,
  management_mode: "",
  location_id: "",
  asset_type_code: "",
  status_code: "",
  registration_status_code: "",
});

const warehouseAssetDrawer = ref(false);
const assetRegistrationSaving = ref(false);
const quantityDialog = ref(false);
const registerDialog = ref(false);
const adjustDialog = ref(false);
const transferDialog = ref(false);
const detailDrawer = ref(false);
const eventDrawer = ref(false);
const editId = ref("");
const currentTarget = ref<AssetLedger | null>(null);
const detailTarget = ref<AssetLedger | null>(null);
const events = ref<AssetEvent[]>([]);
const eventLoading = ref(false);
const relationOptions = ref<AssetOptions>({
  org_id: "",
  organizations: [],
  items: [],
  locations: [],
  departments: [],
  users: [],
  asset_type: [],
  asset_status: [],
  asset_location_type: [],
  asset_change_event_type: [],
  md_unit: [],
});
const transferOptions = ref<AssetOptions>({
  org_id: "",
  organizations: [],
  items: [],
  locations: [],
  departments: [],
  users: [],
  asset_type: [],
  asset_status: [],
  asset_location_type: [],
  asset_change_event_type: [],
  md_unit: [],
});
const formOptions = ref<AssetOptions>({
  org_id: "",
  organizations: [],
  items: [],
  locations: [],
  departments: [],
  users: [],
  asset_type: [],
  asset_status: [],
  asset_location_type: [],
  asset_change_event_type: [],
  md_unit: [],
});

const quantityForm = reactive<Record<string, any>>({});
const registerForm = reactive<Record<string, any>>({});
const adjustForm = reactive<Record<string, any>>({});
const transferForm = reactive<Record<string, any>>({});

const canCreateAsset = computed(() =>
  ["asset_register:create", "asset_register:confirm"].every(permission => hasPerms(permission)),
);
const canViewSummary = computed(() => hasPerms("asset_register:list"));
const canUpdate = computed(() => hasPerms("asset_register:update"));
const canAdjust = computed(() => hasPerms("asset_register:adjust"));
const canTransfer = computed(() => hasPerms("asset_register:transfer"));
const canDetail = computed(() => hasPerms("asset_register:detail"));
const canConfirmRegistration = computed(() =>
  hasPerms("asset_register:confirm"),
);
const canVoidRegistration = computed(() => hasPerms("asset_register:void"));
const manualAssetStatusCodes = new Set(["in_use", "idle"]);
const acquisitionSourceLabels: Record<string, string> = { historical: "历史盘点补录", donation: "受赠直接登记", direct_delivery: "验收后直接交付", stock_receipt: "仓库收货登记", stock_opening: "期初库存人工关联" };

function reset(target: Record<string, any>, value: Record<string, any>) {
  Object.keys(target).forEach((key) => delete target[key]);
  Object.assign(target, value);
}

function label(list: Array<{ value: string; label: string }>, value: string) {
  return list.find((item) => item.value === value)?.label || value || "-";
}

function locationLabel(id: string | null) {
  if (!id) return "-";
  return (
    findAssetLocation(options.value.locations, id)?.location_name ||
    relationFallback(id)
  );
}

function departmentLabel(id: string | null) {
  if (!id) return "-";
  return (
    options.value.departments.find((row) => row.id === id)?.department_name ||
    relationFallback(id)
  );
}

function departmentOptionLabel(item: AssetOptions["departments"][number]) {
  return `${item.org_name} / ${item.department_name}`;
}

function userLabel(id: string | null) {
  if (!id) return "-";
  return (
    options.value.users.find((row) => row.id === id)?.display_name ||
    relationFallback(id)
  );
}

function relationFallback(id: string) {
  return `原记录已失效（${id.slice(0, 8)}…）`;
}

function relationLocationLabel(id: string | null) {
  if (!id) return "-";
  return (
    findAssetLocation(relationOptions.value.locations, id)?.location_name ||
    relationFallback(id)
  );
}

function relationDepartmentLabel(id: string | null) {
  if (!id) return "-";
  return (
    relationOptions.value.departments.find((row) => row.id === id)
      ?.department_name || relationFallback(id)
  );
}

function relationUserLabel(id: string | null) {
  if (!id) return "-";
  return (
    relationOptions.value.users.find((row) => row.id === id)?.display_name ||
    relationFallback(id)
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(date)
    .replaceAll("/", "-");
}

function hasLedgerMoreActions(row: AssetLedger | Record<string, any>) {
  return Boolean(
    (canUpdate.value &&
      row.registration_status_code === "pending_confirmation") ||
    (row.management_mode === "batch" &&
      canAdjust.value &&
      row.registration_status_code === "confirmed") ||
    (canTransfer.value && row.registration_status_code === "confirmed") ||
    canDetail.value ||
    (canConfirmRegistration.value &&
      row.registration_status_code === "pending_confirmation") ||
    (canVoidRegistration.value && !["stock_receipt", "stock_opening"].includes(row.acquisition_source_code)
      && row.registration_status_code !== "voided"),
  );
}

async function loadRelationOptions(row: AssetLedger | Record<string, any>) {
  try {
    relationOptions.value = (await getAssetOptions(row.org_id)).data;
  } catch {
    relationOptions.value = options.value;
  }
}

function statusType(code: string) {
  if (code === "in_use") return "success";
  if (code === "maintenance") return "warning";
  if (code === "disposed") return "info";
  return "primary";
}

function editableStatusOptions(currentStatusCode?: string) {
  return options.value.asset_status.filter(
    (item) =>
      manualAssetStatusCodes.has(item.value) ||
      item.value === currentStatusCode,
  );
}

function isWorkflowManagedStatus(statusCode?: string) {
  return Boolean(statusCode && !manualAssetStatusCodes.has(statusCode));
}

async function loadOptions() {
  options.value = (await getAssetOptions()).data;
}

async function loadSummary() {
  if (!canViewSummary.value) {
    summary.value = null;
    return;
  }
  try {
    summary.value = (await getAssetSummary()).data;
  } catch (error) {
    summary.value = null;
    ElMessage.error(getHttpErrorMessage(error, "资产概览加载失败"));
  }
}

async function loadRows() {
  loading.value = true;
  const requestedFilters = {
    location_id: query.location_id || null,
    asset_type_code: query.asset_type_code || null,
    status_code: query.status_code || null,
    registration_status_code: query.registration_status_code || null,
  };
  try {
    const result = await listAssetLedger({
      ...query,
      keyword: query.keyword || undefined,
      management_mode: query.management_mode || undefined,
      location_id: query.location_id || undefined,
      asset_type_code: query.asset_type_code || undefined,
      status_code: query.status_code || undefined,
      registration_status_code: query.registration_status_code || undefined,
    });
    rows.value = result.data.items;
    total.value = result.data.total;
    assistantFilters.value = requestedFilters;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "资产数据加载失败"));
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  await Promise.all([loadOptions(), loadSummary()]);
  await loadRows();
}

function search() {
  query.page = 1;
  void loadRows();
}

function resetQuery() {
  Object.assign(query, {
    keyword: "",
    management_mode: "",
    location_id: "",
    asset_type_code: "",
    is_asset_managed: undefined,
    status_code: "",
    registration_status_code: "",
    page: 1,
  });
  void loadRows();
}

function openCreate() {
  if (!canCreateAsset.value) return;
  editId.value = "";
  warehouseAssetDrawer.value = true;
}

async function finishWarehouseAsset() {
  warehouseAssetDrawer.value = false;
  await refresh();
}

async function openEdit(row: any) {
  editId.value = row.id;
  if (row.management_mode === "individual") {
    try {
      formOptions.value = (await getAssetOptions(row.org_id, "ledger")).data;
    } catch (error) {
      ElMessage.error(getHttpErrorMessage(error, "资产编辑选项加载失败"));
      return;
    }
    reset(registerForm, {
      expected_version: row.version_no,
      asset_no: row.asset_no,
      item_id: row.item_id,
      item_label: `${row.item_no} · ${row.item_name}${row.specification ? ` · ${row.specification}` : ""}`,
      asset_type_code: row.asset_type_code,
      serial_no: row.serial_no || "",
      status_code: row.status_code,
      acquired_date: row.acquired_date || "",
      original_amount: row.original_amount,
      remark: row.remark || "",
    });
    registerDialog.value = true;
  } else {
    try {
      formOptions.value = (await getAssetOptions(row.org_id, "ledger")).data;
    } catch (error) {
      ElMessage.error(getHttpErrorMessage(error, "资产编辑选项加载失败"));
      return;
    }
    reset(quantityForm, {
      expected_version: row.version_no,
      item_id: row.item_id,
      item_label: `${row.item_no} · ${row.item_name}${row.specification ? ` · ${row.specification}` : ""}`,
      asset_type_code: row.asset_type_code,
        location_id: row.location_id || "",
      quantity: Number(row.quantity),
      department_id: row.department_id,
      custodian_user_id: row.custodian_user_id,
      status_code: row.status_code,
      remark: row.remark || "",
    });
    quantityDialog.value = true;
  }
}

async function saveQuantityAsset() {
  if (!editId.value) return;
  if (
    !quantityForm.item_id ||
    (!quantityForm.location_id && !quantityForm.custodian_user_id) ||
    !quantityForm.department_id
  ) {
    return ElMessage.warning("请选择物品、责任部门，以及固定位置或个人保管人");
  }
  try {
    const { item_id, location_id, quantity, ...payload } = quantityForm;
    await updateLocationAsset(editId.value, payload);
    ElMessage.success("批量资产已更新");
    quantityDialog.value = false;
    await refresh();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "批量资产保存失败"));
  }
}

async function saveRegister() {
  if (!editId.value) return;
  if (
    !registerForm.asset_no ||
    !registerForm.item_id
  ) {
    return ElMessage.warning("请填写资产编号并选择物品");
  }
  try {
    const { item_id, location_id, department_id, custodian_user_id, ...payload } = registerForm;
    await updateAssetRegister(editId.value, {
      ...payload,
      acquired_date: payload.acquired_date || null,
    });
    ElMessage.success("编号资产已更新");
    registerDialog.value = false;
    await refresh();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "编号资产保存失败"));
  }
}

function openAdjust(row: LocationAsset | Record<string, any>) {
  currentTarget.value = row as AssetLedger;
  reset(adjustForm, {
    expected_version: row.version_no,
    quantity: Number(row.quantity),
    reason: "",
  });
  adjustDialog.value = true;
}

async function submitAdjustment() {
  if (!currentTarget.value) return;
  const reason = String(adjustForm.reason || "").trim();
  if (!reason) return ElMessage.warning("请填写数量调整原因");
  if (Number(adjustForm.quantity) === Number(currentTarget.value.quantity)) {
    return ElMessage.warning("调整后数量不能与当前数量相同");
  }
  try {
    await adjustLocationAsset(currentTarget.value.id, {
      expected_version: adjustForm.expected_version,
      quantity: Number(adjustForm.quantity),
      reason,
    });
    ElMessage.success("资产数量已调整并记录历史");
    adjustDialog.value = false;
    await refresh();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "数量调整失败"));
  }
}

async function openTransfer(row: AssetLedger | Record<string, any>) {
  try {
    transferOptions.value = (await getAssetOptions(row.org_id)).data;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "资产调拨选项加载失败"));
    return;
  }
  currentTarget.value = row as AssetLedger;
  const quantityAsset = row.management_mode === "batch";
  reset(transferForm, {
    expected_version: row.version_no,
    target_location_id: "",
    location_id: row.location_id,
    quantity: quantityAsset ? 1 : undefined,
    target_department_id: quantityAsset ? row.department_id : undefined,
    target_custodian_user_id: quantityAsset ? row.custodian_user_id : undefined,
    department_id: quantityAsset ? undefined : row.department_id,
    custodian_user_id: quantityAsset ? undefined : row.custodian_user_id,
    reason: "",
  });
  transferDialog.value = true;
}

async function submitTransfer() {
  if (!currentTarget.value || !transferForm.reason) {
    return ElMessage.warning("请填写调拨或移交原因");
  }
  try {
    if (currentTarget.value.management_mode === "batch") {
      if (!transferForm.target_location_id)
        return ElMessage.warning("请选择目标位置");
      await transferLocationAsset(currentTarget.value.id, {
        ...transferForm,
        target_department_id: transferForm.target_department_id || null,
        target_custodian_user_id: transferForm.target_custodian_user_id || null,
      });
    } else {
      const payload = {
        expected_version: transferForm.expected_version,
        location_id: transferForm.location_id,
        department_id: transferForm.department_id || null,
        custodian_user_id: transferForm.custodian_user_id || null,
        reason: transferForm.reason,
      };
      await transferAssetRegister(currentTarget.value.id, payload);
    }
    ElMessage.success("资产调拨或责任移交已完成");
    transferDialog.value = false;
    await refresh();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "资产调拨失败"));
  }
}

async function openDetail(row: AssetLedger | Record<string, any>) {
  detailTarget.value = row as AssetLedger;
  detailDrawer.value = true;
  await loadRelationOptions(row);
}

async function openEvents(row: AssetLedger | Record<string, any>) {
  eventDrawer.value = true;
  eventLoading.value = true;
  currentTarget.value = row as AssetLedger;
  try {
    const [result] = await Promise.all([
      listAssetEvents({
        page: 1,
        page_size: 100,
        ...(row.management_mode === "individual"
          ? { asset_register_id: row.id }
          : { location_item_id: row.id }),
      }),
      loadRelationOptions(row),
    ]);
    events.value = result.data.items;
  } catch (error) {
    events.value = [];
    ElMessage.error(getHttpErrorMessage(error, "资产变更记录加载失败"));
  } finally {
    eventLoading.value = false;
  }
}

async function confirmRegistration(row: AssetLedger | Record<string, any>) {
  try {
    await ElMessageBox.confirm(
      "确认后原始登记信息将不可修改，只能通过业务变更或作废重建。是否继续？",
      "确认资产登记",
      {
        confirmButtonClass: "app-button-success",
        type: "warning",
        confirmButtonText: "确认登记",
      },
    );
    await confirmAssetRegistration(row.management_mode, row.id, row.version_no);
    ElMessage.success("资产登记已确认");
    await refresh();
  } catch (error: any) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(getHttpErrorMessage(error, "资产登记确认失败"));
  }
}

async function voidRegistration(row: AssetLedger | Record<string, any>) {
  try {
    const { value } = await ElMessageBox.prompt(
      "作废后保留原始记录，如需更正请重新登记。请填写作废原因。",
      "作废资产登记",
      {
        confirmButtonClass: "app-button-danger",
        inputType: "textarea",
        inputValidator: (value) => Boolean(value?.trim()) || "作废原因不能为空",
        confirmButtonText: "确认作废",
      },
    );
    await voidAssetRegistration(row.management_mode, row.id, {
      expected_version: row.version_no,
      reason: value.trim(),
    });
    ElMessage.success("资产登记已作废");
    await refresh();
  } catch (error: any) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(getHttpErrorMessage(error, "资产登记作废失败"));
  }
}

onMounted(refresh);
</script>

<template>
  <ReListPresentation :filters="assistantFilters">
    <main class="asset-page list-page list-presentation-container">
      <section class="list-section">
        <ReListHeading data-list-key="asset-ledger-v2">
          <template #title> 资产台账 </template>
        </ReListHeading>
        <section
          v-if="canViewSummary"
          class="summary-grid list-page-summary"
          aria-label="资产概览"
        >
          <el-card shadow="never">
            <span>历史数量资产</span>
            <strong>{{
              formatQuantity(summary?.location_asset_quantity)
            }}</strong>
          </el-card>
          <el-card shadow="never">
            <span>编号资产</span>
            <strong>{{ summary?.registered_asset_count ?? "—" }}</strong>
          </el-card>
          <el-card shadow="never">
            <span>有效位置</span>
            <strong>{{ summary?.active_location_count ?? "—" }}</strong>
          </el-card>
          <el-card shadow="never">
            <span>维修中设备</span>
            <strong>{{ summary?.maintenance_asset_count ?? "—" }}</strong>
          </el-card>
          <el-card shadow="never">
            <span>待确认登记</span>
            <strong>{{ summary?.pending_registration_count ?? "—" }}</strong>
          </el-card>
        </section>
        <section class="list-query-panel">
          <div class="toolbar list-filters">
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="请输入编号、名称、规格或地点"
              @keyup.enter="search"
            />
            <el-select
              v-model="query.management_mode"
              clearable
              placeholder="请选择管理方式"
            >
              <el-option label="历史数量资产" value="batch" />
              <el-option label="编号资产" value="individual" />
            </el-select>
            <el-select
              v-model="query.location_id"
              clearable
              placeholder="请选择资产位置"
            >
              <el-option
                v-for="item in assetLocationOptions(
                  options.locations,
                  query.location_id,
                )"
                :key="item.id"
                :label="item.location_name"
                :value="item.id"
              />
            </el-select>

            <el-select
              v-model="query.status_code"
              clearable
              placeholder="请选择资产状态"
            >
              <el-option
                v-for="item in options.asset_status"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>

            <ReListMoreFilters
              :enabled="true"
              :active-count="
                Number(Boolean(query.asset_type_code)) +
                Number(Boolean(query.registration_status_code)) +
                Number(query.is_asset_managed !== undefined)
              "
            >
              <el-select
                v-model="query.asset_type_code"
                clearable
                placeholder="请选择资产类型"
              >
                <el-option
                  v-for="item in options.asset_type"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <el-select
                v-model="query.registration_status_code"
                clearable
                placeholder="请选择登记状态"
              >
                <el-option label="待确认" value="pending_confirmation" />
                <el-option label="已确认" value="confirmed" />
                <el-option label="已作废" value="voided" />
              </el-select>
              <el-select
                v-model="query.is_asset_managed"
                clearable
                placeholder="请选择物料资产管理状态"
              >
                <el-option label="已纳入资产管理" :value="true" />
                <el-option label="未纳入，待核对" :value="false" />
              </el-select>
              <template #actions>
                <span class="list-query-actions">
                  <el-button
                    data-list-query="search"
                    type="primary"
                    plain
                    @click="search"
                    >查询</el-button
                  >
                  <el-button data-list-query="reset" @click="resetQuery"
                    >重置</el-button
                  >
                </span>
              </template>
            </ReListMoreFilters>
          </div>

          <ReListTable
            :list-heading="false"
            list-key="asset-ledger-v2"
            :list-refresh="loadRows"
            v-loading="loading"
            :data="rows"
            border
          >
            <el-table-column
              prop="item_name"
              label="资产信息"
              min-width="220"
              fixed="left"
            >
              <template #default="{ row }">
                <ReListIdentity
                  :primary="row.item_name"
                  :secondary="row.asset_no || '无独立编号'"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="management_mode"
              label="管理方式"
              width="105"
            >
              <template #default="{ row }">
                {{
                  row.management_mode === "individual" ? "编号资产" : "历史数量资产"
                }}
              </template>
            </el-table-column>
            <el-table-column
              prop="is_asset_managed"
              label="物料资产配置"
              width="130"
            >
              <template #default="{ row }"
                ><el-tag :type="row.is_asset_managed ? 'success' : 'warning'">{{
                  row.is_asset_managed ? "已纳入" : "未纳入，待核对"
                }}</el-tag></template
              >
            </el-table-column>
            <el-table-column
              prop="asset_no"
              label="资产编号"
              min-width="145"
              :list-hidden="true"
            >
              <template #default="{ row }">{{ row.asset_no || "-" }}</template>
            </el-table-column>
            <el-table-column
              prop="specification"
              :list-hidden="true"
              label="规格"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              prop="asset_type_code"
              label="资产类型"
              width="105"
              :list-hidden="true"
            >
              <template #default="{ row }">
                {{ label(options.asset_type, row.asset_type_code) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="location_name"
              label="资产位置"
              min-width="150"
            />
            <el-table-column
              prop="quantity"
              label="数量"
              width="120"
              align="right"
              ><template #default="{ row }"
                ><strong>{{ formatQuantity(row.quantity) }}</strong>
                {{
                  row.management_mode === "batch"
                    ? label(options.md_unit, row.unit_code)
                    : "件"
                }}</template
              ></el-table-column
            >
            <el-table-column
              prop="department_name"
              :list-hidden="true"
              label="责任部门"
              min-width="120"
            />
            <el-table-column
              prop="custodian_name"
              label="负责人 / 部门"
              min-width="150"
              ><template #default="{ row }"
                ><ReListIdentity
                  :primary="row.custodian_name || '—'"
                  :secondary="row.department_name" /></template
            ></el-table-column>
            <el-table-column prop="status_code" label="状态" width="100"
              ><template #default="{ row }"
                ><el-tag :type="statusType(row.status_code)">{{
                  label(options.asset_status, row.status_code)
                }}</el-tag></template
              ></el-table-column
            >
            <el-table-column prop="acquisition_source_code" label="登记来源" min-width="140"><template #default="{ row }">{{ acquisitionSourceLabels[row.acquisition_source_code] || '历史盘点补录' }}</template></el-table-column>
            <el-table-column
              prop="registration_status_code"
              label="登记状态"
              width="110"
            >
              <template #default="{ row }">
                <el-tag
                  :type="
                    row.registration_status_code === 'confirmed'
                      ? 'success'
                      : row.registration_status_code === 'voided'
                        ? 'info'
                        : 'warning'
                  "
                >
                  {{
                    row.registration_status_code === "confirmed"
                      ? "已确认"
                      : row.registration_status_code === "voided"
                        ? "已作废"
                        : "待确认"
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              label="操作"
              width="140"
              fixed="right"
              align="center"
              header-align="center"
            >
              <template #default="{ row }">
                <div class="operation-actions">
                  <el-button
                    data-action="view"
                    v-if="canDetail"
                    link
                    type="primary"
                    @click="openDetail(row)"
                    >详情</el-button
                  >
                  <el-dropdown v-if="hasLedgerMoreActions(row)" trigger="click">
                    <el-button data-action="neutral" link type="primary"
                      >更多</el-button
                    >
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item
                          data-action="edit"
                          v-if="
                            canUpdate &&
                            row.registration_status_code ===
                              'pending_confirmation'
                          "
                          @click="openEdit(row)"
                        >
                          编辑
                        </el-dropdown-item>
                        <el-dropdown-item
                          data-action="edit"
                          v-if="
                            row.management_mode === 'batch' &&
                            canAdjust &&
                            row.registration_status_code === 'confirmed'
                          "
                          @click="openAdjust(row)"
                        >
                          调数量
                        </el-dropdown-item>
                        <el-dropdown-item
                          data-action="edit"
                          v-if="
                            canTransfer &&
                            row.registration_status_code === 'confirmed'
                          "
                          @click="openTransfer(row)"
                        >
                          调拨/移交
                        </el-dropdown-item>
                        <el-dropdown-item
                          data-action="neutral"
                          v-if="canDetail"
                          @click="openEvents(row)"
                        >
                          变更记录
                        </el-dropdown-item>
                        <el-dropdown-item
                          data-action="primary"
                          v-if="
                            canConfirmRegistration &&
                            row.registration_status_code ===
                              'pending_confirmation'
                          "
                          @click="confirmRegistration(row)"
                        >
                          确认登记
                        </el-dropdown-item>
                        <el-dropdown-item
                          data-action="danger"
                          v-if="
                            canVoidRegistration &&
                            !['stock_receipt', 'stock_opening'].includes(row.acquisition_source_code) &&
                            row.registration_status_code !== 'voided'
                          "
                          class="danger-action"
                          divided
                          @click="voidRegistration(row)"
                        >
                          作废
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
            </el-table-column>

            <template #list-actions
              ><el-button
                data-list-action="create"
                v-if="canCreateAsset"
                type="primary"
                @click="openCreate"
              >
                <IconifyIconOnline icon="ri:add-line" class="mr-1" />
                新增资产
              </el-button>

            </template>

            <template #list-pagination
              ><ReListPagination
                v-model:current-page="query.page"
                v-model:page-size="query.page_size"
                :total="total"
                @change="loadRows"
            /></template>
          </ReListTable>
        </section>
      </section>

      <el-dialog
        v-model="warehouseAssetDrawer"
        title="新增资产"
        width="min(920px, calc(100vw - 32px))"
        class="asset-registration-dialog"
        align-center
        append-to-body
        destroy-on-close
        :close-on-click-modal="false"
        :close-on-press-escape="!assetRegistrationSaving"
        :show-close="!assetRegistrationSaving"
      >
        <AssetRegistrationForm
          v-if="warehouseAssetDrawer"
          @saved="finishWarehouseAsset"
          @busy="assetRegistrationSaving = $event"
          @cancel="warehouseAssetDrawer = false"
        />
      </el-dialog>


      <el-dialog
        v-model="quantityDialog"
        title="编辑批量资产"
        width="600px"
      >
        <el-form label-width="100px">
          <el-form-item label="资产物品" required>
            <AssetItemSelect
              v-model="quantityForm.item_id"
              :org-id="formOptions.org_id"
              disabled
              :selected-label="quantityForm.item_label"
            />
          </el-form-item>
          <el-form-item label="资产位置" required
            ><el-select
              v-model="quantityForm.location_id"
              filterable
              disabled
              class="w-full"
              ><el-option
                v-for="item in assetLocationOptions(
                  formOptions.locations,
                  quantityForm.location_id,
                )"
                :key="item.id"
                :label="item.location_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="资产类型"
            ><el-select v-model="quantityForm.asset_type_code" class="w-full"
              ><el-option
                v-for="item in options.asset_type"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select
          ></el-form-item>
          <el-form-item label="数量" required
            ><el-input-number
              v-model="quantityForm.quantity"
              :min="0.001"
              :precision="3"
              disabled
          /></el-form-item>
          <el-form-item label="责任部门" required
            ><el-select
              v-model="quantityForm.department_id"
              clearable
              filterable
              placeholder="请选择责任部门"
              class="w-full"
              ><el-option
                v-for="item in formOptions.departments"
                :key="item.id"
                :label="departmentOptionLabel(item)"
                :value="item.id"
            /></el-select>
          </el-form-item>
          <el-form-item label="资产保管人"
            ><el-select
              v-model="quantityForm.custodian_user_id"
              clearable
              filterable
              placeholder="请选择资产保管人"
              class="w-full"
              ><el-option
                v-for="item in formOptions.users"
                :key="item.id"
                :label="item.display_name"
                :value="item.id"
            /></el-select>
          </el-form-item>
          <el-form-item label="状态"
            ><el-select
              v-model="quantityForm.status_code"
              :disabled="
                Boolean(editId) &&
                isWorkflowManagedStatus(quantityForm.status_code)
              "
              class="w-full"
              ><el-option
                v-for="item in editableStatusOptions(quantityForm.status_code)"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select
          ></el-form-item>
          <el-alert
            v-if="
              Boolean(editId) &&
              isWorkflowManagedStatus(quantityForm.status_code)
            "
            title="维修和报废状态由对应业务流程维护"
            type="info"
            :closable="false"
            show-icon
            class="status-tip"
          />
          <el-form-item label="备注"
            ><el-input v-model="quantityForm.remark" type="textarea"
          /></el-form-item>
        </el-form>
        <template #footer
          ><el-button data-action="neutral" @click="quantityDialog = false"
            >取消</el-button
          ><el-button
            data-action="primary"
            type="primary"
            @click="saveQuantityAsset"
            >保存</el-button
          ></template
        >
      </el-dialog>

      <el-dialog
        v-model="registerDialog"
        title="编辑编号资产"
        width="620px"
      >
        <el-form label-width="100px">
          <el-form-item label="资产编号" required
            ><el-input v-model="registerForm.asset_no"
          /></el-form-item>
          <el-form-item label="资产物品" required>
            <AssetItemSelect
              v-model="registerForm.item_id"
              :org-id="formOptions.org_id"
              disabled
              :selected-label="registerForm.item_label"
            />
          </el-form-item>
          <el-form-item label="资产类型"
            ><el-select v-model="registerForm.asset_type_code" class="w-full"
              ><el-option
                v-for="item in options.asset_type"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select
          ></el-form-item>
          <el-form-item label="序列号"
            ><el-input v-model="registerForm.serial_no"
          /></el-form-item>
          <el-form-item label="资产状态"
            ><el-select
              v-model="registerForm.status_code"
              :disabled="
                Boolean(editId) &&
                isWorkflowManagedStatus(registerForm.status_code)
              "
              class="w-full"
              ><el-option
                v-for="item in editableStatusOptions(registerForm.status_code)"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select
          ></el-form-item>
          <el-alert
            v-if="
              Boolean(editId) &&
              isWorkflowManagedStatus(registerForm.status_code)
            "
            title="维修和报废状态由对应业务流程维护"
            type="info"
            :closable="false"
            show-icon
            class="status-tip"
          />
          <el-form-item label="购置日期"
            ><el-date-picker
              v-model="registerForm.acquired_date"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="购置原值（元）">
            <div class="amount-field">
              <el-input-number
                v-model="registerForm.original_amount"
                :min="0"
                :precision="2"
              />
              <span class="field-tip">资产取得时的入账成本，未知可不填</span>
            </div>
          </el-form-item>
          <el-form-item label="备注"
            ><el-input v-model="registerForm.remark" type="textarea"
          /></el-form-item>
        </el-form>
        <template #footer
          ><el-button data-action="neutral" @click="registerDialog = false"
            >取消</el-button
          ><el-button data-action="primary" type="primary" @click="saveRegister"
            >保存</el-button
          ></template
        >
      </el-dialog>

      <el-dialog v-model="adjustDialog" title="调整批量资产数量" width="520px">
        <el-form label-width="100px">
          <el-form-item label="当前数量">
            <span
              >{{ formatQuantity(currentTarget?.quantity) }}
              {{ label(options.md_unit, currentTarget?.unit_code || "") }}</span
            >
          </el-form-item>
          <el-form-item label="调整后数量" required>
            <el-input-number
              v-model="adjustForm.quantity"
              :min="0"
              :precision="3"
            />
          </el-form-item>
          <el-form-item label="调整原因" required>
            <el-input
              v-model="adjustForm.reason"
              type="textarea"
              :maxlength="1000"
              show-word-limit
              placeholder="例如：盘点盘盈、损坏报减或登记纠错"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button data-action="neutral" @click="adjustDialog = false"
            >取消</el-button
          >
          <el-button
            data-action="primary"
            type="primary"
            @click="submitAdjustment"
            >确认调整</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="transferDialog"
        title="资产调拨/责任移交"
        width="600px"
      >
        <el-form label-width="110px">
          <template v-if="currentTarget?.management_mode === 'batch'">
            <el-form-item label="目标位置" required
              ><el-select
                v-model="transferForm.target_location_id"
                filterable
                class="w-full"
                ><el-option
                  v-for="item in transferOptions.locations.filter(
                    (item) =>
                      item !==
                      findAssetLocation(
                        transferOptions.locations,
                        currentTarget?.location_id,
                      ),
                  )"
                  :key="item.id"
                  :label="item.location_name"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="调拨数量" required
              ><el-input-number
                v-model="transferForm.quantity"
                :min="0.001"
                :max="Number(currentTarget.quantity)"
                :precision="3"
            /></el-form-item>
            <el-form-item label="目标责任部门"
              ><el-select
                v-model="transferForm.target_department_id"
                clearable
                class="w-full"
                ><el-option
                  v-for="item in transferOptions.departments"
                  :key="item.id"
                  :label="departmentOptionLabel(item)"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="目标资产保管人"
              ><el-select
                v-model="transferForm.target_custodian_user_id"
                clearable
                filterable
                class="w-full"
                ><el-option
                  v-for="item in transferOptions.users"
                  :key="item.id"
                  :label="item.display_name"
                  :value="item.id" /></el-select
            ></el-form-item>
          </template>
          <template v-else>
            <el-form-item label="资产位置"
              ><el-select
                v-model="transferForm.location_id"
                filterable
                class="w-full"
                ><el-option
                  v-for="item in assetLocationOptions(
                    transferOptions.locations,
                    transferForm.location_id,
                  )"
                  :key="item.id"
                  :label="item.location_name"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="责任部门"
              ><el-select
                v-model="transferForm.department_id"
                clearable
                class="w-full"
                ><el-option
                  v-for="item in transferOptions.departments"
                  :key="item.id"
                  :label="departmentOptionLabel(item)"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="资产保管人"
              ><el-select
                v-model="transferForm.custodian_user_id"
                clearable
                filterable
                class="w-full"
                ><el-option
                  v-for="item in transferOptions.users"
                  :key="item.id"
                  :label="item.display_name"
                  :value="item.id" /></el-select
            ></el-form-item>
          </template>
          <el-form-item label="原因" required
            ><el-input
              v-model="transferForm.reason"
              type="textarea"
              placeholder="请说明调拨或责任移交原因"
          /></el-form-item>
        </el-form>
        <template #footer
          ><el-button data-action="neutral" @click="transferDialog = false"
            >取消</el-button
          ><el-button
            data-action="primary"
            type="primary"
            @click="submitTransfer"
            >确认</el-button
          ></template
        >
      </el-dialog>

      <el-drawer v-model="detailDrawer" title="资产详情" size="620px">
        <el-descriptions v-if="detailTarget" :column="1" border>
          <el-descriptions-item label="管理方式">
            {{
              detailTarget.management_mode === "individual"
                ? "编号资产"
                : "批量资产"
            }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailTarget.management_mode === 'individual'"
            label="资产编号"
          >
            {{ detailTarget.asset_no || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="资产名称">
            {{ detailTarget.item_name }}
          </el-descriptions-item>
          <el-descriptions-item label="规格">
            {{ detailTarget.specification || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="资产类型">
            {{ label(options.asset_type, detailTarget.asset_type_code) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailTarget.management_mode === 'individual'"
            label="序列号"
          >
            {{ detailTarget.serial_no || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="资产位置">
            {{ detailTarget.location_name }}
          </el-descriptions-item>
            <el-descriptions-item v-if="detailTarget.is_personal_custody" label="使用地点（选填）">
              {{ detailTarget.custody_location_note || '流动使用，无固定地点' }}
            </el-descriptions-item>
          <el-descriptions-item label="数量">
            {{ formatQuantity(detailTarget.quantity) }}
            {{
              detailTarget.management_mode === "batch"
                ? label(options.md_unit, detailTarget.unit_code)
                : "件"
            }}
          </el-descriptions-item>
          <el-descriptions-item label="责任部门">
            {{ detailTarget.department_name || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="资产保管人">
            {{ detailTarget.custodian_name || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="资产状态">
            {{ label(options.asset_status, detailTarget.status_code) }}
          </el-descriptions-item>
          <el-descriptions-item label="登记状态">
            {{
              detailTarget.registration_status_code === "confirmed"
                ? "已确认（原始登记信息已锁定）"
                : detailTarget.registration_status_code === "voided"
                  ? "已作废"
                  : "待确认"
            }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailTarget.registration_status_code === 'voided'"
            label="作废原因"
          >
            {{ detailTarget.void_reason || "-" }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailTarget.management_mode === 'individual'"
            label="购置日期"
          >
            {{ detailTarget.acquired_date || "-" }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailTarget.management_mode === 'individual'"
            label="购置原值"
          >
            {{
              detailTarget.original_amount === null
                ? "-"
                : `${detailTarget.original_amount} 元`
            }}
          </el-descriptions-item>
          <el-descriptions-item label="备注">
            {{ detailTarget.remark || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="最后更新">
            {{ formatDateTime(detailTarget.updated_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-drawer>

      <el-drawer v-model="eventDrawer" title="资产变更记录" size="620px">
        <el-timeline v-loading="eventLoading">
          <el-timeline-item
            v-for="item in events"
            :key="item.id"
            :timestamp="formatDateTime(item.created_at)"
            placement="top"
          >
            <el-card shadow="never">
              <strong>{{
                label(options.asset_change_event_type, item.event_type_code)
              }}</strong>
              <p>{{ item.note }}</p>
              <small>操作人：{{ item.operator_name_snapshot }}</small>
              <div v-if="item.quantity_before !== null">
                数量：{{ formatQuantity(item.quantity_before) }} →
                {{ formatQuantity(item.quantity_after) }}
              </div>
              <div v-if="item.from_location_id || item.to_location_id">
                位置：{{ relationLocationLabel(item.from_location_id) }} →
                {{ relationLocationLabel(item.to_location_id) }}
              </div>
              <div v-if="item.from_department_id || item.to_department_id">
                责任部门：{{ relationDepartmentLabel(item.from_department_id) }}
                →
                {{ relationDepartmentLabel(item.to_department_id) }}
              </div>
              <div
                v-if="item.from_custodian_user_id || item.to_custodian_user_id"
              >
                资产保管人：{{ relationUserLabel(item.from_custodian_user_id) }}
                →
                {{ relationUserLabel(item.to_custodian_user_id) }}
              </div>
              <div v-if="item.from_status_code || item.to_status_code">
                资产状态：{{
                  label(
                    relationOptions.asset_status,
                    item.from_status_code || "",
                  )
                }}
                →
                {{
                  label(relationOptions.asset_status, item.to_status_code || "")
                }}
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty
          v-if="!eventLoading && !events.length"
          description="暂无变更记录"
        />
      </el-drawer>
    </main>
  </ReListPresentation>
</template>

<style scoped>
.asset-page {
  padding: 20px;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px;
  margin-bottom: 16px;
  color: white;
  background: linear-gradient(120deg, #235f91, #25877c);
  border-radius: 14px;
}

.hero p {
  margin: 0 0 6px;
  opacity: 0.8;
}

.hero h1 {
  margin: 0 0 8px;
  font-size: 26px;
}

.hero span {
  opacity: 0.9;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-grid :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-grid span {
  color: var(--el-text-color-secondary);
}

.summary-grid strong {
  font-size: 25px;
  color: var(--el-color-primary);
}

.ledger-card :deep(.el-card__body) {
  padding-top: 10px;
}

.toolbar {
  display: flex;
  gap: 10px;
  margin: 6px 0 14px;
}

.toolbar .el-input {
  width: 280px;
}

.toolbar .el-select {
  width: 180px;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

.danger-action {
  color: var(--el-color-danger);
}

.operation-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.operation-actions .el-button {
  margin-left: 0;
}

.operation-actions :deep(.el-dropdown) {
  display: inline-flex;
  align-items: center;
  line-height: 1;
}

.w-full {
  width: 100%;
}

.amount-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.field-tip {
  font-size: 12px;
  line-height: 18px;
  color: var(--el-text-color-secondary);
}

.status-tip {
  margin-bottom: 18px;
}

@media (width <= 900px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toolbar {
    flex-wrap: wrap;
  }
}
</style>

<style>
.asset-registration-dialog.el-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 40px);
  padding: 0;
  overflow: hidden;
  border-radius: 10px;
}
.asset-registration-dialog .el-dialog__header {
  flex-shrink: 0;
  padding: 18px 24px;
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.asset-registration-dialog .el-dialog__body {
  min-height: 0;
  padding: 0 24px 20px;
}
@media (width <= 600px) {
  .asset-registration-dialog.el-dialog { max-height: calc(100dvh - 24px); }
  .asset-registration-dialog .el-dialog__header { padding: 16px; }
  .asset-registration-dialog .el-dialog__body { padding: 0 12px 12px; }
}
</style>
