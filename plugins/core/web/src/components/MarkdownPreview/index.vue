<script setup lang="ts">
import { computed, ref } from "vue";
import { Marked } from "marked";
import DOMPurify from "dompurify";

const props = defineProps<{ content: string; previewOnly?: boolean }>();
const mode = ref("preview");
const parser = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    checkbox: ({ checked }) => (checked ? "☑ " : "☐ ")
  }
});
// 正文来自业务文档，解析后仍须清洗，避免预览执行脚本或注入页面样式。
const html = computed(() =>
  DOMPurify.sanitize(parser.parse(props.content, { async: false }), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "input", "button"],
    FORBID_ATTR: ["style"]
  })
);

function openLink(event: MouseEvent) {
  const link = (event.target as HTMLElement).closest("a");
  if (!link) return;
  event.preventDefault();
  const href = link.getAttribute("href");
  if (!href) return;
  const url = new URL(href, window.location.href);
  if (["https:", "http:"].includes(url.protocol))
    window.open(url.href, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <div
    class="markdown-viewer"
    :class="{ 'markdown-viewer--inline': previewOnly }"
  >
    <el-radio-group
      v-if="!previewOnly"
      v-model="mode"
      size="small"
      aria-label="正文显示方式"
    >
      <el-radio-button value="preview">Markdown 预览</el-radio-button>
      <el-radio-button value="source">源码</el-radio-button>
    </el-radio-group>
    <!-- 源码保持原样，供审核人核对 Markdown 标记和完整正文。 -->
    <pre v-if="!previewOnly && mode === 'source'" class="markdown-source">{{
      content
    }}</pre>
    <div
      v-else
      class="markdown-body"
      aria-label="Markdown 正文预览"
      @click="openLink"
      v-html="html"
    />
  </div>
</template>

<style scoped>
.markdown-viewer {
  width: 100%;
  min-width: 0;
}
.markdown-body,
.markdown-source {
  min-height: 200px;
  max-height: 480px;
  padding: 16px;
  margin: 10px 0 0;
  overflow: auto;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.8;
  text-align: left;
  white-space: normal;
  overflow-wrap: anywhere;
}
/* 来源弹窗使用外层滚动区域，正文不再嵌套边框、工具栏和滚动条。 */
.markdown-viewer--inline .markdown-body {
  min-height: 0;
  max-height: none;
  padding: 0;
  margin: 0;
  overflow: visible;
  border: 0;
}
.markdown-source {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre-wrap;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 1em 0 0.6em;
  font-weight: 600;
  line-height: 1.4;
}
.markdown-body :deep(h1) {
  font-size: 1.8em;
}
.markdown-body :deep(h2) {
  font-size: 1.5em;
}
.markdown-body :deep(h3) {
  font-size: 1.25em;
}
.markdown-body :deep(p),
.markdown-body :deep(pre),
.markdown-body :deep(table),
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.8em 0;
}
.markdown-body :deep(ul) {
  list-style: disc;
  padding-left: 1.8em;
}
.markdown-body :deep(ol) {
  list-style: decimal;
  padding-left: 1.8em;
}
.markdown-body :deep(blockquote) {
  padding-left: 1em;
  margin: 1em 0;
  color: var(--el-text-color-secondary);
  border-left: 3px solid var(--el-border-color);
}
.markdown-body :deep(pre) {
  padding: 12px;
  overflow: auto;
  background: var(--el-fill-color-light);
}
.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  background: var(--el-fill-color-light);
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--el-border-color);
  text-align: left;
}
.markdown-body :deep(a) {
  color: var(--el-color-primary);
  text-decoration: underline;
}
.markdown-body :deep(img) {
  max-width: 100%;
}
</style>
