<script setup lang="ts">
import { ref } from "vue";
withDefaults(defineProps<{ activeCount?: number; enabled?: boolean }>(), {
  enabled: true
});
const expanded = ref(false);
</script>
<template>
  <div class="list-more-filters">
    <slot v-if="enabled && expanded" />
    <span class="list-query-actions">
      <el-button
        data-action="neutral"
        v-if="enabled"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? "收起筛选" : "更多筛选"
        }}<span v-if="activeCount">（{{ activeCount }}）</span>
      </el-button>
      <slot name="actions" />
    </span>
  </div>
</template>
