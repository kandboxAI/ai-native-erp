<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, ref, watch } from "vue";
import {
  customers,
  dateAfter,
  lineAmount,
  type DemoState,
  type OrderCommand,
  type QuoteLine,
} from "./model";

const visible = defineModel<boolean>({ default: false });
const props = defineProps<{
  state: DemoState;
  initialQuoteId?: string;
  onConfirm: (command: OrderCommand) => void;
}>();
type Choice = OrderCommand["lines"][number] & {
  selected: boolean;
  quote_no: string;
  revision: number;
  source: QuoteLine;
};
const customer = ref("customer-a"),
  currency = ref("EUR"),
  po = ref(""),
  note = ref("");
const rows = ref<Choice[]>([]);
const confirming = ref(false);
function rebuild() {
  rows.value = props.state.quotes
    .filter(
      (quote) =>
        quote.customer_id === customer.value &&
        quote.currency === currency.value &&
        quote.status === "quoted" &&
        quote.is_current,
    )
    .flatMap((quote) =>
      quote.lines.map((line) => ({
        quote_id: quote.id,
        quote_line_id: line.id,
        quote_no: quote.quote_no,
        revision: quote.revision,
        source: line,
        selected: quote.id === props.initialQuoteId,
        quantity: line.quantity,
        unit_price: line.unit_price,
        due_date: dateAfter(line.lead_days || 14),
        is_price_confirmed: false,
      })),
    );
}
watch([customer, currency], rebuild);
watch(
  visible,
  (value) => {
    if (!value) return;
    confirming.value = false;
    const quote = props.state.quotes.find(
      (row) => row.id === props.initialQuoteId,
    );
    customer.value = quote?.customer_id || "customer-a";
    currency.value = quote?.currency || "EUR";
    po.value = note.value = "";
    rebuild();
  },
  { immediate: true },
);
const selected = computed(() => rows.value.filter((row) => row.selected));
const total = computed(() =>
  selected.value
    .reduce(
      (sum, row) => sum + lineAmount(row.quantity || 0, row.unit_price || 0),
      0,
    )
    .toFixed(2),
);
function priceChanged(row: Choice) {
  return (
    row.quantity !== row.source.quantity ||
    row.unit_price !== row.source.unit_price
  );
}
function confirm() {
  if (!visible.value || confirming.value) return;
  confirming.value = true;
  try {
    props.onConfirm({
      customer_id: customer.value,
      currency: currency.value,
      customer_po_no: po.value,
      note: note.value,
      lines: selected.value.map((row) => ({
        quote_id: row.quote_id,
        quote_line_id: row.quote_line_id,
        quantity: row.quantity,
        unit_price: row.unit_price,
        due_date: row.due_date,
        is_price_confirmed: row.is_price_confirmed,
      })),
    });
  } catch (cause) {
    confirming.value = false;
    actionMessage((cause as Error).message);
  }
}
</script>

<template>
  <section v-if="visible" class="sales-editor-page" aria-label="客户订单表单">
    <header class="prototype-heading">
      <div>
        <h2>新建客户订单</h2>
        <p>确认成交货品、数量和价格，可跨报价单选货。</p>
      </div>
      <el-button @click="visible = false">返回客户订单</el-button>
    </header>
    <div class="sales-prototype">
      <el-alert
        type="info"
        :closable="false"
        title="仅勾选客户本次购买的货品。同一客户、同一币种可跨报价单合并；未选货品保留在原报价中。"
      />
      <el-form label-position="top"
        ><el-row :gutter="16">
          <el-col :span="7"
            ><el-form-item label="客户"
              ><el-select
                v-model="customer"
                @change="
                  currency =
                    customers.find((row) => row.id === customer)?.currency ||
                    'EUR'
                "
                ><el-option
                  v-for="item in customers"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id" /></el-select></el-form-item
          ></el-col>
          <el-col :span="3"
            ><el-form-item label="币种"
              ><el-select v-model="currency"
                ><el-option
                  v-for="item in ['EUR', 'CNY', 'USD']"
                  :key="item"
                  :label="item"
                  :value="item" /></el-select></el-form-item
          ></el-col>
          <el-col :span="7"
            ><el-form-item label="客户采购单号（可选）"
              ><el-input
                v-model="po"
                maxlength="64"
                placeholder="客户本次确认的采购单号" /></el-form-item
          ></el-col>
          <el-col :span="7"
            ><el-form-item label="接单说明"
              ><el-input v-model="note" maxlength="1000" /></el-form-item
          ></el-col> </el-row
      ></el-form>
      <el-table
        :data="rows"
        row-key="quote_line_id"
        border
        max-height="440"
        class="prototype-table"
      >
        <el-table-column label="选购" width="60" fixed
          ><template #default="{ row }"
            ><el-checkbox
              v-model="row.selected"
              :aria-label="`选择 ${row.source.drawing_no}`" /></template
        ></el-table-column>
        <el-table-column label="来源报价 / 图纸" width="250" fixed
          ><template #default="{ row }"
            ><strong>{{ row.source.drawing_no }}</strong
            ><small
              >{{ row.quote_no }} · R{{ row.revision }} · 图纸
              {{ row.source.drawing_revision }}</small
            ><small>{{ row.source.description }}</small></template
          ></el-table-column
        >
        <el-table-column label="原报价数量 / 单价" width="145"
          ><template #default="{ row }"
            >{{ row.source.quantity }} {{ row.source.unit
            }}<small
              >{{ row.source.unit_price?.toFixed(2) }} {{ currency }} /
              {{ row.source.unit }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="本次购买数量" width="165"
          ><template #default="{ row }"
            ><el-input-number
              :key="`quantity-${row.selected}`"
              v-model="row.quantity"
              :disabled="!row.selected"
              :min="0.001"
              :max="1000000"
              :precision="3"
              controls-position="right"
              @change="row.is_price_confirmed = false" /></template
        ></el-table-column>
        <el-table-column :label="`成交单价（${currency}）`" width="165"
          ><template #default="{ row }"
            ><el-input-number
              :key="`price-${row.selected}`"
              v-model="row.unit_price"
              :disabled="!row.selected"
              :min="0"
              :max="1000000"
              :precision="2"
              controls-position="right"
              @change="row.is_price_confirmed = false" /></template
        ></el-table-column>
        <el-table-column label="确认交期" width="170"
          ><template #default="{ row }"
            ><el-date-picker
              v-model="row.due_date"
              :disabled="!row.selected"
              type="date"
              value-format="YYYY-MM-DD" /></template
        ></el-table-column>
        <el-table-column label="数量 / 价格变化确认" min-width="220"
          ><template #default="{ row }"
            ><el-checkbox
              v-if="priceChanged(row as Choice)"
              v-model="row.is_price_confirmed"
              :disabled="!row.selected"
              >已确认本次数量对应的成交价</el-checkbox
            ><span v-else class="prototype-muted"
              >沿用本次选定报价条件</span
            ></template
          ></el-table-column
        >
        <template #empty
          ><el-empty description="该客户、币种下暂无有效的已完成报价"
        /></template>
      </el-table>
      <p class="prototype-muted">
        报价数量是计价条件，购买数量可多可少；变化时需确认成交价格。不同报价来源分别保留明细，不自动合并同图号。
      </p>
    </div>
    <footer class="prototype-footer sales-page-footer">
      <span class="prototype-summary"
        >已选 {{ selected.length }} 项 · 本次金额 {{ total }}
        {{ currency }}</span
      ><el-button @click="visible = false">取消</el-button
      ><el-button
        type="primary"
        :disabled="!selected.length || confirming"
        @click="confirm"
        >确认客户订单</el-button
      >
    </footer>
  </section>
</template>
