<template>
  <ReListPresentation>
  <OrderListPage form="damage" title="报损管理" />

  </ReListPresentation>
</template>

<script setup lang="ts">
/** 报损：出库方向的库存单据，需填写原因与处理方式，按类型配置走审批。 */
import OrderListPage from "../components/OrderListPage.vue";

defineOptions({ name: "LogisticsMaterialDamage" });
</script>
