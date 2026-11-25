<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import {
  getInventoryAlertMeta,
  getInventoryAlerts,
  type InventoryAlertItem,
  type InventoryAlertQuery,
} from "@/api/inventoryAlerts";
import { formatLocalDateTime } from "@/utils/dateTime";

const loading = ref(false);
const loaded = ref(false);
const rows = ref<InventoryAlertItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 30;
const keyword = ref("");
const itemId = ref("");
const unitNames = ref<Record<string, string>>({});
const statusCode =
  ref<NonNullable<InventoryAlertQuery["status_code"]>>("replenishment");

const hasMore = computed(() => rows.value.length < total.value);
const statusOptions: Array<{
  label: string;
  value: NonNullable<InventoryAlertQuery["status_code"]>;
}> = [
  { label: "全部", value: "replenishment" },
  { label: "缺货", value: "out_of_stock" },
  { label: "库存不足", value: "low_stock" },
  { label: "未配置", value: "unconfigured" },
];

function quantity(value?: string | number | null) {
  if (value == null || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function unitLabel(code: string) {
  return unitNames.value[code] || code;
}

async function loadUnits() {
  if (Object.keys(unitNames.value).length) return;
  try {
    const meta = await getInventoryAlertMeta();
    unitNames.value = Object.fromEntries(
      (meta.md_unit || []).map((item) => [item.value, item.label]),
    );
  } catch {
    unitNames.value = {};
  }
}

async function load(reset = true) {
  if (loading.value) return;
  loading.value = true;
  const targetPage = reset ? 1 : page.value + 1;
  try {
    const result = await getInventoryAlerts({
      page: targetPage,
      page_size: pageSize,
      keyword: keyword.value || undefined,
      item_id: itemId.value || undefined,
      status_code: statusCode.value,
    });
    rows.value = reset ? result.items : [...rows.value, ...result.items];
    total.value = result.total;
    page.value = targetPage;
    loaded.value = true;
  } catch (error) {
    uni.showToast({
      title: (error as Error)?.message || "预警加载失败",
      icon: "none",
    });
  } finally {
    loading.value = false;
  }
}

function changeStatus(value: NonNullable<InventoryAlertQuery["status_code"]>) {
  if (statusCode.value === value) return;
  statusCode.value = value;
  void load(true);
}

function search() {
  void load(true);
}

onLoad((options) => {
  itemId.value = typeof options?.item_id === "string" ? options.item_id : "";
});

onShow(() => {
  void loadUnits();
  void load(true);
});

onPullDownRefresh(async () => {
  await load(true);
  uni.stopPullDownRefresh();
});
</script>

<template>
  <view class="alert-page">
    <view class="summary-card">
      <view>
        <text class="summary-title">待补货预警</text>
        <text class="summary-desc">可用库存低于安全库存时自动提醒</text>
      </view>
      <view class="summary-count">
        <text class="summary-number">{{ total }}</text>
        <text class="summary-unit">项</text>
      </view>
    </view>

    <view class="search-bar">
      <input
        v-model="keyword"
        class="search-input"
        placeholder="搜索物料名称、编号或规格"
        confirm-type="search"
        @confirm="search"
      />
      <text class="search-button" @tap="search">查询</text>
    </view>

    <scroll-view scroll-x class="status-scroll" :show-scrollbar="false">
      <view class="status-tabs">
        <view
          v-for="option in statusOptions"
          :key="option.value"
          class="status-tab"
          :class="{ active: statusCode === option.value }"
          @tap="changeStatus(option.value)"
        >
          {{ option.label }}
        </view>
      </view>
    </scroll-view>

    <view v-if="rows.length" class="alert-list">
      <view
        v-for="row in rows"
        :key="`${row.item_id}:${row.warehouse_id}`"
        class="alert-card"
        :class="{ danger: row.stock_alert_status === 'out_of_stock' }"
      >
        <view class="card-head">
          <view class="item-main">
            <text class="item-name">{{ row.item_name }}</text>
            <text class="item-meta">
              {{ row.item_no
              }}{{ row.specification ? ` · ${row.specification}` : "" }}
            </text>
          </view>
          <text
            class="status-badge"
            :class="{ danger: row.stock_alert_status === 'out_of_stock' }"
          >
            {{ row.stock_alert_label }}
          </text>
        </view>

        <view class="organization">
          {{ row.org_name }} · {{ row.warehouse_name }}
        </view>
        <view class="quantity-grid">
          <view class="quantity-cell">
            <text class="quantity-label">当前可用</text>
            <text class="quantity-value current">
              {{ quantity(row.available_quantity) }}
              {{ unitLabel(row.unit_code) }}
            </text>
          </view>
          <view class="quantity-cell">
            <text class="quantity-label">安全库存</text>
            <text class="quantity-value">
              {{ quantity(row.min_quantity) }}
              {{ row.min_quantity == null ? "" : unitLabel(row.unit_code) }}
            </text>
          </view>
          <view class="quantity-cell replenish">
            <text class="quantity-label">建议补货</text>
            <text class="quantity-value replenish-value">
              {{
                row.stock_alert_status === "unconfigured"
                  ? "—"
                  : quantity(row.suggested_replenishment_quantity)
              }}
              {{
                row.stock_alert_status === "unconfigured"
                  ? ""
                  : unitLabel(row.unit_code)
              }}
            </text>
          </view>
        </view>
        <text class="updated-time"
          >库存更新：{{ formatLocalDateTime(row.updated_at) }}</text
        >
      </view>

      <view v-if="hasMore" class="load-more" @tap="load(false)">
        {{ loading ? "加载中..." : "加载更多" }}
      </view>
      <view v-else class="list-end">已显示全部预警</view>
    </view>

    <view v-else-if="loaded && !loading" class="empty-state">
      <view class="empty-icon">✓</view>
      <text class="empty-title">当前库存充足</text>
      <text class="empty-desc">暂无需要补货的物资</text>
    </view>
    <view v-else class="loading-state">正在加载预警...</view>
  </view>
</template>

<style scoped lang="scss">
.alert-page {
  min-height: 100vh;
  padding: 24rpx;
  box-sizing: border-box;
  background: #f4f7fb;
}

.summary-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  color: #fff;
  background: linear-gradient(135deg, #df4f52, #f08b4b);
  border-radius: 26rpx;
  box-shadow: 0 14rpx 34rpx rgba(210, 77, 65, 0.18);
}

.summary-title,
.summary-desc,
.summary-number,
.summary-unit,
.item-name,
.item-meta,
.organization,
.quantity-label,
.quantity-value,
.updated-time,
.empty-title,
.empty-desc {
  display: block;
}

.summary-title {
  font-size: 32rpx;
  font-weight: 700;
}

.summary-desc {
  margin-top: 10rpx;
  color: rgba(255, 255, 255, 0.8);
  font-size: 21rpx;
}

.summary-count {
  display: flex;
  align-items: baseline;
  gap: 5rpx;
}

.summary-number {
  font-size: 54rpx;
  font-weight: 750;
}

.summary-unit {
  font-size: 22rpx;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 20rpx;
  margin-top: 22rpx;
  background: #fff;
  border-radius: 20rpx;
}

.search-input {
  min-width: 0;
  height: 56rpx;
  flex: 1;
  color: #2d3748;
  font-size: 24rpx;
}

.search-button {
  color: #1769e0;
  font-size: 24rpx;
  font-weight: 650;
}

.status-scroll {
  margin: 18rpx 0;
  white-space: nowrap;
}

.status-tabs {
  display: inline-flex;
  gap: 12rpx;
}

.status-tab {
  padding: 13rpx 25rpx;
  color: #68758a;
  background: #fff;
  border-radius: 999rpx;
  font-size: 22rpx;
}

.status-tab.active {
  color: #fff;
  background: #df5655;
  font-weight: 650;
}

.alert-card {
  padding: 26rpx;
  margin-bottom: 18rpx;
  background: #fff;
  border-left: 7rpx solid #f0a545;
  border-radius: 22rpx;
  box-shadow: 0 8rpx 26rpx rgba(36, 63, 98, 0.06);
}

.alert-card.danger {
  border-left-color: #df4f52;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18rpx;
}

.item-main {
  min-width: 0;
  flex: 1;
}

.item-name {
  overflow: hidden;
  color: #243249;
  font-size: 28rpx;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta,
.organization,
.updated-time {
  color: #8a94a6;
  font-size: 20rpx;
}

.item-meta {
  margin-top: 8rpx;
}

.status-badge {
  flex: 0 0 auto;
  padding: 8rpx 15rpx;
  color: #b56706;
  background: #fff3df;
  border-radius: 999rpx;
  font-size: 20rpx;
  font-weight: 650;
}

.status-badge.danger {
  color: #c4363b;
  background: #ffebec;
}

.organization {
  margin-top: 16rpx;
}

.quantity-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10rpx;
  margin-top: 20rpx;
}

.quantity-cell {
  min-width: 0;
  padding: 17rpx 12rpx;
  text-align: center;
  background: #f6f8fb;
  border-radius: 15rpx;
}

.quantity-cell.replenish {
  background: #eef5ff;
}

.quantity-label {
  color: #8b95a5;
  font-size: 19rpx;
}

.quantity-value {
  margin-top: 8rpx;
  overflow: hidden;
  color: #354158;
  font-size: 22rpx;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quantity-value.current {
  color: #d14949;
}

.quantity-value.replenish-value {
  color: #1769e0;
}

.updated-time {
  margin-top: 17rpx;
  text-align: right;
}

.load-more,
.list-end,
.loading-state {
  padding: 24rpx 0 34rpx;
  color: #8a94a6;
  font-size: 22rpx;
  text-align: center;
}

.load-more {
  color: #1769e0;
}

.empty-state {
  display: flex;
  min-height: 480rpx;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.empty-icon {
  display: flex;
  width: 104rpx;
  height: 104rpx;
  align-items: center;
  justify-content: center;
  color: #2aa66d;
  background: #eaf8f1;
  border-radius: 50%;
  font-size: 50rpx;
}

.empty-title {
  margin-top: 25rpx;
  color: #334057;
  font-size: 28rpx;
  font-weight: 650;
}

.empty-desc {
  margin-top: 8rpx;
  color: #98a1af;
  font-size: 22rpx;
}
</style>
