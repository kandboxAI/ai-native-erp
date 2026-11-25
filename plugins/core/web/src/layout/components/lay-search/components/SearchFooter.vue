<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useNav } from "@/layout/hooks/useNav";

withDefaults(defineProps<{ total?: number }>(), {
  total: 0
});

const { t } = useI18n();
const { device } = useNav();
</script>

<template>
  <div class="search-footer text-[#333] dark:text-white">
    <p v-if="device !== 'mobile' && total > 0" class="search-footer-total">
      {{ `${t("search.pureTotal")} ${total}` }}
    </p>
  </div>
</template>

<style lang="scss" scoped>
.search-footer {
  display: flex;

  .search-footer-item {
    display: flex;
    align-items: center;
    margin-right: 14px;
  }

  .icon {
    padding: 2px;
    margin-right: 3px;
    font-size: 20px;
    box-shadow:
      inset 0 -2px #cdcde6,
      inset 0 0 1px 1px #fff,
      0 1px 2px 1px #1e235a66;
  }

  .search-footer-total {
    position: absolute;
    right: 20px;
  }
}
</style>
