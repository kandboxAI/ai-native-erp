<script setup lang="ts">
import { computed, ref } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import type { RecordData } from "../api";

const props = defineProps<{
  page: RecordData;
  assetUrl: (name: string) => string;
  bundleUrl: string;
}>();
const emit = defineEmits<{ select: [value: RecordData] }>();
const active = ref("document");

const rendered = computed(() => {
  const html = DOMPurify.sanitize(
    marked.parse(props.page.ocr_markdown || "", { async: false }) as string,
    {
      ALLOWED_TAGS: [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "br",
        "hr",
        "strong",
        "em",
        "s",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "img",
        "a",
        "sup",
        "sub",
        "span",
        "div",
      ],
      ALLOWED_ATTR: [
        "href",
        "src",
        "alt",
        "title",
        "colspan",
        "rowspan",
        "align",
      ],
      // 先阻止远程 URL，再解析 DOM；浏览器不直接请求 OCR 返回的外部链接。
      ALLOWED_URI_REGEXP: /^(?:ocr-[a-z0-9.-]+|#[a-z0-9_-]*)$/i,
    },
  );
  const document = new DOMParser().parseFromString(html, "text/html");
  const assets = new Set(
    (props.page.ocr_assets || [])
      .filter((asset: RecordData) => asset.asset)
      .map((asset: RecordData) => asset.asset),
  );
  document.querySelectorAll("img").forEach((image) => {
    const name = image.getAttribute("src") || "";
    const url = assets.has(name) ? props.assetUrl(name) : "";
    if (url) image.setAttribute("src", url);
    else {
      image.removeAttribute("src");
      image.setAttribute("alt", "关联图片未下载");
    }
  });
  document.querySelectorAll("a").forEach((link) => {
    const name = link.getAttribute("href") || "";
    const url = assets.has(name) ? props.assetUrl(name) : "";
    if (url) link.setAttribute("href", url);
    else link.removeAttribute("href");
  });
  return document.body.innerHTML;
});
</script>

<template>
  <section class="editor-section ocr-document">
    <div class="section-title">
      <h2>结构化文档</h2>
      <a :href="bundleUrl">下载完整文档包</a>
    </div>
    <div class="ocr-downloads">
      <a v-if="page.ocr_markdown_file" :href="assetUrl(page.ocr_markdown_file)"
        >下载文字稿</a
      >
      <a v-if="page.ocr_result_file" :href="assetUrl(page.ocr_result_file)"
        >下载版面数据</a
      >
    </div>
    <el-tabs v-model="active">
      <el-tab-pane label="文档预览" name="document"
        ><div class="markdown-document" v-html="rendered"
      /></el-tab-pane>
      <el-tab-pane label="版面区域" name="blocks">
        <div
          v-for="block in page.ocr_blocks || []"
          :key="block.id"
          class="layout-block"
        >
          <small
            >{{ block.label }} ·
            {{ block.bbox ? "可定位原图" : "坐标待核对" }}</small
          >
          <button
            :disabled="!block.bbox"
            @click="emit('select', { ...block, image: page.image })"
          >
            {{ block.text || "图片 / 空白区域" }}
          </button>
        </div>
      </el-tab-pane>
      <el-tab-pane label="文字稿" name="source">
        <pre class="extracted-text">{{ page.ocr_markdown }}</pre>
      </el-tab-pane>
    </el-tabs>
    <details v-if="page.ocr_assets?.length">
      <summary>关联图片 {{ page.ocr_assets.length }} 张</summary>
      <div
        v-for="(asset, index) in page.ocr_assets"
        :key="index"
        class="ocr-image-item"
      >
        <a v-if="asset.asset" :href="assetUrl(asset.asset)" target="_blank"
          >查看关联图片 {{ Number(index) + 1 }}</a
        >
        <span v-else class="warning-text"
          >关联图片 {{ Number(index) + 1 }} 暂不可用</span
        >
      </div>
    </details>
  </section>
</template>
