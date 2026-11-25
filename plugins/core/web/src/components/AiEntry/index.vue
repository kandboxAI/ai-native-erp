<script setup lang="ts">
import { computed, nextTick, onDeactivated, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { InputInstance } from "element-plus";
import SearchFooter from "@/layout/components/lay-search/components/SearchFooter.vue";
import SearchIcon from "~icons/ri/search-line";
import SparklingIcon from "~icons/ri/sparkling-line";
import EnterOutlined from "@/assets/svg/enter_outlined.svg?component";
import { useAiPageContextStore } from "@/store/modules/aiPageContext";
import {
  captureAiQuestion,
  captureAiPage,
  type AiPageContext,
  type AiPageSnapshot,
  type AiPresetQuestion
} from "@/utils/aiPageContext";
import { askDesktopAssistant } from "@/utils/desktopAssistant";
import { resolveAiPageSnapshot } from "@/api/aiPageSnapshot";
import { formatAiPageQuestion } from "@/utils/aiPageSnapshot";
import { getHttpErrorMessage } from "@/utils/http";
import { message } from "@/utils/message";

const props = defineProps<{
  subjectKey: string;
  subjectTitle: string;
  questions: readonly AiPresetQuestion[];
  appearance?: "icon" | "button";
  getSnapshot?: () => AiPageSnapshot;
}>();
const id = useId();
const desktop = Boolean(window.erpDesktop);
const assistantName = __PRODUCT_BRANDING__.assistant_name;
const askLabel = `询问${assistantName}`;
const router = useRouter();
const route = useRoute();
const context = useAiPageContextStore();
const visible = ref(false);
const busy = ref(false);
const keyword = ref("");
const activeIndex = ref(0);
const input = ref<InputInstance>();
const captured = ref<AiPageContext | null>(null);
const questions = computed<readonly AiPresetQuestion[]>(() => {
  const prompt = keyword.value.trim();
  return prompt
    ? [{ key: "custom_question", label: prompt, prompt }, ...props.questions]
    : props.questions;
});
watch(keyword, () => {
  activeIndex.value = 0;
});
watch(
  () => [route.path, context.revision],
  () => {
    visible.value = false;
    captured.value = null;
  }
);
onDeactivated(() => {
  visible.value = false;
  captured.value = null;
});

async function send(question: AiPresetQuestion) {
  if (busy.value || !captured.value) return;
  const page = captured.value;
  const revision = context.revision;
  const snapshot = captureAiQuestion(
    page,
    props.subjectKey,
    props.subjectTitle,
    question.key
  );
  busy.value = true;
  try {
    const result = page.snapshot
      ? await resolveAiPageSnapshot(page.page_key, page.snapshot.receipts)
      : undefined;
    const prompt = formatAiPageQuestion(
      question.prompt,
      snapshot,
      result?.data,
      page.snapshot?.metric_keys
    );
    if (revision !== context.revision || route.path !== page.path) return;
    visible.value = false;
    await nextTick();
    if (revision !== context.revision || route.path !== page.path) return;
    // Send one readable message so desktop bridges cannot wrap its context in JSON.
    await askDesktopAssistant(router, prompt);
  } catch (error) {
    message(
      getHttpErrorMessage(
        error,
        page.snapshot
          ? "页面快照校验失败，请刷新页面后重新提问"
          : "智能体暂时无法打开，请稍后重试"
      ),
      { type: "error" }
    );
  } finally {
    busy.value = false;
  }
}

function open() {
  if (busy.value) return;
  if (!desktop) {
    return;
  }
  if (window.erpDesktop?.assistantContextVersion !== 1) {
    message("请更新桌面客户端后使用页面 AI 分析", { type: "warning" });
    return;
  }
  const page = context.page;
  if (!page || page.path !== route.path) {
    message("当前页面上下文尚未就绪，请刷新后重试", { type: "warning" });
    return;
  }
  captured.value = captureAiPage({
    ...page,
    // A card can narrow its data sources. An empty result must not fall back
    // to the whole-page snapshot when that card has no loaded data.
    ...(props.getSnapshot ? { snapshot: props.getSnapshot() } : {})
  });
  keyword.value = "";
  activeIndex.value = 0;
  visible.value = true;
}

function onKeydown(event: KeyboardEvent) {
  if (event.isComposing) return;
  if (!["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) return;
  event.preventDefault();
  event.stopPropagation();
  if (event.key === "Escape") visible.value = false;
  else if (event.key === "Enter") {
    const question = questions.value[activeIndex.value];
    if (question) void send(question);
  } else if (questions.value.length) {
    activeIndex.value =
      (activeIndex.value +
        (event.key === "ArrowDown" ? 1 : -1) +
        questions.value.length) %
      questions.value.length;
  }
}

async function focusSearch() {
  await nextTick();
  input.value?.focus();
}
</script>

<template>
  <span v-if="desktop || appearance === 'button'" class="ai-entry-container">
    <el-tooltip
      :disabled="appearance !== 'button' || busy"
      :content="
        desktop
          ? `结合当前页面向${assistantName}提问`
          : `请在桌面客户端中使用${assistantName}`
      "
      placement="bottom-end"
      :show-after="300"
    >
      <span class="ai-entry-trigger">
        <button
          class="ai-entry"
          :class="{ 'ai-entry--button': appearance === 'button' }"
          type="button"
          :disabled="busy || !desktop"
          :aria-label="
            appearance === 'button'
              ? `${askLabel}：${subjectTitle}`
              : `用 AI 分析${subjectTitle}`
          "
          :title="appearance === 'button' ? undefined : askLabel"
          :aria-haspopup="desktop ? 'dialog' : undefined"
          @click.stop="open"
        >
          <svg
            v-if="appearance === 'button'"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              d="M14 4H6a3 3 0 0 0-3 3v8a3 3 0 0 0 3 3h1v3l4-3h7a3 3 0 0 0 3-3v-4"
            />
            <path
              d="m18 2 1.1 3.9L23 7l-3.9 1.1L18 12l-1.1-3.9L13 7l3.9-1.1Z"
            />
            <path d="M7 11h3m-3 3h8" />
          </svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true">
            <circle class="ai-entry-ring" cx="12" cy="12" r="8" />
            <circle
              class="ai-entry-ring ai-entry-ring-delayed"
              cx="12"
              cy="12"
              r="8"
            />
            <path
              d="M12 7.5 13.3 10.7 16.5 12 13.3 13.3 12 16.5 10.7 13.3 7.5 12 10.7 10.7Z"
            />
          </svg>
          <span v-if="appearance === 'button'">{{ askLabel }}</span>
        </button>
      </span>
    </el-tooltip>
    <el-dialog
      v-if="desktop"
      v-model="visible"
      :title="`AI 分析 · ${subjectTitle}`"
      class="pure-search-dialog"
      align-center
      :show-close="false"
      width="min(640px, 88vw)"
      :style="{ borderRadius: '6px' }"
      append-to-body
      @opened="focusSearch"
    >
      <div class="ai-question-panel" @keydown="onKeydown">
        <el-input
          ref="input"
          v-model="keyword"
          size="large"
          clearable
          placeholder="输入问题，按 Enter 提问"
          aria-label="输入问题"
          :maxlength="2000"
          role="combobox"
          :aria-controls="`${id}-questions`"
          :aria-expanded="true"
          :aria-activedescendant="
            questions.length ? `${id}-question-${activeIndex}` : undefined
          "
          autocomplete="off"
        >
          <template #prefix>
            <IconifyIconOffline
              :icon="SearchIcon"
              class="text-primary size-6"
            />
          </template>
        </el-input>
        <div class="ai-question-context">
          <p class="ai-context-label">
            {{ captured?.title }} › {{ subjectTitle }}
            <span v-if="captured?.filters.period_label">
              · {{ captured.filters.period_label }}
            </span>
          </p>
          <p v-if="captured?.snapshot" class="ai-demo-note">
            {{
              captured.snapshot.receipts.length
                ? `本次附带已加载的数据快照（${captured.snapshot.receipts.length} 个数据源）`
                : "尚无已加载的数据快照，将说明数据未就绪。"
            }}
          </p>
          <p v-if="captured?.data_source === 'demo'" class="ai-demo-note">
            当前页面为演示数据。智能体会区分示例与真实查询结果。
          </p>
        </div>
        <el-scrollbar max-height="calc(90vh - 200px)">
          <div
            :id="`${id}-questions`"
            class="ai-question-results"
            role="listbox"
            aria-label="选择分析问题"
          >
            <button
              v-for="(question, index) in questions"
              :id="`${id}-question-${index}`"
              :key="`${index}-${question.key}`"
              class="ai-question-option"
              :class="{ active: index === activeIndex }"
              type="button"
              role="option"
              :aria-selected="index === activeIndex"
              @mouseenter="activeIndex = index"
              @click="send(question)"
            >
              <IconifyIconOffline :icon="SparklingIcon" aria-hidden="true" />
              <span class="ai-question-title">
                <span
                  v-if="keyword.trim() && index === 0"
                  class="ai-question-custom-label"
                  >询问 AI</span
                >
                {{ question.label }}
              </span>
              <EnterOutlined class="ai-question-enter" aria-hidden="true" />
            </button>
            <p v-if="!questions.length" class="ai-context-label">
              输入你想了解的问题，按 Enter 提问。
            </p>
          </div>
        </el-scrollbar>
      </div>
      <template #footer>
        <SearchFooter :total="questions.length" />
      </template>
    </el-dialog>
  </span>
</template>

<style scoped>
.ai-entry-container,
.ai-entry-trigger {
  display: inline-flex;
}

.ai-entry {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 2px;
  color: var(--el-color-primary);
  cursor: pointer;
  background: var(--el-color-primary-light-9);
  border: 0;
  border-radius: 8px;
}

.ai-entry:not(:disabled):hover,
.ai-entry:focus-visible,
.ai-entry-trigger:focus-visible {
  outline: 2px solid var(--el-color-primary-light-5);
  outline-offset: 2px;
}

.ai-entry svg {
  width: 24px;
  height: 24px;
  overflow: visible;
  fill: currentcolor;
}

.ai-entry--button {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  width: auto;
  height: 36px;
  padding: 0 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--app-button-primary-ink, var(--el-color-primary));
  white-space: nowrap;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  transition:
    background-color 0.15s,
    border-color 0.15s;
}

.ai-entry--button svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentcolor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ai-entry--button:not(:disabled):hover {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}

.ai-entry-platform {
  padding-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
  border-left: 1px solid var(--el-border-color);
}

.ai-entry--button:disabled {
  color: var(--el-disabled-text-color);
  cursor: not-allowed;
  background: var(--el-disabled-bg-color);
  border-color: var(--el-disabled-border-color);
}

.ai-entry--button:disabled svg {
  color: var(--el-disabled-text-color);
}

.ai-entry-ring {
  fill: none;
  stroke: currentcolor;
  stroke-width: 1;
  transform-origin: center;
  animation: ai-ripple 3s ease-out infinite;
}

.ai-entry-ring-delayed {
  animation-delay: -1.5s;
}

@keyframes ai-ripple {
  0% {
    opacity: 0.5;
    transform: scale(0.45);
  }

  100% {
    opacity: 0;
    transform: scale(1.2);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-entry-ring {
    opacity: 0.3;
    animation: none;
  }

  .ai-entry-ring-delayed {
    display: none;
  }
}

.ai-context-label {
  margin: 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--el-text-color-secondary);
}

.ai-question-context {
  margin-top: 12px;
}

.ai-demo-note {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--el-color-warning-dark-2);
}

.ai-question-results {
  padding-bottom: 12px;
}

.ai-question-option {
  display: flex;
  align-items: center;
  width: 100%;
  height: 56px;
  padding: 14px;
  margin-top: 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  background: var(--el-bg-color);
  border: 0.1px solid #ccc;
  border-radius: 4px;
  transition: font-size 0.16s;
}

.ai-question-option.active,
.ai-question-option:focus-visible {
  font-size: 16px;
  color: #fff;
  outline: none;
  background: var(--el-color-primary);
}

.ai-question-title {
  flex: 1;
  min-width: 0;
  margin-left: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-question-custom-label {
  margin-right: 8px;
  font-weight: 600;
}

.ai-question-enter {
  flex-shrink: 0;
}
</style>
