<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { hasPerms } from "@/utils/auth";
import {
  allocatedQuantity,
  clone,
  createCustomerOrder,
  createProduction,
  customerName,
  newQuote,
  orderAmount,
  productionBatches,
  productionSummary,
  productionProgress,
  productionLabels,
  quantityUnits,
  quoteLabels,
  remainingQuantity,
  reviseQuote,
  saveQuote,
  type CustomerOrder,
  type OrderCommand,
  type OrderLine,
  type Quote,
  type Role,
  type Production,
} from "./model";
import {
  orderDelivery,
  shippedQuantity,
  shipmentSources,
} from "./shipmentModel";
import { useMesSalesStoreHook } from "./store";
import { exportQuote } from "./exports";
import QuoteEditor from "./QuoteEditor.vue";
import CustomerOrderDialog from "./CustomerOrderDialog.vue";
import ProductionDialogs from "./ProductionDialogs.vue";
import AiQuoteReview from "./AiQuoteReview.vue";

const props = defineProps<{ page: "quotes" | "orders" }>();
const router = useRouter(),
  route = useRoute();
const session = useMesSalesStoreHook();
const { state, files } = session;
onActivated(session.ensureSession);
const keyword = ref(""),
  status = ref("");
const quoteVisible = ref(false),
  orderVisible = ref(false),
  releaseVisible = ref(false);
const selectedQuote = ref<Quote>(),
  selectedOrder = ref<CustomerOrder>(),
  initialQuoteId = ref<string>();
const actor = ref<Role>("sales"),
  readOnly = ref(false),
  exporting = ref(false);
const selectedAiTask = computed(() =>
  state.ai_quote_tasks.find(
    (task) =>
      task.id === route.query.ai_task_id &&
      task.quote_id === selectedQuote.value?.id,
  ),
);
const canReviewAi = computed(
  () =>
    hasPerms("mes:quotation:price") &&
    !!selectedQuote.value &&
    ["pending", "pricing"].includes(selectedQuote.value.status),
);
function openAiDetail(id: string, tab = String(route.query.ai_tab || "items")) {
  if (!hasPerms("mes:quotation:price")) return;
  const task = state.ai_quote_tasks.find(
    (row) => row.id === id && row.quote_id === selectedQuote.value?.id,
  );
  if (task)
    router.push({
      path: "/mes/quotations",
      query: { ...route.query, ai_task_id: id, ai_tab: tab },
    });
}
function closeAiDetail() {
  const query = { ...route.query };
  delete query.ai_task_id;
  router.push({ path: "/mes/quotations", query });
}
onDeactivated(() => {
  quoteVisible.value = orderVisible.value = releaseVisible.value = false;
});
const quotes = computed(() =>
  state.quotes.filter(
    (quote) =>
      (!status.value || quote.status === status.value) &&
      [quote.quote_no, quote.title, customerName(quote.customer_id)]
        .join(" ")
        .toLowerCase()
        .includes(keyword.value.trim().toLowerCase()),
  ),
);
const orders = computed(() =>
  state.orders.filter((order) =>
    [order.order_no, order.customer_po_no, customerName(order.customer_id)]
      .join(" ")
      .toLowerCase()
      .includes(keyword.value.trim().toLowerCase()),
  ),
);
const orderProgress = computed(() =>
  Object.fromEntries(
    state.orders.map((order) => [order.id, productionSummary(state, order)]),
  ),
);
const deliveries = computed(() =>
  Object.fromEntries(
    state.orders.map((order) => [order.id, orderDelivery(state, order.id)]),
  ),
);
const shippableOrderIds = computed(
  () =>
    new Set(
      shipmentSources(state)
        .filter((row) => row.available_quantity > 0)
        .map((row) => row.order_id),
    ),
);
function viewShipments(order: CustomerOrder, create = false) {
  if (
    !hasPerms("mes:shipment:list") ||
    (create && !hasPerms("mes:shipment:manage"))
  )
    return;
  router.push({
    path: "/mes/shipments",
    query: {
      source: "customer_order",
      sales_order_id: order.id,
      ...(create ? { create: "1" } : {}),
    },
  });
}
const canCreateOrder = computed(() => hasPerms("mes:sales_order:manage"));
const canRelease = computed(
  () =>
    hasPerms("mes:sales_order:release") &&
    hasPerms("mes:work_order:create") &&
    hasPerms("mes:work_order:list"),
);
function openQuote(
  quote?: Quote,
  mode: "sales" | "engineering" | "view" = "view",
) {
  if (
    (mode === "sales" && !hasPerms("mes:quotation:manage")) ||
    (mode === "engineering" && !hasPerms("mes:quotation:price"))
  )
    return;
  selectedQuote.value = quote || newQuote(state);
  if (!state.quotes.some((row) => row.id === selectedQuote.value.id))
    session.quoteDrafts[selectedQuote.value.id] = selectedQuote.value;
  actor.value = mode === "engineering" ? "engineering" : "sales";
  readOnly.value = mode === "view";
  router.push({
    path: "/mes/quotations",
    query: { edit: "quote", mode, quote_id: selectedQuote.value.id },
  });
}
function closeEditor() {
  quoteVisible.value = orderVisible.value = false;
  router.push({
    path: props.page === "quotes" ? "/mes/quotations" : "/mes/sales-orders",
  });
}
function commitQuote(
  quote: Quote,
  action: "save" | "submit" | "finish" | "return",
) {
  if (
    readOnly.value ||
    !hasPerms(
      actor.value === "engineering"
        ? "mes:quotation:price"
        : "mes:quotation:manage",
    )
  )
    throw Error("当前账号没有此操作权限");
  saveQuote(state, quote, action, actor.value);
  delete session.quoteDrafts[quote.id];
  closeEditor();
  ElMessage.success(
    action === "finish"
      ? "报价已完成"
      : action === "submit"
        ? "已提交工程报价"
        : action === "return"
          ? "已退回业务补充资料"
          : "已保存",
  );
}
function revise(quote: Quote) {
  try {
    openQuote(reviseQuote(state, quote), "sales");
  } catch (cause) {
    ElMessage.warning((cause as Error).message);
  }
}
function newOrder(quoteId?: string) {
  if (!canCreateOrder.value) return;
  router.push({
    path: "/mes/sales-orders",
    query: { create: "1", ...(quoteId ? { quote_id: quoteId } : {}) },
  });
}
function restoreEditor() {
  const path =
    props.page === "quotes" ? "/mes/quotations" : "/mes/sales-orders";
  if (route.path !== path) return;
  quoteVisible.value = orderVisible.value = false;
  if (props.page === "quotes" && route.query.edit === "quote") {
    const quote =
      state.quotes.find((row) => row.id === route.query.quote_id) ||
      session.quoteDrafts[String(route.query.quote_id || "")];
    if (!quote) {
      ElMessage.info("当前询价未保存或暂存数据已清空，请返回列表重新打开");
      router.replace({ path });
      return;
    }
    selectedQuote.value = quote;
    actor.value = route.query.mode === "engineering" ? "engineering" : "sales";
    readOnly.value =
      route.query.mode !== "sales" && route.query.mode !== "engineering";
    if (
      !hasPerms("mes:quotation:list") ||
      (!readOnly.value &&
        !hasPerms(
          actor.value === "engineering"
            ? "mes:quotation:price"
            : "mes:quotation:manage",
        ))
    ) {
      router.replace({ path });
      return;
    }
    quoteVisible.value = true;
    if (
      route.query.ai_task_id &&
      (!selectedAiTask.value || !hasPerms("mes:quotation:price"))
    ) {
      ElMessage.info("AI 核价记录已清空、不属于本报价单或无权查看");
      const query = { ...route.query };
      delete query.ai_task_id;
      router.replace({ path, query });
    }
  }
  if (
    props.page !== "orders" ||
    route.query.create !== "1" ||
    !canCreateOrder.value
  )
    return;
  initialQuoteId.value =
    typeof route.query.quote_id === "string" ? route.query.quote_id : undefined;
  orderVisible.value = true;
}
watch(
  () => [
    props.page,
    route.path,
    route.query.edit,
    route.query.mode,
    route.query.create,
    route.query.quote_id,
    route.query.ai_task_id,
  ],
  restoreEditor,
  { immediate: true },
);
onActivated(restoreEditor);
function confirmOrder(command: OrderCommand) {
  if (!canCreateOrder.value) throw Error("当前账号没有客户订单维护权限");
  const order = createCustomerOrder(state, command);
  closeEditor();
  keyword.value = "";
  ElMessage.success(`客户订单 ${order.order_no} 已确认`);
}
function openRelease(order: CustomerOrder) {
  if (canRelease.value) {
    selectedOrder.value = order;
    releaseVisible.value = true;
  }
}
function generate(choices: { order_line_id: string; quantity: number }[]) {
  if (!canRelease.value) throw Error("当前账号没有生产下达权限");
  const project = createProduction(state, selectedOrder.value.id, choices);
  releaseVisible.value = false;
  ElMessage.success(
    `已生成工单 ${project.production_no}，包含 ${project.orders.length} 项货品`,
  );
  router.push({
    path: "/mes/work-orders",
    query: {
      source: "customer_order",
      sales_order_id: selectedOrder.value.id,
      production_id: project.id,
    },
  });
}
function viewProduction(order: CustomerOrder, production?: Production) {
  router.push({
    path: "/mes/work-orders",
    query: {
      source: "customer_order",
      sales_order_id: order.id,
      ...(production ? { production_id: production.id } : {}),
    },
  });
}
function productionRecords(order: CustomerOrder) {
  return productionBatches(state, order.id).map((project) => ({
    ...project,
    product_names: project.orders
      .map((item) => item.snapshot.drawing_no)
      .join("、"),
    progress: productionProgress(project),
  }));
}
async function download(quote: Quote, pack: boolean) {
  if (exporting.value || !hasPerms("mes:quotation:export")) return;
  exporting.value = true;
  try {
    const result = await exportQuote(clone(quote), files, pack);
    ElMessage.success(
      pack
        ? `已打包明细和 ${result.included} 个文件${result.missing ? `；${result.missing} 个示例文件仅列清单` : ""}`
        : "Excel 已导出",
    );
  } catch (cause) {
    ElMessage.error((cause as Error).message || "导出失败");
  } finally {
    exporting.value = false;
  }
}
function orderedCount(quote: Quote) {
  return deals(quote).length;
}
function deals(quote: Quote) {
  return state.orders.filter((order) =>
    order.lines.some((line) => line.quote_id === quote.id),
  );
}
function dealLines(quote: Quote) {
  return deals(quote).flatMap((order) =>
    order.lines
      .filter((line) => line.quote_id === quote.id)
      .map((line) => ({ ...line, order_no: order.order_no })),
  );
}
function search() {
  keyword.value = keyword.value.trim();
}
function resetFilters() {
  keyword.value = status.value = "";
}
</script>

<template>
  <div class="sales-prototype sales-business-page">
    <el-alert v-if="page === 'orders'" type="warning" :closable="false" title="客户订单、生产下达和出货仍为前端演示数据，尚未与真实询价报价关联；不要用于正式接单。" />
    <template v-if="!quoteVisible && !orderVisible">
      <header class="prototype-heading">
        <div>
          <h2>{{ page === "quotes" ? "询价报价" : "客户订单" }}</h2>
          <p>
            {{
              page === "quotes"
                ? "业务整理客户需求与图纸，工程核价，确认后输出报价。"
                : "确认成交货品、数量及价格，再按交付需求分批生成生产工单。"
            }}
          </p>
        </div>
        <div class="prototype-toolbar">
          <el-button
            v-if="page === 'quotes' && hasPerms('mes:quotation:manage')"
            type="primary"
            @click="openQuote(undefined, 'sales')"
            >＋ 新建询价</el-button
          ><el-button
            v-if="page === 'orders' && canCreateOrder"
            type="primary"
            @click="newOrder()"
            >＋ 新建客户订单</el-button
          >
        </div>
      </header>
      <el-alert
        type="info"
        :closable="false"
        title="当前数据由前端暂存，业务接口尚未接入；跨页面保留本次操作，刷新或退出登录后清空。示例文件仅展示名称。"
      />
      <el-card shadow="never"
        ><el-form inline class="prototype-toolbar" @submit.prevent="search"
          ><el-form-item label="搜索"
            ><el-input
              v-model="keyword"
              clearable
              :placeholder="
                page === 'quotes'
                  ? '报价单号、名称或客户'
                  : '订单号、采购单号或客户'
              "
              @keyup.enter="search" /></el-form-item
          ><el-form-item v-if="page === 'quotes'" label="状态"
            ><el-select
              v-model="status"
              clearable
              placeholder="全部状态"
              style="width: 160px"
              ><el-option
                v-for="(label, key) in quoteLabels"
                :key="key"
                :label="label"
                :value="key" /></el-select></el-form-item
          ><el-form-item
            ><el-button type="primary" @click="search">查询</el-button
            ><el-button @click="resetFilters">重置</el-button></el-form-item
          ></el-form
        >
        <el-table v-if="page === 'quotes'" :data="quotes" row-key="id" stripe>
          <el-table-column label="询价 / 报价单" min-width="240"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="openQuote(row as Quote)"
                >{{ row.quote_no }} · R{{ row.revision }}</el-button
              ><strong class="prototype-block">{{ row.title }}</strong
              ><small v-if="!row.is_current && row.status === 'quoted'"
                >历史修订</small
              ></template
            ></el-table-column
          >
          <el-table-column label="客户 / 货品" min-width="195"
            ><template #default="{ row }"
              >{{ customerName(row.customer_id)
              }}<small
                >{{ row.currency }} · {{ row.lines.length }} 种货品</small
              ></template
            ></el-table-column
          >
          <el-table-column label="报价状态" width="145"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.status === 'quoted'
                    ? 'success'
                    : row.status === 'draft'
                      ? 'info'
                      : 'warning'
                "
                >{{ quoteLabels[row.status as Quote["status"]] }}</el-tag
              ><small
                >已填单价
                {{
                  row.lines.filter((line) => line.unit_price !== null).length
                }}
                / {{ row.lines.length }}</small
              ></template
            ></el-table-column
          >
          <el-table-column label="业务 / 工程负责人" min-width="175"
            ><template #default="{ row }"
              >{{ row.owner }} / {{ row.engineer
              }}<small>截止：{{ row.deadline || "未设定" }}</small></template
            ></el-table-column
          >
          <el-table-column label="成交记录" width="150"
            ><template #default="{ row }"
              ><el-popover
                v-if="orderedCount(row as Quote)"
                trigger="click"
                placement="bottom"
                :width="560"
              >
                <template #reference
                  ><el-button
                    link
                    type="primary"
                    :aria-label="`查看 ${row.quote_no} R${row.revision} 成交记录`"
                    >{{ orderedCount(row as Quote) }} 张订单 · 查看</el-button
                  ></template
                >
                <strong
                  >成交记录 · {{ row.quote_no }} · R{{ row.revision }}</strong
                >
                <el-table
                  :data="dealLines(row as Quote)"
                  max-height="300"
                  size="small"
                  style="margin-top: 12px"
                >
                  <el-table-column
                    label="客户订单"
                    prop="order_no"
                    width="125"
                  />
                  <el-table-column label="图号" min-width="175"
                    ><template #default="{ row: line }">{{
                      line.snapshot.drawing_no
                    }}</template></el-table-column
                  >
                  <el-table-column label="成交数量" width="110"
                    ><template #default="{ row: line }"
                      >{{ line.quantity }} {{ line.snapshot.unit }}</template
                    ></el-table-column
                  >
                  <el-table-column label="交期" prop="due_date" width="110" />
                </el-table> </el-popover
              ><span v-else class="prototype-muted">尚未成交</span></template
            ></el-table-column
          >
          <el-table-column label="操作" min-width="320" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="openQuote(row as Quote)"
                >查看</el-button
              ><el-button
                v-if="
                  row.status === 'draft' && hasPerms('mes:quotation:manage')
                "
                link
                type="primary"
                @click="openQuote(row as Quote, 'sales')"
                >编辑需求</el-button
              ><el-button
                v-if="
                  ['pending', 'pricing'].includes(row.status) &&
                  hasPerms('mes:quotation:price')
                "
                link
                type="primary"
                @click="openQuote(row as Quote, 'engineering')"
                >工程报价</el-button
              ><el-button
                v-if="
                  row.status === 'quoted' &&
                  row.is_current &&
                  canCreateOrder &&
                  hasPerms('mes:sales_order:list')
                "
                link
                type="primary"
                @click="newOrder(row.id)"
                >选择货品下单</el-button
              ><template v-if="hasPerms('mes:quotation:export')"
                ><el-button
                  link
                  :disabled="exporting"
                  @click="download(row as Quote, false)"
                  >Excel</el-button
                ><el-button
                  link
                  :disabled="exporting"
                  @click="download(row as Quote, true)"
                  >打包</el-button
                ></template
              ><el-button
                v-if="
                  row.status === 'quoted' && hasPerms('mes:quotation:manage')
                "
                link
                title="已完成报价需要改价或改图时，保留旧版并创建下一修订"
                @click="revise(row as Quote)"
                >新建修订</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <el-table v-else :data="orders" row-key="id" stripe>
          <el-table-column type="expand"
            ><template #default="{ row }"
              ><el-table :data="row.lines" border class="prototype-inner-table"
                ><el-table-column label="图号 / 描述" min-width="230"
                  ><template #default="{ row: line }"
                    >{{ line.snapshot.drawing_no
                    }}<small
                      >{{ line.snapshot.description }} · 图纸
                      {{ line.snapshot.drawing_revision }}</small
                    ></template
                  ></el-table-column
                ><el-table-column label="来源报价" width="180"
                  ><template #default="{ row: line }"
                    >{{ line.quote_no }} · R{{ line.quote_revision }}</template
                  ></el-table-column
                ><el-table-column label="订购数量" width="115"
                  ><template #default="{ row: line }"
                    >{{ line.quantity }} {{ line.snapshot.unit }}</template
                  ></el-table-column
                ><el-table-column label="成交单价" width="125"
                  ><template #default="{ row: line }"
                    >{{ line.unit_price.toFixed(2) }}
                    {{ row.currency }}</template
                  ></el-table-column
                ><el-table-column
                  label="交期"
                  prop="due_date"
                  width="125"
                /><el-table-column label="已下达" width="100"
                  ><template #default="{ row: line }">{{
                    allocatedQuantity(state, line.id)
                  }}</template></el-table-column
                ><el-table-column label="待下达" width="100"
                  ><template #default="{ row: line }"
                    ><strong>{{
                      remainingQuantity(state, line as OrderLine)
                    }}</strong></template
                  ></el-table-column
                ><el-table-column label="已发货" width="100"
                  ><template #default="{ row: line }"
                    >{{ shippedQuantity(state, line.id, true) }}
                    {{ line.snapshot.unit }}</template
                  ></el-table-column
                >
                <el-table-column label="待发货" width="100"
                  ><template #default="{ row: line }"
                    >{{
                      Math.max(
                        0,
                        quantityUnits(line.quantity) -
                          quantityUnits(shippedQuantity(state, line.id, true)),
                      ) / 1000
                    }}
                    {{ line.snapshot.unit }}</template
                  ></el-table-column
                >
              </el-table></template
            ></el-table-column
          >
          <el-table-column
            label="客户订单"
            prop="order_no"
            width="165"
          /><el-table-column label="客户 / 采购单号" min-width="230"
            ><template #default="{ row }"
              >{{ customerName(row.customer_id)
              }}<small>{{
                row.customer_po_no || "未填写采购单号"
              }}</small></template
            ></el-table-column
          ><el-table-column label="成交明细" width="160"
            ><template #default="{ row }"
              >{{ row.lines.length }} 项 ·
              {{ new Set(row.lines.map((line) => line.quote_id)).size }}
              张报价</template
            ></el-table-column
          ><el-table-column label="订单金额" width="160"
            ><template #default="{ row }"
              >{{ orderAmount(row as CustomerOrder).toFixed(2) }}
              {{ row.currency }}</template
            ></el-table-column
          ><el-table-column label="生产安排" min-width="245"
            ><template #default="{ row }"
              ><el-popover
                v-if="orderProgress[row.id].batch_count"
                trigger="click"
                placement="bottom"
                :width="760"
              >
                <template #reference>
                  <el-button
                    link
                    type="primary"
                    :aria-label="`查看 ${row.order_no} 生产安排记录`"
                    >{{ orderProgress[row.id].work_order_count }} 张工单 ·
                    {{ orderProgress[row.id].product_count }} 项货品</el-button
                  >
                </template>
                <strong>生产安排记录 · {{ row.order_no }}</strong>
                <p class="prototype-muted">
                  每次生成一张工单，包含当时选择的全部货品。货品执行明细不另计为工单；取消记录保留。
                </p>
                <el-table
                  :data="productionRecords(row as CustomerOrder)"
                  max-height="320"
                  size="small"
                >
                  <el-table-column label="生产工单" width="145"
                    ><template #default="{ row: production }">
                      <el-button
                        v-if="hasPerms('mes:work_order:list')"
                        link
                        type="primary"
                        @click="
                          viewProduction(
                            row as CustomerOrder,
                            production as Production,
                          )
                        "
                        >{{ production.production_no }}</el-button
                      >
                      <span v-else>{{ production.production_no }}</span>
                    </template></el-table-column
                  >
                  <el-table-column label="货品数量" width="110"
                    ><template #default="{ row: production }"
                      >{{ production.orders.length }} 项货品</template
                    ></el-table-column
                  >
                  <el-table-column
                    label="本次货品图号"
                    prop="product_names"
                    min-width="240"
                    show-overflow-tooltip
                  />
                  <el-table-column label="工单状态" width="100"
                    ><template #default="{ row: production }">{{
                      productionLabels[production.progress.status]
                    }}</template></el-table-column
                  >
                </el-table>
              </el-popover>
              <span v-else class="prototype-muted">尚未安排生产</span>
              <small
                >已全部安排
                {{ orderProgress[row.id].fully_arranged_line_count }} /
                {{ row.lines.length }} 项货品</small
              >
              <small
                v-if="
                  orderProgress[row.id].active_batch_count <
                  orderProgress[row.id].batch_count
                "
                >含取消共
                {{ orderProgress[row.id].batch_count }} 张工单记录</small
              >
            </template> </el-table-column
          ><el-table-column label="交付进度" min-width="190"
            ><template #default="{ row }">
              <el-button
                v-if="hasPerms('mes:shipment:list')"
                link
                type="primary"
                @click="viewShipments(row as CustomerOrder)"
                >{{ deliveries[row.id].shipment_count }} 张有效出货单</el-button
              >
              <span v-else
                >{{ deliveries[row.id].shipment_count }} 张有效出货单</span
              >
              <small
                >已全部交付 {{ deliveries[row.id].complete_line_count }} /
                {{ row.lines.length }} 项货品</small
              >
            </template></el-table-column
          ><el-table-column label="操作" width="310" fixed="right"
            ><template #default="{ row }"
              ><el-button
                v-if="canRelease"
                link
                type="primary"
                :disabled="
                  !row.lines.some((line) => remainingQuantity(state, line) > 0)
                "
                @click="openRelease(row as CustomerOrder)"
                >分批生成生产工单</el-button
              ><el-button
                v-if="hasPerms('mes:work_order:list')"
                link
                @click="viewProduction(row as CustomerOrder)"
                >查看生产工单</el-button
              ><el-button
                v-if="
                  hasPerms('mes:shipment:list') &&
                  hasPerms('mes:shipment:manage')
                "
                link
                type="primary"
                :disabled="!shippableOrderIds.has(row.id)"
                @click="viewShipments(row as CustomerOrder, true)"
                >创建出货单</el-button
              ></template
            ></el-table-column
          >
          <template #empty
            ><el-empty
              description="暂无客户订单，点击新建后从已完成报价中选择成交货品"
          /></template>
        </el-table>
        <p class="prototype-muted">
          {{
            page === "quotes"
              ? "报价完成后可分批成交；修改图纸或价格请新建修订，已成交订单保持原版本。"
              : "同一客户、币种可跨报价单选货；一条订单明细可分多批生产，检验放行后直接发货。展开订单查看各货品已发和待发数量。"
          }}
        </p>
      </el-card>
    </template>
    <QuoteEditor
      v-if="quoteVisible && !selectedAiTask"
      v-model="quoteVisible"
      :initial="selectedQuote"
      :state="state"
      :files="files"
      :role="actor"
      :read-only="
        readOnly ||
        !hasPerms(
          actor === 'engineering'
            ? 'mes:quotation:price'
            : 'mes:quotation:manage',
        )
      "
      :on-commit="commitQuote"
      :can-price="hasPerms('mes:quotation:price')"
      @update:model-value="
        (value) => {
          if (!value) closeEditor();
        }
      "
      @price="openQuote(selectedQuote, 'engineering')"
      @ai-detail="openAiDetail"
    />
    <AiQuoteReview
      v-if="quoteVisible && selectedAiTask && hasPerms('mes:quotation:price')"
      :task="selectedAiTask"
      :quote="selectedQuote"
      :can-edit="canReviewAi"
      @back="closeAiDetail"
      @open="openAiDetail"
    />
    <CustomerOrderDialog
      v-if="orderVisible"
      v-model="orderVisible"
      :state="state"
      :initial-quote-id="initialQuoteId"
      :on-confirm="confirmOrder"
      @update:model-value="
        (value) => {
          if (!value) closeEditor();
        }
      "
    />
    <ProductionDialogs
      v-model:release-visible="releaseVisible"
      :state="state"
      :order="selectedOrder"
      :files="files"
      :can-configure="false"
      :on-generate="generate"
      :on-configure="() => {}"
      :on-release="() => {}"
    />
  </div>
</template>

<style src="./prototype.css" />
<style scoped>
.sales-business-page {
  padding: 20px;
}

.sales-business-page > .el-alert {
  margin: 20px 0;
}
</style>
