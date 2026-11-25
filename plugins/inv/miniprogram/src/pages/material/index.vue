<script setup lang="ts">
import { computed, ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppTabBar from "@/components/AppTabBar.vue";
import { hasPermission, showApiError } from "@/utils/permissions";
import { formatQuantity } from "./shared/utils/quantity";
import {
  requisitionStatusLabels,
  listManagedMaterialRequisitions,
  listMyMaterialRequisitions,
  type MaterialRequisition,
} from "@plugins/inv/miniprogram/src/api/inventoryRequisition";

const loading = ref(false);
const rows = ref<MaterialRequisition[]>([]);
const mode = ref<"mine" | "manage">(
  hasPermission("inventory_requisition:list") &&
    (hasPermission("inventory_requisition:approve") ||
      !hasPermission("inventory_requisition:create"))
    ? "manage"
    : "mine",
);
const status = ref("");
const canApply = computed(() => hasPermission("inventory_requisition:create"));
const canManage = computed(() => hasPermission("inventory_requisition:list"));
const statusLabels = requisitionStatusLabels;
const statusFilters = [
  { value: "", label: "全部" },
  { value: "submitted", label: "待审批" },
  { value: "approved", label: "待发放" },
  { value: "pending_receipt", label: "待签收" },
  { value: "receipt_exception", label: "收货异常" },
  { value: "received", label: "已签收" },
  { value: "issued", label: "历史发放" },
  { value: "rejected", label: "已驳回" },
  { value: "withdrawn", label: "已撤回" },
];

let loadVersion = 0;
async function load() {
  const version = ++loadVersion;
  const currentMode = mode.value;
  loading.value = true;
  rows.value = [];
  try {
    const params = {
      page: 1,
      page_size: 100,
      status_code: status.value || undefined,
    };
    const result =
      currentMode === "manage"
        ? await listManagedMaterialRequisitions(params)
        : await listMyMaterialRequisitions(params);
    if (version === loadVersion) rows.value = result.items;
  } catch (error) {
    if (version === loadVersion) showApiError(error, "物资申请加载失败");
  } finally {
    if (version === loadVersion) loading.value = false;
  }
}

function switchMode(value: "mine" | "manage") {
  if (value === mode.value) return;
  mode.value = value;
  status.value = value === "manage" ? "submitted" : "";
  load();
}

function filter(value: string) {
  status.value = value;
  load();
}

function goApply() {
  uni.navigateTo({ url: "/pages/material-form/index" });
}

function open(id: string) {
  uni.navigateTo({ url: `/pages/material-detail/index?id=${id}` });
}

onShow(() => load());
</script>

<template>
  <view class="page-shell material-page">
    <view class="hero-card">
      <view
        ><text class="eyebrow">WAREHOUSE SERVICE</text
        ><text class="hero-title">{{ mode === 'manage' ? '领用审批' : '物资领用' }}</text
        ><text class="hero-desc"
          >在线申请、审批发放，收货核对与照片留档</text
        ></view
      >
      <button v-if="canApply" class="apply-button" @tap="goApply">
        ＋ 申请
      </button>
    </view>
    <view v-if="canManage" class="mode-tabs">
      <view :class="{ active: mode === 'manage' }" @tap="switchMode('manage')"
        >领用审批</view
      >
      <view v-if="canApply" :class="{ active: mode === 'mine' }" @tap="switchMode('mine')"
        >我的申请</view
      >
    </view>
    <scroll-view scroll-x class="status-tabs" :show-scrollbar="false">
      <view class="status-row">
        <text
          v-for="item in statusFilters"
          :key="item.value"
          :class="{ active: status === item.value }"
          @tap="filter(item.value)"
          >{{ item.label }}</text
        >
      </view>
    </scroll-view>
    <view v-if="loading" class="card empty-state"
      ><text>正在加载...</text></view
    >
    <view v-else-if="!rows.length" class="card empty-state"
      ><view class="empty-icon">物</view><text>暂无物资申请</text></view
    >
    <view v-else class="request-list">
      <view
        v-for="item in rows"
        :key="item.id"
        class="card request-card pressable"
        @tap="open(item.id)"
      >
        <view class="row between request-header"
          ><text class="request-no">{{ item.request_no }}</text
          ><text class="status" :class="item.status_code">{{
            item.status_code === "issued"
              ? "已发放"
              : statusLabels[item.status_code]
          }}</text></view
        >
        <text v-if="item.status_code === 'issued'" class="legacy-receipt-note"
          >历史单据，未记录签收</text
        >
        <text class="purpose">{{ item.purpose }}</text>
        <text class="warehouse">{{ item.warehouse_name || "—" }}</text>
        <text class="approval-department">审批部门：{{ item.requisition_approval_department_name || '未配置' }}</text>
        <view class="material-summary"
          ><text v-for="line in item.lines.slice(0, 3)" :key="line.id"
            >{{ line.item_name_snapshot }} × {{ formatQuantity(line.quantity)
            }}{{ line.unit_name }}</text
          ><text v-if="item.lines.length > 3"
            >等 {{ item.lines.length }} 种物资</text
          ></view
        >
        <view class="footer row between"
          ><text
            >{{ item.applicant_name_snapshot }} ·
            {{ item.department_name_snapshot || "未关联部门" }}</text
          ><text>{{ item.created_at }}</text></view
        >
      </view>
    </view>
    <AppTabBar current="secondary" />
  </view>
</template>

<style scoped lang="scss">
.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx;
  color: #fff;
  background: linear-gradient(135deg, #0f766e, #155e75);
  border-radius: 28rpx;
  gap: 20rpx;
}
.hero-card > view {
  flex: 1;
  min-width: 0;
}
.eyebrow,
.hero-title,
.hero-desc {
  display: block;
}
.eyebrow {
  font-size: 18rpx;
  letter-spacing: 2rpx;
  opacity: 0.72;
}
.hero-title {
  margin-top: 7rpx;
  font-size: 38rpx;
  font-weight: 720;
}
.hero-desc {
  margin-top: 8rpx;
  font-size: 21rpx;
  opacity: 0.85;
}
.apply-button {
  flex: 0 0 auto;
  margin: 0;
  padding: 0 24rpx;
  color: #0f6e68;
  background: #fff;
  font-size: 22rpx;
  line-height: 68rpx;
}
.mode-tabs {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  margin-top: 22rpx;
  padding: 7rpx;
  background: #e9eef5;
  border-radius: 18rpx;
}
.mode-tabs view {
  padding: 14rpx;
  color: #78859a;
  text-align: center;
  border-radius: 13rpx;
}
.mode-tabs .active {
  color: #1769e0;
  background: #fff;
  font-weight: 650;
  box-shadow: 0 4rpx 12rpx rgba(38, 63, 95, 0.08);
}
.approval-department {
  display: block;
  margin-bottom: 12rpx;
  color: #66758a;
  font-size: 21rpx;
}
.status-tabs {
  width: 100%;
  margin: 18rpx 0;
  white-space: nowrap;
}
.status-row {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 12rpx;
  padding: 4rpx 0;
  vertical-align: top;
}
.status-row text {
  display: inline-block;
  flex: 0 0 auto;
  padding: 14rpx 24rpx;
  color: #718096;
  background: #fff;
  border-radius: 99rpx;
  font-size: 21rpx;
  line-height: 30rpx;
  white-space: nowrap;
  word-break: keep-all;
}
.status-row text.active {
  color: #fff;
  background: #1769e0;
}
.request-card {
  margin-bottom: 18rpx;
}
.request-header {
  flex-wrap: wrap;
  gap: 12rpx;
}
.request-no {
  min-width: 0;
  overflow-wrap: anywhere;
  color: #66758a;
  font-size: 21rpx;
}
.status {
  flex: 0 0 auto;
  padding: 6rpx 14rpx;
  color: #1769e0;
  background: #e9f2ff;
  border-radius: 99rpx;
  font-size: 19rpx;
  line-height: 28rpx;
  white-space: nowrap;
}
.status.approved,
.status.pending_receipt {
  color: #b56a13;
  background: #fff1d9;
}
.status.issued,
.status.received {
  color: #137a5b;
  background: #e1f6ed;
}
.status.receipt_exception {
  color: #c14e37;
  background: #fff0eb;
}
.legacy-receipt-note {
  display: block;
  margin-top: 10rpx;
  color: #8b96a7;
  font-size: 20rpx;
}
.status.rejected,
.status.withdrawn {
  color: #778293;
  background: #eef1f5;
}
.purpose {
  display: block;
  margin: 19rpx 0 14rpx;
  font-size: 29rpx;
  font-weight: 680;
}
.warehouse {
  display: block;
  margin-bottom: 12rpx;
  color: #1769e0;
  font-size: 21rpx;
}
.material-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 9rpx;
}
.material-summary text {
  padding: 8rpx 12rpx;
  color: #536176;
  background: #f3f6fa;
  border-radius: 10rpx;
  font-size: 20rpx;
}
.footer {
  flex-wrap: wrap;
  gap: 8rpx 20rpx;
  margin-top: 18rpx;
  padding-top: 16rpx;
  color: #8b96a7;
  border-top: 1rpx solid #edf1f5;
  font-size: 19rpx;
}
</style>
