<template>
  <ReListPresentation>
  <OrderListPage
    form="inbound"
    title="入库管理"
    form-route="/inventory/inbound/form"
  />

  </ReListPresentation>
</template>

<script setup lang="ts">
/** 入库：单据类型为“入库”方向（采购入库、其他入库等，类型从后端读取）的库存单据。 */
import OrderListPage from "../components/OrderListPage.vue";

defineOptions({ name: "LogisticsMaterialInbound" });
</script>
