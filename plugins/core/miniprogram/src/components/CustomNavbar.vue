<script setup lang="ts">
import { computed } from "vue";
import { getNavigationMetrics } from "@/utils/navigation";

const props = withDefaults(
  defineProps<{
    title?: string;
    light?: boolean;
    horizontalPadding?: number;
  }>(),
  {
    title: "",
    light: false,
    horizontalPadding: 34
  }
);

const metrics = getNavigationMetrics();
const shellStyle = computed(() => ({
  height: `${metrics.totalHeight}px`,
  paddingTop: `${metrics.statusBarHeight}px`
}));
const contentStyle = computed(() => ({
  height: `${metrics.navigationBarHeight}px`,
  paddingLeft: `${props.horizontalPadding}rpx`,
  paddingRight: `${metrics.capsuleSafeRight}px`
}));
</script>

<template>
  <view
    class="custom-navbar"
    :class="{ 'custom-navbar--light': light }"
    :style="shellStyle"
  >
    <view class="custom-navbar-content" :style="contentStyle">
      <slot>
        <text v-if="title" class="custom-navbar-title">{{ title }}</text>
      </slot>
    </view>
  </view>
</template>

<style scoped lang="scss">
.custom-navbar {
  position: relative;
  z-index: 20;
  width: 100%;
  box-sizing: border-box;
}
.custom-navbar-content {
  display: flex;
  width: 100%;
  align-items: center;
  box-sizing: border-box;
}
.custom-navbar-title {
  overflow: hidden;
  color: #17243a;
  font-size: 34rpx;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.custom-navbar--light .custom-navbar-title {
  color: #fff;
}
</style>
