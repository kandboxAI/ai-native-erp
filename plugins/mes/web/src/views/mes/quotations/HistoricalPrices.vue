<script setup lang="ts">
import { ref } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import ListPagination from "@/components/ListPagination/index.vue";
import { request, type QuoteLine } from "./api";
const props = defineProps<{
  currency: string;
  customerId: string;
  editable: boolean;
}>();
type History = {
  quotation_line_id: string;
  quote_no: string;
  revision: number;
  quoted_at: string;
  customer_name_snapshot: string;
  currency: string;
  drawing_no: string;
  drawing_revision: string;
  customer_material: string;
  quoted_material: string;
  quantity: string;
  unit_price: string;
  weight_kg: string | null;
  lead_days: number;
  quantity_tiers: { quantity: string; unit_price: string }[];
};
const visible = ref(false),
  keyword = ref(""),
  onlyCustomer = ref(true),
  error = ref(""),
  busy = ref(false),
  page = ref(1),
  total = ref(0),
  rows = ref<History[]>([]),
  target = ref<QuoteLine>();
let generation = 0;
async function search() {
  const token = ++generation;
  busy.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      drawing_no: keyword.value.trim(),
      page: String(page.value),
      page_size: "20",
    });
    if (onlyCustomer.value) params.set("customer_id", props.customerId);
    const result = await request<{ items: History[]; total: number }>(
      `/historical-prices?${params}`,
    );
    if (token === generation) {
      rows.value = result.items;
      total.value = result.total;
    }
  } catch (cause) {
    if (token === generation) error.value = (cause as Error).message;
  } finally {
    if (token === generation) busy.value = false;
  }
}
function open(line: QuoteLine) {
  target.value = line;
  keyword.value = line.drawing_no;
  page.value = 1;
  visible.value = true;
  void search();
}
async function apply(row: History) {
  const line = target.value;
  if (!props.editable || !line) return;
  if (row.currency !== props.currency) {
    ElMessage.warning("历史报价币种不同，请按本次币种人工核算，不直接带入单价");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `历史版本 ${row.drawing_revision || "未填"}、数量 ${row.quantity}、材料 ${row.quoted_material}；本次版本 ${line.drawing_revision || "未填"}、数量 ${line.quantity}、客户材料 ${line.customer_material}。确认将历史材料、重量和主数量单价作为本次参考？`,
      "带入历史报价",
      { type: "warning" },
    );
  } catch {
    return;
  }
  line.quoted_material = row.quoted_material;
  line.weight_kg = row.weight_kg === null ? null : Number(row.weight_kg);
  line.unit_price = Number(row.unit_price);
  line.engineering_note =
    `${line.engineering_note || ""}\n参考报价 ${row.quote_no} R${row.revision}；图号 ${row.drawing_no} / ${row.drawing_revision}；历史数量 ${row.quantity}，单价 ${row.unit_price} ${row.currency}。`.trim();
  line.adopted_cnc_quote_id = undefined;
  visible.value = false;
  ElMessage.success("已带入参考信息，请核对后保存本次工程报价");
}
defineExpose({ open });
</script>
<template>
  <el-dialog
    v-model="visible"
    title="历史报价参考"
    width="90%"
    @closed="generation++"
  >
    <el-form
      class="erp-query-form"
      inline
      @submit.prevent="
        page = 1;
        search();
      "
      ><el-form-item label="图号"
        ><el-input
          v-model="keyword"
          clearable
          placeholder="输入完整图号" /></el-form-item
      ><el-form-item
        ><el-checkbox
          v-model="onlyCustomer"
          @change="
            page = 1;
            search();
          "
          >仅当前客户</el-checkbox
        ></el-form-item
      ><el-form-item
        ><el-button type="primary" native-type="submit"
          >查询</el-button
        ></el-form-item
      ></el-form
    >
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-table v-loading="busy" :data="rows" border max-height="500"
      ><el-table-column label="报价来源" min-width="200"
        ><template #default="{ row }"
          >{{ row.quote_no }} · R{{ row.revision }}</template
        ></el-table-column
      ><el-table-column
        prop="quoted_at"
        label="报价时间"
        min-width="170"
      /><el-table-column
        prop="customer_name_snapshot"
        label="客户"
        min-width="150"
      /><el-table-column
        prop="drawing_revision"
        label="图纸版本"
        width="100"
      /><el-table-column
        prop="quoted_material"
        label="报价材料"
        min-width="150"
      /><el-table-column
        prop="quantity"
        label="主数量"
        width="100"
      /><el-table-column label="主数量单价" min-width="130"
        ><template #default="{ row }"
          >{{ row.unit_price }} {{ row.currency }}</template
        ></el-table-column
      ><el-table-column label="其他数量档" min-width="170"
        ><template #default="{ row }"
          ><div v-for="tier in row.quantity_tiers" :key="tier.quantity">
            {{ tier.quantity }}：{{ tier.unit_price }} {{ row.currency }}
          </div></template
        ></el-table-column
      ><el-table-column v-if="editable" label="操作" width="120" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="apply(row as History)"
            >带入参考</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <ListPagination
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="search"
    />
  </el-dialog>
</template>
