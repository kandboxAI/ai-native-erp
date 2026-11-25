<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref, watch } from "vue";
import AppTabBar from "@/components/AppTabBar.vue";
import CustomNavbar from "@/components/CustomNavbar.vue";
import MenuStatus from "@/components/MenuStatus.vue";
import ApplicationIcon from "@/components/ApplicationIcon.vue";
import HomeSectionHeading from "@/components/HomeSectionHeading.vue";
import InboxPreview from "@/components/InboxPreview.vue";
import {
  inboxStore,
  announcementPreviewStore,
  messagePreviewStore,
} from "@/store/inbox";
import HomeCarousel from "@/components/HomeCarousel.vue";
import { appStore, bootstrapStore } from "@/store/app";
import { menuStore } from "@/store/menus";
import { homeStore } from "@/store/home";

bootstrapStore();
const profile = appStore.currentProfile;
const avatarFailed = ref(false);
watch(
  () => profile.value.avatarUrl,
  () => {
    avatarFailed.value = false;
  },
);
const services = menuStore.services;
const favoriteServices = menuStore.favoriteServices;
onShow(() => {
  void menuStore.refresh();
  void homeStore.refresh();
  void announcementPreviewStore.load();
  void messagePreviewStore.load();
  void inboxStore.refreshCounts();
});
</script>

<template>
  <view class="page-shell portal-page home-page">
    <view class="portal-navbar home-navbar">
      <CustomNavbar :horizontal-padding="28">
        <view class="account-row">
          <view class="account-avatar">
            <image
              v-if="profile.avatarUrl && !avatarFailed"
              :src="profile.avatarUrl"
              mode="aspectFill"
              @error="avatarFailed = true"
            />
            <text v-else>{{ profile.avatarText }}</text>
          </view>
          <view class="account-copy">
            <text class="account-name">{{ profile.name }}</text>
            <text class="account-role">{{ profile.roleName }}</text>
          </view>
        </view>
      </CustomNavbar>
    </view>
    <view v-if="homeStore.state.banners.length" class="banner-frame">
      <HomeCarousel :items="homeStore.state.banners" />
    </view>
    <view
      v-if="homeStore.state.error"
      class="banner-error"
      @tap="homeStore.refresh()"
      >{{ homeStore.state.error }}</view
    >
    <HomeSectionHeading title="我的常用">
      <text v-if="favoriteServices.length" class="section-count"
        >{{ favoriteServices.length }} 个应用</text
      >
    </HomeSectionHeading>
    <view class="service-panel card">
      <MenuStatus />
      <view
        v-if="
          services.length &&
          !menuStore.state.loading &&
          !menuStore.state.favoritesLoading &&
          !menuStore.state.favoritesError &&
          !favoriteServices.length
        "
        class="empty-favorites"
      >
        <image
          class="empty-star"
          src="/static/tabbar/favorites.png"
          mode="aspectFit"
        />
        <text class="empty-title">还没有常用应用</text>
        <text>在“应用”页点亮星标，将应用添加到这里</text>
      </view>
      <view
        v-if="menuStore.state.favoritesError"
        class="favorites-error"
        @tap="menuStore.refresh(true)"
      >
        {{ menuStore.state.favoritesError }}，点击重试
      </view>
      <view v-if="favoriteServices.length" class="service-grid">
        <view
          v-for="item in favoriteServices"
          :key="item.url"
          class="service-item pressable"
          role="button"
          :aria-label="item.title"
          @tap="menuStore.open(item.url)"
        >
          <ApplicationIcon :src="item.icon" :size="84" />
          <text class="service-title">{{ item.title }}</text>
        </view>
      </view>
    </view>
    <InboxPreview kind="announcement" />
    <InboxPreview kind="message" />
    <AppTabBar current="home" />
  </view>
</template>

<style scoped lang="scss">
.page-shell.home-page {
  --hq-bg: #f7f7f7;
  --hq-ink: #22252a;
}
.home-navbar {
  background: #fff;
  border-bottom: 1rpx solid #ebedef;
}
.account-row {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 20rpx;
}
.account-avatar {
  display: flex;
  width: 76rpx;
  height: 76rpx;
  flex: 0 0 76rpx;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border: 0;
  border-radius: 50%;
  font-size: 32rpx;
  font-weight: 700;
}
.account-avatar image {
  width: 100%;
  height: 100%;
}
.account-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 4rpx;
}
.account-name,
.account-role {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.account-name {
  color: var(--hq-ink);
  font-size: 32rpx;
  font-weight: 700;
  line-height: 1.3;
}
.account-role {
  color: #83878d;
  font-size: 22rpx;
  line-height: 1.4;
}
.banner-frame {
  margin-top: 28rpx;
}
.banner-error {
  padding: 20rpx 8rpx;
  color: var(--hq-muted);
  font-size: 24rpx;
}
.section-count {
  flex: 0 0 auto;
  color: var(--hq-muted);
  font-size: 22rpx;
  line-height: 1.5;
}
.service-panel {
  padding: 22rpx 10rpx 12rpx;
}
.service-grid {
  display: flex;
  flex-wrap: wrap;
}
.service-item {
  display: flex;
  width: 20%;
  flex: 0 0 20%;
  flex-direction: column;
  align-items: center;
  padding: 10rpx 5rpx 26rpx;
}
.service-title {
  display: -webkit-box;
  width: 100%;
  min-height: 64rpx;
  overflow: hidden;
  margin-top: 14rpx;
  color: var(--hq-ink);
  font-size: 24rpx;
  font-weight: 400;
  line-height: 32rpx;
  text-align: center;
  word-break: break-all;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.empty-favorites {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16rpx;
  padding: 44rpx 12rpx 56rpx;
  color: var(--hq-muted);
  font-size: 24rpx;
  line-height: 1.6;
  text-align: center;
}
.empty-star {
  width: 64rpx;
  height: 64rpx;
  margin-bottom: 8rpx;
  opacity: 0.6;
}
.empty-title {
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 600;
}
.favorites-error {
  padding: 24rpx;
  color: #a56813;
  font-size: 24rpx;
}
</style>
