<script setup lang="ts">
import { computed } from "vue";
import {
  renderAssistantMarkdown,
  extractAssistantCitations,
} from "@/utils/assistantMarkdown";

const props = defineProps<{ content: string }>();
const parts = computed(() => renderAssistantMarkdown(props.content));
const citations = computed(() => extractAssistantCitations(props.content));
const emit = defineEmits<{ cite: [address: string] }>();
</script>

<template>
  <view class="assistant-markdown">
    <template v-for="(part, index) in parts" :key="index">
      <scroll-view
        v-if="part.kind === 'table'"
        scroll-x
        class="markdown-table-scroll"
      >
        <view
          class="markdown-table-inner"
          :style="{ width: `${part.width}px` }"
        >
          <rich-text :nodes="part.html" :selectable="true" />
        </view>
      </scroll-view>
      <rich-text v-else :nodes="part.html" :selectable="true" />
    </template>
    <view v-if="citations.length" class="knowledge-sources">
      <text class="sources-label">知识来源</text>
      <button
        v-for="source in citations"
        :key="source.address"
        class="source-button"
        size="mini"
        @tap="emit('cite', source.address)"
      >
        {{ source.label }}
      </button>
    </view>
  </view>
</template>

<style scoped lang="scss">
.assistant-markdown {
  min-width: 0;
  overflow: hidden;
  font-size: 24rpx;
  line-height: 1.75;
  overflow-wrap: break-word;
}
.markdown-table-scroll {
  width: 100%;
  margin: 14rpx 0 20rpx;
  white-space: nowrap;
}
.markdown-table-inner {
  min-width: 100%;
  white-space: normal;
}
.knowledge-sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-top: 16rpx;
}
.sources-label {
  color: #64748b;
  font-size: 22rpx;
}
.source-button {
  margin: 0;
  padding: 0 16rpx;
  color: #2467ba;
  background: #edf3fb;
  font-size: 22rpx;
}
</style>
