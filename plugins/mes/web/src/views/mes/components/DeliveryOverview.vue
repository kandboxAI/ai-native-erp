<script setup lang="ts">
import type {
  DeliveryDocument,
  DeliveryKind,
} from "@plugins/mes/web/src/api/mesDelivery";
import { hasPerms } from "@/utils/auth";
import {
  deliveryCurrency,
  deliveryLabel,
  deliveryPriceLabel,
} from "./deliveryDocuments";

defineProps<{ document: DeliveryDocument; kind: DeliveryKind }>();
const emit = defineEmits<{ openStockOrder: [id: string] }>();
</script>

<template>
  <section class="delivery-overview">
    <h3 v-if="kind === 'shipments'">本次出货货品</h3>
    <el-descriptions v-else :column="2" border>
      <el-descriptions-item label="单号">{{
        document.reconciliation_no
      }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{
        deliveryLabel(document.status_code)
      }}</el-descriptions-item>
      <el-descriptions-item label="客户"
        >{{ document.customer_no_snapshot }} /
        {{ document.customer_name_snapshot }}</el-descriptions-item
      >
      <el-descriptions-item label="期间"
        >{{ document.period_start }} ~
        {{ document.period_end }}</el-descriptions-item
      >
    </el-descriptions>
    <el-table
      :data="document.lines"
      :max-height="kind === 'reconciliations' ? 440 : undefined"
      border
    >
      <el-table-column
        v-if="kind === 'reconciliations'"
        prop="shipment_no"
        label="出货单"
        min-width="155"
      />
      <el-table-column
        prop="work_order_no_snapshot"
        label="工单"
        min-width="190"
      />
      <el-table-column
        prop="product_item_name_snapshot"
        label="产品"
        min-width="210"
      />
      <el-table-column prop="quantity" label="数量" width="100" align="right" />
      <el-table-column prop="unit_code" label="单位" width="80" />
      <el-table-column
        prop="unit_price"
        :label="deliveryPriceLabel(document.order_currency_snapshot)"
        min-width="145"
        align="right"
      />
      <el-table-column
        v-if="kind === 'reconciliations'"
        prop="adjustment_amount"
        :label="`调整（${deliveryCurrency(document.order_currency_snapshot)}）`"
        min-width="120"
        align="right"
      />
      <el-table-column
        prop="amount"
        :label="`金额（${deliveryCurrency(document.order_currency_snapshot)}）`"
        min-width="130"
        align="right"
      />
      <el-table-column
        v-if="kind === 'reconciliations'"
        prop="adjustment_reason"
        label="调整原因"
        min-width="160"
      />
    </el-table>
    <p v-if="kind === 'reconciliations'">
      合计：{{ document.total_amount }}
      {{ deliveryCurrency(document.order_currency_snapshot) }}
    </p>
    <section
      v-if="kind === 'shipments' && document.fulfillment_mode_code === 'stock'"
      class="stock-orders"
    >
      <h3>关联出库单</h3>
      <p>待审批时先到「出库作业」审批，再回本单点击「完成出库」。</p>
      <el-table
        :data="document.stock_orders || []"
        empty-text="尚未生成出库单"
        border
      >
        <el-table-column prop="order_no" label="库存单号" min-width="175" />
        <el-table-column label="状态" min-width="110">
          <template #default="{ row }">{{
            deliveryLabel(row.status_code)
          }}</template>
        </el-table-column>
        <el-table-column
          v-if="hasPerms('inventory_outbound:detail')"
          label="操作"
          width="120"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="emit('openStockOrder', row.stock_order_id)"
              >查看库存单</el-button
            >
          </template>
        </el-table-column>
      </el-table>
    </section>
    <p v-if="document.note" class="delivery-note">
      <strong>说明：</strong>{{ document.note }}
    </p>
    <el-alert
      v-if="document.cancellation_reason"
      :title="'取消理由：' + document.cancellation_reason"
      type="warning"
      :closable="false"
    />
  </section>
</template>

<style scoped>
.delivery-overview h3 {
  margin: 0 0 14px;
}

.stock-orders {
  margin-top: 24px;
}

.stock-orders p,
.delivery-note {
  color: var(--el-text-color-secondary);
}

.delivery-note {
  margin: 16px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
