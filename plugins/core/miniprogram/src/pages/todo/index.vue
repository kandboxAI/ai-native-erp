<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
// 保留已授权菜单和外部链接的旧地址，统一进入底部待办页。
onLoad(() => uni.switchTab({ url: "/pages/messages/index" }));
</script>

<template><view class="page-shell">正在打开统一待办…</view></template>
