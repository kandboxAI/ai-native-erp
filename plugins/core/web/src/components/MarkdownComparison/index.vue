<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import { useResizeObserver } from "@vueuse/core";
import { useDark } from "@pureadmin/utils";
import { CodeDiff, type DiffResult } from "v-code-diff";
import MarkdownPreview from "@/components/MarkdownPreview/index.vue";

const props = withDefaults(
  defineProps<{
    oldContent: string | null;
    newContent: string | null;
    oldLabel?: string;
    newLabel?: string;
    unavailableReason?: string;
    review?: boolean;
  }>(),
  { oldLabel: "当前生效版本", newLabel: "待审核版本", unavailableReason: "" }
);
const container = ref<HTMLElement>();
const width = ref(1000);
const mode = ref("diff");
const outputFormat = ref<"side-by-side" | "line-by-line">(
  props.review ? "line-by-line" : "side-by-side"
);
const changedLines = ref(0);
const { isDark } = useDark();
useResizeObserver(container, entries => {
  width.value = entries[0].contentRect.width;
});
const canSplit = computed(() => width.value >= 760);
const activeFormat = computed(() =>
  canSplit.value ? outputFormat.value : "line-by-line"
);
// null 表示原文不可用；只有明确的新建文档才传入空字符串作旧版，避免误报整篇新增。
const canCompare = computed(
  () => props.oldContent != null && props.newContent != null
);
const isIdentical = computed(
  () =>
    canCompare.value &&
    props.oldContent.replace(/\r\n/g, "\n") ===
      props.newContent.replace(/\r\n/g, "\n")
);

async function onDiff({ stat }: DiffResult) {
  if (!props.review) return;
  changedLines.value = stat.addNum + stat.delNum;
  await nextTick();
  // 只滚动差异区，避免打开审批时跳过读取许可和变更原因。
  const viewport =
    container.value?.querySelector<HTMLElement>(".code-diff-view");
  const firstChange = viewport?.querySelector("[data-diff-change]");
  if (viewport && firstChange) {
    viewport.scrollTop +=
      firstChange.getBoundingClientRect().top -
      viewport.getBoundingClientRect().top -
      viewport.clientHeight / 3;
  }
}
</script>

<template>
  <div ref="container" class="markdown-comparison" :class="{ review }">
    <div class="comparison-toolbar">
      <el-radio-group v-model="mode" size="small" aria-label="版本对比视图">
        <el-radio-button value="diff">变动对比</el-radio-button>
        <el-radio-button value="preview">Markdown 预览</el-radio-button>
      </el-radio-group>
      <el-radio-group
        v-if="mode === 'diff' && canCompare && (!review || canSplit)"
        v-model="outputFormat"
        size="small"
        aria-label="差异排列方式"
      >
        <el-radio-button value="side-by-side" :disabled="!canSplit"
          >左右对比</el-radio-button
        >
        <el-radio-button value="line-by-line">{{
          review ? "统一视图" : "上下对比"
        }}</el-radio-button>
      </el-radio-group>
    </div>
    <el-alert
      v-if="!canCompare"
      :title="
        unavailableReason ||
        '缺少完整正文，暂时无法计算变动；请核对原文或原件。'
      "
      type="info"
      :closable="false"
    />
    <template v-if="mode === 'diff' && canCompare">
      <p v-if="!review" class="comparison-hint">
        红色为删除，绿色为新增；行内高亮标出具体文字变化，箭头可跳转变动。
      </p>
      <el-alert
        v-if="isIdentical"
        title="两个版本正文一致"
        type="info"
        :closable="false"
      />
      <CodeDiff
        :old-string="oldContent"
        :new-string="newContent"
        :filename="oldLabel"
        :new-filename="newLabel"
        :output-format="activeFormat"
        :theme="isDark ? 'dark' : 'light'"
        language="plaintext"
        diff-style="char"
        :force-inline-comparison="true"
        :no-diff-line-feed="true"
        :context="3"
        :hide-navigation="review && changedLines <= 1"
        max-height="480px"
        @diff="onDiff"
      >
        <template #stat="{ stat }">
          <span class="diff-stat-added">新增 {{ stat.additionsNum }} 行</span>
          <span class="diff-stat-deleted">删除 {{ stat.deletionsNum }} 行</span>
        </template>
      </CodeDiff>
    </template>
    <div v-else class="comparison-previews" :class="{ stacked: !canSplit }">
      <section>
        <h4>{{ oldLabel }}</h4>
        <MarkdownPreview v-if="oldContent" :content="oldContent" />
        <p v-else class="comparison-hint">
          {{
            oldContent == null ? "旧版完整正文不可用" : "新建文档，无旧版正文"
          }}
        </p>
      </section>
      <section>
        <h4>{{ newLabel }}</h4>
        <MarkdownPreview v-if="newContent" :content="newContent" />
        <p v-else class="comparison-hint">所选版本没有可预览的正文</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.markdown-comparison {
  width: 100%;
  min-width: 0;
  margin-top: 16px;
}
.markdown-comparison.review {
  margin-top: 0;
}
.review .comparison-toolbar {
  gap: 8px;
  margin-bottom: 8px;
}
.review .diff-stat-added,
.review .diff-stat-deleted {
  white-space: nowrap;
}
.comparison-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 12px;
}
.comparison-hint {
  margin: 10px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.comparison-previews {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.comparison-previews.stacked {
  grid-template-columns: 1fr;
}
.comparison-previews section {
  min-width: 0;
}
.comparison-previews h4 {
  margin: 8px 0;
}
</style>
