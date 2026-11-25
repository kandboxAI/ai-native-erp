<script setup lang="ts">
import OrderListPage from "@plugins/inv/web/src/views/inventory/components/OrderListPage.vue";
defineOptions({ name: "MesWarehouseInbound" });
</script>
<template>
  <OrderListPage
    form="inbound"
    title="入库作业"
    description="原料和刀具在此入库；工单成品请到生产消耗办理成品入库。"
    warehouse-scope-key="mes"
    :create-type-nos="['MES_RAW_IN', 'MES_TOOL_IN']"
  />
</template>
