<template>
  <div class="sys-module sys-page inv-order-form-page">
    <el-card shadow="never" class="sys-card">
      <template #header>
        <div class="page-header">
          <div class="page-title">
            {{ orderId ? "编辑出库单" : "新建出库单" }}
          </div>
        </div>
      </template>
      <OrderForm
        :key="formKey"
        form="outbound"
        :order-id="orderId"
        @saved="back"
        @cancel="back"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import OrderForm from "../components/OrderForm.vue";

defineOptions({ name: "OutboundListForm" });

const route = useRoute();
const router = useRouter();
const orderId = computed(() =>
  typeof route.query.id === "string" ? route.query.id : null
);
// 页面开启了 keepAlive：每次进入都重新加载表单
const formKey = ref(0);
onActivated(() => {
  formKey.value += 1;
});

function back() {
  router.push({ path: "/inventory/outbound" });
}
</script>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>
