<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getStockWarehouseOptions,
  type WarehouseOption,
} from "@plugins/mes/web/src/api/mesInventory";
import OrderDetailDialog from "@plugins/inv/web/src/views/inventory/components/OrderDetailDialog.vue";
import ShipmentDocuments from "./ShipmentDocuments.vue";
import DeliveryOverview from "./DeliveryOverview.vue";
import RemoteSelect from "./RemoteSelect.vue";
import ActionButton from "@/components/ActionButton/index.vue";
import type { MesOption } from "@plugins/mes/web/src/api/mes";
import {
  getDeliveries,
  getDelivery,
  getDeliverySources,
  getShipmentCustomerOptions,
  getShipmentSalesOrderOptions,
  saveDelivery,
  actDelivery,
  type DeliveryKind,
  type DeliveryDocument,
  type DeliveryLine,
  type DeliverySource,
  type ShipmentCustomer,
} from "@plugins/mes/web/src/api/mesDelivery";
import {
  deliveryAmount,
  deliveryCurrency,
  deliveryLabel,
  deliveryPriceLabel,
  exportDelivery,
  printDelivery,
} from "./deliveryDocuments";
type ShipmentTab = "overview" | "documents";
const props = defineProps<{
  kind: DeliveryKind;
  salesOrderId?: string;
  shipmentId?: string;
  shipmentTab?: ShipmentTab;
}>();
const emit = defineEmits<{
  openShipment: [id: string, tab: ShipmentTab];
  closeShipment: [];
}>();
const isShipment = computed(() => props.kind === "shipments");
const canViewDocuments = computed(
  () => isShipment.value && hasPerms("mes:shipment:documents"),
);
const currentTab = ref<ShipmentTab>(props.shipmentTab || "overview");
watch(
  () => [props.shipmentId, props.shipmentTab],
  () => {
    currentTab.value = props.shipmentTab || "overview";
  },
);
const selectedTab = computed(() =>
  currentTab.value === "documents" && canViewDocuments.value
    ? "documents"
    : "overview",
);
const title = computed(() => (isShipment.value ? "出货单" : "对账单"));
const canManage = computed(() =>
  hasPerms(`mes:${isShipment.value ? "shipment" : "reconciliation"}:manage`),
);
const rows = ref<DeliveryDocument[]>([]),
  total = ref(0),
  page = ref(1),
  size = ref(10),
  loading = ref(false),
  error = ref("");
const filters = reactive({ keyword: "", customer: "", status_code: "" });
const active = ref<DeliveryDocument>(),
  viewing = ref(false),
  documentBusy = ref(false),
  detailLoading = ref(false),
  detailError = ref(""),
  pageRoot = ref<HTMLElement>(),
  editing = ref(false),
  busy = ref(false),
  editError = ref("");
const documentKey = computed(
  () =>
    active.value &&
    `${active.value.id}:${active.value.lines.map((line) => line.id).join(",")}`,
);
const form = reactive({
  number: "",
  org_id: "",
  customer_id: "",
  sales_order_id: "",
  sales_order_no: "",
  customer_no_snapshot: "",
  customer_name_snapshot: "",
  business_date: "",
  fulfillment_mode_code: "direct" as "direct" | "stock",
  warehouse_id: "",
  period_start: "",
  period_end: "",
  note: "",
  lines: [] as DeliveryLine[],
});
const orderCurrency = computed(
  () => form.lines[0]?.order_currency_snapshot || null,
);
const fulfillmentWarehouses = ref<WarehouseOption[]>([]),
  stockDetailId = ref(""),
  stockDetailVisible = ref(false);
const warehousesForCustomer = computed(() =>
  fulfillmentWarehouses.value.filter((row) => row.org_id === form.org_id),
);
const customerChoices = new Map<string, ShipmentCustomer>();
let customerRequest = 0;
const pinnedCustomerLoading = ref(false);
const canChooseSource = computed(
  () =>
    !isShipment.value ||
    (!!form.customer_no_snapshot &&
      !!form.org_id &&
      (form.fulfillment_mode_code !== "stock" || !!form.warehouse_id)),
);
function applyCustomer(customer?: ShipmentCustomer) {
  form.customer_id = customer?.id || "";
  form.customer_no_snapshot = customer?.customer_no || "";
  form.customer_name_snapshot = customer?.customer_name || "";
  form.org_id = customer?.org_id || "";
  form.sales_order_id = props.salesOrderId || "";
  form.sales_order_no = customer?.sales_order_no || "";
  form.warehouse_id = "";
}
async function loadCustomers(keyword: string): Promise<MesOption[]> {
  const rows = (await getShipmentCustomerOptions(keyword)).data;
  for (const row of rows) customerChoices.set(row.id, row);
  return rows.map((row) => ({
    value: row.id,
    label: `${row.customer_name} · ${row.customer_no}`,
  }));
}
function changeCustomer(option?: MesOption) {
  applyCustomer(option ? customerChoices.get(option.value) : undefined);
}
async function loadSalesOrders(keyword: string): Promise<MesOption[]> {
  if (!form.customer_id) return [];
  return (
    await getShipmentSalesOrderOptions(form.customer_id, keyword)
  ).data.map((row) => ({
    value: row.id,
    label: row.customer_po_no
      ? `${row.order_no} · ${row.customer_po_no}`
      : row.order_no,
  }));
}
async function loadPinnedCustomer(salesOrderId: string) {
  const current = ++customerRequest;
  pinnedCustomerLoading.value = true;
  try {
    const row = (await getShipmentCustomerOptions("", salesOrderId)).data[0];
    if (current !== customerRequest || !editing.value) return;
    if (!row) {
      editError.value =
        "找不到可用于出货的订单客户，请核对客户启用状态和出货权限";
      return;
    }
    applyCustomer(row);
  } catch (cause) {
    if (current === customerRequest)
      editError.value = getHttpErrorMessage(cause, "订单客户读取失败");
  } finally {
    if (current === customerRequest) pinnedCustomerLoading.value = false;
  }
}
onBeforeUnmount(() => {
  ++customerRequest;
});
async function loadFulfillmentWarehouses() {
  try {
    fulfillmentWarehouses.value = (
      await getStockWarehouseOptions("out", "shipment")
    ).data;
  } catch (cause) {
    editError.value = getHttpErrorMessage(cause, "出库仓库读取失败");
  }
}
function changeFulfillmentMode() {
  form.lines = [];
  form.warehouse_id = "";
  if (form.fulfillment_mode_code === "stock") loadFulfillmentWarehouses();
}
const sourceVisible = ref(false),
  sourceRows = ref<DeliverySource[]>([]),
  sourceTotal = ref(0),
  sourcePage = ref(1),
  sourceKeyword = ref(""),
  sourceLoading = ref(false);
let request = 0,
  sourceRequest = 0,
  previous = "",
  key = "";
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getDeliveries(props.kind, {
      ...filters,
      sales_order_id: isShipment.value ? props.salesOrderId : undefined,
      page: page.value,
      page_size: size.value,
    });
    if (current === request) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "单据加载失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
async function view(row: DeliveryDocument) {
  if (busy.value) return;
  if (isShipment.value) {
    emit("openShipment", row.id, "overview");
    return;
  }
  busy.value = true;
  try {
    active.value = (await getDelivery(props.kind, row.id)).data;
    viewing.value = true;
  } catch (cause) {
    message(getHttpErrorMessage(cause, "单据读取失败"), { type: "error" });
  } finally {
    busy.value = false;
  }
}
let detailRequest = 0;
async function loadShipment(id?: string) {
  if (!id) return;
  const current = ++detailRequest;
  detailLoading.value = true;
  detailError.value = "";
  try {
    const result = await getDelivery("shipments", id);
    if (current === detailRequest) active.value = result.data;
  } catch (cause) {
    if (current === detailRequest)
      detailError.value = getHttpErrorMessage(cause, "出货单读取失败");
  } finally {
    if (current === detailRequest) detailLoading.value = false;
  }
}
watch(
  () => props.shipmentId,
  (id, previousId) => {
    if (!isShipment.value) return;
    ++detailRequest;
    detailLoading.value = false;
    detailError.value = "";
    documentBusy.value = false;
    if (active.value?.id !== id) active.value = undefined;
    if (id) loadShipment(id);
    if (previousId !== id)
      nextTick(() => pageRoot.value?.scrollIntoView({ block: "start" }));
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  ++detailRequest;
});
function selectShipmentTab(tab: string | number) {
  if (tab === "overview" || (tab === "documents" && canViewDocuments.value))
    currentTab.value = tab;
}
function openStockOrder(id: string) {
  stockDetailId.value = id;
  stockDetailVisible.value = true;
}
function create() {
  if (busy.value) return;
  active.value = undefined;
  previous = "";
  key = "";
  editError.value = "";
  ++customerRequest;
  pinnedCustomerLoading.value = false;
  customerChoices.clear();
  const today = new Date().toLocaleDateString("sv-SE");
  Object.assign(form, {
    number: "",
    org_id: "",
    customer_id: "",
    sales_order_id: props.salesOrderId || "",
    sales_order_no: "",
    customer_no_snapshot: "",
    customer_name_snapshot: "",
    business_date: today,
    fulfillment_mode_code: "direct",
    warehouse_id: "",
    period_start: today.slice(0, 8) + "01",
    period_end: today,
    note: "",
    lines: [],
  });
  editing.value = true;
  if (isShipment.value && props.salesOrderId)
    loadPinnedCustomer(props.salesOrderId);
}
function edit() {
  const row = active.value;
  if (!row || !isShipment.value) return;
  Object.assign(form, {
    number: row.shipment_no,
    org_id: row.org_id,
    customer_id: "",
    sales_order_id: props.salesOrderId || "",
    sales_order_no: "",
    customer_no_snapshot: row.customer_no_snapshot,
    customer_name_snapshot: row.customer_name_snapshot,
    business_date: row.business_date,
    fulfillment_mode_code: row.fulfillment_mode_code || "direct",
    warehouse_id: row.warehouse_id || "",
    note: row.note || "",
    lines: row.lines.map((line) => ({
      ...line,
      unit_price: line.order_unit_price ?? line.unit_price,
      order_currency_snapshot:
        line.order_currency || row.order_currency_snapshot,
    })),
  });
  previous = "";
  key = "";
  editError.value = "";
  viewing.value = false;
  editing.value = true;
  if (form.fulfillment_mode_code === "stock") loadFulfillmentWarehouses();
}
async function sourceSearch(reset = false) {
  if (reset) sourcePage.value = 1;
  const current = ++sourceRequest;
  sourceLoading.value = true;
  if (reset) {
    sourceRows.value = [];
    sourceTotal.value = 0;
  }
  try {
    const result = await getDeliverySources(props.kind, {
      page: sourcePage.value,
      page_size: 10,
      keyword: sourceKeyword.value,
      ...(isShipment.value
        ? {
            fulfillment_mode_code: form.fulfillment_mode_code,
            warehouse_id: form.warehouse_id,
            org_id: form.org_id,
            customer_id: form.customer_id,
            customer_no: form.customer_id
              ? undefined
              : form.customer_no_snapshot,
            sales_order_id: form.sales_order_id,
          }
        : {}),
      ...(!isShipment.value
        ? {
            customer: form.customer_no_snapshot,
            start_date: form.period_start,
            end_date: form.period_end,
          }
        : {}),
    });
    if (current === sourceRequest) {
      sourceRows.value = result.data.items;
      sourceTotal.value = result.data.total;
    }
  } catch (cause) {
    if (current === sourceRequest) {
      sourceRows.value = [];
      sourceTotal.value = 0;
      actionMessage(getHttpErrorMessage(cause, "来源读取失败"));
    }
  } finally {
    if (current === sourceRequest) sourceLoading.value = false;
  }
}
function openSources() {
  if (isShipment.value && !form.customer_no_snapshot) {
    message("请先选择出货客户", { type: "warning" });
    return;
  }
  if (
    isShipment.value &&
    form.fulfillment_mode_code === "stock" &&
    !form.warehouse_id
  ) {
    message("请先选择来源仓库", { type: "warning" });
    return;
  }
  if (
    !isShipment.value &&
    (!form.period_start || !form.period_end || !form.customer_no_snapshot)
  ) {
    message("请先填写客户编号与对账期间", { type: "warning" });
    return;
  }
  sourceVisible.value = true;
  sourceKeyword.value = "";
  sourceSearch(true);
}
function addSource(row: DeliverySource) {
  if (form.lines.length >= 100) {
    actionMessage("每张单据最多 100 行", "warning");
    return;
  }
  if (form.org_id && row.org_id !== form.org_id) {
    actionMessage("只能添加同一组织的数据", "warning");
    return;
  }
  if (
    form.customer_id && row.customer_id
      ? row.customer_id !== form.customer_id
      : row.customer_no_snapshot &&
        form.customer_no_snapshot &&
        row.customer_no_snapshot !== form.customer_no_snapshot
  ) {
    actionMessage("来源客户与当前客户编号不一致", "warning");
    return;
  }
  if (
    form.lines.some((line) =>
      isShipment.value
        ? line.work_order_id === row.work_order_id
        : line.shipment_line_id === row.id,
    )
  ) {
    actionMessage("该来源已添加", "warning");
    return;
  }
  if (isShipment.value && Number(row.available_quantity) <= 0) {
    actionMessage("当前没有可出货数量，请先结束末道执行或完成检验", "warning");
    return;
  }
  if (
    isShipment.value &&
    row.has_order_source &&
    (!row.order_currency || row.order_unit_price == null)
  ) {
    actionMessage("这个工单的客户订单单价不可用，请核对来源订单", "warning");
    return;
  }
  const currency =
    (isShipment.value ? row.order_currency : row.order_currency_snapshot) ||
    null;
  if (form.lines.length && currency !== orderCurrency.value) {
    actionMessage("币种或计价口径不同，请分开制单", "warning");
    return;
  }
  form.org_id = row.org_id;
  if (!form.customer_no_snapshot)
    form.customer_no_snapshot = row.customer_no_snapshot || "";
  if (!form.customer_name_snapshot)
    form.customer_name_snapshot = row.customer_name_snapshot || "";
  form.lines.push({
    work_order_id: row.work_order_id,
    work_order_no_snapshot: row.work_order_no || row.work_order_no_snapshot,
    product_item_name_snapshot:
      row.product_item_name || row.product_item_name_snapshot,
    unit_code: row.unit_code,
    quantity: isShipment.value ? row.available_quantity! : row.quantity!,
    unit_price: isShipment.value
      ? (row.order_unit_price ?? "")
      : row.unit_price!,
    order_currency_snapshot: currency,
    shipment_line_id: isShipment.value ? undefined : row.id,
    shipment_no: row.shipment_no,
    adjustment_amount: "0.00",
    adjustment_reason: "",
  });
}
function preview(line: DeliveryLine) {
  try {
    return deliveryAmount(
      line.quantity,
      line.unit_price,
      isShipment.value ? "0" : line.adjustment_amount || "0",
    );
  } catch {
    return "—";
  }
}
async function save() {
  if (busy.value) return;
  if (
    (!isShipment.value && !form.number.trim()) ||
    !form.customer_no_snapshot.trim() ||
    !form.customer_name_snapshot.trim() ||
    !form.lines.length
  ) {
    actionMessage(
      isShipment.value
        ? "请选择出货客户并添加工单产品"
        : "请填写单号、客户编号和名称，并添加明细",
      "warning",
    );
    return;
  }
  if (
    isShipment.value &&
    form.lines.some(
      (line) => !line.order_currency_snapshot && !line.unit_price.trim(),
    )
  ) {
    actionMessage("未关联订单的工单需要填写人民币含税单价", "warning");
    return;
  }
  const contents = {
    org_id: form.org_id,
    ...(isShipment.value && form.customer_id
      ? { customer_id: form.customer_id }
      : {
          customer_no_snapshot: form.customer_no_snapshot,
          customer_name_snapshot: form.customer_name_snapshot,
        }),
    note: form.note,
    ...(isShipment.value
      ? {
          business_date: form.business_date,
          fulfillment_mode_code: form.fulfillment_mode_code,
          sales_order_id: form.sales_order_id || undefined,
          warehouse_id:
            form.fulfillment_mode_code === "stock" ? form.warehouse_id : null,
          lines: form.lines.map((line) => ({
            work_order_id: line.work_order_id,
            quantity: line.quantity,
            ...(line.order_currency_snapshot
              ? {}
              : { unit_price: line.unit_price.trim() }),
          })),
        }
      : {
          reconciliation_no: form.number,
          period_start: form.period_start,
          period_end: form.period_end,
          lines: form.lines.map((line) => ({
            shipment_line_id: line.shipment_line_id,
            adjustment_amount: line.adjustment_amount || "0",
            adjustment_reason: line.adjustment_reason,
          })),
        }),
  };
  const fingerprint = JSON.stringify(contents);
  if (previous !== fingerprint) {
    previous = fingerprint;
    key = crypto.randomUUID();
  }
  busy.value = true;
  try {
    const result = await saveDelivery(
      props.kind,
      {
        ...contents,
        idempotency_key: key,
        ...(active.value ? { version_no: active.value.version_no } : {}),
      },
      active.value?.id,
    );
    active.value = result.data;
    editing.value = false;
    if (isShipment.value) {
      if (props.shipmentId !== result.data.id)
        emit("openShipment", result.data.id, "overview");
    } else viewing.value = true;
    await load();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "保存失败，内容已保留，可重试"));
  } finally {
    busy.value = false;
  }
}
async function act(action: string) {
  if (busy.value || documentBusy.value || detailLoading.value || !active.value)
    return;
  const row = active.value;
  busy.value = true;
  try {
    let reason: string | undefined;
    if (action === "cancel") {
      const result = await ElMessageBox.prompt(
        "请输入取消理由；取消后保留记录",
        `取消${title.value}`,
        { inputValidator: (value) => !!value?.trim() || "请填写理由" },
      );
      reason = result.value;
    } else
      await ElMessageBox.confirm(
        `确认${isShipment.value ? "出货？将占用工单可出货数量" : "本次对账？这不表示已收款"}`,
        `确认${title.value}`,
      );
    active.value = (
      await actDelivery(props.kind, row.id, action, {
        version_no: row.version_no,
        reason,
      })
    ).data;
    await load();
  } catch (cause) {
    if (!["cancel", "close"].includes(cause as string))
      message(getHttpErrorMessage(cause, "操作失败，请刷新单据后重试"), {
        type: "error",
      });
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div ref="pageRoot" class="mes-delivery">
    <template v-if="!isShipment || !props.shipmentId">
      <div class="heading">
        <div>
          <h2>{{ title }}</h2>
          <p>
            {{
              isShipment
                ? "生产直发不扣库存；仓储出货使用已入库的工单数量，确认时生成库存出库，取消时同步作废或冲销。"
                : "按客户、期间及币种引用有效出货明细，金额沿用出货计价口径。"
            }}
          </p>
        </div>
        <ActionButton v-if="canManage" intent="create" @click="create"
          >新增{{ title }}</ActionButton
        >
      </div>
      <el-card shadow="never">
        <el-form inline @submit.prevent="search"
          ><el-form-item label="单号"
            ><el-input
              v-model="filters.keyword"
              clearable
              @keyup.enter="search" /></el-form-item
          ><el-form-item label="客户"
            ><el-input
              v-model="filters.customer"
              clearable
              @keyup.enter="search" /></el-form-item
          ><el-form-item label="状态"
            ><el-select
              v-model="filters.status_code"
              clearable
              style="width: 130px"
              ><el-option label="草稿" value="draft" /><el-option
                v-if="isShipment"
                label="待库存办理"
                value="awaiting_stock" /><el-option
                :label="isShipment ? '已出货' : '已确认'"
                :value="isShipment ? 'posted' : 'confirmed'" /><el-option
                label="已取消"
                value="cancelled" /></el-select></el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              Object.assign(filters, {
                keyword: '',
                customer: '',
                status_code: '',
              });
              search();
            "
            >重置</el-button
          ></el-form
        >
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
        <el-table v-loading="loading" :data="rows" row-key="id"
          ><el-table-column
            :prop="isShipment ? 'shipment_no' : 'reconciliation_no'"
            label="单号"
            min-width="170"
          /><el-table-column
            prop="customer_no_snapshot"
            label="客户编号"
            min-width="120"
          /><el-table-column
            prop="customer_name_snapshot"
            label="客户"
            min-width="160"
          /><el-table-column label="日期 / 期间" min-width="190"
            ><template #default="{ row }">{{
              row.business_date || `${row.period_start} ~ ${row.period_end}`
            }}</template></el-table-column
          ><el-table-column label="状态" width="100"
            ><template #default="{ row }"
              ><el-tag>{{ deliveryLabel(row.status_code) }}</el-tag></template
            ></el-table-column
          ><el-table-column label="金额" min-width="140">
            <template #default="{ row }"
              >{{ row.total_amount }}
              {{ deliveryCurrency(row.order_currency_snapshot) }}</template
            > </el-table-column
          ><el-table-column
            label="操作"
            fixed="right"
            :width="canViewDocuments ? 150 : 100"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                :disabled="busy"
                @click="view(row as DeliveryDocument)"
                >查看</el-button
              ><el-button
                v-if="canViewDocuments"
                link
                type="primary"
                :disabled="busy"
                @click="emit('openShipment', row.id, 'documents')"
                >单据</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <ListPagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="search"
        />
      </el-card>
    </template>
    <section v-else class="shipment-page">
      <el-button
        :icon="ArrowLeft"
        link
        type="primary"
        :disabled="busy || documentBusy"
        @click="emit('closeShipment')"
        >返回出货单列表</el-button
      >
      <header class="shipment-heading">
        <div class="shipment-title">
          <h2>出货单详情</h2>
          <el-tag
            v-if="active"
            :type="
              active.status_code === 'posted'
                ? 'success'
                : active.status_code === 'awaiting_stock'
                  ? 'warning'
                  : 'info'
            "
            >{{ deliveryLabel(active.status_code) }}</el-tag
          >
        </div>
        <div
          v-if="
            active &&
            canManage &&
            !['posted', 'cancelled'].includes(active.status_code)
          "
          class="shipment-primary"
        >
          <el-button
            v-if="active.status_code === 'draft'"
            data-action="edit"
            :disabled="busy || detailLoading || documentBusy"
            @click="edit"
            >编辑草稿</el-button
          >
          <el-button
            v-if="['draft', 'awaiting_stock'].includes(active.status_code)"
            type="primary"
            :loading="busy"
            :disabled="detailLoading || documentBusy"
            @click="act('post')"
            >{{
              active.status_code === "awaiting_stock" ? "完成出库" : "确认出货"
            }}</el-button
          >
        </div>
      </header>
      <dl v-if="active" class="shipment-summary">
        <div>
          <dt>出货单号</dt>
          <dd>{{ active.shipment_no }}</dd>
        </div>
        <div>
          <dt>客户</dt>
          <dd>{{ active.customer_name_snapshot }}</dd>
        </div>
        <div>
          <dt>出货日期</dt>
          <dd>{{ active.business_date }}</dd>
        </div>
        <div>
          <dt>出货金额</dt>
          <dd>
            {{ active.total_amount }}
            {{ deliveryCurrency(active.order_currency_snapshot) }}
          </dd>
        </div>
      </dl>
      <el-alert
        v-if="detailError"
        :title="detailError"
        type="error"
        show-icon
        :closable="false"
      >
        <el-button link type="primary" @click="loadShipment(props.shipmentId)"
          >重新加载</el-button
        >
      </el-alert>
      <el-skeleton v-else-if="!active && detailLoading" :rows="4" animated />
      <div v-if="active" v-loading="detailLoading" class="shipment-workspace">
        <el-tabs
          :model-value="selectedTab"
          @update:model-value="selectShipmentTab"
        >
          <el-tab-pane label="出货明细" name="overview">
            <div class="shipment-pane">
              <DeliveryOverview
                :document="active"
                kind="shipments"
                @open-stock-order="openStockOrder"
              />
              <footer class="erp-form-actions">
                <div class="erp-form-actions__secondary">
                  <el-button
                    :disabled="busy || detailLoading || documentBusy"
                    @click="loadShipment(active.id)"
                    >刷新单据</el-button
                  >
                  <el-button
                    data-action="view"
                    @click="printDelivery(active, kind)"
                    >打印 / PDF</el-button
                  >
                  <ActionButton
                    intent="download"
                    @click="exportDelivery(active, kind)"
                    >导出明细</ActionButton
                  >
                </div>
                <div
                  v-if="canManage && active.status_code !== 'cancelled'"
                  class="erp-form-actions__primary"
                >
                  <el-button
                    type="danger"
                    plain
                    :disabled="busy || detailLoading || documentBusy"
                    @click="act('cancel')"
                    >取消出货单</el-button
                  >
                </div>
              </footer>
            </div>
          </el-tab-pane>
          <el-tab-pane
            v-if="canViewDocuments"
            label="出货单据"
            name="documents"
            lazy
          >
            <ShipmentDocuments
              :key="documentKey"
              :shipment="active"
              @busy-change="documentBusy = $event"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </section>
    <el-dialog
      v-if="!isShipment"
      v-model="viewing"
      title="对账单详情"
      width="min(1150px, 96vw)"
      :close-on-click-modal="!busy"
      :show-close="!busy"
    >
      <DeliveryOverview
        v-if="active"
        :document="active"
        kind="reconciliations"
      />
      <template #footer>
        <template v-if="active">
          <el-button :disabled="busy" @click="view(active)">刷新单据</el-button>
          <el-button data-action="view" @click="printDelivery(active, kind)"
            >打印 / PDF</el-button
          >
          <ActionButton intent="download" @click="exportDelivery(active, kind)"
            >导出明细</ActionButton
          >
          <template v-if="canManage && active.status_code !== 'cancelled'">
            <el-button
              v-if="active.status_code === 'draft'"
              type="primary"
              :loading="busy"
              @click="act('confirm')"
              >确认对账</el-button
            >
            <el-button
              type="danger"
              plain
              :disabled="busy"
              @click="act('cancel')"
              >取消对账单</el-button
            >
          </template>
        </template>
      </template>
    </el-dialog>
    <el-dialog
      v-model="editing"
      :title="(active ? '编辑' : '新增') + title"
      width="min(1150px, 96vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
    >
      <el-alert
        v-if="editError"
        :title="editError"
        type="error"
        :closable="false"
      />
      <el-form
        v-if="editing"
        v-loading="pinnedCustomerLoading"
        label-position="top"
        :disabled="busy"
        ><div class="form-grid">
          <template v-if="isShipment">
            <el-form-item label="客户" required>
              <span v-if="active || props.salesOrderId">{{
                form.customer_name_snapshot
                  ? `${form.customer_name_snapshot} · ${form.customer_no_snapshot}`
                  : "等待读取订单客户"
              }}</span>
              <RemoteSelect
                v-else
                v-model="form.customer_id"
                :load-options="loadCustomers"
                :disabled="busy || !!form.lines.length"
                placeholder="选择客户，可按名称或编号搜索"
                @select="changeCustomer"
              />
            </el-form-item>
            <el-form-item
              v-if="props.salesOrderId || (!active && form.customer_id)"
              label="客户订单"
            >
              <span v-if="props.salesOrderId">{{
                form.sales_order_no || "当前客户订单"
              }}</span>
              <RemoteSelect
                v-else
                v-model="form.sales_order_id"
                :context-key="form.customer_id"
                :load-options="loadSalesOrders"
                :disabled="busy || !!form.lines.length"
                placeholder="可选，按订单号或客户采购单号搜索"
              />
            </el-form-item>
            <el-form-item label="出货单号">
              <span>{{ active ? form.number : "保存后自动生成" }}</span>
            </el-form-item>
            <el-form-item label="履约方式" required
              ><el-select
                v-model="form.fulfillment_mode_code"
                :disabled="!!form.lines.length"
                @change="changeFulfillmentMode"
                ><el-option
                  label="生产直发（不经过库存）"
                  value="direct" /><el-option
                  label="仓储出货（出库扣库存）"
                  value="stock" /></el-select></el-form-item
            ><el-form-item
              v-if="form.fulfillment_mode_code === 'stock'"
              label="来源仓库"
              required
              ><el-select
                v-model="form.warehouse_id"
                :disabled="!form.org_id || !!form.lines.length"
                placeholder="选择客户所在组织的仓库"
                filterable
                ><el-option
                  v-for="row in warehousesForCustomer"
                  :key="row.id"
                  :label="row.label"
                  :value="row.id" /></el-select></el-form-item
          ></template>
          <el-form-item v-if="isShipment" label="出货日期" required
            ><el-date-picker
              v-model="form.business_date"
              type="date"
              value-format="YYYY-MM-DD" /></el-form-item
          ><template v-else
            ><el-form-item label="单号" required
              ><el-input v-model="form.number" maxlength="64" /></el-form-item
            ><el-form-item label="客户外部编号" required
              ><el-input
                v-model="form.customer_no_snapshot"
                maxlength="64" /></el-form-item
            ><el-form-item label="客户名称" required
              ><el-input
                v-model="form.customer_name_snapshot"
                maxlength="128" /></el-form-item
            ><el-form-item label="期间开始" required
              ><el-date-picker
                v-model="form.period_start"
                type="date"
                value-format="YYYY-MM-DD" /></el-form-item
            ><el-form-item label="期间结束" required
              ><el-date-picker
                v-model="form.period_end"
                type="date"
                value-format="YYYY-MM-DD" /></el-form-item
          ></template>
        </div>
        <ActionButton
          :disabled="busy || !canChooseSource"
          intent="create"
          @click="openSources"
          >添加{{ isShipment ? "工单产品" : "出货明细" }}</ActionButton
        ><span class="hint">
          已选 {{ form.lines.length }} 行；{{
            isShipment
              ? "选择工单后带入可出货数量和客户订单单价。"
              : "草稿即占用整条出货明细，取消后可重新对账。"
          }}</span
        >
        <el-table :data="form.lines" max-height="360"
          ><el-table-column
            v-if="!isShipment"
            prop="shipment_no"
            label="出货单"
            min-width="140"
          /><el-table-column
            prop="work_order_no_snapshot"
            label="工单"
            min-width="130"
          /><el-table-column
            prop="product_item_name_snapshot"
            label="产品"
            min-width="150"
          /><el-table-column label="数量" width="125"
            ><template #default="{ row }"
              ><el-input v-if="isShipment" v-model="row.quantity" /><span
                v-else
                >{{ row.quantity }}</span
              ></template
            ></el-table-column
          ><el-table-column
            :label="deliveryPriceLabel(orderCurrency)"
            min-width="145"
            ><template #default="{ row }"
              ><el-input
                v-if="isShipment && !row.order_currency_snapshot"
                v-model="row.unit_price"
                placeholder="填写单价"
              /><span v-else>{{ row.unit_price }}</span></template
            ></el-table-column
          ><el-table-column
            v-if="!isShipment"
            :label="`调整（${deliveryCurrency(orderCurrency)}）`"
            min-width="120"
            ><template #default="{ row }"
              ><el-input
                v-model="row.adjustment_amount" /></template></el-table-column
          ><el-table-column v-if="!isShipment" label="调整原因" min-width="160"
            ><template #default="{ row }"
              ><el-input
                v-model="row.adjustment_reason"
                maxlength="1000" /></template></el-table-column
          ><el-table-column
            :label="`预计金额（${deliveryCurrency(orderCurrency)}）`"
            min-width="150"
            ><template #default="{ row }">{{
              preview(row as DeliveryLine)
            }}</template></el-table-column
          ><el-table-column width="80"
            ><template #default="{ $index }"
              ><el-button
                link
                type="danger"
                @click="
                  form.lines.splice($index, 1);
                  if (!form.lines.length) form.org_id = '';
                "
                >移除</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <el-form-item label="说明"
          ><el-input
            v-model="form.note"
            type="textarea"
            maxlength="2000" /></el-form-item
      ></el-form>
      <template #footer
        ><el-button :disabled="busy" @click="editing = false">返回</el-button
        ><el-button type="primary" :loading="busy" @click="save"
          >保存草稿</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="sourceVisible"
      :title="isShipment ? '选择工单产品' : '选择未对账出货明细'"
      width="min(1000px, 94vw)"
    >
      <el-input
        v-model="sourceKeyword"
        clearable
        :placeholder="
          isShipment ? '搜索客户订单、工单或产品' : '搜索工单、产品或出货单'
        "
        @keyup.enter="sourceSearch(true)"
        ><template #append
          ><el-button @click="sourceSearch(true)">查询</el-button></template
        ></el-input
      >
      <el-table v-loading="sourceLoading" :data="sourceRows"
        ><el-table-column
          v-if="!isShipment"
          prop="shipment_no"
          label="出货单"
          min-width="140"
        /><el-table-column label="工单 / 产品" min-width="210"
          ><template #default="{ row }"
            >{{ row.work_order_no || row.work_order_no_snapshot }} ·
            {{
              row.product_item_name || row.product_item_name_snapshot
            }}</template
          ></el-table-column
        ><el-table-column
          v-if="isShipment"
          prop="sales_order_no"
          label="客户订单"
          min-width="165"
        /><el-table-column label="客户编号" min-width="130">
          <template #default="{ row }">
            {{
              row.customer_no_snapshot || (isShipment ? "工单未绑定客户" : "—")
            }}
          </template>
        </el-table-column>
        <el-table-column v-if="isShipment" label="订单未税单价" min-width="120">
          <template #default="{ row }">{{
            row.order_currency && row.order_unit_price != null
              ? `${row.order_unit_price} ${row.order_currency}`
              : row.has_order_source
                ? "订单价格不可用"
                : "未关联订单"
          }}</template> </el-table-column
        ><el-table-column label="可出货 / 出货数量" width="155"
          ><template #default="{ row }"
            >{{ row.available_quantity ?? row.quantity }}
            {{ row.unit_code }}</template
          ></el-table-column
        ><el-table-column width="90"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="
                isShipment &&
                (Number(row.available_quantity) <= 0 ||
                  (row.has_order_source && !row.order_currency) ||
                  form.lines.some(
                    (line) => line.work_order_id === row.work_order_id,
                  ))
              "
              @click="addSource(row as DeliverySource)"
              >添加</el-button
            ></template
          ></el-table-column
        ></el-table
      >
      <ListPagination
        v-model:current-page="sourcePage"
        :page-size="10"
        :total="sourceTotal"
        layout="total, prev, pager, next"
        @current-change="sourceSearch(false)"
      /><template #footer
        ><el-button type="primary" @click="sourceVisible = false"
          >完成选择（{{ form.lines.length }}）</el-button
        ></template
      >
    </el-dialog>
    <OrderDetailDialog v-model="stockDetailVisible" :order-id="stockDetailId" />
  </div>
</template>
<style scoped>
.mes-delivery {
  padding: 16px;
}

.heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.shipment-page {
  scroll-margin-top: 16px;
}

.shipment-heading,
.shipment-title,
.shipment-primary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.shipment-heading {
  justify-content: space-between;
  gap: 16px;
  margin: 20px 0 14px;
}

.shipment-title h2 {
  margin: 0;
  font-size: 24px;
  line-height: 1.4;
}

.shipment-primary .el-button {
  margin-left: 0;
}

.shipment-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 20px;
  margin: 0 0 22px;
  color: var(--el-text-color-regular);
}

.shipment-summary > div {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
}

.shipment-summary dt {
  color: var(--el-text-color-secondary);
}

.shipment-summary dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

.shipment-workspace {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.shipment-workspace :deep(.el-tabs__header) {
  padding-inline: 20px;
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.shipment-workspace :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.shipment-workspace :deep(.el-tabs__item) {
  height: 49px;
  font-weight: 600;
}

.shipment-pane {
  padding: 20px;
}

@media (max-width: 640px) {
  .shipment-heading {
    align-items: flex-start;
  }

  .shipment-pane {
    padding: 14px;
  }

  .shipment-workspace :deep(.el-tabs__header) {
    padding-inline: 14px;
  }
}

h2 {
  margin: 0 0 10px;
}

p,
.hint {
  color: var(--el-text-color-secondary);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0 18px;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}

.note {
  white-space: pre-wrap;
}
</style>
