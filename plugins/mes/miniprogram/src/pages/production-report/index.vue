<script setup lang="ts">
import { ref } from "vue";
import { onPullDownRefresh, onReady, onShow } from "@dcloudio/uni-app";
import AppTabBar from "@/components/AppTabBar.vue";
import StatusBadge from "@plugins/mes/miniprogram/src/pages/production-report/shared/components/StatusBadge.vue";
import {
  listMyProductionTasks,
  productionTaskStatusLabel,
  type ProductionTaskRow,
} from "@plugins/mes/miniprogram/src/api/mesProduction";

const loading = ref(false);
const scanning = ref(false);
const hasQueried = ref(false);
const rows = ref<ProductionTaskRow[]>([]);
const total = ref(0);
const keyword = ref("");
const status = ref("");

const tabs = [
  { value: "", label: "全部" },
  { value: "pending", label: "待执行" },
  { value: "in_progress", label: "执行中" },
  { value: "completed", label: "已完成" },
];

async function load() {
  if (loading.value) return;
  hasQueried.value = true;
  loading.value = true;
  try {
    const result = await listMyProductionTasks({
      page: 1,
      page_size: 100,
      status_code: status.value || undefined,
      keyword: keyword.value.trim() || undefined,
    });
    rows.value = result.items;
    total.value = result.total;
  } catch (error: any) {
    rows.value = [];
    total.value = 0;
    uni.showToast({
      title: error?.message || "生产任务加载失败",
      icon: "none",
    });
  } finally {
    loading.value = false;
    uni.stopPullDownRefresh();
  }
}

function chooseStatus(value: string) {
  if (loading.value || scanning.value) return;
  status.value = value;
  if (hasQueried.value) void load();
}

function submitSearch() {
  if (!scanning.value) void load();
}

function scanTask() {
  if (scanning.value || loading.value) return;
  if (typeof uni.scanCode !== "function") {
    uni.showToast({ title: "当前环境无法扫码，请输入工单号", icon: "none" });
    return;
  }
  scanning.value = true;
  uni.scanCode({
    onlyFromCamera: true,
    scanType: ["qrCode", "barCode"],
    success: (result) => {
      const value = String(result.result || "").trim();
      if (!value) {
        uni.showToast({ title: "未识别到任务码", icon: "none" });
        return;
      }
      keyword.value = value;
      status.value = "";
      void load();
    },
    fail: (error) => {
      if (!error.errMsg?.includes("cancel")) {
        uni.showToast({ title: "无法打开扫码，请重试或输入工单号", icon: "none" });
      }
    },
    complete: () => {
      scanning.value = false;
    },
  });
}

function openTask(id: string) {
  uni.navigateTo({ url: `/pages/production-report-detail/index?id=${id}` });
}

function displayStatus(row: ProductionTaskRow) {
  return productionTaskStatusLabel(row.status_code, row.status_label);
}

function formatDueAt(value?: string | null): string {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function percent(row: ProductionTaskRow): number {
  if (!row.planned_quantity) return 0;
  return Math.min(100, Math.round((row.good_quantity / row.planned_quantity) * 100));
}

onReady(scanTask);
onShow(() => {
  if (hasQueried.value && !scanning.value) void load();
});
onPullDownRefresh(() => {
  if (hasQueried.value && !scanning.value) void load();
  else uni.stopPullDownRefresh();
});
</script>

<template>
  <view class="page">
    <view class="hero">
      <view>
        <text class="eyebrow">MANUFACTURING EXECUTION</text>
        <text class="title">扫码报工</text>
      </view>
      <view class="hero-icon">报</view>
    </view>

    <view class="search-card">
      <view class="search-row">
        <input
          v-model="keyword"
          class="search-input"
          placeholder="工单号、产品或任务码"
          confirm-type="search"
          @confirm="submitSearch"
        />
        <button class="scan-button" :disabled="scanning || loading" aria-label="扫码" @tap="scanTask">
          <image class="icon-scan" src="/static/mes/service-icons/icon-scan.png" mode="aspectFit" />
        </button>
        <button class="search-button" :disabled="scanning || loading" aria-label="搜索" @tap="submitSearch">
          <image class="icon-search" src="/static/mes/service-icons/icon-search.png" mode="aspectFit" />
        </button>
      </view>
    </view>

    <scroll-view scroll-x class="tabs">
      <view class="tab-row">
        <text
          v-for="item in tabs"
          :key="item.value"
          :class="{ active: status === item.value }"
          @tap="chooseStatus(item.value)"
        >
          {{ item.label }}
        </text>
      </view>
    </scroll-view>

    <view class="content">
      <view class="list-head">
        <text class="section-title">我的生产任务</text>
        <text class="muted">共 {{ total }} 条</text>
      </view>

      <view v-if="loading" class="empty">正在加载任务…</view>
      <view v-else-if="!hasQueried" class="empty">请扫描工单卡上的二维码</view>
      <view v-else-if="rows.length">
        <view
          v-for="item in rows"
          :key="item.id"
          class="task-card"
          @tap="openTask(item.id)"
        >
          <view class="task-head">
            <view class="task-icon">工</view>
            <view class="grow">
              <text class="operation-name">{{ item.operation_name }}</text>
              <text class="task-no"
                >{{ item.work_order_no }} · 工序 {{ item.operation_no }}</text
              >
            </view>
            <StatusBadge :status="displayStatus(item)" />
          </view>
          <view class="product-line">
            <text>{{ item.product_item_no }}</text>
            <text class="product-name">{{ item.product_item_name }}</text>
          </view>
          <view class="task-info">
            <view class="progress-col">
              <text>完成进度</text>
              <view class="progress-wrap">
                <view class="progress-track">
                  <view class="progress-fill" :style="{ width: percent(item) + '%' }" />
                </view>
                <text class="progress-num">{{ item.good_quantity }}/{{ item.planned_quantity }}</text>
              </view>
            </view>
            <view>
              <text>工作站</text>
              <text class="value">{{ item.workstation_name || item.work_center_name || "待分配" }}</text>
            </view>
            <view>
              <text>交期</text>
              <text class="value">{{ formatDueAt(item.due_at) }}</text>
            </view>
          </view>
          <view class="task-foot">
            <text v-if="item.priority_label" class="priority">{{ item.priority_label }}</text>
            <text v-else class="muted">现场任务</text>
            <text class="open-link">查看并报工 ›</text>
          </view>
        </view>
      </view>
      <view v-else class="empty">
        <text class="empty-icon">✓</text>
        <text>暂无可报工任务</text>
        <text class="empty-hint">请确认 MES 服务已开通，或尝试扫码查询</text>
      </view>
    </view>
    <AppTabBar current="secondary" />
  </view>
</template>

<style scoped lang="scss">
.page { min-height: 100vh; color: #20364d; background: #f3f6fa; }
.hero { display: flex; align-items: center; justify-content: space-between; padding: 38rpx 30rpx; color: #fff; background: linear-gradient(145deg, #094e9f, #2084dd); }
.eyebrow, .title { display: block; }
.eyebrow { font-size: 17rpx; opacity: .66; letter-spacing: 3rpx; }
.title { margin-top: 8rpx; font-size: 42rpx; font-weight: 750; }
.hero-icon { display: flex; width: 88rpx; height: 88rpx; align-items: center; justify-content: center; border: 2rpx solid rgba(255,255,255,.32); border-radius: 26rpx; background: rgba(255,255,255,.12); font-size: 36rpx; font-weight: 700; }
.search-card { padding: 20rpx 22rpx 16rpx; background: #fff; }
.search-row { display: flex; align-items: center; gap: 10rpx; }
.search-input { flex: 1; height: 72rpx; padding: 0 18rpx; box-sizing: border-box; border-radius: 15rpx; background: #f3f6fa; font-size: 23rpx; }
.scan-button, .search-button { display: flex; width: 72rpx; height: 72rpx; margin: 0; padding: 0; align-items: center; justify-content: center; border: 0; border-radius: 15rpx; flex-shrink: 0; }
.scan-button::after, .search-button::after { border: 0; }
.scan-button { background: #eaf3ff; }
.search-button { background: #1769d2; }
.icon-search { width: 30rpx; height: 30rpx; }
.icon-scan { width: 34rpx; height: 34rpx; }
.tabs { white-space: nowrap; background: #fff; }
.tab-row { display: flex; gap: 12rpx; padding: 18rpx 22rpx; }
.tab-row text { padding: 12rpx 22rpx; color: #718197; border-radius: 99rpx; background: #f1f4f8; font-size: 21rpx; }
.tab-row text.active { color: #1769d2; background: #e8f2ff; font-weight: 650; }
.content { padding: 22rpx; }
.list-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.section-title { font-size: 29rpx; font-weight: 700; }
.muted { color: #8793a2; font-size: 20rpx; }
.task-card { margin-bottom: 16rpx; padding: 24rpx; border: 1rpx solid #e5ebf2; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 26rpx rgba(28,68,105,.05); }
.task-head { display: flex; align-items: center; gap: 14rpx; }
.task-icon { display: flex; width: 58rpx; height: 58rpx; align-items: center; justify-content: center; color: #1769d2; border-radius: 17rpx; background: #eaf3ff; font-weight: 700; }
.grow { flex: 1; min-width: 0; }
.operation-name, .task-no, .product-line, .task-info text, .task-foot { display: block; }
.operation-name { font-size: 28rpx; font-weight: 680; }
.task-no { margin-top: 5rpx; color: #91a0af; font-size: 18rpx; }
.product-line { display: flex; align-items: center; gap: 12rpx; margin-top: 20rpx; color: #526a82; font-size: 22rpx; }
.product-line text:first-child { flex-shrink: 0; }
.product-name { flex: 1; min-width: 0; overflow: hidden; color: #1e3852; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.task-info { display: grid; grid-template-columns: 1.5fr 1fr 1.1fr; gap: 12rpx; margin-top: 20rpx; padding: 16rpx 0; border-top: 1rpx solid #edf1f5; border-bottom: 1rpx solid #edf1f5; align-items: center; }
.task-info text:first-child { color: #8c98a5; font-size: 18rpx; }
.task-info .value { margin-top: 7rpx; color: #334f6d; font-size: 21rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-wrap { display: flex; align-items: center; gap: 8rpx; margin-top: 9rpx; }
.progress-track { flex: 1; height: 10rpx; overflow: hidden; border-radius: 99rpx; background: #e8eff6; }
.progress-fill { height: 100%; border-radius: 99rpx; background: linear-gradient(90deg, #2084dd, #52b0f5); }
.progress-num { flex-shrink: 0; color: #334f6d; font-size: 20rpx; }
.task-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 16rpx; font-size: 19rpx; }
.priority { padding: 6rpx 12rpx; color: #a76500; border-radius: 99rpx; background: #fff5df; }
.open-link { color: #1769d2; }
.empty { display: flex; min-height: 420rpx; align-items: center; justify-content: center; color: #8793a2; flex-direction: column; }
.empty-icon { margin-bottom: 12rpx; color: #20a472; font-size: 48rpx; }
.empty-hint { margin-top: 12rpx; color: #abb5c0; font-size: 19rpx; }
</style>
