<script setup lang="ts">
import InventoryQuery from "@plugins/inv/web/src/views/inventory/inventory-query/index.vue";
defineOptions({ name: "MesWarehouseMovements" });
</script>
<template>
  <InventoryQuery initial-tab="transaction" warehouse-scope-key="mes" />
</template>
