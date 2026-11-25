<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { listInventoryStock, type StockRow } from "@plugins/inv/miniprogram/src/api/invStock";

const items = ref<StockRow[]>([]);
const keyword = ref("");
const page = ref(1);
const total = ref(0);
const error = ref("");
const loading = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const data = await listInventoryStock(page.value, keyword.value);
    items.value = data.items;
    total.value = data.total;
  } catch (reason) {
    items.value = [];
    error.value = reason instanceof Error ? reason.message : "库存查询失败";
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  void load();
}

function turn(delta: number) {
  page.value += delta;
  void load();
}

onShow(load);
</script>

<template>
  <view class="page-shell stock-page">
    <view class="page-heading">
      <view>
        <text class="title-lg">库存查询</text>
        <text class="heading-copy">查询当前权限范围内的实时库存</text>
      </view>
      <view class="heading-icon">库</view>
    </view>

    <view class="search-card card">
      <view class="search-row">
        <input
          v-model="keyword"
          class="search-input"
          confirm-type="search"
          placeholder="物料名称或编号"
          @confirm="search"
        />
        <button class="search-button" :disabled="loading" @tap="search">
          查询
        </button>
      </view>
    </view>

    <view class="result-heading">
      <text>库存明细</text>
      <text class="result-count">共 {{ total }} 条</text>
    </view>

    <view v-if="loading && !items.length" class="state-panel">
      <view class="state-icon">…</view>
      <text>正在加载库存</text>
    </view>
    <view v-else-if="error" class="state-panel state-panel--error" @tap="load">
      <view class="state-icon">!</view>
      <text class="state-title">库存查询失败</text>
      <text class="state-copy">{{ error }}，点击重试</text>
    </view>
    <view v-else-if="!items.length" class="state-panel">
      <view class="state-icon">库</view>
      <text class="state-title">暂无库存记录</text>
      <text class="state-copy">请调整关键词或确认当前账号的数据范围</text>
    </view>

    <view v-else class="stock-list">
      <view
        v-for="item in items"
        :key="item.org_id + item.item_id"
        class="stock-card card"
      >
        <view class="row between">
          <view class="grow">
            <text class="stock-name">{{ item.item_name }}</text>
            <text class="stock-meta">{{ item.item_no }} · {{ item.org_name }}</text>
          </view>
          <view class="unit-tag">{{ item.unit_code }}</view>
        </view>
        <view class="quantity-grid">
          <view class="quantity-item">
            <text class="quantity-label">账面数量</text>
            <text class="quantity-value">{{ item.quantity }}</text>
          </view>
          <view class="quantity-divider" />
          <view class="quantity-item">
            <text class="quantity-label">可用数量</text>
            <text class="quantity-value quantity-value--available">
              {{ item.available_quantity }}
            </text>
          </view>
        </view>
      </view>
    </view>

    <view v-if="total > 20" class="pagination">
      <button
        class="page-button"
        :disabled="page <= 1 || loading"
        @tap="turn(-1)"
      >
        上一页
      </button>
      <text class="page-info">第 {{ page }} 页</text>
      <button
        class="page-button"
        :disabled="page * 20 >= total || loading"
        @tap="turn(1)"
      >
        下一页
      </button>
    </view>
  </view>
</template>

<style scoped lang="scss">
.stock-page {
  padding-top: 32rpx;
  padding-bottom: 48rpx;
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 26rpx;
}

.heading-copy {
  display: block;
  margin-top: 8rpx;
  color: var(--hq-muted);
  font-size: 22rpx;
}

.heading-icon {
  display: flex;
  width: 70rpx;
  height: 70rpx;
  align-items: center;
  justify-content: center;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 22rpx;
  font-size: 27rpx;
  font-weight: 750;
}

.search-card {
  padding: 22rpx;
}

.search-row {
  display: flex;
  gap: 16rpx;
}

.search-input {
  height: 76rpx;
  min-width: 0;
  flex: 1;
  padding: 0 22rpx;
  color: var(--hq-ink);
  background: #f5f7fa;
  border: 1rpx solid #edf1f5;
  border-radius: 19rpx;
  font-size: 25rpx;
}

.search-button {
  width: 130rpx;
  height: 76rpx;
  margin: 0;
  padding: 0;
  color: #fff;
  background: linear-gradient(135deg, #2177ea, #0e55c3);
  border-radius: 19rpx;
  font-size: 25rpx;
  font-weight: 700;
  line-height: 76rpx;
}

.result-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 30rpx 4rpx 18rpx;
  color: var(--hq-ink);
  font-size: 29rpx;
  font-weight: 750;
}

.result-count {
  color: var(--hq-muted);
  font-size: 21rpx;
  font-weight: 400;
}

.stock-list {
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}

.stock-card {
  margin-top: 0 !important;
  padding: 28rpx;
}

.stock-name,
.stock-meta {
  display: block;
}

.stock-name {
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 700;
  line-height: 1.4;
}

.stock-meta {
  margin-top: 7rpx;
  color: var(--hq-muted);
  font-size: 21rpx;
}

.unit-tag {
  margin-left: 18rpx;
  padding: 7rpx 14rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 99rpx;
  font-size: 20rpx;
}

.quantity-grid {
  display: flex;
  align-items: center;
  margin-top: 24rpx;
  padding: 22rpx 12rpx;
  background: #f7f9fc;
  border-radius: 20rpx;
}

.quantity-item {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
}

.quantity-label {
  color: var(--hq-muted);
  font-size: 20rpx;
}

.quantity-value {
  margin-top: 7rpx;
  color: var(--hq-ink);
  font-size: 31rpx;
  font-weight: 750;
}

.quantity-value--available {
  color: var(--hq-success);
}

.quantity-divider {
  width: 1rpx;
  height: 54rpx;
  background: var(--hq-line);
}

.state-panel {
  display: flex;
  min-height: 300rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40rpx;
  color: var(--hq-muted);
  background: #fff;
  border: 1rpx solid var(--hq-line);
  border-radius: 27rpx;
  text-align: center;
}

.state-panel--error {
  background: #fffafa;
  border-color: #f5dfe1;
}

.state-icon {
  display: flex;
  width: 74rpx;
  height: 74rpx;
  align-items: center;
  justify-content: center;
  margin-bottom: 18rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 23rpx;
  font-size: 28rpx;
  font-weight: 750;
}

.state-title {
  color: var(--hq-ink);
  font-size: 27rpx;
  font-weight: 700;
}

.state-copy {
  margin-top: 8rpx;
  font-size: 22rpx;
  line-height: 1.5;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20rpx;
  margin-top: 28rpx;
}

.page-button {
  width: 150rpx;
  height: 66rpx;
  margin: 0;
  padding: 0;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 18rpx;
  font-size: 23rpx;
  line-height: 66rpx;
}

.page-button[disabled] {
  color: #a8b0bd;
  background: #eef1f5;
}

.page-info {
  color: var(--hq-muted);
  font-size: 22rpx;
}
</style>
