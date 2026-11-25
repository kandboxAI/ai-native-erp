<template>
  <ReListPresentation>
  <OrderListPage form="transfer" title="调拨管理" />

  </ReListPresentation>
</template>

<script setup lang="ts">
/** 调拨：确认时来源仓库减少、目标仓库增加（可跨校区，物料档案不复制）。 */
import OrderListPage from "../components/OrderListPage.vue";

defineOptions({ name: "LogisticsMaterialTransfer" });
</script>
