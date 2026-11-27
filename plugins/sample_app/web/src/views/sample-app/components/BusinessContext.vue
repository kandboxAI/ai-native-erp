<script setup lang="ts">
import { onMounted, provide } from "vue";
import { ElMessage } from "element-plus";
import { createSampleApi } from "@plugins/sample_app/web/src/api/sample_app";
import {
  businessContextKey,
  createBusinessContext,
} from "@plugins/sample_app/web/src/api/sample_appContext";
const context = createBusinessContext();
provide(businessContextKey, context);
onMounted(async () => {
  try {
    const response = await createSampleApi().listOrganizations();
    if (response.code !== 0) throw new Error(response.message);
    context.organizations.value = response.data;
    if (response.data.length === 1)
      context.operationOrg.value = response.data[0].id;
  } catch {
    ElMessage.error("组织选项加载失败，请检查权限后刷新页面");
  }
});
</script>
<template>
  <section class="sample-business-page"><slot /></section>
</template>
<style>
.sample-business-page {
  margin: 16px;
  min-width: 0;
}
.sample-business-page .sample-page {
  min-width: 0;
}
.sample-business-page .sample-page > .el-tabs {
  padding: 0 20px 20px;
  background: var(--el-bg-color);
}
.sample-business-page .sample-page > p {
  padding: 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.sample-business-page .parameter-card {
  margin-bottom: 20px;
  border: none;
  border-radius: 0;
}
.sample-business-page .cash-summary {
  margin-bottom: 20px;
  row-gap: 12px;
}
.sample-business-page .cash-summary .el-card {
  background: var(--el-fill-color-lighter);
  border: none;
}
.sample-business-page .business-entry-form {
  padding: 0 20px;
  margin: 0 0 20px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
.sample-business-page .business-entry-form .el-form {
  padding-top: 12px;
}
.sample-business-page .business-entry-form .el-form-item {
  margin-bottom: 18px;
}
.sample-business-page .el-dialog .el-select,
.sample-business-page .el-dialog .el-date-editor,
.sample-business-page .el-dialog .el-input-number {
  width: 100%;
}
.sample-business-page .el-dialog {
  max-width: calc(100vw - 32px);
}
.sample-business-page label.cursor-pointer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  padding: 8px 15px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  color: var(--el-text-color-regular);
  background: var(--el-bg-color);
  line-height: 1;
}
.sample-business-page label.cursor-pointer:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}
@media (max-width: 640px) {
  .sample-business-page {
    margin: 10px;
  }
  .sample-business-page .business-context {
    padding: 16px;
  }
}
</style>
