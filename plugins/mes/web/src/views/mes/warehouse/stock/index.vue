<script setup lang="ts">
import InventoryQuery from "@plugins/inv/web/src/views/inventory/inventory-query/index.vue";
defineOptions({ name: "MesWarehouseStock" });
</script>
<template><InventoryQuery warehouse-scope-key="mes" /></template>
