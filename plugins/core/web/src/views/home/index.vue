<script setup lang="ts">
import { onActivated, onBeforeUnmount, onMounted, ref } from "vue";
import PersonalWorkbench from "@/views/workbench/index.vue";
import { listHomeBanners, type MiniappBanner } from "@/api/miniappBanner";
import { getHttpErrorMessage } from "@/utils/http";

defineOptions({ name: "Welcome" });
const banners = ref<MiniappBanner[]>([]),
  loading = ref(false),
  error = ref("");
let loadedAt = 0,
  disposed = false;
async function loadBanners() {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const { data } = await listHomeBanners();
    if (disposed) return;
    banners.value = data.items.filter(item => !!item.image?.url);
    loadedAt = Date.now();
  } catch (cause) {
    if (!disposed) error.value = getHttpErrorMessage(cause, "轮播图片加载失败");
  } finally {
    if (!disposed) loading.value = false;
  }
}
onMounted(loadBanners);
onActivated(() => {
  if (Date.now() - loadedAt > 300000) void loadBanners();
});
onBeforeUnmount(() => {
  disposed = true;
});
</script>

<template>
  <div class="home-page">
    <section v-loading="loading" class="home-banner" aria-label="首页图片轮播">
      <el-carousel
        v-if="banners.length"
        height="100%"
        :interval="5000"
        :autoplay="banners.length > 1"
        :loop="banners.length > 1"
        :arrow="banners.length > 1 ? 'hover' : 'never'"
        :indicator-position="banners.length > 1 ? '' : 'none'"
      >
        <el-carousel-item v-for="banner in banners" :key="banner.id">
          <el-image
            :src="banner.image?.url"
            alt="首页轮播图"
            fit="cover"
            class="banner-image"
          >
            <template #error
              ><div class="banner-image-error">图片暂时无法显示</div></template
            >
          </el-image>
        </el-carousel-item>
      </el-carousel>
      <div v-else-if="!loading" class="banner-empty">
        <IconifyIconOnline icon="ri:image-line" />
        <h2>{{ error ? "图片暂时无法加载" : "暂无轮播图片" }}</h2>
        <p>{{ error || "配置首页轮播图后，将在这里展示" }}</p>
        <el-button v-if="error" @click="loadBanners">重新加载</el-button>
      </div>
    </section>
    <PersonalWorkbench surface="home" class="home-inbox" />
  </div>
</template>

<style scoped>
.home-page {
  display: grid;
  grid-template-rows: clamp(280px, 24vw, 360px) minmax(320px, 1fr);
  gap: 20px;
  width: 100%;
  max-width: 1600px;
  height: calc(100vh - 120px - var(--portal-header-height, 0px));
  min-height: 700px;
  margin-inline: auto;
}

.home-banner {
  position: relative;
  min-width: 0;
  overflow: hidden;
  background: #f1f5fa;
  border: 1px solid #e2eaf4;
  border-radius: 18px;
}

.home-banner :deep(.el-carousel) {
  position: absolute;
  inset: 0;
  height: 100%;
}

.home-banner :deep(.el-carousel__container) {
  height: 100%;
}

.banner-image {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}

.banner-empty,
.banner-image-error {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 0;
  padding: 24px;
  color: #728198;
  text-align: center;
}

.banner-empty > svg {
  font-size: 38px;
  color: #8aa4c4;
}

.banner-empty h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
}

.banner-empty p {
  margin: 0;
  line-height: 1.6;
}

.home-inbox {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.home-inbox :deep(.workbench-shell) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.home-inbox :deep(.detail-heading),
.home-inbox :deep(.workspace-tabs) {
  flex-shrink: 0;
}

.home-inbox :deep(.workspace-card) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.home-inbox :deep(.todo-section) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.home-inbox :deep(.todo-list) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
}

@media (width <= 768px) {
  .home-page {
    grid-template-rows: 240px auto;
    gap: 16px;
    height: auto;
    min-height: auto;
  }

  .banner-empty {
    min-height: 240px;
  }
}
</style>
