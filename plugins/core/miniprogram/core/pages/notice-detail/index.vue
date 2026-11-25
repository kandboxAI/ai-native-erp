<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import {
  announcementDetail, notificationDetail, readAnnouncement, readNotification,
  type AnnouncementItem, type NotificationDetail,
} from "@/api/inbox";
import { inboxStore } from "@/store/inbox";
import { appStore } from "@/store/app";
const id = ref("");
const recipientId = ref("");
const notice = ref<AnnouncementItem | null>(null);
const message = ref<NotificationDetail | null>(null);
const loading = ref(false);
const error = ref("");
onLoad(options => {
  id.value = String(options?.id || "");
  recipientId.value = String(options?.recipient_id || "");
  void load();
});
async function load() {
  const userId = appStore.state.account?.userId;
  notice.value = null; message.value = null; loading.value = true; error.value = "";
  try {
    if (recipientId.value) {
      const result = await notificationDetail(recipientId.value);
      if (appStore.state.account?.userId === userId) {
        message.value = result;
        const saved = await readNotification(recipientId.value);
        if (!saved.updated) throw new Error("阅读记录保存失败，请重试");
        await inboxStore.refreshCounts();
      }
    } else {
      const result = await announcementDetail(id.value);
      if (appStore.state.account?.userId === userId) notice.value = result;
    }
  } catch (e) { error.value = e instanceof Error ? e.message : "详情加载失败"; }
  finally { loading.value = false; }
}
async function acknowledge() {
  const userId = appStore.state.account?.userId;
  try {
    const result = await readAnnouncement(id.value);
    if (appStore.state.account?.userId !== userId) return;
    notice.value = result;
    await inboxStore.refreshCounts();
    uni.showToast({ title: "已确认阅读", icon: "success" });
  } catch (e) { uni.showToast({ title: e instanceof Error ? e.message : "阅读确认失败", icon: "none" }); }
}
</script>

<template>
  <view v-if="message" class="page-shell notice-page">
    <view class="notice-paper card">
      <view class="notice-category">{{ message.scene_name }}</view>
      <text class="notice-title">{{ message.title }}</text>
      <view class="notice-meta">{{ message.occurred_at.slice(0, 10) }}</view>
      <view class="divider" />
      <text class="notice-content">{{ message.content || "暂无正文" }}</text>
      <view v-if="error" class="read-hint" @tap="load">{{ error }}，点击重试</view>
    </view>
  </view>
  <view v-else-if="notice" class="page-shell notice-page">
    <view class="notice-paper card">
      <view class="notice-category">{{
        notice.notice_type_code === "notice" ? "通知" : "公告"
      }}</view>
      <text class="notice-title">{{ notice.title }}</text>
      <view class="notice-meta"
        ><text>{{ notice.publisher_name_snapshot || "学校公告" }}</text
        ><text>{{ notice.published_at || notice.created_at }}</text></view
      >
      <view class="divider" />
      <text class="notice-content">{{ notice.summary || "暂无正文" }}</text>
      <view class="notice-sign"
        ><text>{{ notice.publisher_name_snapshot || "学校公告" }}</text
        ><text>{{ (notice.published_at || notice.created_at).slice(0, 10) }}</text></view
      >
    </view>
    <view class="read-card card"
      ><view class="read-icon">✓</view
      ><view class="grow"
        ><text>阅读确认</text
        ><text class="read-hint">学校可查看本通知的阅读状态</text></view
      ><text class="read-status">{{ notice.is_read ? "已读" : "未读" }}</text></view
    >
    <button class="btn-primary acknowledge" @click="acknowledge">
      我已知悉
    </button>
  </view>
  <view v-else class="empty-state" @tap="load"
    ><view class="empty-icon">!</view><text>{{ loading ? "正在加载…" : error || "内容不存在" }}</text></view
  >
</template>

<style scoped lang="scss">
.notice-paper {
  padding: 34rpx;
}
.notice-category {
  display: inline-flex;
  padding: 7rpx 14rpx;
  color: #1769e0;
  background: #eaf2ff;
  border-radius: 99rpx;
  font-size: 19rpx;
}
.notice-title {
  display: block;
  margin-top: 20rpx;
  font-size: 37rpx;
  font-weight: 750;
  line-height: 1.45;
}
.notice-meta {
  display: flex;
  gap: 20rpx;
  margin-top: 18rpx;
  color: #939daa;
  font-size: 19rpx;
}
.notice-content {
  display: block;
  color: #405068;
  font-size: 26rpx;
  line-height: 1.95;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.notice-sign {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6rpx;
  margin-top: 45rpx;
  color: #657287;
  font-size: 21rpx;
}
.read-card {
  display: flex;
  align-items: center;
  gap: 15rpx;
  padding: 22rpx;
}
.read-icon {
  display: flex;
  width: 50rpx;
  height: 50rpx;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #18a66a;
  border-radius: 15rpx;
  font-size: 22rpx;
}
.read-card text {
  display: block;
  font-size: 24rpx;
  font-weight: 650;
}
.read-card small {
  display: block;
  margin-top: 4rpx;
  color: #929caa;
  font-size: 18rpx;
}
.read-status {
  color: #18a66a !important;
  font-size: 21rpx !important;
}
.acknowledge {
  margin-top: 24rpx;
}
.read-card .read-hint {
  display: block;
  margin-top: 4rpx;
  color: #929caa;
  font-size: 18rpx;
  font-weight: 400;
}
</style>
