<script setup lang="ts">
import { computed, ref } from "vue";
import { onShow, onReachBottom } from "@dcloudio/uni-app";
import { recommendTodoPriority, type TodoItem } from "@/api/todo";
import AppTabBar from "@/components/AppTabBar.vue";
import CustomNavbar from "@/components/CustomNavbar.vue";
import HomeSectionHeading from "@/components/HomeSectionHeading.vue";
import { todoInboxStore, type InboxMessage } from "@/store/inbox";
import { openTodoEntry, todoEntryTarget } from "@/utils/todoEntry";

const tasks = computed(() => todoInboxStore.state.rows);
const error = computed(() => todoInboxStore.state.error);
const loading = computed(() => todoInboxStore.state.loading);
const total = computed(() => todoInboxStore.state.total);
const canRank = computed(() => !error.value && tasks.value.length > 0);

const ranking = ref(false);
const recommendations = ref<TodoItem[] | null>(null);
const recommendationTotal = ref(0);

function load(more = false) {
  if (loading.value || ranking.value) return;
  if (!more) recommendations.value = null;
  if (more) return todoInboxStore.load(true);
  void todoInboxStore.refreshCounts();
  return todoInboxStore.select("todo");
}
async function rankTodos() {
  if (ranking.value || loading.value || !canRank.value) return;
  ranking.value = true;
  try {
    const result = await recommendTodoPriority();
    recommendations.value = result.items.slice(0, 4);
    recommendationTotal.value = result.total;
  } catch (reason) {
    uni.showToast({
      title:
        reason instanceof Error
          ? reason.message
          : "AI 排序暂不可用，请稍后重试",
      icon: "none",
    });
  } finally {
    ranking.value = false;
  }
}

function openRecommendation(task: TodoItem) {
  openTodoEntry(todoEntryTarget(task), task.title, task.summary);
}

function open(task: InboxMessage) {
  openTodoEntry(task.target, task.title, task.content);
}
onShow(() => {
  void load();
});
onReachBottom(() => {
  void load(true);
});
</script>

<template>
  <view class="page-shell portal-page todo-page">
    <view class="portal-navbar todo-navbar">
      <CustomNavbar title="待办" :horizontal-padding="28" />
    </view>

    <view class="todo-overview card">
      <image
        class="overview-icon"
        src="/static/service-icons/tasks.png"
        mode="aspectFit"
      />
      <view class="overview-main">
        <text class="pending-label">待处理</text>
        <view class="pending-count">
          <text class="pending-number">{{
            (loading && !tasks.length) || error ? "—" : total
          }}</text>
          <text class="pending-unit">项</text>
        </view>
      </view>
    </view>

    <view class="ai-priority">
      <HomeSectionHeading title="AI 优先处理" :accent="false">
        <button
          class="toolbar-action smart-action btn-secondary btn-sm"
          :disabled="!canRank || ranking || loading"
          @tap="rankTodos"
        >
          {{ ranking ? "排序中…" : "智能排序" }}
        </button>
      </HomeSectionHeading>
      <view class="ai-content card">
        <text class="section-subtitle">结合事项内容推荐，原因仅供参考</text>
        <text v-if="error" class="ranking-note"
          >待办加载失败，重试后可使用智能排序</text
        >
        <text v-else-if="loading && !tasks.length" class="ranking-note"
          >待办加载完成后可使用智能排序</text
        >
        <text v-else-if="!tasks.length" class="ranking-note"
          >暂无待处理事项，有待办后可使用智能排序</text
        >
        <text
          v-else-if="recommendations === null && !ranking"
          class="ranking-note"
          >点击智能排序，推荐当前应优先处理的事项（仅通用待办）</text
        >

        <view
          v-if="canRank && (ranking || recommendations !== null)"
          class="priority-panel"
        >
          <view class="priority-heading">
            <text class="priority-title">优先处理建议</text>
            <button
              v-if="!ranking"
              class="toolbar-action collapse-action btn-secondary btn-sm"
              @tap="recommendations = null"
            >
              收起
            </button>
          </view>
          <text v-if="ranking" class="priority-note"
            >正在分析通用待办，请稍候…</text
          >
          <template v-else>
            <text class="priority-note"
              >从通用待办中最多推荐 4 项，原因仅供参考{{
                recommendationTotal > 100 ? "；本次从原排序前 100 项中推荐" : ""
              }}</text
            >
            <text v-if="!recommendations?.length" class="priority-note"
              >暂无可推荐的通用待办，全部事项仍可在下方办理</text
            >
            <view
              v-for="(task, index) in recommendations"
              :key="task.id"
              class="task-card recommendation-card pressable"
              @tap="openRecommendation(task)"
            >
              <image v-if="task.avatar_url" class="task-icon task-avatar" :src="task.avatar_url" mode="aspectFill" @error="task.avatar_url = null" />
              <view v-else class="task-icon">{{ index + 1 }}</view>
              <view class="task-content grow">
                <text class="task-title">{{ task.title }}</text>
                <text class="task-summary">{{
                  task.summary || "暂无业务摘要"
                }}</text>
                <text class="priority-reason"
                  >优先原因：{{ task.ai_priority_reason }}</text
                >
                <text class="task-link">查看并办理 ›</text>
              </view>
            </view>
          </template>
        </view>
      </view>
    </view>

    <HomeSectionHeading title="全部待处理事项" :accent="false">
      <button
        class="toolbar-action refresh-action btn-secondary btn-sm"
        :disabled="loading || ranking"
        :aria-label="loading ? '正在刷新待办' : '刷新待办'"
        @tap="load()"
      >
        {{ loading ? "刷新中…" : "刷新" }}
      </button>
    </HomeSectionHeading>
    <text v-if="tasks.length && !error" class="list-caption"
      >按接收时间倒序</text
    >

    <view
      v-if="error"
      class="state-panel state-panel--error card"
      @tap="load()"
    >
      <view class="state-icon">!</view>
      <text class="state-title">待办加载失败</text>
      <text class="state-copy">{{ error }}</text>
      <button
        class="toolbar-action smart-action retry-action btn-secondary btn-sm"
        :disabled="loading || ranking"
        @tap.stop="load()"
      >
        重新加载
      </button>
    </view>

    <view v-else-if="loading && !tasks.length" class="state-panel card">
      <view class="state-icon">…</view>
      <text class="state-title">正在加载待办</text>
    </view>

    <view v-else-if="!tasks.length" class="state-panel card">
      <image
        class="state-image"
        src="/static/service-icons/tasks.png"
        mode="aspectFit"
      />
      <text class="state-title">当前没有待办</text>
      <text class="state-copy">新的事项会显示在这里，可点击刷新查看</text>
    </view>

    <view v-else class="task-list">
      <view
        v-for="task in tasks"
        :key="task.id"
        class="task-card card pressable"
        @tap="open(task)"
      >
        <image v-if="task.avatar_url" class="task-icon task-avatar" :src="task.avatar_url" mode="aspectFill" @error="task.avatar_url = null" />
        <view v-else class="task-icon">办</view>
        <view class="task-content grow">
          <view class="row between">
            <text class="task-title">{{ task.title || "待办事项" }}</text>
            <text class="status-tag">待处理</text>
          </view>
          <text class="task-summary">
            {{ task.content || "暂无业务摘要" }}
          </text>
          <view class="task-footer">
            <text v-if="task.time" class="task-time">{{ task.time }}</text>
            <text class="task-link">{{ task.target ? "查看并办理" : "查看详情" }} ›</text>
          </view>
        </view>
      </view>
    </view>
    <button
      v-if="!error && tasks.length < total"
      class="toolbar-action load-more btn-secondary btn-sm"
      :disabled="loading || ranking"
      @tap="load(true)"
    >
      {{ loading ? "正在加载" : "加载更多" }}
    </button>
    <AppTabBar current="messages" />
  </view>
</template>

<style scoped lang="scss">
.page-shell.todo-page {
  padding-top: 0;
}

.todo-page .todo-overview.card {
  position: relative;
  display: flex;
  gap: 24rpx;
  align-items: center;
  padding: 28rpx 30rpx;
  overflow: hidden;
  background: linear-gradient(115deg, #e7f0ff, #f4f8ff 75%, #fff);
  border: 1rpx solid #d4e5ff;
  box-shadow: 0 8rpx 24rpx rgba(23, 105, 224, 0.08);
}

.todo-overview::after {
  position: absolute;
  top: -76rpx;
  right: -44rpx;
  width: 180rpx;
  height: 180rpx;
  border: 24rpx solid rgba(23, 105, 224, 0.045);
  border-radius: 50%;
  content: "";
}

.overview-icon {
  position: relative;
  z-index: 1;
  width: 88rpx;
  height: 88rpx;
  flex: 0 0 88rpx;
  box-sizing: border-box;
  padding: 12rpx;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 20rpx;
}

.overview-main {
  position: relative;
  z-index: 1;
  min-width: 0;
  flex: 1;
}

.pending-label {
  display: block;
  color: var(--hq-primary-dark);
  font-size: 26rpx;
  font-weight: 500;
  line-height: 1.5;
}

.pending-count {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx 12rpx;
  align-items: baseline;
  margin-top: 6rpx;
}

.pending-number {
  min-width: 0;
  color: var(--hq-primary);
  font-size: 56rpx;
  font-weight: 700;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.pending-unit {
  color: var(--hq-muted);
  font-size: 24rpx;
}

.toolbar-action {
  min-width: 144rpx;
  flex: 0 0 auto;
  padding: 0 20rpx;
  margin: 0;
  border: 0;
  font-weight: 500;
  white-space: nowrap;

  &[disabled] {
    color: #a4adba;
    background: #f4f6f9;
    box-shadow: none;
  }
}

.refresh-action {
  width: 144rpx;
}

.ai-content {
  padding: 26rpx 28rpx;
}

.section-subtitle,
.ranking-note,
.priority-note {
  display: block;
  font-size: 24rpx;
  line-height: 1.6;
}

.section-subtitle {
  color: var(--hq-body);
}

.ranking-note {
  margin-top: 12rpx;
  color: var(--hq-muted);
}

.priority-panel {
  padding-top: 20rpx;
  margin-top: 20rpx;
  border-top: 1rpx solid var(--hq-line);
}

.priority-heading {
  display: flex;
  gap: 12rpx;
  align-items: center;
  justify-content: space-between;
}

.priority-title {
  min-width: 0;
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 600;
}

.collapse-action {
  min-width: 100rpx;
}

.priority-note {
  margin-top: 12rpx;
  color: var(--hq-muted);
}

.recommendation-card {
  display: flex;
  padding: 22rpx 0;
  border-bottom: 1rpx solid var(--hq-line);
}

.recommendation-card:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.list-caption {
  display: block;
  margin: -8rpx 6rpx 20rpx;
  color: var(--hq-muted);
  font-size: 23rpx;
  line-height: 1.5;
}

.state-panel {
  display: flex;
  min-height: 300rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 44rpx 28rpx;
  text-align: center;
}

.state-icon {
  display: flex;
  width: 72rpx;
  height: 72rpx;
  align-items: center;
  justify-content: center;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 50%;
  font-size: 30rpx;
}

.state-panel--error .state-icon {
  color: var(--hq-danger);
  background: #fff0f1;
}

.state-image {
  width: 76rpx;
  height: 76rpx;
  opacity: 0.45;
}

.state-title {
  display: block;
  margin-top: 24rpx;
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 600;
  line-height: 1.5;
}

.state-copy {
  display: block;
  margin-top: 10rpx;
  color: var(--hq-muted);
  font-size: 24rpx;
  line-height: 1.6;
}

.retry-action {
  margin-top: 24rpx;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.task-card.card {
  display: flex;
  padding: 24rpx;
  margin-top: 0;
}

.task-icon.task-avatar { border-radius: 50%; }

.task-icon {
  display: flex;
  width: 56rpx;
  height: 56rpx;
  flex: 0 0 56rpx;
  align-items: center;
  justify-content: center;
  margin-right: 20rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 16rpx;
  font-size: 24rpx;
  font-weight: 600;
}

.task-content {
  min-width: 0;
}

.task-title {
  min-width: 0;
  flex: 1;
  color: var(--hq-ink);
  font-size: 29rpx;
  font-weight: 600;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.status-tag {
  flex: 0 0 auto;
  padding: 5rpx 10rpx;
  margin-left: 14rpx;
  color: #9a6515;
  background: #fff5df;
  border-radius: 99rpx;
  font-size: 19rpx;
}

.task-summary {
  display: -webkit-box;
  margin-top: 10rpx;
  overflow: hidden;
  color: var(--hq-body);
  font-size: 24rpx;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.task-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx 16rpx;
  align-items: center;
  justify-content: space-between;
  margin-top: 16rpx;
}

.task-link {
  display: block;
  margin-top: 14rpx;
  color: var(--hq-primary);
  font-size: 23rpx;
  line-height: 1.5;
}

.task-footer .task-link {
  margin-top: 0;
}

.task-time {
  color: var(--hq-muted);
  font-size: 21rpx;
  line-height: 1.5;
}

.load-more {
  width: 100%;
  margin-top: 20rpx;
}

.priority-reason {
  display: block;
  margin-top: 12rpx;
  color: var(--hq-primary);
  font-size: 24rpx;
  line-height: 1.6;
}
</style>
