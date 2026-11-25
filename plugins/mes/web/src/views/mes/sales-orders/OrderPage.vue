<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, ref, watch, onDeactivated, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import ListPagination from "@/components/ListPagination/index.vue";
import ActionButton from "@/components/ActionButton/index.vue";
import RemoteSelect from "../components/RemoteSelect.vue";
import CustomerOrderEdit from "./CustomerOrderEdit.vue";
import {
  DISCOUNTS,
  applyDiscount,
  discountPrice,
  discountLabel,
} from "./pricing";
import { getMesProductOptions } from "@plugins/mes/web/src/api/mes";
import {
  orderRequest,
  deliveryDate,
  type CustomerOrder,
  type OrderSource,
  type SourceCustomer,
  type OrderLine,
  type ProductionDefaults,
  type Page,
} from "./api";

const route = useRoute(),
  router = useRouter();
const busy = ref(false),
  error = ref("");
const orders = ref<CustomerOrder[]>([]),
  order = ref<CustomerOrder>();
const page = ref(1),
  pageSize = ref(20),
  total = ref(0),
  keyword = ref("");
const statusFilter = ref<CustomerOrder["status_code"] | "">("");
const orderStatuses = {
  confirmed: { label: "待审核", type: "warning" },
  approved: { label: "审核通过", type: "success" },
  cancelled: { label: "已取消", type: "info" },
} as const;
const sources = ref<OrderSource[]>([]),
  sourcePage = ref(1),
  sourceTotal = ref(0),
  sourceKeyword = ref("");
const sourceCustomer = ref<SourceCustomer | null>(null),
  sourceCustomers = ref<SourceCustomer[]>([]),
  customerLoading = ref(false);
const customerOptions = computed(() => {
  const current = sourceCustomer.value;
  return current && !sourceCustomers.value.some((row) => row.id === current.id)
    ? [current, ...sourceCustomers.value]
    : sourceCustomers.value;
});
const MAIN_QUANTITY_TIER = "main";
type Choice = {
  source: OrderSource;
  tier_id: string;
  discount_rate: string;
  quantity: number;
  unit_price: number;
  due_date: string;
  adjustment_reason: string;
  is_price_confirmed: boolean;
};
const choices = ref<Record<string, Choice>>({});
const selected = computed(() => Object.values(choices.value));
const pageSelectedCount = computed(
  () => sources.value.filter((source) => !!choices.value[source.id]).length,
);
const customerPo = ref(""),
  note = ref("");
const requestKey = ref(crypto.randomUUID());
const releaseKey = ref(crypto.randomUUID());
const releaseOpen = ref(false);
const editOpen = ref(false);
const unitNames = ref<Record<string, string>>({});
const releaseRows = ref<
  {
    source: OrderLine;
    selected: boolean;
    quantity: number;
    product_item_id: string;
    unit: string;
    processing_type_code: string;
    initial_option?: { value: string; label: string; unit?: string };
    match_note?: string;
    is_create_product: boolean;
    product_unit_code: string;
    can_create_product: boolean;
    unit_fixed: boolean;
    order_unit_code: string;
  }[]
>([]);
type ReleaseRow = (typeof releaseRows.value)[number];
const quantityFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 3,
});
function displayQuantity(value: string | number | null | undefined) {
  if (value == null || value === "") return "—";
  const quantity = Number(value);
  return Number.isFinite(quantity) ? quantityFormatter.format(quantity) : "—";
}
function unitsMatch(row: ReleaseRow) {
  let expected = row.order_unit_code;
  if (!expected) {
    const value = row.source.unit_name_snapshot.trim().toLowerCase();
    const matches = Object.entries(unitNames.value).filter(
      ([code, name]) =>
        code.toLowerCase() === value || name.trim().toLowerCase() === value,
    );
    if (matches.length === 1) expected = matches[0][0];
  }
  return !!expected && expected === row.product_unit_code;
}
const isNew = computed(() => route.query.new === "1");
const canCreate = computed(
  () => hasPerms("mes:sales_order:manage") && hasPerms("mes:quotation:list"),
);
const canApprove = computed(() => hasPerms("mes:sales_order:approve"));
const canRelease = computed(
  () =>
    order.value?.status_code === "approved" &&
    hasPerms("mes:sales_order:release") &&
    hasPerms("mes:work_order:create"),
);
let generation = 0;
let sourceRequest = 0,
  customerRequest = 0;
async function run(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  try {
    await action();
  } catch (cause) {
    if (cause !== "cancel" && cause !== "close")
      actionMessage((cause as Error).message || "操作未完成，请重试");
  } finally {
    busy.value = false;
  }
}
async function listing() {
  const token = generation;
  const result = await orderRequest<Page<CustomerOrder>>("", "get", undefined, {
    page: page.value,
    page_size: pageSize.value,
    keyword: keyword.value,
    status_code: statusFilter.value || undefined,
    quotation_id: route.query.quotation_id,
  });
  if (token !== generation) return;
  orders.value = result.items;
  total.value = result.total;
}
async function loadSources() {
  const token = generation;
  const request = ++sourceRequest;
  const customerId = sourceCustomer.value?.id;
  if (!customerId) {
    sources.value = [];
    sourceTotal.value = 0;
    return;
  }
  const result = await orderRequest<Page<OrderSource>>(
    "/sources",
    "get",
    undefined,
    {
      page: sourcePage.value,
      page_size: 20,
      keyword: sourceKeyword.value,
      customer_id: customerId,
    },
  );
  if (
    token !== generation ||
    request !== sourceRequest ||
    customerId !== sourceCustomer.value?.id
  )
    return;
  sources.value = result.items;
  sourceTotal.value = result.total;
}
async function loadSourceCustomers(keyword = "") {
  const token = generation;
  const request = ++customerRequest;
  customerLoading.value = true;
  try {
    const result = await orderRequest<SourceCustomer[]>(
      "/source-customers",
      "get",
      undefined,
      { keyword },
    );
    if (token === generation && request === customerRequest)
      sourceCustomers.value = result;
  } catch (cause) {
    if (token === generation && request === customerRequest)
      actionMessage((cause as Error).message);
  } finally {
    if (token === generation && request === customerRequest)
      customerLoading.value = false;
  }
}
async function changeCustomer(id?: string) {
  if ((id || "") === (sourceCustomer.value?.id || "")) return;
  const customer = customerOptions.value.find((row) => row.id === id) || null;
  if (id && !customer) return;
  await run(async () => {
    const token = generation;
    if (selected.value.length)
      await ElMessageBox.confirm(
        "切换客户将清空已选货品及其成交信息，是否继续？",
        "切换客户",
        { type: "warning" },
      );
    if (token !== generation) return;
    choices.value = {};
    sourceCustomer.value = customer;
    requestKey.value = crypto.randomUUID();
    sourcePage.value = 1;
    sourceKeyword.value = "";
    sources.value = [];
    sourceTotal.value = 0;
    await loadSources();
  });
}
async function load() {
  const token = ++generation;
  order.value = undefined;
  releaseOpen.value = false;
  editOpen.value = false;
  choices.value = {};
  error.value = "";
  if (isNew.value) {
    requestKey.value = crypto.randomUUID();
    customerPo.value = note.value = "";
    sourceCustomer.value = null;
    sourceCustomers.value = [];
    sources.value = [];
    sourceTotal.value = 0;
    sourceKeyword.value = "";
    sourcePage.value = 1;
    await loadSourceCustomers();
    if (token !== generation) return;
    if (typeof route.query.quote_id === "string") {
      const seed = await orderRequest<Page<OrderSource>>(
        "/sources",
        "get",
        undefined,
        { quotation_id: route.query.quote_id, page: 1, page_size: 1 },
      );
      if (token !== generation) return;
      const first = seed.items[0];
      if (first) {
        sourceCustomer.value = {
          id: first.customer_id,
          name: first.customer_name_snapshot,
        };
        await loadSources();
      } else error.value = "该报价暂无可下单货品，请选择客户后重新查询";
    }
  } else if (typeof route.query.order_id === "string") {
    const result = await orderRequest<CustomerOrder>(
      `/${route.query.order_id}`,
    );
    if (token === generation) order.value = result;
  } else await listing();
}
watch(
  () => route.fullPath,
  () => {
    busy.value = true;
    const pending = load();
    const token = generation;
    void pending
      .catch((cause) => {
        if (token === generation) error.value = (cause as Error).message;
      })
      .finally(() => {
        if (token === generation) busy.value = false;
      });
  },
  { immediate: true },
);
onDeactivated(() => {
  generation++;
  releaseOpen.value = false;
});
onBeforeUnmount(() => {
  generation++;
});
function choose(source: OrderSource, value: boolean) {
  if (!value) {
    delete choices.value[source.id];
    return;
  }
  if (choices.value[source.id]) return;
  if (!sourceCustomer.value || source.customer_id !== sourceCustomer.value.id) {
    actionMessage("请先选择客户，再选择该客户的报价货品", "warning");
    return;
  }
  const first = selected.value[0]?.source;
  if (
    first &&
    ["org_id", "customer_id", "currency"].some(
      (key) => first[key] !== source[key],
    )
  ) {
    actionMessage("请选择同组织、同客户、同币种的货品", "warning");
    return;
  }
  choices.value[source.id] = {
    source,
    tier_id: MAIN_QUANTITY_TIER,
    discount_rate: "1",
    quantity: Number(source.quantity),
    unit_price: Number(source.unit_price),
    due_date: deliveryDate(source.lead_days),
    adjustment_reason: "",
    is_price_confirmed: false,
  };
}
function choosePage(value: boolean) {
  if (!value) {
    sources.value.forEach((source) => choose(source, false));
    return;
  }
  const combined = [
    ...selected.value.map((row) => row.source),
    ...sources.value,
  ];
  if (
    combined.some(
      (row) =>
        row.customer_id !== combined[0].customer_id ||
        row.org_id !== combined[0].org_id ||
        row.currency !== combined[0].currency,
    )
  ) {
    actionMessage("本页包含不同客户、组织或币种，请逐项选择同一客户的货品", "warning");
    return;
  }
  sources.value.forEach((row) => {
    choose(row, true);
  });
}
function tierChanged(row: Choice) {
  const tier =
    row.source.quantity_tiers.find((t) => t.id === row.tier_id) || row.source;
  row.quantity = Number(tier.quantity);
  row.unit_price = Number(tier.unit_price);
  applyDiscount(row, tier.unit_price);
  row.is_price_confirmed = false;
}
function tierOptions(source: OrderSource) {
  return [{ ...source, id: MAIN_QUANTITY_TIER }, ...source.quantity_tiers].map(
    (tier) => ({
      value: tier.id,
      label: `${displayQuantity(tier.quantity)} ${source.unit_name} / ${Number(tier.unit_price).toFixed(2)} ${source.currency}`,
    }),
  );
}
function originalPrice(row: Choice) {
  return Number(
    (row.source.quantity_tiers.find((t) => t.id === row.tier_id) || row.source)
      .unit_price,
  );
}
async function confirmOrder() {
  const token = generation;
  if (!sourceCustomer.value) throw Error("请先选择客户");
  if (!selected.value.length) throw Error("请至少选择一项货品");
  if (
    selected.value.some(
      (row) => row.source.customer_id !== sourceCustomer.value!.id,
    )
  )
    throw Error("已选货品与当前客户不一致，请重新选择");
  if (
    selected.value.some(
      (row) => !row.due_date || !(row.quantity > 0) || !(row.unit_price >= 0),
    )
  )
    throw Error("请补齐数量、单价和承诺交付日期");
  if (
    selected.value.some(
      (row) => row.unit_price < discountPrice(originalPrice(row), "0.7"),
    )
  )
    throw Error("成交单价不能低于所选报价的七折");
  await ElMessageBox.confirm(
    `确认 ${selected.value.length} 项货品的成交数量、价格及交付日期？`,
    "确认客户订单",
    { type: "warning" },
  );
  if (token !== generation) return;
  const result = await orderRequest<CustomerOrder>("", "post", {
    idempotency_key: requestKey.value,
    customer_po_no: customerPo.value,
    note: note.value,
    lines: selected.value.map((row) => ({
      quotation_line_id: row.source.id,
      quotation_version_no: row.source.quotation_version_no,
      quotation_tier_id:
        row.tier_id === MAIN_QUANTITY_TIER ? null : row.tier_id,
      quantity: row.quantity,
      unit_price: row.unit_price,
      discount_rate: row.discount_rate === "manual" ? null : row.discount_rate,
      due_date: row.due_date,
      is_price_confirmed: row.is_price_confirmed,
      adjustment_reason: row.adjustment_reason,
    })),
  });
  if (token !== generation) return;
  ElMessage.success(
    result.status_code === "confirmed" ? "客户订单已确认，待审核" : "已打开客户订单",
  );
  await router.replace({
    path: "/mes/sales-orders",
    query: { order_id: result.id },
  });
  order.value = result;
}
async function approveOrder() {
  const current = order.value;
  if (current?.status_code !== "confirmed" || !canApprove.value) return;
  const token = generation;
  await ElMessageBox.confirm(
    "请核对客户、货品、成交数量、单价和承诺交期。审核通过后，该订单可以生成生产工单。",
    "审核客户订单",
    { type: "warning", confirmButtonText: "审核通过" },
  );
  if (token !== generation) return;
  const result = await orderRequest<CustomerOrder>(`/${current.id}/approve`, "post", {
    version_no: current.version_no,
  });
  if (token !== generation) return;
  order.value = result;
  ElMessage.success("客户订单审核通过");
}
async function startRelease() {
  if (!canRelease.value) throw Error("客户订单审核通过后才能安排生产");
  const token = generation;
  const orderId = order.value!.id;
  const result = await orderRequest<ProductionDefaults>(
    `/${orderId}/production-defaults`,
  );
  if (token !== generation || order.value?.id !== orderId) return;
  releaseKey.value = crypto.randomUUID();
  releaseRows.value = order
    .value!.lines.filter((line) => Number(line.remaining_quantity) > 0)
    .map((source, index) => ({
      source,
      selected: index < 100,
      quantity: Number(source.remaining_quantity),
      product_item_id: "",
      unit: "",
      processing_type_code: "in_house",
      is_create_product: false,
      product_unit_code: "",
      can_create_product: false,
      unit_fixed: false,
      order_unit_code: "",
    }));
  releaseOpen.value = true;
  unitNames.value = result.unit_names;
  const byLine = new Map(
    result.lines.map((line) => [line.order_line_id, line]),
  );
  for (const row of releaseRows.value) {
    const item = byLine.get(row.source.id);
    row.order_unit_code = item?.order_unit_code || "";
    if (item?.product_item_id) {
      row.product_item_id = item.product_item_id;
      row.product_unit_code = item.unit_code || "";
      row.unit = item.unit_name || item.unit_code || "";
      row.initial_option = {
        value: item.product_item_id,
        label: `${item.item_no} · ${item.item_name}`,
        unit: item.unit_code || undefined,
      };
    } else if (item?.is_create_product && item.can_create) {
      row.is_create_product = true;
      row.can_create_product = true;
      row.product_unit_code = item.unit_code || "";
      row.unit = item.unit_name || "";
      row.unit_fixed = !!item.unit_code;
    } else
      row.match_note =
        item?.match_status === "ambiguous"
          ? "存在多个对应货品，请选择确认"
          : item?.match_status === "unit_mismatch"
            ? "档案与订单单位不同，请核对"
            : item?.is_create_product && !item.can_create
              ? "尚未建档，需要新增物料权限，或选择已有物料"
              : "未找到对应货品档案，请选择";
  }
}
async function release() {
  if (!canRelease.value) throw Error("客户订单审核通过后才能安排生产");
  const token = generation;
  const { id, version_no } = order.value!;
  const rows = releaseRows.value.filter((row) => row.selected);
  if (rows.length > 100)
    throw Error("每张生产工单最多安排 100 项货品，请分批勾选");
  if (
    !rows.length ||
    rows.some(
      (row) =>
        (!row.product_item_id && !row.is_create_product) ||
        !(row.quantity > 0) ||
        row.quantity > Number(row.source.remaining_quantity),
    )
  )
    throw Error("请选择生产货品及有效的本次数量");
  const invalidUnit = rows.find((row) => !unitsMatch(row));
  if (invalidUnit)
    throw Error(
      `${invalidUnit.source.drawing_no_snapshot || "当前货品"}：订单单位与生产货品单位不一致或尚未匹配，请核对单位`,
    );
  await ElMessageBox.confirm(
    `将本次 ${rows.length} 项货品生成一张生产工单，自动带入已采用的报价工艺，由工程复核调整后下单。是否继续？`,
    "生成生产工单",
    { type: "warning" },
  );
  if (token !== generation) return;
  const result = await orderRequest<CustomerOrder>(
    `/${id}/release`,
    "post",
    {
      version_no,
      idempotency_key: releaseKey.value,
      lines: rows.map((row) => ({
        order_line_id: row.source.id,
        quantity: row.quantity,
        product_item_id: row.is_create_product ? null : row.product_item_id,
        is_create_product: row.is_create_product,
        product_unit_code: row.is_create_product ? row.product_unit_code : null,
        processing_type_code: row.processing_type_code,
      })),
    },
  );
  if (token !== generation) return;
  order.value = result;
  releaseOpen.value = false;
  ElMessage.success("生产工单已生成，请复核工序后下单");
}
async function cancelOrder() {
  const result = await ElMessageBox.prompt("请填写取消原因", "取消客户订单", {
    inputValidator: (value) => !!value?.trim() || "请输入取消原因",
  });
  order.value = await orderRequest<CustomerOrder>(
    `/${order.value!.id}/cancel`,
    "post",
    { version_no: order.value!.version_no, note: result.value.trim() },
  );
  ElMessage.success("客户订单已取消");
}
function openOrder(id: string) {
  return router.push({
    path: "/mes/sales-orders",
    query: { order_id: id },
  });
}

async function back() {
  if ((isNew.value && selected.value.length) || releaseOpen.value) {
    try {
      await ElMessageBox.confirm(
        "当前未确认的录入将不保留，确定返回列表？",
        "返回客户订单",
        { type: "warning" },
      );
    } catch {
      return;
    }
  }
  router.push("/mes/sales-orders");
}
</script>

<template>
  <main v-loading="busy" class="sales-order-page">
    <header class="sales-order-heading">
      <div>
        <h2>{{ isNew ? "新建客户订单" : order?.order_no || "客户订单" }}</h2>
        <p>
          {{
            isNew
              ? "先选择客户，再从该客户的已审核报价中选货，确认成交与交付日期。"
              : "客户订单确认后需审核，审核通过后可分批生成生产工单。"
          }}
        </p>
      </div>
      <el-button v-if="isNew || order" @click="back">返回列表</el-button
      ><ActionButton
        v-else-if="canCreate"
        intent="create"
        @click="router.push({ path: '/mes/sales-orders', query: { new: '1' } })"
        >新建客户订单</ActionButton
      >
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="isNew">
      <section class="sales-order-panel">
        <h3>选择已审核报价货品</h3>
        <el-form
          class="erp-query-form"
          inline
          @submit.prevent="
            sourcePage = 1;
            run(loadSources);
          "
          ><el-form-item label="客户" required>
            <el-select
              :model-value="sourceCustomer?.id || ''"
              filterable
              remote
              clearable
              :remote-method="loadSourceCustomers"
              :loading="customerLoading"
              :disabled="busy"
              placeholder="选择客户，可输入名称查找"
              style="width: 280px"
              @change="changeCustomer"
              ><el-option
                v-for="customer in customerOptions"
                :key="customer.id"
                :value="customer.id"
                :label="customer.name"
            /></el-select> </el-form-item
          ><el-form-item label="搜索"
            ><el-input
              v-model="sourceKeyword"
              clearable
              maxlength="128"
              :disabled="!sourceCustomer || busy"
              placeholder="图号、报价单号" /></el-form-item
          ><el-form-item
            ><el-button
              type="primary"
              native-type="submit"
              :disabled="!sourceCustomer || busy"
              >查询</el-button
            ><el-button
              :disabled="!sourceCustomer || busy"
              @click="
                sourceKeyword = '';
                sourcePage = 1;
                run(loadSources);
              "
              >重置</el-button
            ></el-form-item
          ></el-form
        >
        <el-table
          :data="sources"
          border
          :empty-text="
            sourceCustomer
              ? '该客户暂无符合条件的已审核报价货品'
              : '请先选择客户'
          "
          ><el-table-column width="48" align="center"
            ><template #header
              ><el-checkbox
                :model-value="
                  sources.length > 0 && pageSelectedCount === sources.length
                "
                :indeterminate="
                  pageSelectedCount > 0 && pageSelectedCount < sources.length
                "
                :disabled="!sources.length || busy"
                aria-label="全选本页货品"
                title="全选或取消本页货品，其他页的选择保留"
                @change="(value) => choosePage(!!value)" /></template
            ><template #default="{ row }"
              ><el-checkbox
                :model-value="!!choices[row.id]"
                :disabled="busy"
                @change="
                  (value) => choose(row as OrderSource, !!value)
                " /></template></el-table-column
          ><el-table-column
            prop="drawing_no"
            label="图号"
            min-width="170"
          /><el-table-column
            prop="description"
            label="描述"
            min-width="180"
          /><el-table-column label="报价来源" min-width="190"
            ><template #default="{ row }"
              >{{ row.quote_no }} · R{{ row.revision }}</template
            ></el-table-column
          ><el-table-column
            prop="customer_name_snapshot"
            label="客户"
            min-width="160"
          /><el-table-column label="主数量 / 单价" min-width="180"
            ><template #default="{ row }"
              >{{ row.quantity }} {{ row.unit_name }} / {{ row.unit_price }}
              {{ row.currency }}</template
            ></el-table-column
          ></el-table
        >
        <ListPagination
          v-model:current-page="sourcePage"
          :page-size="20"
          :total="sourceTotal"
          :disabled="busy"
          layout="total, prev, pager, next"
          @current-change="run(loadSources)"
        />
      </section>
      <section class="sales-order-panel">
        <h3>本次成交 · 已选 {{ selected.length }} 项</h3>
        <el-form label-position="top" class="sales-order-fields"
          ><el-form-item label="客户采购单号"
            ><el-input v-model="customerPo" maxlength="64" /></el-form-item
          ><el-form-item label="接单说明"
            ><el-input v-model="note" maxlength="1000" /></el-form-item
        ></el-form>
        <el-table :data="selected" border max-height="600"
          ><el-table-column label="图号 / 来源" min-width="220"
            ><template #default="{ row }"
              >{{ row.source.drawing_no }}
              <p>
                {{ row.source.quote_no }} · R{{ row.source.revision }}
              </p></template
            ></el-table-column
          >
          <el-table-column label="报价数量 / 单价" min-width="245"
            ><template #default="{ row }"
              ><el-select
                v-if="row.source.quantity_tiers.length"
                v-model="row.tier_id"
                @change="tierChanged(row as Choice)"
                ><el-option
                  v-for="tier in tierOptions(row.source)"
                  :key="tier.value"
                  :value="tier.value"
                  :label="tier.label" /></el-select
              ><span v-else>{{
                tierOptions(row.source)[0].label
              }}</span></template
            ></el-table-column
          >
          <el-table-column label="订购数量" min-width="170"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.quantity"
                :min="0.001"
                :max="1000000"
                :precision="3"
                controls-position="right"
                @change="row.is_price_confirmed = false" /></template
          ></el-table-column>
          <el-table-column label="原始单价" width="140"
            ><template #default="{ row }"
              >{{ originalPrice(row as Choice) }}
              {{ row.source.currency }}</template
            ></el-table-column
          >
          <el-table-column label="成交折扣" width="135"
            ><template #default="{ row }"
              ><el-select
                v-model="row.discount_rate"
                @change="
                  applyDiscount(row as Choice, originalPrice(row as Choice))
                "
              >
                <el-option
                  v-for="option in DISCOUNTS"
                  :key="option.value"
                  :value="option.value"
                  :label="option.label"
                /> </el-select></template
          ></el-table-column>
          <el-table-column label="成交单价" min-width="170"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.unit_price"
                :min="discountPrice(originalPrice(row as Choice), '0.7')"
                :max="100000000"
                :precision="2"
                controls-position="right"
                @change="
                  row.discount_rate = 'manual';
                  row.is_price_confirmed = false;
                " /></template
          ></el-table-column>
          <el-table-column label="承诺交付日期" min-width="180"
            ><template #default="{ row }"
              ><el-date-picker
                v-model="row.due_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%" /></template
          ></el-table-column>
          <el-table-column label="调整说明及确认" min-width="230"
            ><template #default="{ row }"
              ><el-input
                v-model="row.adjustment_reason"
                placeholder="改数量或改价时填写原因"
                maxlength="1000"
              /><el-checkbox v-model="row.is_price_confirmed"
                >确认本次成交价格</el-checkbox
              ></template
            ></el-table-column
          >
          <el-table-column label="操作" width="80" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="danger" @click="choose(row.source, false)"
                >移除</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <footer class="erp-form-actions">
          <div class="erp-form-actions__primary">
            <el-button @click="back">取消</el-button
            ><el-button
              type="primary"
              :disabled="!selected.length"
              @click="run(confirmOrder)"
              >确认客户订单</el-button
            >
          </div>
        </footer>
      </section>
    </template>
    <template v-else-if="order">
      <section v-if="editOpen" class="sales-order-panel">
        <CustomerOrderEdit
          :key="order.id"
          :order="order"
          @saved="
            (value) => {
              order = value;
              editOpen = false;
            }
          "
          @cancel="editOpen = false"
        />
      </section>
      <section class="sales-order-panel">
        <el-descriptions :column="3" border
          ><el-descriptions-item label="客户">{{
            order.customer_name_snapshot
          }}</el-descriptions-item
          ><el-descriptions-item label="客户采购单号">{{
            order.customer_po_no || "—"
          }}</el-descriptions-item
          ><el-descriptions-item label="状态"
            ><el-tag
              :type="orderStatuses[order.status_code].type"
              >{{ orderStatuses[order.status_code].label }}</el-tag
            ></el-descriptions-item
          ><el-descriptions-item label="订单金额"
            >{{ order.amount }} {{ order.currency }}</el-descriptions-item
          ><el-descriptions-item label="成交货品"
            >{{ order.line_count }} 项</el-descriptions-item
          ><el-descriptions-item label="待安排生产"
            >{{ order.remaining_count }} 项</el-descriptions-item
          ></el-descriptions
        >
        <el-table :data="order.lines" border
          ><el-table-column
            prop="drawing_no_snapshot"
            label="图号"
            min-width="180" /><el-table-column label="来源报价" min-width="200"
            ><template #default="{ row }"
              >{{ row.quote_no_snapshot }} · R{{
                row.quotation_revision_snapshot
              }}</template
            ></el-table-column
          ><el-table-column
            prop="quantity"
            label="订购数量"
            width="120" /><el-table-column
            prop="original_unit_price_snapshot"
            label="报价原价"
            width="120" /><el-table-column
            prop="unit_price"
            label="成交单价"
            width="120" /><el-table-column label="成交折扣" width="110"
            ><template #default="{ row }">{{
              discountLabel(row.discount_rate)
            }}</template></el-table-column
          ><el-table-column
            prop="due_date"
            label="承诺交付"
            width="130" /><el-table-column
            prop="allocated_quantity"
            label="已安排"
            width="100" /><el-table-column
            prop="remaining_quantity"
            label="待安排"
            width="100"
        /></el-table>
      </section>
      <section v-if="releaseOpen && !editOpen" class="sales-order-panel">
        <h3>本次生产安排</h3>
        <p>
          货品和单位自动带入；未建档的货品在确认生成工单时建立档案。每次最多 100
          项，已采用的报价工艺自动带入，工程复核后下单。
        </p>
        <el-table :data="releaseRows" border
          ><el-table-column width="48"
            ><template #default="{ row }"
              ><el-checkbox
                v-model="row.selected" /></template></el-table-column
          ><el-table-column label="图号" min-width="180"
            ><template #default="{ row }">{{
              row.source.drawing_no_snapshot
            }}</template></el-table-column
          ><el-table-column label="本次数量" min-width="170"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.quantity"
                :min="0.001"
                :max="Number(row.source.remaining_quantity)"
                :precision="3"
                controls-position="right" /></template></el-table-column
          ><el-table-column label="生产货品" min-width="260"
            ><template #default="{ row }"
              ><div v-if="row.is_create_product">
                <div>
                  {{ row.source.drawing_no_snapshot }} ·
                  {{ row.source.description_snapshot }}
                </div>
                <el-tag size="small" type="info">生成工单时建档</el-tag
                ><el-button
                  link
                  type="primary"
                  @click="row.is_create_product = false"
                  >改选已有货品</el-button
                >
              </div>
              <RemoteSelect
                v-else
                v-model="row.product_item_id"
                :load-options="getMesProductOptions"
                :initial-option="row.initial_option"
                placeholder="选择对应的生产货品"
                @select="
                  (value) => {
                    row.product_unit_code = value?.unit || '';
                    row.unit = value?.unit
                      ? unitNames[value.unit] || value.unit
                      : '';
                    row.match_note = '';
                  }
                "
              /><el-button
                v-if="!row.is_create_product && row.can_create_product"
                link
                type="primary"
                @click="
                  row.is_create_product = true;
                  row.match_note = '';
                "
                >按订单货品建档</el-button
              ><span v-if="row.match_note" class="sales-order-match-note">{{
                row.match_note
              }}</span></template
            ></el-table-column
          ><el-table-column label="订单数量 / 本次生产" min-width="190"
            ><template #default="{ row }"
              >{{ displayQuantity(row.source.quantity) }}
              {{ row.source.unit_name_snapshot }} /
              <span
                v-if="row.is_create_product && !row.unit_fixed"
                class="sales-order-unit-error"
                >订单单位未匹配，请核对单位字典</span
              ><span v-else
                >{{ displayQuantity(row.quantity) }}
                {{ row.unit || "待选择单位" }}</span
              ><span
                v-if="row.product_unit_code && !unitsMatch(row as ReleaseRow)"
                class="sales-order-unit-error"
                >单位不一致或未匹配</span
              ></template
            ></el-table-column
          ><el-table-column label="生产方式" min-width="130"
            ><template #default="{ row }"
              ><el-select v-model="row.processing_type_code"
                ><el-option label="自制" value="in_house" /><el-option
                  label="委外"
                  value="outsourced" /><el-option
                  label="采购"
                  value="purchased" /></el-select></template></el-table-column
        ></el-table>
        <footer class="erp-form-actions">
          <div class="erp-form-actions__primary">
            <el-button @click="releaseOpen = false">取消</el-button
            ><el-button type="primary" @click="run(release)"
              >生成一张生产工单</el-button
            >
          </div>
        </footer>
      </section>
      <section class="sales-order-panel">
        <h3>生产安排 · {{ order.productions.length }} 张工单</h3>
        <el-table :data="order.productions" border
          ><el-table-column
            prop="production_order_no"
            label="生产工单"
            min-width="220"
          /><el-table-column label="本次货品" width="130"
            ><template #default="{ row }"
              >{{ row.lines.length }} 项</template
            ></el-table-column
          ><el-table-column label="操作" min-width="130"
            ><template #default="{ row }"
              ><el-button
                v-if="hasPerms('mes:work_order:list')"
                link
                type="primary"
                @click="
                  router.push({
                    path: '/mes/work-orders',
                    query: { production_order_id: row.production_order_id },
                  })
                "
                >查看并配置工单</el-button
              ></template
            ></el-table-column
          ></el-table
        >
      </section>
      <section v-if="order.events?.length" class="sales-order-panel">
        <h3>操作记录</h3>
        <el-table :data="order.events" border max-height="300"
          ><el-table-column
            prop="created_at"
            label="时间"
            min-width="190" /><el-table-column label="操作" width="130"
            ><template #default="{ row }">{{
              {
                confirm: "确认客户订单",
                approve: "审核通过",
                update: "修改成交信息",
                release: "安排生产",
                cancel: "取消订单",
              }[row.action_key] || row.action_key
            }}</template></el-table-column
          ><el-table-column prop="note" label="说明" min-width="300"
        /></el-table>
        <p>显示最近 500 条操作记录。</p>
      </section>
      <footer
        v-if="order.status_code !== 'cancelled' && !editOpen"
        class="erp-form-actions sales-order-panel"
      >
        <div class="erp-form-actions__primary">
          <el-button
            v-if="order.productions.length && hasPerms('mes:shipment:list')"
            data-action="view"
            @click="router.push({ path: '/mes/shipments', query: { sales_order_id: order.id } })"
            >出货单</el-button
          >
          <el-button
            v-if="
              hasPerms('mes:sales_order:manage') &&
              !order.lines.some((line) => Number(line.allocated_quantity) > 0)
            "
            data-action="edit"
            @click="
              editOpen = true;
              releaseOpen = false;
            "
            >修改成交信息</el-button
          >
          <el-button
            v-if="hasPerms('mes:sales_order:manage')"
            type="danger"
            plain
            @click="run(cancelOrder)"
            >取消订单</el-button
          >
          <el-button
            v-if="order.status_code === 'confirmed' && canApprove"
            type="primary"
            @click="run(approveOrder)"
            >审核</el-button
          >
          <el-button
            v-if="canRelease"
            type="primary"
            :disabled="!order.remaining_count"
            @click="run(startRelease)"
            >分批生成生产工单</el-button
          >
        </div>
      </footer>
    </template>
    <template v-else>
      <section class="sales-order-panel">
        <el-form
          class="erp-query-form"
          inline
          @submit.prevent="
            page = 1;
            run(listing);
          "
          ><el-form-item label="搜索"
            ><el-input
              v-model="keyword"
              clearable
              placeholder="订单号、客户采购单号、客户" /></el-form-item
          ><el-form-item label="状态">
            <el-select
              v-model="statusFilter"
              clearable
              placeholder="全部状态"
              style="width: 145px"
            >
              <el-option
                v-for="(item, value) in orderStatuses"
                :key="value"
                :value="value"
                :label="item.label"
              />
            </el-select>
          </el-form-item
          ><el-form-item
            ><el-button type="primary" native-type="submit">查询</el-button
            ><el-button
              @click="
                keyword = '';
                statusFilter = '';
                page = 1;
                run(listing);
              "
              >重置</el-button
            ></el-form-item
          ></el-form
        >
      </section>
      <section class="erp-list-panel">
        <el-table :data="orders" border
          ><el-table-column label="客户订单" min-width="230"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="openOrder(row.id)"
                >{{ row.order_no }}</el-button
              ></template
            ></el-table-column
          ><el-table-column
            prop="customer_name_snapshot"
            label="客户"
            min-width="160" /><el-table-column
            prop="customer_po_no"
            label="客户采购单号"
            min-width="170" /><el-table-column
            prop="line_count"
            label="货品项数"
            width="110" /><el-table-column label="订单金额" min-width="150"
            ><template #default="{ row }"
              >{{ row.amount }} {{ row.currency }}</template
            ></el-table-column
          ><el-table-column label="状态" width="110"
            ><template #default="{ row }"
              ><el-tag
                :type="orderStatuses[(row as CustomerOrder).status_code].type"
                >{{ orderStatuses[(row as CustomerOrder).status_code].label }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column
            prop="remaining_count"
            label="待安排项数"
            width="120"
          />
          <el-table-column v-if="canApprove" label="操作" width="88" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status_code === 'confirmed'"
                link
                type="primary"
                @click="openOrder(row.id)"
              >审核</el-button>
            </template>
          </el-table-column>
        </el-table
        ><ListPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          @current-change="run(listing)"
          @size-change="
            page = 1;
            run(listing);
          "
        />
      </section>
    </template>
  </main>
</template>

<style scoped>
.sales-order-page {
  padding: 20px;
}

.sales-order-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.sales-order-heading p,
.sales-order-panel p {
  color: var(--el-text-color-secondary);
}

.sales-order-panel {
  padding: 20px;
  margin: 16px 0;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.sales-order-panel h3 {
  margin: 0 0 16px;
}

.sales-order-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.sales-order-match-note {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sales-order-unit-error {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-danger);
}
</style>
