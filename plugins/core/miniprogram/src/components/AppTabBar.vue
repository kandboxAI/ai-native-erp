<script setup lang="ts">
import { computed, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { menuStore } from "@/store/menus";
import { bootstrapStore } from "@/store/app";
import { inboxStore } from "@/store/inbox";
import {
  buildAppTabs,
  type AppTabKey,
} from "@/config/appTabBar";

const branding = __PRODUCT_BRANDING__;

const props = withDefaults(
  defineProps<{
    current: AppTabKey;
    reserveSpace?: boolean;
  }>(),
  { reserveSpace: true }
);

bootstrapStore();

const tabs = buildAppTabs();

const pendingText = computed(() => {
  const count = inboxStore.state.todoPending;
  return count > 99 ? "99+" : String(count);
});

function hideNativeTabBar() {
  uni.hideTabBar({ animation: false, fail: () => undefined });
}

function initializeTabBar() {
  hideNativeTabBar();
  void menuStore.refresh();
  void inboxStore.refreshCounts();
}

function switchTo(path: string) {
  const pages = getCurrentPages();
  if (`/${pages[pages.length - 1]?.route}` === path) return;
  if (__MINIAPP_TAB_PAGES__.includes(path)) uni.switchTab({ url: path });
  else uni.navigateTo({ url: path });
}

onMounted(initializeTabBar);
onShow(() => {
  void menuStore.refresh();
  void inboxStore.refreshCounts();
});
</script>

<template>
  <view v-if="reserveSpace && tabs.length" class="app-tabbar-spacer" />
  <view v-if="tabs.length" class="app-tabbar">
    <view class="tabbar-hairline" />
    <view
      v-for="tab in tabs"
      :key="tab.key"
      class="tabbar-item pressable"
      :class="{
        active: current === tab.key,
        'tabbar-item--agent': tab.key === 'xiaohang'
      }"
      @tap="switchTo(tab.path)"
    >
      <template v-if="tab.key === 'xiaohang'">
        <view class="agent-halo">
          <view class="agent-orb">
            <view class="agent-spark agent-spark--one" />
            <view class="agent-spark agent-spark--two" />
            <text>{{ branding.mark }}</text>
          </view>
        </view>
      </template>
      <template v-else>
        <view class="tab-icon-wrap">
          <image
            class="tab-icon"
            :src="current === tab.key ? tab.iconActive : tab.icon"
            mode="aspectFit"
          />
          <text
            v-if="tab.key === 'messages' && inboxStore.state.todoPending"
            class="tab-badge"
            >{{ pendingText }}</text
          >
        </view>
      </template>
      <text class="tab-label">{{ tab.label }}</text>
    </view>
  </view>
</template>

<style scoped lang="scss">
.app-tabbar-spacer {
  height: calc(118rpx + env(safe-area-inset-bottom));
}
.app-tabbar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 90;
  display: flex;
  height: calc(104rpx + env(safe-area-inset-bottom));
  align-items: flex-start;
  padding: 10rpx 10rpx env(safe-area-inset-bottom);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 -10rpx 30rpx rgba(28, 51, 84, 0.07);
}
.tabbar-hairline {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 1rpx;
  background: #edf1f6;
}
.tabbar-item {
  position: relative;
  display: flex;
  min-width: 0;
  height: 94rpx;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  color: #8a94a6;
}
.tab-icon-wrap {
  position: relative;
  width: 48rpx;
  height: 48rpx;
}
.tab-icon {
  width: 48rpx;
  height: 48rpx;
}
.tab-label {
  margin-top: 1rpx;
  font-size: 20rpx;
  line-height: 28rpx;
}
.tabbar-item.active {
  color: #1769e0;
  font-weight: 650;
}
.tab-badge {
  position: absolute;
  top: -5rpx;
  left: 32rpx;
  min-width: 27rpx;
  height: 27rpx;
  padding: 0 7rpx;
  color: #fff;
  background: #e84b55;
  border: 3rpx solid #fff;
  border-radius: 99rpx;
  font-size: 16rpx;
  line-height: 27rpx;
  text-align: center;
}
.tabbar-item--agent {
  margin-top: -39rpx;
}
.agent-halo {
  display: flex;
  width: 94rpx;
  height: 94rpx;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 11rpx 30rpx rgba(23, 105, 224, 0.2);
}
.agent-orb {
  position: relative;
  display: flex;
  width: 78rpx;
  height: 78rpx;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #fff;
  background: linear-gradient(145deg, #2b83f3 3%, #1769e0 52%, #0f4fa9);
  border-radius: 27rpx;
  box-shadow: inset 0 1rpx 1rpx rgba(255, 255, 255, 0.36);
}
.agent-orb::after {
  position: absolute;
  width: 96rpx;
  height: 48rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.27);
  border-radius: 50%;
  content: "";
  transform: rotate(-25deg);
}
.agent-orb text {
  position: relative;
  z-index: 2;
  font-size: 35rpx;
  font-weight: 800;
}
.agent-spark {
  position: absolute;
  z-index: 3;
  width: 6rpx;
  height: 6rpx;
  background: #7be9ff;
  border-radius: 50%;
  box-shadow: 0 0 10rpx rgba(123, 233, 255, 0.9);
}
.agent-spark--one {
  top: 14rpx;
  right: 15rpx;
}
.agent-spark--two {
  bottom: 14rpx;
  left: 13rpx;
}
.tabbar-item--agent .tab-label {
  margin-top: 1rpx;
  color: #1769e0;
  font-size: 21rpx;
  font-weight: 750;
}
</style>
