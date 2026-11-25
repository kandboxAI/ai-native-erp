<template>
  <ReListPresentation>
  <OrderListPage form="lend" title="借用归还" />

  </ReListPresentation>
</template>

<script setup lang="ts">
/** 借出：库存状态由“可用”转为“借出”；归还时按借出明细生成归还单，恢复为“可用”。 */
import OrderListPage from "../components/OrderListPage.vue";

defineOptions({ name: "LogisticsMaterialLending" });
</script>
