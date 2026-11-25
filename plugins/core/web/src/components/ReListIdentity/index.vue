<script setup lang="ts">
defineProps<{
  primary?: string | number | null;
  secondary?: string | number | null;
}>();
</script>
<template>
  <div class="list-cell-identity">
    <span class="list-cell-primary" :title="String(primary ?? '')">{{
      primary || "—"
    }}</span>
    <span
      v-if="secondary != null && secondary !== ''"
      class="list-cell-secondary"
      :title="String(secondary)"
      >{{ secondary }}</span
    >
  </div>
</template>
