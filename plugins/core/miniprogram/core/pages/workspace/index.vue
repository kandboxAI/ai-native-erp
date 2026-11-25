<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref, watch } from "vue";
import AppTabBar from "@/components/AppTabBar.vue";
import CustomNavbar from "@/components/CustomNavbar.vue";
import MenuStatus from "@/components/MenuStatus.vue";
import ApplicationIcon from "@/components/ApplicationIcon.vue";
import FavoriteToggle from "@/components/FavoriteToggle.vue";
import { bootstrapStore } from "@/store/app";
import { menuStore } from "@/store/menus";
import {
  applicationCategories,
  filterApplications,
} from "@/utils/application-filter";

bootstrapStore();
const services = menuStore.services;
const keyword = ref("");
const selectedCategory = ref("");
const query = computed(() => keyword.value.trim());
const categories = computed(() => applicationCategories(services.value));
const filteredServices = computed(() =>
  filterApplications(services.value, keyword.value, selectedCategory.value),
);
watch(categories, (items) => {
  if (!items.some((item) => item.id === selectedCategory.value))
    selectedCategory.value = "";
});
onShow(() => {
  void menuStore.refresh();
});
</script>

<template>
  <view class="page-shell portal-page workspace-page">
    <view class="application-header">
      <view class="portal-navbar">
        <CustomNavbar title="应用中心" :horizontal-padding="28" />
      </view>
      <view class="search-bar">
        <view class="search-icon" />
        <input
          v-model="keyword"
          class="search-input"
          type="text"
          confirm-type="search"
          placeholder="搜索应用名称或功能"
          aria-label="搜索应用"
        />
        <view
          v-if="keyword"
          class="search-clear"
          role="button"
          aria-label="清除搜索"
          @tap="keyword = ''"
          >清除</view
        >
      </view>
      <scroll-view
        v-if="categories.length > 1"
        class="category-scroll"
        scroll-x
        :show-scrollbar="false"
      >
        <view
          class="application-categories"
          role="tablist"
          aria-label="应用分类"
        >
          <view
            v-for="item in categories"
            :key="item.id"
            class="application-category"
            :class="{ active: selectedCategory === item.id }"
            role="tab"
            :aria-selected="selectedCategory === item.id"
            @tap="selectedCategory = item.id"
            >{{ item.name }}</view
          >
        </view>
      </scroll-view>
    </view>
    <view v-if="services.length" class="list-caption">
      <text>{{
        query || selectedCategory
          ? `找到 ${filteredServices.length} 个应用`
          : `共 ${services.length} 个应用`
      }}</text>
      <text>点亮星标加入常用</text>
    </view>
    <MenuStatus />
    <view
      v-if="menuStore.state.favoritesError"
      class="favorites-error"
      @tap="menuStore.refresh(true)"
    >
      {{ menuStore.state.favoritesError }}，点击重试
    </view>
    <view v-if="filteredServices.length" class="workspace-list">
      <view
        v-for="item in filteredServices"
        :key="item.url"
        class="workspace-card pressable"
        @tap="menuStore.open(item.url)"
      >
        <ApplicationIcon :src="item.icon" />
        <view class="service-copy-block">
          <text class="service-title">{{ item.title }}</text>
          <text class="service-copy">{{ item.desc }}</text>
        </view>
        <view class="favorite-corner" @tap.stop
          ><FavoriteToggle :menu-id="item.id" :title="item.title"
        /></view>
      </view>
    </view>
    <view
      v-if="
        (query || selectedCategory) &&
        services.length &&
        !filteredServices.length
      "
      class="search-empty"
    >
      <view class="search-empty-symbol"><view class="search-icon" /></view>
      <text class="search-empty-title">未找到匹配的应用</text>
      <text>试试其他关键词，或切换应用分类</text>
      <view
        class="reset-search pressable"
        role="button"
        @tap="
          keyword = '';
          selectedCategory = '';
        "
        >查看全部应用</view
      >
    </view>
    <AppTabBar current="secondary" />
  </view>
</template>

<style scoped lang="scss">
.application-header {
  position: sticky;
  top: 0;
  z-index: 20;
  margin: 0 -28rpx;
  padding-right: 28rpx;
  padding-left: 28rpx;
  background: var(--hq-bg);
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 22rpx;
  padding: 12rpx 28rpx;
  background: #fff;
  border: 1rpx solid #e8ebf0;
  border-radius: 99rpx;
  box-shadow: 0 5rpx 18rpx rgba(29, 46, 75, 0.025);
}
.search-icon {
  position: relative;
  width: 30rpx;
  height: 30rpx;
  flex: 0 0 30rpx;
  margin-right: 6rpx;
  border: 3rpx solid #8a94a3;
  border-radius: 50%;
}
.search-icon::after {
  position: absolute;
  right: -9rpx;
  bottom: -5rpx;
  width: 13rpx;
  height: 3rpx;
  background: #8a94a3;
  border-radius: 3rpx;
  content: "";
  transform: rotate(45deg);
}
.search-input {
  min-width: 0;
  height: 64rpx;
  flex: 1;
  color: var(--hq-ink);
  font-size: 28rpx;
}
.search-clear {
  display: flex;
  min-height: 64rpx;
  align-items: center;
  color: var(--hq-primary);
  font-size: 24rpx;
}
.category-scroll {
  width: 100%;
  margin-top: 18rpx;
  white-space: nowrap;
}
.application-categories {
  display: inline-flex;
  min-width: 100%;
  border-bottom: 1rpx solid #e6eaf0;
}
.application-category {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  min-height: 90rpx;
  padding: 0 24rpx;
  color: #687385;
  font-size: 28rpx;
}
.application-category:first-child {
  padding-left: 8rpx;
}
.application-category.active {
  color: var(--hq-primary);
  font-weight: 650;
}
.application-category.active::after {
  position: absolute;
  right: 24rpx;
  bottom: 0;
  left: 24rpx;
  height: 6rpx;
  background: var(--hq-primary);
  border-radius: 8rpx;
  content: "";
}
.application-category:first-child.active::after {
  left: 8rpx;
}
.list-caption {
  display: flex;
  justify-content: space-between;
  gap: 12rpx;
  padding: 24rpx 4rpx 20rpx;
  color: var(--hq-muted);
  font-size: 23rpx;
}
.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}
.workspace-card {
  display: flex;
  align-items: center;
  gap: 22rpx;
  min-height: 148rpx;
  padding: 26rpx 16rpx 26rpx 24rpx;
  background: #fff;
  border-radius: 26rpx;
  box-shadow: 0 6rpx 24rpx rgba(29, 46, 75, 0.03);
}
.service-copy-block {
  flex: 1;
  min-width: 0;
}
.service-title {
  display: block;
  color: var(--hq-ink);
  font-size: 30rpx;
  font-weight: 600;
  line-height: 1.5;
  word-break: break-all;
}
.service-copy {
  display: -webkit-box;
  overflow: hidden;
  margin-top: 6rpx;
  color: var(--hq-muted);
  font-size: 24rpx;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.favorite-corner {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  margin-left: auto;
}
.favorites-error {
  padding: 24rpx 4rpx;
  color: #a56813;
  font-size: 24rpx;
}
.search-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18rpx;
  padding: 90rpx 12rpx;
  color: var(--hq-muted);
  font-size: 24rpx;
  text-align: center;
}
.search-empty-symbol {
  display: flex;
  width: 96rpx;
  height: 96rpx;
  align-items: center;
  justify-content: center;
  margin-bottom: 8rpx;
  background: #e9edf3;
  border-radius: 50%;
}
.search-empty-title {
  color: var(--hq-ink);
  font-size: 30rpx;
  font-weight: 600;
}
.reset-search {
  margin-top: 8rpx;
  padding: 16rpx 30rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 99rpx;
  font-size: 25rpx;
}
</style>
