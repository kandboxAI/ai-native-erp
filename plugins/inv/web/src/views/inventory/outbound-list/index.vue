<template>
  <ReListPresentation>
  <OrderListPage
    form="outbound"
    title="出库管理"
    form-route="/inventory/outbound/form"
  />

  </ReListPresentation>
</template>

<script setup lang="ts">
/** 出库：领用出库、其他出库等（类型从后端读取）的库存单据。报损、调拨各有自己的单据类型与页面。 */
import OrderListPage from "../components/OrderListPage.vue";

defineOptions({ name: "LogisticsMaterialOutbound" });
</script>
