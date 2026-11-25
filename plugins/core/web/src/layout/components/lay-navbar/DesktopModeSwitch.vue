<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { message } from "@/utils/message";
import {
  returnToDesktopManagement,
  continueDesktopAssistant,
  desktopAssistantPath
} from "@/utils/desktopAssistant";

const desktop = Boolean(window.erpDesktop);
const { locale } = useI18n();
const route = useRoute();
const router = useRouter();
const isAgentPage = computed(() => route.path === desktopAssistantPath);
const opening = ref(false);
const managementLabel = computed(() =>
  locale.value === "en" ? "Management" : "管理"
);
const agentLabel = computed(() => (locale.value === "en" ? "Agent" : "智能体"));
const switchLabel = computed(() =>
  locale.value === "en" ? "Page switch" : "页面切换"
);

async function showAgent() {
  if (opening.value) return;
  opening.value = true;
  try {
    await continueDesktopAssistant(router);
  } catch {
    message("智能体暂时无法打开，请稍后重试", { type: "error" });
  } finally {
    opening.value = false;
  }
}

async function showManagement() {
  if (opening.value) return;
  opening.value = true;
  try {
    await returnToDesktopManagement(router);
  } catch {
    message("无法返回管理页面，请重试", { type: "error" });
  } finally {
    opening.value = false;
  }
}
</script>

<template>
  <div
    v-if="desktop"
    class="desktop-mode-switch"
    role="group"
    :aria-label="switchLabel"
  >
    <button
      type="button"
      :class="{ 'desktop-mode-switch__active': !isAgentPage }"
      :aria-current="!isAgentPage ? 'page' : undefined"
      :disabled="opening"
      @click="showManagement"
    >
      {{ managementLabel }}
    </button>
    <button
      type="button"
      :class="{ 'desktop-mode-switch__active': isAgentPage }"
      :aria-current="isAgentPage ? 'page' : undefined"
      :disabled="opening"
      @click="showAgent"
    >
      {{ agentLabel }}
    </button>
  </div>
</template>

<style scoped>
.desktop-mode-switch {
  display: inline-flex;
  flex: none;
  gap: 2px;
  align-items: center;
  height: 34px;
  padding: 3px;
  white-space: nowrap;
  background: var(--el-fill-color-light, #f5f7fa);
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 10px;
}

.desktop-mode-switch button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  padding: 0 11px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular, #606266);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 7px;
}

.desktop-mode-switch button.desktop-mode-switch__active {
  color: var(--el-color-primary, #409eff);
  background: var(--el-bg-color, #fff);
  box-shadow: 0 1px 3px rgb(0 0 0 / 8%);
}

.desktop-mode-switch button:hover,
.desktop-mode-switch button:focus-visible {
  color: var(--el-color-primary, #409eff);
  background: var(--el-bg-color, #fff);
}

.desktop-mode-switch button:disabled {
  cursor: wait;
}
</style>
