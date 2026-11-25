<script setup lang="ts">
import { menuStore } from "@/store/menus";
</script>
<template>
  <view v-if="menuStore.state.loading" class="menu-status">正在加载菜单…</view>
  <view v-else-if="menuStore.state.error" class="menu-status" @tap="menuStore.refresh()">{{ menuStore.state.error }}，点击重试</view>
  <view v-else-if="!menuStore.services.value.length" class="menu-status">暂无已授权的功能，请联系管理员配置小程序菜单</view>
</template>
<style scoped>
.menu-status { padding: 24rpx; color: #7a8ba3; font-size: 26rpx; }
</style>
