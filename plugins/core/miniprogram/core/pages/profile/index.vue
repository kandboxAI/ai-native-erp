<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref, watch } from "vue";
import AppTabBar from "@/components/AppTabBar.vue";
import CustomNavbar from "@/components/CustomNavbar.vue";
import ApplicationIcon from "@/components/ApplicationIcon.vue";
import { appStore, bootstrapStore } from "@/store/app";
import { avatarStore } from "@/store/avatar";
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

onShow(() => {
  void homeStore.refresh();
});

function chooseAvatar() {
  if (avatarStore.state.saving) return;
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    sourceType: ["album", "camera"],
    success: (result) => {
      const paths = Array.isArray(result.tempFilePaths)
        ? result.tempFilePaths
        : [result.tempFilePaths];
      if (paths[0]) void changeAvatar(paths[0]);
    },
  });
}

async function changeAvatar(path: string) {
  uni.showLoading({ title: "正在更新头像", mask: true });
  try {
    if (await avatarStore.save(path))
      uni.showToast({ title: "头像已更新", icon: "success" });
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : "头像更新失败，请重试",
      icon: "none",
      duration: 3500,
    });
  } finally {
    uni.hideLoading();
  }
}

function logout() {
  if (avatarStore.state.saving) return;
  uni.showModal({
    title: "退出登录",
    content: "确认退出当前账号？",
    confirmColor: "#e84b55",
    success: (result) => {
      if (!result.confirm) return;
      appStore.logout();
      uni.reLaunch({ url: "/pages/login/index" });
    },
  });
}
</script>

<template>
  <view class="page-shell portal-page profile-page">
    <view class="portal-navbar">
      <CustomNavbar title="我的" :horizontal-padding="28" />
    </view>

    <view class="profile-hero card">
      <view
        class="profile-avatar pressable"
        role="button"
        aria-label="更换头像"
        @tap="chooseAvatar"
      >
        <image
          v-if="profile.avatarUrl && !avatarFailed"
          :src="profile.avatarUrl"
          mode="aspectFill"
          @error="avatarFailed = true"
        />
        <text v-else>{{ profile.avatarText }}</text>
        <text class="avatar-edit-label">更换</text>
      </view>
      <view class="profile-copy">
        <text class="profile-name">{{ profile.name }}</text>
        <text class="profile-role">{{ profile.roleName }}</text>
        <text class="avatar-hint">{{
          avatarStore.state.saving ? "正在更新头像…" : "点击头像更换 · 最大2MB"
        }}</text>
      </view>
    </view>

    <view class="info-card card">
      <text class="section-label">账号信息</text>
      <view class="info-row">
        <ApplicationIcon src="/static/service-icons/mail.png" :size="64" />
        <view class="grow">
          <text class="info-label">登录邮箱</text>
          <text class="info-value">{{
            appStore.state.account?.email || "未设置"
          }}</text>
        </view>
      </view>
      <view class="info-divider" />
      <view class="info-row">
        <ApplicationIcon src="/static/service-icons/access.png" :size="64" />
        <view class="grow">
          <text class="info-label">已授权权限</text>
          <text class="info-value">
            {{ appStore.state.account?.permissions.length || 0 }} 项
          </text>
        </view>
      </view>
    </view>

    <button
      class="logout-button"
      :disabled="avatarStore.state.saving"
      @tap="logout"
    >
      退出登录
    </button>

    <AppTabBar current="profile" />
  </view>
</template>

<style scoped lang="scss">
.profile-hero {
  display: flex;
  align-items: center;
  padding: 36rpx;
  color: var(--hq-ink);
}

.profile-avatar {
  position: relative;
  z-index: 1;
  display: flex;
  width: 114rpx;
  height: 114rpx;
  flex: 0 0 114rpx;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 50%;
  font-size: 38rpx;
  font-weight: 750;
  box-shadow: 0 0 0 6rpx #f5f8fd;
}

.profile-avatar image {
  width: 100%;
  height: 100%;
}
.avatar-edit-label {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 28rpx;
  color: #fff;
  background: rgba(9, 55, 118, 0.62);
  font-size: 16rpx;
  font-weight: 500;
  line-height: 28rpx;
  text-align: center;
}
.avatar-hint {
  display: block;
  margin-top: 12rpx;
  color: var(--hq-muted);
  font-size: 22rpx;
  line-height: 1.5;
}

.profile-copy {
  position: relative;
  z-index: 1;
  display: flex;
  min-width: 0;
  flex-direction: column;
  margin-left: 24rpx;
}

.profile-name {
  font-size: 36rpx;
  font-weight: 700;
  word-break: break-all;
}

.profile-role {
  margin-top: 8rpx;
  align-self: flex-start;
  padding: 5rpx 14rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 10rpx;
  font-size: 23rpx;
  line-height: 1.5;
}

.info-card {
  margin-top: 24rpx;
  padding: 30rpx;
}

.section-label {
  display: block;
  margin-bottom: 24rpx;
  color: var(--hq-ink);
  font-size: 31rpx;
  font-weight: 650;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 22rpx;
  padding: 6rpx 0;
}

.info-label,
.info-value {
  display: block;
}

.info-label {
  color: var(--hq-muted);
  font-size: 24rpx;
}

.info-value {
  margin-top: 5rpx;
  color: var(--hq-ink);
  font-size: 28rpx;
  line-height: 1.5;
  word-break: break-all;
}

.info-divider {
  height: 1rpx;
  margin: 24rpx 0;
  background: var(--hq-line);
}

.logout-button {
  height: 94rpx;
  margin-top: 24rpx;
  color: var(--hq-danger);
  background: #fff;
  border: 0;
  border-radius: 26rpx;
  font-size: 28rpx;
  font-weight: 500;
  line-height: 94rpx;
  box-shadow: 0 8rpx 28rpx rgba(29, 46, 75, 0.035);
}
</style>
