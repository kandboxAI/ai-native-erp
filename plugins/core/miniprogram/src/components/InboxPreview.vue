<script setup lang="ts">
import HomeSectionHeading from "@/components/HomeSectionHeading.vue";
import { computed } from "vue";
import { announcementPreviewStore, messagePreviewStore } from "@/store/inbox";
import { openInboxMessage } from "@/utils/inboxMessage";

const props = defineProps<{ kind: "announcement" | "message" }>();
const store =
  props.kind === "announcement"
    ? announcementPreviewStore
    : messagePreviewStore;
const title = props.kind === "announcement" ? "公告" : "消息";
const unread = computed(() =>
  props.kind === "announcement"
    ? store.state.announcementUnread
    : store.state.notificationUnread,
);
const rows = computed(() => store.state.rows.slice(0, 2));
function showAll() {
  uni.navigateTo({
    url:
      props.kind === "announcement"
        ? "/pages/announcements/index"
        : "/pages/notifications/index",
  });
}
</script>

<template>
  <view class="inbox-preview" :class="`preview-${kind}`">
    <HomeSectionHeading :title="title">
      <template #meta>
        <text v-if="unread" class="preview-unread"
          >{{ unread > 99 ? "99+" : unread }} 未读</text
        >
      </template>
      <view
        class="preview-more pressable"
        role="button"
        :aria-label="`查看更多${title}`"
        @tap="showAll"
      >
        <text>查看更多</text><text class="more-arrow">›</text>
      </view>
    </HomeSectionHeading>
    <view class="preview-card card">
      <view
        v-for="item in rows"
        :key="item.id"
        class="preview-row pressable"
        role="button"
        :aria-label="item.title"
        @tap="openInboxMessage(item, store)"
      >
        <view v-if="!item.read" class="preview-dot" />
        <text class="preview-item-title">{{ item.title }}</text>
        <text class="preview-date">{{ item.time.slice(5, 10) }}</text>
        <text class="row-arrow">›</text>
      </view>
      <view
        v-if="store.state.error"
        class="preview-feedback pressable"
        @tap="store.load()"
      >
        {{ store.state.error }}，点击重试
      </view>
      <view v-else-if="!rows.length" class="preview-feedback">
        {{ store.state.loading ? "正在加载…" : `暂无${title}` }}
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.preview-unread {
  color: #e5484d;
  font-size: 20rpx;
  white-space: nowrap;
}
.preview-more {
  display: flex;
  flex: 0 0 auto;
  min-height: 50rpx;
  align-items: center;
  gap: 8rpx;
  color: var(--hq-muted);
  font-size: 22rpx;
}
.more-arrow,
.row-arrow {
  color: #aab4c1;
  font-size: 30rpx;
}
.preview-card {
  padding: 0 22rpx;
}
.preview-row {
  display: flex;
  min-height: 82rpx;
  align-items: center;
  gap: 12rpx;
}
.preview-row + .preview-row {
  border-top: 1rpx solid var(--hq-line);
}
.preview-dot {
  width: 9rpx;
  height: 9rpx;
  flex: 0 0 9rpx;
  background: #e5484d;
  border-radius: 50%;
}
.preview-item-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--hq-ink);
  font-size: 26rpx;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.preview-date {
  flex: 0 0 auto;
  color: var(--hq-muted);
  font-size: 21rpx;
}
.preview-feedback {
  padding: 24rpx 0;
  color: var(--hq-muted);
  font-size: 23rpx;
}
</style>
