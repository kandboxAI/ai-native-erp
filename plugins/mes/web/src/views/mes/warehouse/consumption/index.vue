<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import { approveStockOrder } from "@plugins/inv/web/src/api/inventoryManagement";
import OrderDetailDialog from "@plugins/inv/web/src/views/inventory/components/OrderDetailDialog.vue";
import {
  getInventoryPostings,
  createInventoryPosting,
  actInventoryPosting,
  getInventoryOrderOptions,
  getOrderInventoryOptions,
  getStockWarehouseOptions,
  getInventoryItemOptions,
  getInventoryLotOptions,
  type InventoryPosting,
  type WarehouseOption,
  type OrderInventoryOptions,
} from "@plugins/mes/web/src/api/mesInventory";
defineOptions({ name: "MesWarehouseConsumption" });
const rows = ref<InventoryPosting[]>([]),
  total = ref(0),
  page = ref(1),
  loading = ref(false),
  busy = ref(false),
  error = ref("");
const keyword = ref(""),
  filterKind = ref("");
const labels: Record<string, string> = {
  issue: "生产领料",
  return: "生产退料",
  receipt: "成品入库",
  shipment: "出货出库",
  draft: "草稿",
  submitted: "待审批",
  approved: "待记账",
  confirmed: "已记账",
  voided: "已作废",
  reversed: "已冲销",
};
const visible = ref(false),
  formError = ref(""),
  orderOptions = ref<{ id: string; label: string }[]>([]),
  itemOptions = ref<{ id: string; item_name: string; item_no?: string }[]>([]);
const warehouses = ref<WarehouseOption[]>([]),
  lots = ref<{ id: string; label: string }[]>([]),
  orderInfo = ref<OrderInventoryOptions>();
const returnSelection = ref(""),
  detailId = ref(""),
  detailVisible = ref(false);
const form = reactive({
  work_order_id: "",
  operation_id: "",
  posting_type_code: "issue",
  source_posting_id: "",
  item_id: "",
  warehouse_id: "",
  lot_id: "",
  quantity: "1",
  unit_price: "",
  note: "",
});
const returnOptions = computed(() =>
  (orderInfo.value?.issues || []).map((row, index) => ({
    ...row,
    key: String(index),
  })),
);
let request = 0,
  optionsRequest = 0,
  itemsRequest = 0,
  lotsRequest = 0,
  ordersRequest = 0,
  last = "",
  idempotencyKey = "";
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getInventoryPostings({
      keyword: keyword.value,
      posting_type_code: filterKind.value,
      page: page.value,
      page_size: 15,
    });
    if (current === request) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "库存业务读取失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
async function searchOrders(value = "") {
  const current = ++ordersRequest;
  try {
    const result = await getInventoryOrderOptions(value);
    if (current === ordersRequest) orderOptions.value = result.data.items;
  } catch (cause) {
    if (current === ordersRequest) formError.value = getHttpErrorMessage(cause);
  }
}
async function searchItems(value = "") {
  const current = ++itemsRequest;
  try {
    const result = await getInventoryItemOptions(value);
    if (current === itemsRequest && form.posting_type_code === "issue")
      itemOptions.value = result.data;
  } catch (cause) {
    if (current === itemsRequest) formError.value = getHttpErrorMessage(cause);
  }
}
async function changeKind() {
  ++itemsRequest;
  ++lotsRequest;
  ++optionsRequest;
  lots.value = [];
  form.operation_id = "";
  form.source_posting_id = "";
  form.lot_id = "";
  returnSelection.value = "";
  form.quantity = "1";
  if (form.posting_type_code === "receipt" && orderInfo.value) {
    form.item_id = orderInfo.value.product_item_id;
    itemOptions.value = [
      { id: form.item_id, item_name: orderInfo.value.product_item_name },
    ];
  } else {
    form.item_id = "";
    if (form.posting_type_code === "issue") searchItems();
  }
  if (form.posting_type_code !== "return") {
    const current = ++optionsRequest;
    form.warehouse_id = "";
    try {
      const result = await getStockWarehouseOptions(
        form.posting_type_code === "issue" ? "out" : "in",
        form.posting_type_code,
      );
      if (current === optionsRequest) warehouses.value = result.data;
    } catch (cause) {
      if (current === optionsRequest)
        formError.value = getHttpErrorMessage(cause);
    }
  }
}
async function changeOrder(id: string) {
  const current = ++optionsRequest;
  orderInfo.value = undefined;
  form.operation_id = "";
  form.source_posting_id = "";
  returnSelection.value = "";
  form.item_id = "";
  form.lot_id = "";
  if (!id) return;
  try {
    const result = await getOrderInventoryOptions(id);
    if (current !== optionsRequest) return;
    orderInfo.value = result.data;
    await changeKind();
  } catch (cause) {
    if (current === optionsRequest)
      formError.value = getHttpErrorMessage(cause);
  }
}
function chooseReturn(key: string) {
  const row = returnOptions.value.find((row) => row.key === key);
  if (!row) return;
  Object.assign(form, {
    source_posting_id: row.id,
    operation_id: row.operation_id || "",
    item_id: row.item_id,
    warehouse_id: row.warehouse_id,
    lot_id: row.lot_id || "",
    quantity: row.available_quantity,
  });
}
async function changeItem(id: string) {
  const current = ++lotsRequest;
  form.lot_id = "";
  lots.value = [];
  if (!id) return;
  try {
    const result = await getInventoryLotOptions(id);
    if (
      current === lotsRequest &&
      form.item_id === id &&
      form.posting_type_code === "issue"
    )
      lots.value = result.data;
  } catch (cause) {
    if (current === lotsRequest) formError.value = getHttpErrorMessage(cause);
  }
}
function create(kind: string) {
  if (busy.value) return;
  ++optionsRequest;
  last = "";
  idempotencyKey = "";
  formError.value = "";
  orderInfo.value = undefined;
  returnSelection.value = "";
  lots.value = [];
  Object.assign(form, {
    work_order_id: "",
    operation_id: "",
    posting_type_code: kind,
    source_posting_id: "",
    item_id: "",
    warehouse_id: "",
    lot_id: "",
    quantity: "1",
    unit_price: "",
    note: "",
  });
  visible.value = true;
  searchOrders();
  changeKind();
}
async function save() {
  if (busy.value) return;
  if (
    !form.work_order_id ||
    !form.item_id ||
    !form.warehouse_id ||
    !form.note.trim()
  ) {
    actionMessage("请选择工单、物料、仓库并填写说明", "warning");
    return;
  }
  const data = {
    ...form,
    operation_id: form.operation_id || null,
    lot_id: form.lot_id || null,
    source_posting_id: form.source_posting_id || null,
    unit_price: form.unit_price || null,
  };
  const fingerprint = JSON.stringify(data);
  if (last !== fingerprint) {
    last = fingerprint;
    idempotencyKey = crypto.randomUUID();
  }
  busy.value = true;
  try {
    const result = await createInventoryPosting({
      ...data,
      idempotency_key: idempotencyKey,
    });
    visible.value = false;
    message(
      result.data.status_code === "submitted"
        ? "已提交库存审批，审批后再确认记账"
        : "库存业务已记账",
      { type: "success" },
    );
    await load();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "操作失败，内容已保留，可重试"));
  } finally {
    busy.value = false;
  }
}
function resource(row: InventoryPosting) {
  return ["receipt", "return"].includes(row.posting_type_code)
    ? "inventory_inbound"
    : "inventory_outbound";
}
async function act(row: InventoryPosting, action: string) {
  if (busy.value) return;
  busy.value = true;
  try {
    let reason = "确认库存记账";
    if (action === "cancel") {
      const result = await ElMessageBox.prompt(
        "请填写作废或冲销理由",
        "取消库存业务",
        { inputValidator: (value) => !!value?.trim() || "请填写理由" },
      );
      reason = result.value;
    } else
      await ElMessageBox.confirm(
        action === "approve" ? "确认审批通过？" : "确认库存记账？",
      );
    if (action === "approve") await approveStockOrder(row.stock_order_id);
    else await actInventoryPosting(row.id, action, reason);
    await load();
  } catch (cause) {
    if (!["cancel", "close"].includes(cause as string))
      message(getHttpErrorMessage(cause), { type: "error" });
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="mes-stock-page">
    <div class="heading">
      <div>
        <h2>生产消耗与成品入库</h2>
        <p>
          领料扣库存、退料回原批次，成品入库占用末道合格产出。只有库存记账成功才计入实际消耗；审批中仅占业务额度。
        </p>
      </div>
      <div v-if="hasPerms('mes:inventory:manage')">
        <el-button :disabled="busy" @click="create('issue')">生产领料</el-button
        ><el-button :disabled="busy" @click="create('return')"
          >生产退料</el-button
        ><el-button type="primary" :disabled="busy" @click="create('receipt')"
          >成品入库</el-button
        >
      </div>
    </div>
    <el-card shadow="never"
      ><el-form
        inline
        @submit.prevent="
          page = 1;
          load();
        "
        ><el-form-item
          ><el-input
            v-model="keyword"
            clearable
            placeholder="工单 / 物料编号 / 名称"
            @keyup.enter="
              page = 1;
              load();
            " /></el-form-item
        ><el-form-item
          ><el-select
            v-model="filterKind"
            clearable
            style="width: 140px"
            placeholder="业务类型"
            ><el-option
              v-for="key in ['issue', 'return', 'receipt', 'shipment']"
              :key="key"
              :label="labels[key]"
              :value="key" /></el-select></el-form-item
        ><el-button
          type="primary"
          @click="
            page = 1;
            load();
          "
          >查询</el-button
        ><el-button
          @click="
            keyword = '';
            filterKind = '';
            page = 1;
            load();
          "
          >重置</el-button
        ></el-form
      >
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows"
        ><el-table-column
          prop="work_order_no"
          label="工单"
          min-width="150"
        /><el-table-column label="类型" width="110"
          ><template #default="{ row }">{{
            labels[row.posting_type_code]
          }}</template></el-table-column
        ><el-table-column
          prop="item_no"
          label="物料编号"
          min-width="120"
        /><el-table-column
          prop="item_name"
          label="物料"
          min-width="150"
        /><el-table-column label="数量 / 单位" min-width="130"
          ><template #default="{ row }"
            >{{ row.quantity }} {{ row.unit_code }}</template
          ></el-table-column
        ><el-table-column label="状态" width="110"
          ><template #default="{ row }"
            ><el-tag>{{
              labels[row.status_code] || row.status_code
            }}</el-tag></template
          ></el-table-column
        ><el-table-column
          prop="order_no"
          label="库存单号"
          min-width="170"
        /><el-table-column
          prop="business_date"
          label="业务日期"
          width="120"
        /><el-table-column label="操作" width="230" fixed="right"
          ><template #default="{ row }"
            ><el-button
              v-if="hasPerms(resource(row as InventoryPosting) + ':detail')"
              link
              type="primary"
              @click="
                detailId = row.stock_order_id;
                detailVisible = true;
              "
              >库存详情</el-button
            ><template
              v-if="
                hasPerms('mes:inventory:manage') &&
                row.posting_type_code !== 'shipment'
              "
              ><el-button
                v-if="
                  row.status_code === 'submitted' &&
                  hasPerms(resource(row as InventoryPosting) + ':approve')
                "
                link
                type="primary"
                :disabled="busy"
                @click="act(row as InventoryPosting, 'approve')"
                >审批通过</el-button
              ><el-button
                v-if="
                  row.status_code === 'approved' &&
                  hasPerms(resource(row as InventoryPosting) + ':confirm')
                "
                link
                type="primary"
                :disabled="busy"
                @click="act(row as InventoryPosting, 'confirm')"
                >确认记账</el-button
              ><el-button
                v-if="!['voided', 'reversed'].includes(row.status_code)"
                link
                type="danger"
                :disabled="busy"
                @click="act(row as InventoryPosting, 'cancel')"
                >{{
                  row.status_code === "confirmed" ? "冲销" : "作废"
                }}</el-button
              ></template
            ><span v-if="row.posting_type_code === 'shipment'"
              >随出货单办理</span
            ></template
          ></el-table-column
        ></el-table
      >
      <ListPagination
        v-model:current-page="page"
        :page-size="15"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
    /></el-card>
    <el-dialog
      v-model="visible"
      :title="labels[form.posting_type_code]"
      width="min(760px,96vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      ><el-alert
        v-if="formError"
        :title="formError"
        type="error"
        :closable="false"
      /><el-form label-position="top" :disabled="busy"
        ><el-form-item label="生产工单" required
          ><el-select
            v-model="form.work_order_id"
            filterable
            remote
            :remote-method="searchOrders"
            placeholder="按工单号或产品名称搜索"
            @change="changeOrder"
            ><el-option
              v-for="row in orderOptions"
              :key="row.id"
              :value="row.id"
              :label="row.label" /></el-select
        ></el-form-item>
        <el-alert
          v-if="form.posting_type_code === 'receipt' && orderInfo"
          :title="'当前可申请入库：' + orderInfo.receipt_available_quantity"
          type="info"
          :closable="false" />
        <el-form-item
          v-if="form.posting_type_code === 'return'"
          label="原领料 / 实际批次"
          required
          ><el-select v-model="returnSelection" @change="chooseReturn"
            ><el-option
              v-for="row in returnOptions"
              :key="row.key"
              :value="row.key"
              :label="`${row.order_no} · ${row.item_name} · ${row.lot_no || '未分批'} · 可退 ${row.available_quantity}`" /></el-select
        ></el-form-item>
        <el-form-item v-else label="物料 / 产品" required
          ><el-select
            v-model="form.item_id"
            filterable
            remote
            :disabled="form.posting_type_code === 'receipt'"
            :remote-method="searchItems"
            @change="changeItem"
            ><el-option
              v-for="row in itemOptions"
              :key="row.id"
              :value="row.id"
              :label="`${row.item_no || ''} ${row.item_name}`" /></el-select
        ></el-form-item>
        <el-form-item
          v-if="form.posting_type_code === 'issue'"
          label="工序（可选）"
          ><el-select v-model="form.operation_id" clearable
            ><el-option
              v-for="row in orderInfo?.operations || []"
              :key="row.id"
              :label="row.label"
              :value="row.id" /></el-select
        ></el-form-item>
        <el-form-item
          v-if="form.posting_type_code !== 'return'"
          label="仓库"
          required
          ><el-select v-model="form.warehouse_id" filterable
            ><el-option
              v-for="row in warehouses.filter(
                (row) => !orderInfo || row.org_id === orderInfo.org_id,
              )"
              :key="row.id"
              :label="row.label"
              :value="row.id" /></el-select
        ></el-form-item>
        <el-form-item
          v-if="form.posting_type_code === 'issue'"
          label="批次（可选，未指定时由库存按规则扣减）"
          ><el-select v-model="form.lot_id" clearable filterable
            ><el-option
              v-for="row in lots"
              :key="row.id"
              :label="row.label"
              :value="row.id" /></el-select
        ></el-form-item>
        <div class="grid">
          <el-form-item label="数量" required
            ><el-input
              v-model="form.quantity"
              placeholder="最多三位小数" /></el-form-item
          ><el-form-item
            v-if="form.posting_type_code === 'receipt'"
            label="入库成本单价（可选，元）"
            ><el-input
              v-model="form.unit_price"
              placeholder="人民币，最多两位小数"
          /></el-form-item>
        </div>
        <el-form-item label="说明" required
          ><el-input
            v-model="form.note"
            type="textarea"
            maxlength="1000" /></el-form-item></el-form
      ><template #footer
        ><el-button :disabled="busy" @click="visible = false">返回</el-button
        ><el-button type="primary" :loading="busy" @click="save"
          >提交库存业务</el-button
        ></template
      ></el-dialog
    >
    <OrderDetailDialog v-model="detailVisible" :order-id="detailId" />
  </div>
</template>
<style scoped>
.mes-stock-page {
  padding: 18px;
}

.heading {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

h2 {
  margin: 0 0 10px;
}

p {
  color: var(--el-text-color-secondary);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.el-select {
  width: 100%;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
