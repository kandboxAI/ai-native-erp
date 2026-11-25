<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import DeliveryDocuments from "../components/DeliveryDocuments.vue";

defineOptions({ name: "MesShipments" });
const route = useRoute();
const router = useRouter();
const salesOrderId = computed(() =>
  typeof route.query.sales_order_id === "string"
    ? route.query.sales_order_id
    : undefined,
);
const shipmentId = computed(() =>
  typeof route.query.shipment_id === "string"
    ? route.query.shipment_id
    : undefined,
);
const shipmentTab = computed(() =>
  route.query.tab === "documents" ? "documents" : "overview",
);
function openShipment(id: string, tab: "overview" | "documents") {
  router.push({
    path: route.path,
    query: {
      ...route.query,
      shipment_id: id,
      tab: tab === "documents" ? tab : undefined,
    },
  });
}
function closeShipment() {
  const query = { ...route.query };
  delete query.shipment_id;
  delete query.tab;
  router.push({ path: route.path, query });
}
</script>

<template>
  <div>
    <el-button
      v-if="salesOrderId && !shipmentId"
      link
      type="primary"
      class="clear-order"
      @click="router.replace({ path: route.path })"
      >查看全部出货单</el-button
    >
    <DeliveryDocuments
      :key="salesOrderId || 'shipments'"
      kind="shipments"
      :sales-order-id="salesOrderId"
      :shipment-id="shipmentId"
      :shipment-tab="shipmentTab"
      @open-shipment="openShipment"
      @close-shipment="closeShipment"
    />
  </div>
</template>

<style scoped>
.clear-order {
  margin: 12px 16px 0;
}
</style>
