<template>
  <div class="sys-module sys-page inv-order-form-page inbound-order-page">
    <el-card shadow="never" class="sys-card">
      <template #header>
        <div class="page-header">
          <div class="page-title">
            {{ orderId ? "编辑入库单" : "新建入库单" }}
          </div>
          <p class="page-description">
            填写收货信息与物料明细，确认后更新库存，资产物料同步登记。
          </p>
        </div>
      </template>
      <OrderForm
        :key="formKey"
        form="inbound"
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

defineOptions({ name: "InboundListForm" });
const props = withDefaults(defineProps<{ returnPath?: string }>(), {
  returnPath: "/inventory/inbound"
});

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
  router.push({ path: props.returnPath });
}
</script>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>

<style scoped lang="scss">
.inbound-order-page {
  :deep(.sys-card.el-card) {
    border-radius: 8px;
  }
  :deep(.el-card__header) {
    padding: 20px 20px 16px;
  }
  :deep(.el-card__body) {
    padding: 0 20px 20px;
  }
  .page-header {
    display: block;
  }
  .page-title {
    font-size: 22px;
    line-height: 30px;
  }
  .page-description {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 20px;
    color: var(--el-text-color-secondary);
  }
}
@media (width <= 600px) {
  .inbound-order-page {
    :deep(.el-card__header) {
      padding: 16px 12px 12px;
    }
    :deep(.el-card__body) {
      padding: 0 12px 12px;
    }
  }
}
</style>
