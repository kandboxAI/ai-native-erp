<script setup lang="ts">
import { computed, ref, watch } from "vue";
const props = withDefaults(defineProps<{ src?: string; size?: number }>(), {
  src: "/static/service-icons/apps.png",
  size: 92,
});
const failed = ref(false);
watch(
  () => props.src,
  () => {
    failed.value = false;
  },
);
// Colored companions ship beside the original icons in their owning plugin.
const tile = computed(() => props.src.replace(/\.png$/, "-tile.png"));
</script>
<template>
  <view
    class="application-icon"
    :style="{ width: `${size}rpx`, height: `${size}rpx` }"
  >
    <image
      v-if="!failed"
      class="application-art"
      :src="tile"
      mode="aspectFit"
      @error="failed = true"
    />
    <image v-else class="application-fallback" :src="src" mode="aspectFit" />
  </view>
</template>
<style scoped>
.application-icon {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #eaf2ff;
  border-radius: 26%;
}
.application-art {
  display: block;
  width: 100%;
  height: 100%;
}
.application-fallback {
  display: block;
  width: 62%;
  height: 62%;
}
</style>
