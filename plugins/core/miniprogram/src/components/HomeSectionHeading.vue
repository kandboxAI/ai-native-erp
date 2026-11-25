<script setup lang="ts">
withDefaults(defineProps<{ title: string; accent?: boolean }>(), {
  accent: true,
});
</script>

<template>
  <view class="section-heading" :class="{ 'section-heading--plain': !accent }">
    <view class="section-label">
      <text class="section-title">{{ title }}</text>
      <slot name="meta" />
    </view>
    <slot />
  </view>
</template>

<style scoped lang="scss">
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
  margin: 32rpx 6rpx 24rpx;
}
.section-label {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12rpx;
}
.section-title {
  position: relative;
  flex: 0 0 auto;
  padding-left: 20rpx;
  color: var(--hq-ink);
  font-size: 36rpx;
  font-weight: 700;
  line-height: 1.4;
}
.section-title::before {
  position: absolute;
  top: 10rpx;
  bottom: 10rpx;
  left: 0;
  width: 5rpx;
  background: var(--hq-primary);
  content: "";
}

.section-heading--plain .section-title {
  padding-left: 0;
}

.section-heading--plain .section-title::before {
  display: none;
}
</style>
