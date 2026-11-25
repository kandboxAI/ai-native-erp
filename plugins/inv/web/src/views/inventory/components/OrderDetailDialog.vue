<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="1000px"
    destroy-on-close
    align-center
    @open="load"
  >
    <div v-loading="loading">
      <template v-if="order">
        <el-descriptions :column="3" border size="small" class="mb-3">
          <el-descriptions-item label="单号">{{
            order.order_no
          }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{
            dash(order.order_type_name)
          }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(order.status_code)" size="small">{{
              statusLabel(order.status_code)
            }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="组织">{{
            dash(order.org_name)
          }}</el-descriptions-item>
          <el-descriptions-item label="业务日期">{{
            dash(order.business_date)
          }}</el-descriptions-item>
          <el-descriptions-item label="金额合计">{{
            formatMoney(order.total_amount)
          }}</el-descriptions-item>
          <el-descriptions-item
            v-if="order.from_warehouse"
            label="来源仓库"
            :span="order.to_warehouse ? 1 : 3"
            >{{ order.from_warehouse.label }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="order.to_warehouse"
            label="目标仓库"
            :span="order.from_warehouse ? 2 : 3"
            >{{ order.to_warehouse.label }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="order.counterparty_name_snapshot"
            label="往来方"
            >{{ order.counterparty_name_snapshot }}</el-descriptions-item
          >
          <el-descriptions-item v-if="order.department_name" label="领用部门">{{
            order.department_name
          }}</el-descriptions-item>
          <el-descriptions-item
            v-if="order.expected_return_date"
            label="预计归还"
            >{{ order.expected_return_date }}</el-descriptions-item
          >
          <el-descriptions-item
            v-if="order.handling_method_code"
            label="处理方式"
            >{{
              label("inv_handling_method", order.handling_method_code)
            }}</el-descriptions-item
          >
          <el-descriptions-item v-if="order.purpose" label="用途" :span="3">{{
            order.purpose
          }}</el-descriptions-item>
          <el-descriptions-item v-if="order.reason" label="原因" :span="3">{{
            order.reason
          }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{
            dash(order.created_by_name)
          }}</el-descriptions-item>
          <el-descriptions-item label="确认人">{{
            dash(order.confirmed_by_name)
          }}</el-descriptions-item>
          <el-descriptions-item label="确认时间">{{
            formatDateTime(order.confirmed_at, "—")
          }}</el-descriptions-item>
          <el-descriptions-item
            v-if="order.status_code === 'voided'"
            label="作废原因"
            :span="3"
            >{{ dash(order.void_reason) }}</el-descriptions-item
          >
          <el-descriptions-item v-if="order.remark" label="备注" :span="3">{{
            order.remark
          }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">明细</div>
        <ReListTable list-key="OrderDetailDialog-0" :list-controls="false" :list-refresh="load"
          :data="order.lines || []"
          border
          size="small"
          max-height="360"
          row-key="id"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="tx-box">
                <div v-if="!row.transactions?.length" class="muted">未记账</div>
                <ReListTable list-key="OrderDetailDialog-1" :list-controls="false" v-else :data="row.transactions" size="small">
                  <el-table-column
                    prop="transaction_no"
                    label="流水号"
                    min-width="180"
                  />
                  <el-table-column label="方向" width="80">
                    <template #default="{ row: tx }">{{
                      label("inv_transaction_type", tx.transaction_type_code)
                    }}</template>
                  </el-table-column>
                  <el-table-column prop="lot_no" label="批次" width="120" />
                  <el-table-column label="状态变化" width="160">
                    <template #default="{ row: tx }">
                      {{
                        label("inv_stock_status", tx.from_stock_status_code) ||
                        "—"
                      }}
                      →
                      {{
                        label("inv_stock_status", tx.to_stock_status_code) ||
                        "—"
                      }}
                    </template>
                  </el-table-column>
                  <el-table-column label="数量" width="90" align="right">
                    <template #default="{ row: tx }">{{
                      formatQuantity(tx.quantity)
                    }}</template>
                  </el-table-column>
                  <el-table-column label="时间" min-width="150">
                    <template #default="{ row: tx }">{{
                      formatDateTime(tx.occurred_at)
                    }}</template>
                  </el-table-column>
                </ReListTable>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="line_no" label="行" width="50" />
          <el-table-column
            prop="item_no"
            label="物料编号"
            width="130"
            show-overflow-tooltip
          />
          <el-table-column
            prop="item_name"
            label="物料名称"
            min-width="130"
            show-overflow-tooltip
          />
          <el-table-column
            prop="specification"
            label="规格"
            width="110"
            show-overflow-tooltip
          />
          <el-table-column prop="unit_code" label="单位" width="60">
            <template #default="{ row }">{{
              unitLabel(row.unit_code)
            }}</template>
          </el-table-column>
          <el-table-column label="关联资产" min-width="150"><template #default="{ row }">
            <span v-if="row.tracking?.asset?.registration_summary">已登记 {{ formatQuantity(row.tracking.asset.registration_summary.registered_quantity) }} / {{ formatQuantity(row.tracking.asset.registration_summary.quantity) }}</span>
            <span v-else-if="!row.tracking?.asset?.selections?.length">—</span>
            <div v-for="selection in row.tracking?.asset?.selections || []" :key="selection.binding_id">{{ selection.asset_label || '实物资产' }} × {{ formatQuantity(selection.quantity) }}</div>
          </template></el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" align="right">
            <template #default="{ row }">{{
              formatQuantity(row.quantity)
            }}</template>
          </el-table-column>
          <el-table-column prop="counted_quantity"
            v-if="order.direction_code === 'adjust'"
            label="实盘"
            width="80"
            align="right"
          >
            <template #default="{ row }">{{
              formatQuantity(row.counted_quantity)
            }}</template>
          </el-table-column>
          <el-table-column prop="unit_price"
            v-if="order.direction_code === 'in'"
            label="单价"
            width="90"
            align="right"
          >
            <template #default="{ row }">{{
              formatMoney(row.unit_price)
            }}</template>
          </el-table-column>
          <el-table-column prop="amount"
            v-if="order.direction_code === 'in'"
            label="金额"
            width="100"
            align="right"
          >
            <template #default="{ row }">{{
              formatMoney(row.amount)
            }}</template>
          </el-table-column>
          <el-table-column
            prop="lot_no"
            label="批次"
            width="110"
            show-overflow-tooltip
          />
          <el-table-column prop="returned_quantity"
            v-if="order.form === 'lend'"
            label="已归还"
            width="80"
            align="right"
          >
            <template #default="{ row }">{{
              formatQuantity(row.returned_quantity)
            }}</template>
          </el-table-column>
          <el-table-column
            prop="remark"
            label="备注"
            min-width="100"
            show-overflow-tooltip
          />
        </ReListTable>

        <template v-if="order.related_orders?.length">
          <div class="section-title">关联单据</div>
          <ReListTable list-key="OrderDetailDialog-2" :list-controls="false" :list-refresh="load" :data="order.related_orders" border size="small">
            <el-table-column prop="order_no" label="单号" min-width="180" />
            <el-table-column prop="is_reversal" label="类别" width="100">
              <template #default="{ row }">{{
                row.is_reversal ? "冲销" : "归还"
              }}</template>
            </el-table-column>
            <el-table-column
              prop="business_date"
              label="业务日期"
              width="120"
            />
            <el-table-column prop="status_code" label="状态" width="100">
              <template #default="{ row }">{{
                statusLabel(row.status_code)
              }}</template>
            </el-table-column>
          </ReListTable>
        </template>
      </template>
    </div>
    <template #footer>
      <el-button data-action="neutral" type="primary" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  formatMoney,
  formatQuantity,
  getStockOrder,
  type StockOrder
} from "@plugins/inv/web/src/api/inventoryManagement";
import { dash, statusLabel, statusTagType, useInventoryMeta } from "./common";

const props = defineProps<{ modelValue: boolean; orderId?: string | null }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const visible = computed({
  get: () => props.modelValue,
  set: v => emit("update:modelValue", v)
});

const { loadMeta, label, unitLabel } = useInventoryMeta();
const loading = ref(false);
const order = ref<StockOrder | null>(null);
const title = computed(() =>
  order.value
    ? `${order.value.order_type_name ?? "库存单据"}详情`
    : "库存单据详情"
);

async function load() {
  if (!props.orderId) return;
  loading.value = true;
  order.value = null;
  try {
    await loadMeta();
    const res = await getStockOrder(props.orderId);
    if (res.code !== 0) throw new Error(res.message);
    order.value = res.data;
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载详情失败"));
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped lang="scss">
.mb-3 {
  margin-bottom: 12px;
}

.section-title {
  margin: 12px 0 8px;
  font-weight: 600;
  color: #334155;
}

.tx-box {
  padding: 4px 16px 8px 48px;
}

.muted {
  color: #94a3b8;
}
</style>
