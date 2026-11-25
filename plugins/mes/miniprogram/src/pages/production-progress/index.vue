<script setup lang="ts">
import { ref } from "vue";
import { onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import AppTabBar from "@/components/AppTabBar.vue";
import { apiBaseUrl } from "@/api/client";
import {
  listWorkOrders,
  getWorkOrderDrawings,
  type WorkOrderProgressRow,
  type OperationProgressItem,
  type WorkOrderDrawingFile,
} from "@plugins/mes/miniprogram/src/api/mesProduction";

type ViewMode = "order" | "product";

const loading = ref(false);
const rows = ref<WorkOrderProgressRow[]>([]);
const total = ref(0);
const keyword = ref("");
const status = ref("unfinished");
const viewMode = ref<ViewMode>("order");

const craftVisible = ref(false);
const craftOrder = ref<WorkOrderProgressRow | null>(null);

const tabs = [
  { value: "unfinished", label: "未完成" },
  { value: "completed", label: "已完成" },
];
const segments: { value: ViewMode; label: string }[] = [
  { value: "order", label: "工单" },
  { value: "product", label: "货品" },
];

async function load() {
  if (loading.value) return;
  loading.value = true;
  try {
    const result = await listWorkOrders({
      page: 1,
      page_size: 100,
      status_code: status.value,
      keyword: keyword.value.trim() || undefined,
    });
    rows.value = result.items;
    total.value = result.total;
  } catch (error: any) {
    rows.value = [];
    total.value = 0;
    uni.showToast({ title: error?.message || "加工进度加载失败", icon: "none" });
  } finally {
    loading.value = false;
    uni.stopPullDownRefresh();
  }
}

function chooseStatus(value: string) {
  if (loading.value || value === status.value) return;
  status.value = value;
  void load();
}

function chooseView(value: ViewMode) {
  if (value === viewMode.value) return;
  viewMode.value = value;
}

function submitSearch() {
  void load();
}

function isOverdue(row: WorkOrderProgressRow) {
  if (!row.due_at) return false;
  if (row.status_code === "completed" || row.status_code === "cancelled") return false;
  return new Date(row.due_at).getTime() < Date.now();
}

function dueText(row: WorkOrderProgressRow) {
  if (!row.due_at) return "交期未定";
  const d = new Date(row.due_at);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function summaryPercent(row: WorkOrderProgressRow) {
  if (!row.operation_count) return 0;
  return Math.min(100, Math.round((row.completed_operation_count / row.operation_count) * 100));
}

function opPercent(op: OperationProgressItem) {
  if (op.planned_quantity > 0) {
    return Math.min(100, Math.round((op.good_quantity / op.planned_quantity) * 100));
  }
  return op.status_code === "completed" ? 100 : 0;
}

function opTone(op: OperationProgressItem): "done" | "active" | "todo" {
  if (op.status_code === "completed") return "done";
  if (op.good_quantity > 0) return "active";
  return "todo";
}

function opQuantity(op: OperationProgressItem) {
  return `${op.good_quantity}/${op.planned_quantity}`;
}

function ringColor(tone: "done" | "active" | "todo") {
  if (tone === "done") return "#16a34a";
  if (tone === "active") return "#1a6fee";
  return "#d5dae2";
}

function ringStyle(op: OperationProgressItem) {
  const p = opPercent(op);
  const color = ringColor(opTone(op));
  return { background: `conic-gradient(${color} 0% ${p}%, #eef1f5 ${p}% 100%)` };
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function resolveFileUrl(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `${apiBaseUrl}${url}`;
}

async function openDrawing(row: WorkOrderProgressRow) {
  uni.showLoading({ title: "加载图纸" });
  try {
    const result = await getWorkOrderDrawings(row.id);
    const files = result.items || [];
    if (!files.length) {
      uni.showToast({ title: "暂无图纸", icon: "none" });
      return;
    }
    const pdf = files.find((f) => f.content_type === "application/pdf" || /\.pdf$/i.test(f.file_name));
    if (pdf) {
      openPdf(pdf);
      return;
    }
    const images = files.filter((f) => f.file_kind === "image");
    if (images.length) {
      uni.previewImage({ current: resolveFileUrl(images[0]!.url), urls: images.map((f) => resolveFileUrl(f.url)) });
      return;
    }
    openPdf(files[0]!);
  } catch (error: any) {
    uni.showToast({ title: error?.message || "图纸加载失败", icon: "none" });
  } finally {
    uni.hideLoading();
  }
}

function openPdf(file: WorkOrderDrawingFile) {
  uni.downloadFile({
    url: resolveFileUrl(file.url),
    success: (res) => {
      if (res.statusCode !== 200) {
        uni.showToast({ title: "图纸下载失败", icon: "none" });
        return;
      }
      uni.openDocument({
        filePath: res.tempFilePath,
        showMenu: true,
        fail: () => uni.showToast({ title: "暂不支持预览该图纸", icon: "none" }),
      });
    },
    fail: () => uni.showToast({ title: "图纸下载失败", icon: "none" }),
  });
}

function openCraft(row: WorkOrderProgressRow) {
  craftOrder.value = row;
  craftVisible.value = true;
}

onShow(() => {
  void load();
});
onPullDownRefresh(() => {
  void load();
});
</script>

<template>
  <view class="page">
    <view class="hero">
      <view>
        <text class="eyebrow">MANUFACTURING EXECUTION</text>
        <text class="title">加工进度</text>
      </view>
      <view class="hero-badge">{{ total }} 单</view>
    </view>

    <view class="sticky">
      <scroll-view scroll-x class="tabs" :show-scrollbar="false">
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

      <view class="seg-row">
        <view class="seg">
          <text
            v-for="item in segments"
            :key="item.value"
            :class="{ active: viewMode === item.value }"
            @tap="chooseView(item.value)"
          >
            {{ item.label }}
          </text>
        </view>
      </view>

      <view class="search-card">
        <view class="search-row">
          <input
            v-model="keyword"
            class="search-input"
            :placeholder="viewMode === 'order' ? '工单号 / 产品名称' : '产品名称 / 编号'"
            confirm-type="search"
            @confirm="submitSearch"
          />
          <button class="search-button" :disabled="loading" aria-label="搜索" @tap="submitSearch">
            <image class="icon-search" src="/static/mes/service-icons/icon-search.png" mode="aspectFit" />
          </button>
        </view>
      </view>
    </view>

    <view class="content">
      <view v-if="loading" class="state">正在加载进度…</view>
      <view v-else-if="rows.length">
        <!-- 工单视角 -->
        <view v-if="viewMode === 'order'">
          <view v-for="item in rows" :key="item.id" class="order-card">
            <view class="order-head">
              <view class="order-id">
                <text class="order-no">{{ item.work_order_no }}</text>
                <text class="order-meta">{{ item.product_item_no }}</text>
              </view>
              <view class="due" :class="{ overdue: isOverdue(item) }">
                <text v-if="isOverdue(item)" class="due-tag">逾</text>
                <text class="due-label">交期</text>
                <text class="due-divider">|</text>
                <text class="due-date">{{ dueText(item) }}</text>
              </view>
            </view>

            <text class="product-name">{{ item.product_item_name }}</text>

            <view class="summary">
              <view class="summary-head">
                <text class="summary-text">工序 {{ item.completed_operation_count }}/{{ item.operation_count }} 完成</text>
                <text class="summary-value">{{ summaryPercent(item) }}%</text>
              </view>
              <view class="summary-track">
                <view class="summary-fill" :style="{ width: summaryPercent(item) + '%' }" />
              </view>
            </view>

            <view v-if="item.operation_progress.length" class="ops">
              <view v-for="op in item.operation_progress" :key="op.id" class="op-row">
                <view class="op-name">
                  <text class="op-dot" :class="opTone(op)" />
                  <text class="op-label">{{ op.operation_name }}</text>
                </view>
                <view class="op-mid">
                  <view class="op-track">
                    <view class="op-fill" :class="opTone(op)" :style="{ width: opPercent(op) + '%' }" />
                  </view>
                </view>
                <text class="op-qty">{{ opQuantity(op) }}</text>
                <text class="op-unit">{{ item.unit_name }}</text>
              </view>
            </view>
            <view v-else class="ops-empty">尚未配置工序</view>

            <view class="order-foot">
              <text v-if="item.priority_label" class="priority">{{ item.priority_label }}</text>
              <text class="foot-meta">{{ item.processing_type_label || "生产工单" }}</text>
            </view>
          </view>
        </view>

        <!-- 货品视角 -->
        <view v-else>
          <view v-for="item in rows" :key="item.id" class="product-card">
            <view class="product-head">
              <view class="thumb">货</view>
              <view class="product-id">
                <text class="product-name">{{ item.product_item_name }}</text>
                <text class="product-no">{{ item.product_item_no }}</text>
              </view>
              <view class="due" :class="{ overdue: isOverdue(item) }">
                <text v-if="isOverdue(item)" class="due-tag">逾</text>
                <text class="due-date">{{ dueText(item) }}</text>
              </view>
            </view>

            <view class="drawing-entry" @tap="openDrawing(item)">
              <text class="drawing-entry-label">货品图档</text>
              <text class="drawing-entry-link">查看 ›</text>
            </view>

            <view class="craft" @tap="openCraft(item)">
              <text class="craft-label">工艺进度</text>
              <view class="craft-right">
                <text class="craft-value">工艺 {{ item.completed_operation_count }}/{{ item.operation_count }}</text>
                <text class="craft-arrow">›</text>
              </view>
            </view>

            <view v-if="item.operation_progress.length" class="rings">
              <template v-for="(op, idx) in item.operation_progress" :key="op.id">
                <view class="ring-node">
                  <view class="ring" :style="ringStyle(op)">
                    <view class="ring-hole">
                      <text class="ring-num">{{ opPercent(op) }}%</text>
                    </view>
                  </view>
                  <text class="ring-op">{{ op.operation_name }}</text>
                  <text class="ring-qty">{{ opQuantity(op) }} {{ item.unit_name }}</text>
                </view>
                <view v-if="idx < item.operation_progress.length - 1" class="ring-arrow">→</view>
              </template>
            </view>
            <view v-else class="ops-empty">尚未配置工序</view>
          </view>
        </view>
      </view>
      <view v-else class="state">
        <text class="state-icon">✓</text>
        <text>{{ status === "completed" ? "暂无已完成的工单" : "暂无进行中的工单" }}</text>
        <text class="state-hint">请先创建生产工单，或调整筛选条件</text>
      </view>
    </view>
    <!-- 工艺进度详情弹层 -->
    <view v-if="craftVisible" class="mask" @tap="craftVisible = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-head">
          <view class="sheet-heading">
            <text class="sheet-title">工艺进度</text>
            <text class="sheet-sub">{{ craftOrder?.work_order_no }}</text>
          </view>
          <text class="sheet-close" @tap="craftVisible = false">×</text>
        </view>
        <view class="sheet-body">
          <view v-if="craftOrder && craftOrder.operation_progress.length">
            <view v-for="op in craftOrder.operation_progress" :key="op.id" class="craft-op">
              <view class="craft-op-head">
                <view class="craft-ring" :style="ringStyle(op)">
                  <view class="craft-ring-hole"><text>{{ opPercent(op) }}%</text></view>
                </view>
                <view class="craft-op-info">
                  <text class="craft-op-name">{{ op.operation_name }}</text>
                  <text class="craft-op-qty">{{ opQuantity(op) }} {{ craftOrder.unit_name }} · {{ op.status_label }}</text>
                </view>
              </view>
              <view class="craft-time">
                <text class="craft-time-label">计划</text>
                <text class="craft-time-value">{{ formatTime(op.planned_start_at) }} ~ {{ formatTime(op.planned_end_at) }}</text>
              </view>
              <view class="craft-time">
                <text class="craft-time-label">实际</text>
                <text class="craft-time-value">{{ formatTime(op.actual_started_at) }} ~ {{ formatTime(op.actual_finished_at) }}</text>
              </view>
            </view>
          </view>
          <view v-else class="sheet-state">尚未配置工序</view>
        </view>
      </view>
    </view>

    <AppTabBar current="secondary" />
  </view>
</template>

<style scoped lang="scss">
.page { min-height: 100vh; color: #20364d; background: #f2f4f7; padding-bottom: calc(120rpx + env(safe-area-inset-bottom)); }
.hero { display: flex; align-items: center; justify-content: space-between; padding: 40rpx 30rpx; color: #fff; background: linear-gradient(145deg, #1552c8, #1a6fee); }
.eyebrow, .title { display: block; }
.eyebrow { font-size: 17rpx; opacity: .7; letter-spacing: 3rpx; }
.title { margin-top: 8rpx; font-size: 42rpx; font-weight: 750; }
.hero-badge { padding: 12rpx 20rpx; border: 2rpx solid rgba(255,255,255,.32); border-radius: 99rpx; background: rgba(255,255,255,.12); font-size: 22rpx; }
.sticky { position: sticky; top: 0; z-index: 10; background: #fff; box-shadow: 0 4rpx 14rpx rgba(28,68,105,.05); }
.tabs { white-space: nowrap; }
.tab-row { display: flex; gap: 34rpx; padding: 24rpx 30rpx 12rpx; }
.tab-row text { position: relative; padding-bottom: 12rpx; color: #86909c; font-size: 27rpx; font-weight: 500; }
.tab-row text.active { color: #1a6fee; font-weight: 680; }
.tab-row text.active::after { content: ""; position: absolute; left: 50%; bottom: 0; width: 36rpx; height: 6rpx; transform: translateX(-50%); border-radius: 99rpx; background: #1a6fee; }
.seg-row { padding: 14rpx 22rpx 0; }
.seg { display: flex; padding: 6rpx; border-radius: 16rpx; background: #eef1f5; }
.seg text { flex: 1; padding: 12rpx 0; text-align: center; color: #86909c; border-radius: 12rpx; font-size: 23rpx; }
.seg text.active { color: #1a6fee; background: #fff; font-weight: 680; box-shadow: 0 2rpx 8rpx rgba(28,68,105,.08); }
.search-card { padding: 16rpx 22rpx 20rpx; }
.search-row { display: flex; align-items: center; gap: 10rpx; }
.search-input { flex: 1; height: 72rpx; padding: 0 18rpx; box-sizing: border-box; border-radius: 15rpx; background: #f2f4f7; font-size: 23rpx; }
.search-button { display: flex; width: 72rpx; height: 72rpx; margin: 0; padding: 0; align-items: center; justify-content: center; border: 0; border-radius: 15rpx; background: #1a6fee; flex-shrink: 0; }
.search-button::after { border: 0; }
.icon-search { width: 30rpx; height: 30rpx; }
.content { padding: 22rpx; }
.order-card, .product-card { margin-bottom: 18rpx; padding: 24rpx; border: 1rpx solid #e5e9f0; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 26rpx rgba(28,68,105,.05); }
.order-head, .product-head { display: flex; align-items: flex-start; gap: 16rpx; }
.order-id, .product-id { flex: 1; min-width: 0; }
.order-no, .order-meta, .product-name, .product-no { display: block; }
.order-no { font-size: 28rpx; font-weight: 700; }
.order-meta { margin-top: 6rpx; color: #a3adba; font-size: 18rpx; }
.product-name { color: #1e3852; font-size: 26rpx; font-weight: 680; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-no { margin-top: 6rpx; color: #a3adba; font-size: 18rpx; }
.thumb { display: flex; width: 76rpx; height: 76rpx; align-items: center; justify-content: center; color: #1a6fee; border-radius: 18rpx; background: #eef4ff; font-size: 32rpx; font-weight: 700; flex-shrink: 0; }
.due { display: flex; align-items: center; gap: 6rpx; color: #86909c; font-size: 20rpx; flex-shrink: 0; }
.due.overdue { color: #d92d20; }
.due-tag { padding: 2rpx 8rpx; color: #fff; border-radius: 8rpx; background: #d92d20; font-size: 18rpx; font-weight: 700; }
.due-divider { opacity: .4; }
.due-date { font-weight: 650; }
.summary { margin-top: 18rpx; padding: 16rpx 18rpx; border-radius: 14rpx; background: #f6f9ff; }
.summary-head { display: flex; align-items: center; justify-content: space-between; }
.summary-text { color: #4b5f75; font-size: 20rpx; }
.summary-value { color: #1a6fee; font-size: 22rpx; font-weight: 700; }
.summary-track { height: 12rpx; margin-top: 12rpx; overflow: hidden; border-radius: 99rpx; background: #e6ebf5; }
.summary-fill { height: 100%; border-radius: 99rpx; background: linear-gradient(90deg, #1a6fee, #4d8dff); transition: width .3s ease; }
.ops { margin-top: 16rpx; }
.op-row { display: flex; align-items: center; gap: 14rpx; padding: 13rpx 0; }
.op-name { display: flex; align-items: center; gap: 8rpx; width: 108rpx; flex-shrink: 0; }
.op-dot { width: 12rpx; height: 12rpx; border-radius: 50%; flex-shrink: 0; }
.op-dot.done { background: #16a34a; }
.op-dot.active { background: #1a6fee; }
.op-dot.todo { background: #d5dae2; }
.op-label { color: #334f6d; font-size: 21rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.op-mid { flex: 1; }
.op-track { height: 12rpx; overflow: hidden; border-radius: 99rpx; background: #eef1f5; }
.op-fill { height: 100%; border-radius: 99rpx; transition: width .3s ease; }
.op-fill.done { background: #16a34a; }
.op-fill.active { background: #1a6fee; }
.op-fill.todo { background: #e5e9f0; }
.op-qty { min-width: 88rpx; text-align: right; color: #334f6d; font-size: 20rpx; font-weight: 650; }
.op-unit { width: 44rpx; color: #a3adba; font-size: 18rpx; }
.ops-empty { padding: 18rpx 0; color: #a3adba; font-size: 20rpx; }
.order-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 16rpx; padding-top: 14rpx; border-top: 1rpx solid #eef1f5; font-size: 19rpx; }
.priority { padding: 6rpx 12rpx; color: #b54708; border-radius: 99rpx; background: #fff3e2; }
.foot-meta { color: #a3adba; }
.craft { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; padding: 16rpx 18rpx; border-radius: 14rpx; background: #f6f9ff; }
.craft-label { color: #4b5f75; font-size: 20rpx; }
.craft-value { color: #1a6fee; font-size: 22rpx; font-weight: 700; }
.rings { display: flex; align-items: center; margin-top: 20rpx; overflow-x: auto; padding: 4rpx 2rpx; }
.ring-node { display: flex; flex-direction: column; align-items: center; min-width: 120rpx; flex-shrink: 0; }
.ring { display: flex; width: 100rpx; height: 100rpx; align-items: center; justify-content: center; border-radius: 50%; }
.ring-hole { display: flex; width: 76rpx; height: 76rpx; align-items: center; justify-content: center; border-radius: 50%; background: #fff; }
.ring-num { color: #334f6d; font-size: 20rpx; font-weight: 700; }
.ring-op { margin-top: 10rpx; color: #334f6d; font-size: 21rpx; font-weight: 600; max-width: 128rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ring-qty { margin-top: 5rpx; color: #a3adba; font-size: 18rpx; }
.ring-arrow { margin: 0 6rpx; color: #c3ccd6; font-size: 26rpx; flex-shrink: 0; }
.state { display: flex; min-height: 420rpx; align-items: center; justify-content: center; color: #86909c; flex-direction: column; }
.state-icon { margin-bottom: 12rpx; color: #16a34a; font-size: 48rpx; }
.state-hint { margin-top: 12rpx; color: #aab3bf; font-size: 19rpx; }
.drawing-entry { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; padding: 16rpx 18rpx; border-radius: 14rpx; background: #f6f9ff; }
.drawing-entry-label { color: #4b5f75; font-size: 20rpx; }
.drawing-entry-link { color: #1a6fee; font-size: 20rpx; font-weight: 650; }
.craft-right { display: flex; align-items: center; gap: 8rpx; }
.craft-arrow { color: #1a6fee; font-size: 26rpx; }
.mask { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: flex-end; background: rgba(15, 30, 50, .5); }
.sheet { display: flex; width: 100%; max-height: 80vh; padding: 26rpx 26rpx calc(26rpx + env(safe-area-inset-bottom)); flex-direction: column; border-radius: 28rpx 28rpx 0 0; background: #fff; box-sizing: border-box; }
.sheet-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18rpx; }
.sheet-heading { flex: 1; min-width: 0; }
.sheet-title { display: block; color: #1e3852; font-size: 30rpx; font-weight: 720; }
.sheet-sub { display: block; margin-top: 6rpx; color: #a3adba; font-size: 20rpx; }
.sheet-close { padding: 0 8rpx; color: #a3adba; font-size: 40rpx; line-height: 1; }
.sheet-body { overflow-y: auto; }
.sheet-state { padding: 60rpx 0; color: #a3adba; font-size: 22rpx; text-align: center; }
.craft-op { padding: 18rpx 0; border-bottom: 1rpx solid #eef1f5; }
.craft-op:last-child { border-bottom: 0; }
.craft-op-head { display: flex; align-items: center; gap: 18rpx; }
.craft-ring { display: flex; width: 84rpx; height: 84rpx; align-items: center; justify-content: center; border-radius: 50%; flex-shrink: 0; }
.craft-ring-hole { display: flex; width: 62rpx; height: 62rpx; align-items: center; justify-content: center; color: #334f6d; border-radius: 50%; background: #fff; font-size: 18rpx; font-weight: 700; }
.craft-op-info { flex: 1; min-width: 0; }
.craft-op-name { display: block; color: #1e3852; font-size: 25rpx; font-weight: 650; }
.craft-op-qty { display: block; margin-top: 6rpx; color: #86909c; font-size: 20rpx; }
.craft-time { display: flex; align-items: center; gap: 14rpx; margin-top: 12rpx; padding-left: 102rpx; }
.craft-time-label { width: 56rpx; color: #a3adba; font-size: 19rpx; flex-shrink: 0; }
.craft-time-value { color: #4b5f75; font-size: 20rpx; }
</style>
