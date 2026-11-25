<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { getTodo, type TodoItem } from "@/api/todo";
import { isTodoRecordId, todoMiniappTarget } from "@/utils/todoEntry";

const id = ref("");
const todo = ref<TodoItem>();
const loading = ref(false);
const error = ref("");

async function load() {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const item = await getTodo(id.value);
    const target = todoMiniappTarget(item);
    if (target) {
      uni.redirectTo({
        url: target,
        fail: () => { error.value = "打开办理页面失败，请重试"; },
      });
    } else {
      todo.value = item;
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "待办加载失败";
  } finally {
    loading.value = false;
  }
}

onLoad((options) => {
  id.value = String(options?.id || "").trim();
  if (isTodoRecordId(id.value)) void load();
  else error.value = "该待办链接已失效，请返回待办列表重新打开。";
});
</script>

<template>
  <view class="page-shell">
    <view class="card todo-summary">
      <text v-if="error">{{ error }}</text>
      <template v-else-if="todo">
        <text>{{ todo.title }}</text>
        <text v-if="todo.summary">{{ todo.summary }}</text>
        <text>请登录 ERP 管理端，在工作台打开此待办办理。</text>
      </template>
      <text v-else>正在打开待办详情…</text>
      <button
        v-if="error && isTodoRecordId(id)"
        class="btn-secondary btn-sm"
        :disabled="loading"
        @tap="load"
      >重试</button>
    </view>
  </view>
</template>

<style scoped>
.todo-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16rpx;
  padding: 28rpx;
}
</style>
