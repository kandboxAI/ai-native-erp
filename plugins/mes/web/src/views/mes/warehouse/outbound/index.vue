<script setup lang="ts">
import OrderListPage from "@plugins/inv/web/src/views/inventory/components/OrderListPage.vue";
defineOptions({ name: "MesWarehouseOutbound" });
</script>
<template>
  <OrderListPage
    form="outbound"
    title="出库作业"
    description="普通出库不计工单消耗；生产领料请到生产消耗，可归还刀具请用借出归还。"
    warehouse-scope-key="mes"
    :create-type-nos="['MES_RAW_OUT', 'MES_TOOL_OUT']"
  />
</template>
