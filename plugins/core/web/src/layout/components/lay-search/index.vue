<script setup lang="ts">
import { useBoolean } from "../../hooks/useBoolean";
import SearchModal from "./components/SearchModal.vue";

const { bool: show, setTrue } = useBoolean();
function openCommandPalette() {
  setTrue();
}
</script>

<template>
  <div class="header-search-entry">
    <button
      type="button"
      class="command-entry navbar-bg-hover"
      aria-label="打开菜单命令面板"
      aria-haspopup="dialog"
      @click="openCommandPalette"
    >
      <IconifyIconOffline icon="ri/search-line" class="command-entry__icon" />
      <span class="command-entry__label">搜索菜单或询问 AI</span>
      <kbd>Ctrl K</kbd>
      <span class="command-entry__separator">/</span>
      <kbd>⌘ K</kbd>
    </button>
    <SearchModal v-model:value="show" />
  </div>
</template>

<style lang="scss" scoped>
// PC 总览已有大搜索框时隐藏顶部入口；保留面板挂载，继续响应 Ctrl/⌘ + K。
:global(
  .app-wrapper:not(.mobile):has(.personal-workbench .overview-content)
    .header-search-entry
) {
  display: none;
}

.command-entry {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  width: 248px;
  height: 32px;
  padding: 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: left;
  cursor: pointer;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;

  &:hover,
  &:focus-visible {
    outline: none;
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 0 0 2px var(--el-color-primary-light-9);
  }

  &__icon {
    flex: 0 0 auto;
    font-size: 15px;
    color: var(--el-color-primary);
  }

  &__label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  kbd {
    flex: 0 0 auto;
    padding: 1px 5px;
    font-family: inherit;
    font-size: 11px;
    line-height: 18px;
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
  }

  &__separator {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }
}

@media (width <= 1100px) {
  .command-entry {
    width: 220px;

    &__label {
      max-width: 95px;
    }
  }
}
</style>
