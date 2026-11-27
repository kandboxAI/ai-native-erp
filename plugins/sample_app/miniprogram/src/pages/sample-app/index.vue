<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { requestApi } from "@/api/client";
const status = ref("正在检查插件入口");
onShow(async () => { try { await requestApi({ path: "/api/sample_app/status" }); status.value = "插件入口已接通，业务功能待实现"; } catch { status.value = "入口不可访问，请检查权限和租户启用状态"; } });
</script>
<template><view class="page-shell"><text>{{ status }}</text></view></template>
