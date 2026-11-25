<script setup lang="ts">
import type { HomeBanner } from "@/api/homeBanner";
defineProps<{ items: HomeBanner[] }>();
</script>

<template>
  <swiper
    v-if="items.length"
    class="home-carousel"
    :indicator-dots="items.length > 1"
    :autoplay="items.length > 1"
    :circular="items.length > 1"
    :interval="5000"
    :duration="450"
    indicator-color="rgba(255,255,255,0.5)"
    indicator-active-color="#ffffff"
  >
    <swiper-item v-for="item in items" :key="item.id">
      <image class="banner-image" :src="item.image?.url" mode="aspectFill" aria-label="首页轮播图" />
    </swiper-item>
  </swiper>
</template>

<style scoped>
.home-carousel {
  height: 330rpx;
  overflow: hidden;
  border-radius: 26rpx;
  background: #e8eef7;
}
.banner-image { display: block; width: 100%; height: 100%; }
</style>
