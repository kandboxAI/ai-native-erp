<script setup lang="ts">
import { computed } from "vue";
import { Document } from "@element-plus/icons-vue";
import type { WorkflowBusinessContractPreview } from "@/api/workflowTask";

const props = defineProps<{
  contract?: WorkflowBusinessContractPreview | null;
}>();

const title = computed(() => props.contract?.title?.trim() || "合同预览");
const previewUrl = computed(() => props.contract?.preview_url?.trim() || "");
const openUrl = computed(
  () => props.contract?.open_url?.trim() || previewUrl.value || ""
);
const showPdfFrame = computed(
  () => props.contract?.mode === "pdf" && !!previewUrl.value
);
const showExternalHint = computed(
  () => props.contract?.mode === "external" && !!openUrl.value
);
const attachments = computed(() => props.contract?.attachments ?? []);

function openContract() {
  if (!openUrl.value) return;
  window.open(openUrl.value, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <div v-if="contract" class="workflow-contract-preview">
    <div class="workflow-contract-preview-head">
      <div class="workflow-contract-preview-title">{{ title }}</div>
      <el-button data-action="view" v-if="openUrl" link type="primary" @click="openContract">
        在新窗口打开
      </el-button>
    </div>
    <div v-if="showPdfFrame" class="workflow-contract-preview-box">
      <iframe
        :src="`${previewUrl}#toolbar=1&navpanes=0`"
        class="workflow-contract-preview-frame"
        title="合同 PDF 预览"
      />
    </div>
    <div v-else-if="showExternalHint" class="workflow-contract-external">
      <el-icon class="workflow-contract-external-icon"><Document /></el-icon>
      <p>
        法大大合同页不支持在系统内嵌预览，请点击上方「在新窗口打开」查看 PDF。
      </p>
      <el-button data-action="view" type="primary" @click="openContract">查看合同 PDF</el-button>
    </div>
    <div v-else-if="attachments.length" class="workflow-contract-attachments">
      <el-link
        data-action="primary"
        v-for="item in attachments"
        :key="item.url"
        :href="item.url"
        target="_blank"
        type="primary"
      >
        {{ item.name || "查看合同附件" }}
      </el-link>
    </div>
    <div v-else-if="openUrl" class="workflow-contract-open">
      <el-button data-action="view" type="primary" @click="openContract">查看合同</el-button>
    </div>
    <div v-else class="workflow-contract-empty">暂无合同预览</div>
  </div>
</template>

<style lang="scss" scoped>
.workflow-contract-preview-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.workflow-contract-preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.workflow-contract-preview-box {
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.workflow-contract-preview-frame {
  display: block;
  width: 100%;
  height: 420px;
  border: 0;
}

.workflow-contract-external {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  padding: 28px 16px;
  color: var(--el-text-color-secondary);
  text-align: center;
  background: var(--el-fill-color-lighter);
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
}

.workflow-contract-external-icon {
  font-size: 32px;
  color: var(--el-color-primary);
}

.workflow-contract-external p {
  max-width: 420px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.workflow-contract-attachments,
.workflow-contract-open {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workflow-contract-empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
