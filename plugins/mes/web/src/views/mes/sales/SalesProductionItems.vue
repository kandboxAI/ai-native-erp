<script setup lang="ts">
import { hasPerms } from "@/utils/auth";
import {
  quantityUnits,
  workOrderLabels,
  type DemoState,
  type WorkOrder,
} from "./model";
import { shippedQuantity } from "./shipmentModel";

defineProps<{
  items: WorkOrder[];
  state: DemoState;
  onOpen: (id: string) => void;
  onCancel: (id: string) => void;
  onShip: (id: string) => void;
}>();
</script>
<template>
  <el-table :data="items" row-key="id" stripe class="sales-production-items">
    <el-table-column label="货品明细编号" min-width="175">
      <template #default="{ row }"
        ><el-button link type="primary" @click="onOpen(row.id)">{{
          row.work_order_no
        }}</el-button></template
      >
    </el-table-column>
    <el-table-column label="图号 / 货品" min-width="230"
      ><template #default="{ row }">
        <strong>{{ row.snapshot.drawing_no }}</strong
        ><small
          >{{ row.snapshot.description }} · 图纸
          {{ row.snapshot.drawing_revision }}</small
        >
      </template></el-table-column
    >
    <el-table-column label="本次数量" width="130"
      ><template #default="{ row }"
        >{{ row.quantity }} {{ row.snapshot.unit }}</template
      ></el-table-column
    >
    <el-table-column label="工艺路线" min-width="220"
      ><template #default="{ row }">{{
        row.operations
          .map((operation) => operation.operation_name)
          .join(" → ") || "尚未配置工序"
      }}</template></el-table-column
    >
    <el-table-column label="货品状态" width="135"
      ><template #default="{ row }"
        ><el-tag
          :type="
            row.status === 'completed'
              ? 'success'
              : row.status === 'cancelled'
                ? 'danger'
                : 'info'
          "
          >{{ workOrderLabels[row.status as WorkOrder["status"]] }}</el-tag
        ></template
      ></el-table-column
    >
    <el-table-column label="交付进度" width="150"
      ><template #default="{ row }">
        <span
          >已发 {{ shippedQuantity(state, row.id) }}
          {{ row.snapshot.unit }}</span
        >
        <small>{{
          row.status === "completed"
            ? `可发 ${Math.max(0, quantityUnits(row.quantity) - quantityUnits(shippedQuantity(state, row.id))) / 1000} ${row.snapshot.unit}`
            : "检验放行后可发货"
        }}</small>
      </template></el-table-column
    >
    <el-table-column label="交期" prop="due_date" width="125" />
    <el-table-column label="操作" width="210" fixed="right"
      ><template #default="{ row }">
        <el-button link type="primary" @click="onOpen(row.id)">{{
          hasPerms("mes:work_order:manage") &&
          ["unconfigured", "configured"].includes(row.status)
            ? "配置工序"
            : "查看货品"
        }}</el-button>
        <el-button
          v-if="
            hasPerms('mes:work_order:manage') &&
            ['unconfigured', 'configured', 'released'].includes(row.status)
          "
          link
          type="danger"
          @click="onCancel(row.id)"
          >取消货品</el-button
        >
        <el-button
          v-if="
            row.status === 'completed' &&
            shippedQuantity(state, row.id) < row.quantity &&
            hasPerms('mes:shipment:list') &&
            hasPerms('mes:shipment:manage')
          "
          link
          type="primary"
          @click="onShip(row.id)"
          >单项发货</el-button
        >
      </template></el-table-column
    >
    <template #empty><el-empty description="本张工单没有货品明细" /></template>
  </el-table>
</template>
