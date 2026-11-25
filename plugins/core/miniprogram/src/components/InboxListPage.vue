<script setup lang="ts">
import { computed, ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import CustomNavbar from "@/components/CustomNavbar.vue";
import { inboxStore, messageInboxStore } from "@/store/inbox";
import { openInboxMessage } from "@/utils/inboxMessage";

const props = defineProps<{ kind: "announcement" | "message" }>();
const store = props.kind === "announcement" ? inboxStore : messageInboxStore;
const title = props.kind === "announcement" ? "公告" : "消息";
const unreadCount = computed(() =>
  props.kind === "announcement"
    ? store.state.announcementUnread
    : store.state.notificationUnread,
);
const unreadOnly = ref(false);

function load() {
  void store.select(props.kind, unreadOnly.value);
}

function selectFilter(value: boolean) {
  unreadOnly.value = value;
  load();
}

function loadMore() {
  void store.load(true);
}

onShow(load);
onReachBottom(loadMore);
</script>

<template>
  <view class="page-shell inbox-list-page">
    <CustomNavbar :title="title" />

    <view class="inbox-toolbar card">
      <view class="inbox-filters">
        <button
          class="filter-button"
          :class="{ 'filter-button--active': !unreadOnly }"
          @tap="selectFilter(false)"
        >
          全部
        </button>
        <button
          class="filter-button"
          :class="{ 'filter-button--active': unreadOnly }"
          @tap="selectFilter(true)"
        >
          未读{{ unreadCount ? ` ${unreadCount}` : "" }}
        </button>
      </view>
      <button
        v-if="unreadCount"
        class="read-all-button"
        :disabled="store.state.saving"
        @tap="store.markAllRead()"
      >
        {{ store.state.saving ? "处理中…" : "全部标为已读" }}
      </button>
    </view>

    <view v-if="store.state.error" class="inbox-state card" @tap="load">
      <text class="state-title">{{ store.state.error }}</text>
      <text class="state-hint">点击重试</text>
    </view>
    <view
      v-else-if="store.state.loading && !store.state.rows.length"
      class="inbox-state card"
    >
      <text class="state-title">正在加载{{ title }}…</text>
    </view>
    <view v-else-if="!store.state.rows.length" class="inbox-state card">
      <text class="state-title">暂无{{ unreadOnly ? "未读" : "" }}{{ title }}</text>
      <text class="state-hint">新的内容会显示在这里</text>
    </view>
    <view v-else class="inbox-list">
      <view
        v-for="item in store.state.rows"
        :key="item.id"
        class="inbox-item card pressable"
        @tap="openInboxMessage(item, store)"
      >
        <view class="inbox-item-top">
          <text class="inbox-category">{{ item.category }}</text>
          <text class="inbox-time">{{ item.time }}</text>
        </view>
        <view class="inbox-item-title-row">
          <view v-if="!item.read" class="unread-dot" />
          <text class="inbox-item-title">{{ item.title }}</text>
        </view>
        <text class="inbox-item-content">{{ item.content || "暂无摘要" }}</text>
        <view class="inbox-item-footer">
          <text>{{ item.sourceSystem }}</text>
          <text class="item-link">查看详情 ›</text>
        </view>
      </view>
    </view>

    <view v-if="store.state.rows.length < store.state.total" class="load-more">
      {{ store.state.loading ? "正在加载…" : "上拉加载更多" }}
    </view>
  </view>
</template>

<style scoped lang="scss">
.inbox-list-page {
  padding-bottom: 48rpx;
}

.inbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 20rpx;
}

.inbox-filters {
  display: flex;
  gap: 12rpx;
}

.filter-button,
.read-all-button {
  min-height: 62rpx;
  padding: 0 22rpx;
  margin: 0;
  color: var(--hq-body);
  background: #f4f6f9;
  border: 0;
  border-radius: 16rpx;
  font-size: 23rpx;
  line-height: 62rpx;
}

.filter-button--active {
  color: #fff;
  background: var(--hq-primary);
}

.read-all-button {
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
}

.read-all-button[disabled] {
  opacity: 0.6;
}

.inbox-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.inbox-item {
  padding: 24rpx 26rpx;
  margin-top: 0;
}

.inbox-item-top,
.inbox-item-title-row,
.inbox-item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.inbox-category {
  padding: 5rpx 12rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 99rpx;
  font-size: 20rpx;
}

.inbox-time,
.inbox-item-footer {
  color: var(--hq-muted);
  font-size: 21rpx;
}

.inbox-item-title-row {
  justify-content: flex-start;
  gap: 12rpx;
  margin-top: 18rpx;
}

.inbox-item-title {
  min-width: 0;
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.unread-dot {
  width: 12rpx;
  height: 12rpx;
  flex: 0 0 12rpx;
  background: #e5484d;
  border-radius: 50%;
}

.inbox-item-content {
  display: block;
  margin-top: 10rpx;
  color: var(--hq-body);
  font-size: 23rpx;
  line-height: 1.6;
}

.inbox-item-footer {
  gap: 16rpx;
  margin-top: 16rpx;
}

.item-link {
  color: var(--hq-primary);
}

.inbox-state {
  display: flex;
  min-height: 240rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32rpx;
  text-align: center;
}

.state-title {
  color: var(--hq-ink);
  font-size: 27rpx;
  line-height: 1.5;
}

.state-hint,
.load-more {
  margin-top: 10rpx;
  color: var(--hq-muted);
  font-size: 22rpx;
}

.load-more {
  padding: 20rpx;
  text-align: center;
}
</style>
