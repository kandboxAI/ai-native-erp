<script setup lang="ts">
/** 只统一分页呈现，原生 Element Plus 属性、v-model 和事件保持透传。 */
defineOptions({ name: "ListPagination", inheritAttrs: false });
</script>

<template>
  <nav class="erp-list-pagination" aria-label="列表分页">
    <el-pagination
      background
      layout="total, sizes, prev, pager, next"
      :page-sizes="[10, 20, 50, 100]"
      :pager-count="5"
      v-bind="$attrs"
    />
  </nav>
</template>
