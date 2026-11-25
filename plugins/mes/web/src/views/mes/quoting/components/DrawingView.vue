<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { binary } from "../api";
import type { RecordData } from "../api";

const props = defineProps<{
  imageUrl: string;
  page: RecordData;
  selected?: RecordData | null;
}>();
const emit = defineEmits<{ select: [value: RecordData] }>();
const imageSource = ref("");
const error = ref("");
const loading = ref(false);
const showLabels = ref(true);
const zoom = ref(100);
const tokens = computed(() =>
  (props.page.ocr_tokens ?? props.page.tokens ?? [])
    .filter((t: RecordData) => t.dimension_candidate)
    .slice(0, 160),
);
const layoutBlocks = computed(() =>
  (props.page.ocr_blocks ?? []).filter((block: RecordData) => block.bbox),
);
const box = (bbox: number[]) => ({
  x: bbox[0] * 1000,
  y: bbox[1] * 1000,
  width: (bbox[2] - bbox[0]) * 1000,
  height: (bbox[3] - bbox[1]) * 1000,
});

watch(
  () => props.imageUrl,
  async (url, _, onCleanup) => {
    let disposed = false;
    let objectUrl = "";
    onCleanup(() => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    });
    loading.value = true;
    error.value = "";
    imageSource.value = "";
    try {
      // 直接复用解析时生成的当前页预览，避免浏览器重复下载和解析整份 PDF。
      const blob = await binary(url);
      if (disposed) return;
      objectUrl = URL.createObjectURL(blob);
      imageSource.value = objectUrl;
    } catch (reason) {
      if (!disposed) {
        console.error("图纸预览失败", reason);
        imageFailed();
      }
    }
  },
  { immediate: true },
);

function imageFailed() {
  loading.value = false;
  error.value =
    "当前页预览读取失败，请刷新页面重试，也可下载上方 PDF 原件查看。";
}
</script>

<template>
  <div class="drawing-view">
    <div class="viewer-toolbar">
      <span
        >第 {{ page.number }} 页 ·
        {{
          page.ocr_blocks
            ? "图纸识别标注"
            : page.ocr_tokens
              ? "图纸识别标注"
              : "图纸文字标注"
        }}</span
      >
      <div class="inline-actions">
        <el-switch v-model="showLabels" active-text="标注候选" /><el-button
          size="small"
          @click="zoom = Math.max(60, zoom - 20)"
          >−</el-button
        ><span>{{ zoom }}%</span
        ><el-button size="small" @click="zoom = Math.min(240, zoom + 20)"
          >＋</el-button
        >
      </div>
    </div>
    <div class="drawing-scroll" v-loading="loading">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div class="drawing-paper" :style="{ width: zoom + '%' }">
        <img
          v-if="imageSource"
          :src="imageSource"
          :width="page.width"
          :height="page.height"
          :alt="`第 ${page.number} 页图纸预览`"
          @load="loading = false"
          @error="imageFailed"
        />
        <svg
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          aria-label="图纸证据覆盖层"
        >
          <g
            v-if="showLabels"
            v-for="block in layoutBlocks"
            :key="block.id"
            class="layout-region"
            @click="emit('select', block)"
          >
            <title>{{ block.label }}：{{ block.text }}</title>
            <rect v-bind="box(block.bbox)" />
          </g>
          <g
            v-if="showLabels"
            v-for="(token, index) in tokens"
            :key="token.id"
            class="dimension-mark"
            @click="emit('select', token)"
          >
            <title>{{ token.text }}（标注候选，需复核）</title>
            <rect v-bind="box(token.bbox)" />
            <circle
              :cx="token.bbox[0] * 1000"
              :cy="Math.max(8, token.bbox[1] * 1000 - 5)"
              r="6"
            />
            <text
              :x="token.bbox[0] * 1000"
              :y="Math.max(8, token.bbox[1] * 1000 - 5) + 2"
            >
              {{ Number(index) + 1 }}
            </text>
          </g>
          <rect
            v-if="selected?.bbox"
            v-bind="box(selected.bbox)"
            class="selected-evidence"
          />
        </svg>
      </div>
    </div>
  </div>
</template>
