<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { orderRequest, type CustomerOrder } from "./api";
import {
  DISCOUNTS,
  applyDiscount,
  discountPrice,
  discountValue,
} from "./pricing";
const props = defineProps<{ order: CustomerOrder }>();
const emit = defineEmits<{ saved: [order: CustomerOrder]; cancel: [] }>();
const customerPo = ref(props.order.customer_po_no),
  note = ref(props.order.note),
  busy = ref(false);
const rows = ref(
  props.order.lines.map((line) => ({
    ...line,
    quantity: Number(line.quantity),
    unit_price: Number(line.unit_price),
    discount_rate: discountValue(line.discount_rate),
    adjustment_reason: "",
    is_price_confirmed: false,
  })),
);
type EditRow = (typeof rows.value)[number];
async function save() {
  if (busy.value) return;
  busy.value = true;
  try {
    if (
      rows.value.some(
        (row) =>
          row.unit_price <
          discountPrice(row.original_unit_price_snapshot, "0.7"),
      )
    )
      throw Error("成交单价不能低于所选报价的七折");
    await ElMessageBox.confirm(
      "确认修改当前订单的成交信息？原始报价及修改记录会保留。",
      "修改成交信息",
      { type: "warning" },
    );
    const result = await orderRequest<CustomerOrder>(
      `/${props.order.id}`,
      "put",
      {
        version_no: props.order.version_no,
        customer_po_no: customerPo.value,
        note: note.value,
        lines: rows.value.map((line) => ({
          id: line.id,
          quantity: line.quantity,
          unit_price: line.unit_price,
          discount_rate:
            line.discount_rate === "manual" ? null : line.discount_rate,
          due_date: line.due_date,
          adjustment_reason: line.adjustment_reason,
          is_price_confirmed: line.is_price_confirmed,
        })),
      },
    );
    emit("saved", result);
    ElMessage.success("订单已更新");
  } catch (cause) {
    if (cause !== "cancel" && cause !== "close")
      actionMessage((cause as Error).message);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section v-loading="busy" class="sales-order-edit">
    <h3>修改成交信息</h3>
    <el-form inline
      ><el-form-item label="客户采购单号"
        ><el-input v-model="customerPo" maxlength="64" /></el-form-item
      ><el-form-item label="说明"
        ><el-input v-model="note" maxlength="1000" /></el-form-item
    ></el-form>
    <el-table :data="rows" border
      ><el-table-column
        prop="drawing_no_snapshot"
        label="图号"
        min-width="170"
      /><el-table-column
        prop="original_unit_price_snapshot"
        label="原始报价单价"
        width="130"
      />
      <el-table-column label="成交数量" min-width="170"
        ><template #default="{ row }"
          ><el-input-number
            v-model="row.quantity"
            :min="0.001"
            :max="1000000"
            :precision="3"
            controls-position="right"
            @change="row.is_price_confirmed = false" /></template
      ></el-table-column>
      <el-table-column label="成交折扣" width="135"
        ><template #default="{ row }"
          ><el-select
            v-model="row.discount_rate"
            @change="
              applyDiscount(row as EditRow, row.original_unit_price_snapshot)
            "
          >
            <el-option
              v-for="option in DISCOUNTS"
              :key="option.value"
              :value="option.value"
              :label="option.label"
            /> </el-select></template
      ></el-table-column>
      <el-table-column :label="`成交单价（${order.currency}）`" min-width="180"
        ><template #default="{ row }"
          ><el-input-number
            v-model="row.unit_price"
            :min="discountPrice(row.original_unit_price_snapshot, '0.7')"
            :max="100000000"
            :precision="2"
            controls-position="right"
            @change="
              row.discount_rate = 'manual';
              row.is_price_confirmed = false;
            " /></template
      ></el-table-column>
      <el-table-column label="交付日期" min-width="170"
        ><template #default="{ row }"
          ><el-date-picker
            v-model="row.due_date"
            value-format="YYYY-MM-DD"
            style="width: 100%" /></template
      ></el-table-column>
      <el-table-column label="调整原因 / 确认" min-width="240"
        ><template #default="{ row }"
          ><el-input
            v-model="row.adjustment_reason"
            maxlength="1000"
            placeholder="数量或价格调整时必填"
          /><el-checkbox v-model="row.is_price_confirmed"
            >确认修改后的成交价格</el-checkbox
          ></template
        ></el-table-column
      >
    </el-table>
    <footer class="erp-form-actions">
      <div class="erp-form-actions__primary">
        <el-button :disabled="busy" @click="emit('cancel')">取消</el-button
        ><el-button type="primary" :loading="busy" @click="save"
          >保存修改</el-button
        >
      </div>
    </footer>
  </section>
</template>
