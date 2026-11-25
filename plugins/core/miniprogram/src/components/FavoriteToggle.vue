<script setup lang="ts">
import { computed } from "vue";
import { menuStore } from "@/store/menus";

const props = defineProps<{ menuId: string; title: string }>();
const selected = computed(() => menuStore.state.favoriteMenuIds.includes(props.menuId));
const disabled = computed(() =>
  menuStore.state.loading || menuStore.state.favoritesSaving || !menuStore.state.favoritesReady,
);

async function toggle() {
  if (disabled.value) return;
  const wasSelected = selected.value;
  try {
    if (await menuStore.toggleFavorite(props.menuId)) {
      uni.showToast({ title: wasSelected ? "已取消常用" : "已加入常用", icon: "none" });
    }
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : "保存失败，请重试",
      icon: "none",
    });
  }
}
</script>

<template>
  <button
    class="favorite-toggle"
    :class="{ selected }"
    :disabled="disabled"
    :aria-label="`${selected ? '取消常用' : '加入常用'}：${title}`"
    @tap.stop="toggle"
  >
    <image
      class="favorite-icon"
      :src="selected ? '/static/service-icons/favorite-selected.png' : '/static/tabbar/favorites.png'"
      mode="aspectFit"
    />
  </button>
</template>

<style scoped>
.favorite-toggle {
  display: flex;
  width: 72rpx;
  height: 72rpx;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 16rpx;
  line-height: 1;
}
.favorite-toggle::after { border: 0; }
.favorite-toggle.selected { background: transparent; }
.favorite-toggle[disabled] { opacity: 0.45; }
.favorite-icon { width: 44rpx; height: 44rpx; }
</style>
