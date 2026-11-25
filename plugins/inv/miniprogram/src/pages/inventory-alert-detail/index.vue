<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onPullDownRefresh } from "@dcloudio/uni-app";
import {
  getInventoryAlertDetail,
  getInventoryAlertMeta,
  type InventoryAlertItem,
} from "@/api/inventoryAlerts";
import { formatLocalDateTime } from "@/utils/dateTime";

const loading = ref(false);
const itemId = ref("");
const warehouseId = ref("");
const detail = ref<InventoryAlertItem>();
const unitNames = ref<Record<string, string>>({});

const isNormal = computed(() => detail.value?.stock_alert_status === "normal");
const statusTone = computed(() => {
  if (detail.value?.stock_alert_status === "normal") return "normal";
  if (detail.value?.stock_alert_status === "overstock") return "overstock";
  if (detail.value?.stock_alert_status === "out_of_stock") return "danger";
  return "warning";
});
const statusHint = computed(() => {
  const status = detail.value?.stock_alert_status;
  if (status === "normal") return "当前库存处于安全范围，无需补货。";
  if (status === "overstock") return "当前库存已超过库存上限，请关注库存周转。";
  if (status === "unconfigured") return "尚未配置该仓库的安全库存和补货目标。";
  return "当前库存需要补充，建议补至库存上限。";
});

function quantity(value?: string | number | null) {
  if (value == null || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function unitLabel(code?: string) {
  return code ? unitNames.value[code] || code : "";
}

function quantityWithUnit(value?: string | number | null) {
  if (!detail.value || value == null || value === "") return "—";
  return `${quantity(value)} ${unitLabel(detail.value.unit_code)}`;
}

async function load() {
  if (!itemId.value || !warehouseId.value || loading.value) return;
  loading.value = true;
  try {
    const [row, meta] = await Promise.all([
      getInventoryAlertDetail(itemId.value, warehouseId.value),
      getInventoryAlertMeta(),
    ]);
    detail.value = row;
    unitNames.value = Object.fromEntries(
      (meta.md_unit || []).map((item) => [item.value, item.label]),
    );
  } catch (error) {
    uni.showToast({
      title: (error as Error)?.message || "库存详情加载失败",
      icon: "none",
    });
  } finally {
    loading.value = false;
  }
}

onLoad((options) => {
  itemId.value = typeof options?.item_id === "string" ? options.item_id : "";
  warehouseId.value =
    typeof options?.warehouse_id === "string" ? options.warehouse_id : "";
  if (!itemId.value || !warehouseId.value) {
    uni.showToast({ title: "库存详情参数不完整", icon: "none" });
    return;
  }
  void load();
});

onPullDownRefresh(async () => {
  await load();
  uni.stopPullDownRefresh();
});
</script>

<template>
  <view class="detail-page">
    <view v-if="detail" class="detail-card">
      <view class="detail-head">
        <view class="item-main">
          <text class="item-name">{{ detail.item_name }}</text>
          <text class="item-meta">
            {{ detail.item_no
            }}{{ detail.specification ? ` · ${detail.specification}` : "" }}
          </text>
        </view>
        <text class="status-badge" :class="`status--${statusTone}`">
          {{ detail.stock_alert_label }}
        </text>
      </view>

      <view class="status-hint" :class="{ recovered: isNormal }">
        {{ statusHint }}
      </view>

      <view class="field-list">
        <view class="field-row">
          <text class="field-label">所属组织</text>
          <text class="field-value">{{ detail.org_name }}</text>
        </view>
        <view class="field-row">
          <text class="field-label">预警仓库</text>
          <text class="field-value strong">{{ detail.warehouse_name }}</text>
        </view>
        <view class="field-row">
          <text class="field-label">当前可用</text>
          <text class="field-value current">
            {{ quantityWithUnit(detail.available_quantity) }}
          </text>
        </view>
        <view class="field-row">
          <text class="field-label">安全库存</text>
          <text class="field-value">
            {{ quantityWithUnit(detail.min_quantity) }}
          </text>
        </view>
        <view class="field-row">
          <text class="field-label">库存上限</text>
          <text class="field-value">
            {{ quantityWithUnit(detail.max_quantity) }}
          </text>
        </view>
        <view class="field-row">
          <text class="field-label">建议补货</text>
          <text class="field-value replenish">
            {{ quantityWithUnit(detail.suggested_replenishment_quantity) }}
          </text>
        </view>
        <view class="field-row">
          <text class="field-label">库存更新时间</text>
          <text class="field-value">{{ formatLocalDateTime(detail.updated_at) }}</text>
        </view>
      </view>
    </view>

    <view v-else class="loading-state">
      {{ loading ? "正在加载库存详情..." : "暂无库存详情" }}
    </view>
  </view>
</template>

<style scoped lang="scss">
.detail-page {
  min-height: 100vh;
  padding: 24rpx;
  box-sizing: border-box;
  background: #f4f7fb;
}

.detail-card {
  padding: 30rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 10rpx 30rpx rgba(36, 63, 98, 0.07);
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20rpx;
}

.item-main {
  min-width: 0;
  flex: 1;
}

.item-name,
.item-meta,
.field-label,
.field-value {
  display: block;
}

.item-name {
  color: #243249;
  font-size: 34rpx;
  font-weight: 700;
}

.item-meta {
  margin-top: 10rpx;
  color: #8a94a6;
  font-size: 22rpx;
}

.status-badge {
  flex: 0 0 auto;
  padding: 9rpx 17rpx;
  border-radius: 999rpx;
  font-size: 21rpx;
  font-weight: 650;
}

.status--normal {
  color: #198754;
  background: #e8f7ef;
}

.status--warning {
  color: #b56706;
  background: #fff3df;
}

.status--danger,
.status--overstock {
  color: #c4363b;
  background: #ffebec;
}

.status-hint {
  padding: 20rpx 22rpx;
  margin-top: 26rpx;
  color: #8a5a10;
  background: #fff7e9;
  border-radius: 16rpx;
  font-size: 23rpx;
  line-height: 1.5;
}

.status-hint.recovered {
  color: #18764c;
  background: #eaf8f1;
}

.field-list {
  margin-top: 26rpx;
  border-top: 1rpx solid #edf0f4;
}

.field-row {
  display: flex;
  min-height: 86rpx;
  align-items: center;
  justify-content: space-between;
  gap: 24rpx;
  border-bottom: 1rpx solid #edf0f4;
}

.field-label {
  flex: 0 0 auto;
  color: #7c8798;
  font-size: 24rpx;
}

.field-value {
  min-width: 0;
  color: #354158;
  font-size: 24rpx;
  text-align: right;
}

.field-value.strong {
  color: #243249;
  font-weight: 650;
}

.field-value.current {
  color: #d14949;
  font-weight: 700;
}

.field-value.replenish {
  color: #1769e0;
  font-weight: 700;
}

.loading-state {
  padding: 160rpx 0;
  color: #8a94a6;
  font-size: 24rpx;
  text-align: center;
}
</style>
