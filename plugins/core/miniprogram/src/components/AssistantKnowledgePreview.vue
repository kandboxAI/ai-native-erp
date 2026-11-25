<script setup lang="ts">
import { ref, watch } from "vue";
import { parseKnowledgeCitation } from "@/utils/assistantMarkdown";
import {
  readKnowledgeCitation,
  type KnowledgeContent,
} from "@/api/knowledgeCitation";
import { appStore } from "@/store/app";
import AssistantMarkdown from "@/components/AssistantMarkdown.vue";

const props = defineProps<{ address: string }>();
const emit = defineEmits<{ close: [] }>();
const content = ref<KnowledgeContent | null>(null);
const error = ref("");
const loading = ref(false);
const whole = ref(false);
const page = ref(1);
watch(
  () => props.address,
  () => {
    whole.value = false;
    page.value = 1;
  },
);
watch(
  () => appStore.state.account,
  () => emit("close"),
);
watch(
  [() => props.address, whole, page],
  async (_, __, onCleanup) => {
    let active = true;
    onCleanup(() => {
      active = false;
    });
    content.value = null;
    error.value = "";
    const source = parseKnowledgeCitation(props.address);
    if (!source) return;
    loading.value = true;
    const account = appStore.state.account;
    try {
      const result = await readKnowledgeCitation(
        source,
        whole.value ? page.value : undefined,
      );
      if (active && account === appStore.state.account) content.value = result;
    } catch (failure) {
      if (active)
        error.value =
          failure instanceof Error
            ? failure.message
            : "来源不可用，请重新检索或核对读取权限";
    } finally {
      if (active) loading.value = false;
    }
  },
  { immediate: true },
);
</script>

<template>
  <view class="citation-overlay" @tap="emit('close')">
    <view class="citation-sheet" @tap.stop>
      <view class="citation-heading">
        <text class="citation-title">{{
          content?.document_name || "知识来源"
        }}</text>
        <button size="mini" @tap="emit('close')">关闭</button>
      </view>
      <scroll-view scroll-y class="citation-body">
        <text v-if="loading" class="citation-hint">正在读取来源…</text>
        <text v-if="error" class="citation-error">{{ error }}</text>
        <template v-if="content">
          <text class="citation-hint"
            >{{ whole ? "已发布正文" : "引用片段" }} ·
            已校验当前权限和来源版本</text
          >
          <view
            v-for="(chunk, index) in content.chunks"
            :key="chunk.chunk_no || index"
            class="citation-chunk"
          >
            <text class="citation-hint"
              >分块 {{ chunk.chunk_index ?? index }}</text
            >
            <AssistantMarkdown :content="chunk.content" />
            <text v-if="chunk.truncated" class="citation-hint"
              >此片段已截断</text
            >
          </view>
          <text v-if="!content.chunks.length" class="citation-hint"
            >暂无正文片段</text
          >
        </template>
      </scroll-view>
      <view v-if="content" class="citation-actions">
        <button v-if="!whole" size="mini" @tap="whole = true">
          查看正文上下文
        </button>
        <template v-else>
          <button size="mini" :disabled="page <= 1" @tap="page--">
            上一页
          </button>
          <text>第 {{ page }} 页</text>
          <button
            size="mini"
            :disabled="page * 10 >= content.total_chunks"
            @tap="page++"
          >
            下一页
          </button>
        </template>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.citation-overlay {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: flex;
  align-items: flex-end;
  background: rgba(15, 23, 42, 0.45);
}
.citation-sheet {
  box-sizing: border-box;
  width: 100%;
  padding: 28rpx 28rpx calc(28rpx + env(safe-area-inset-bottom));
  border-radius: 28rpx 28rpx 0 0;
  background: #fff;
  color: #1e293b;
}
.citation-heading,
.citation-actions {
  display: flex;
  align-items: center;
  gap: 20rpx;
}
.citation-title {
  flex: 1;
  font-size: 30rpx;
  font-weight: 600;
}
.citation-heading button,
.citation-actions button {
  margin: 0;
  flex-shrink: 0;
}
.citation-body {
  height: 55vh;
  margin: 20rpx 0;
}
.citation-hint,
.citation-error {
  display: block;
  margin: 12rpx 0;
  font-size: 23rpx;
  color: #64748b;
}
.citation-error {
  color: #b45309;
}
.citation-chunk {
  padding: 16rpx 0;
  border-bottom: 1rpx solid #e2e8f0;
}
.citation-actions {
  justify-content: center;
  font-size: 24rpx;
}
</style>
