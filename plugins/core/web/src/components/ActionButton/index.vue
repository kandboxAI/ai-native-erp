<script setup lang="ts">
/** 统一工具栏动作配色；原生 Element Plus 点击、loading、disabled 等属性透传。 */
defineOptions({ name: "ActionButton", inheritAttrs: false });
defineProps<{ intent: "create" | "import" | "upload" | "download" }>();
</script>

<template>
  <el-button
    v-bind="$attrs"
    type="primary"
    class="erp-action-button"
    :data-intent="intent"
  >
    <template v-if="$slots.icon" #icon><slot name="icon" /></template>
    <template v-if="$slots.loading" #loading><slot name="loading" /></template>
    <slot />
  </el-button>
</template>

<style scoped>
.erp-action-button.el-button {
  --erp-action-color: var(--el-color-primary);
  --el-button-text-color: #fff;
  --el-button-bg-color: var(--erp-action-color);
  --el-button-border-color: var(--erp-action-color);
  --el-button-hover-text-color: #fff;
  --el-button-hover-bg-color: color-mix(
    in srgb,
    var(--erp-action-color),
    #000 10%
  );
  --el-button-hover-border-color: var(--el-button-hover-bg-color);
  --el-button-active-text-color: #fff;
  --el-button-active-bg-color: color-mix(
    in srgb,
    var(--erp-action-color),
    #000 18%
  );
  --el-button-active-border-color: var(--el-button-active-bg-color);
  --el-button-disabled-text-color: var(--el-text-color-disabled);
  --el-button-disabled-bg-color: color-mix(
    in srgb,
    var(--erp-action-color) 20%,
    var(--el-bg-color)
  );
  --el-button-disabled-border-color: var(--el-button-disabled-bg-color);
}

.erp-action-button[data-intent="download"] {
  --erp-action-color: #52647c;
}

.erp-action-button[data-intent="import"] {
  --erp-action-color: #18795e;
}

.erp-action-button[data-intent="upload"] {
  --erp-action-color: #6750a4;
}

.erp-action-button:focus-visible {
  outline: 2px solid var(--erp-action-color);
  outline-offset: 3px;
}
</style>
