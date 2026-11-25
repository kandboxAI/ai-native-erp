<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import {
  getAssetHandover,
  listMyAssetHandovers,
  receiveAssetHandoverLine,
  rejectAssetHandoverLine,
  type AssetHandover,
  type AssetHandoverLine,
} from "@plugins/inv/miniprogram/src/api/invAssetHandover";
import { showApiError } from "@/utils/permissions";

const rows = ref<AssetHandover[]>([]);
const current = ref<AssetHandover | null>(null);
const loading = ref(false);
const actingLineId = ref("");
const rejectingLine = ref<AssetHandoverLine | null>(null);
const rejectionReason = ref("");
const rejectionError = ref("");
const directId = ref("");
const status = ref("");
const statuses = [
  { value: "", label: "全部" },
  { value: "awaiting_receipt", label: "待处理" },
  { value: "completed", label: "已完成" },
];
const statusLabels: Record<string, string> = {
  draft: "草稿",
  awaiting_receipt: "待接收",
  completed: "已完成",
  voided: "已作废",
};
const sourceLabels: Record<string, string> = {
  manual: "人工发起",
  teacher_offboarding: "教师离职交接",
};
const unitLabels: Record<string, string> = {
  bottle: "瓶",
  box: "箱",
  pack: "包",
  piece: "件",
  set: "套",
  sheet: "张",
  unit: "件",
};
const pendingCount = computed(
  () =>
    current.value?.lines.filter((line) => line.status_code === "pending")
      .length || 0,
);
const rejectedCount = computed(
  () =>
    current.value?.lines.filter((line) => line.status_code === "rejected")
      .length || 0,
);

function handoverRejectedCount(item: AssetHandover) {
  return (
    item.rejected_count ??
    item.lines.filter((line) => line.status_code === "rejected").length
  );
}

function displayStatusLabel(item: AssetHandover) {
  if (
    item.status_code === "awaiting_receipt" &&
    handoverRejectedCount(item) > 0
  )
    return "已拒收·待后勤处理";
  if (
    item.status_code === "awaiting_receipt" &&
    item.lines.some(
      (line) => line.status_code === "pending" && line.rejection_reason,
    )
  )
    return "待重新确认";
  return statusLabels[item.status_code] || item.status_code;
}

function lineStatusLabel(line: AssetHandoverLine) {
  if (line.status_code === "pending" && line.rejection_reason)
    return "待重新确认";
  return {
    pending: "待接收",
    rejected: "已拒收",
    received: "已接收",
  }[line.status_code];
}

function formatQuantity(value: string) {
  const quantity = Number(value);
  return Number.isFinite(quantity)
    ? quantity.toLocaleString("zh-CN", { maximumFractionDigits: 3 })
    : value;
}

function unitLabel(code: string) {
  return unitLabels[code] || code;
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

async function loadList() {
  loading.value = true;
  try {
    const result = await listMyAssetHandovers({
      page: 1,
      page_size: 100,
      status_code: status.value || undefined,
    });
    rows.value = result.items;
  } catch (error) {
    showApiError(error, "资产交接任务加载失败");
  } finally {
    loading.value = false;
  }
}

async function open(id: string) {
  loading.value = true;
  try {
    current.value = await getAssetHandover(id);
  } catch (error) {
    showApiError(error, "资产交接详情加载失败");
  } finally {
    loading.value = false;
  }
}

function backToList() {
  directId.value = "";
  current.value = null;
  loadList();
}

function filter(value: string) {
  status.value = value;
  loadList();
}

function confirm(title: string, content: string): Promise<boolean> {
  return new Promise((resolve) =>
    uni.showModal({
      title,
      content,
      success: (result) => resolve(Boolean(result.confirm)),
      fail: () => resolve(false),
    }),
  );
}

function openRejectDialog(line: AssetHandoverLine) {
  rejectingLine.value = line;
  rejectionReason.value = "";
  rejectionError.value = "";
}

function closeRejectDialog() {
  if (actingLineId.value) return;
  rejectingLine.value = null;
  rejectionReason.value = "";
  rejectionError.value = "";
}

async function receive(line: AssetHandoverLine) {
  if (!current.value) return;
  const accepted = await confirm(
    line.rejection_reason ? "确认重新接收" : "确认接收",
    `请确认已实际核对并接收“${line.asset_name_snapshot}”。确认后将更新资产保管责任。`,
  );
  if (!accepted) return;
  actingLineId.value = line.id;
  try {
    current.value = await receiveAssetHandoverLine(current.value.id, line.id);
    uni.showToast({ title: "资产已接收", icon: "success" });
    await loadList();
  } catch (error) {
    showApiError(error, "接收失败");
  } finally {
    actingLineId.value = "";
  }
}

async function reject() {
  const line = rejectingLine.value;
  if (!current.value || !line) return;
  const reason = rejectionReason.value.trim();
  if (!reason) {
    rejectionError.value = "请填写拒收原因";
    return;
  }
  actingLineId.value = line.id;
  try {
    current.value = await rejectAssetHandoverLine(
      current.value.id,
      line.id,
      reason,
    );
    uni.showToast({ title: "已拒收", icon: "success" });
    await loadList();
    rejectingLine.value = null;
    rejectionReason.value = "";
    rejectionError.value = "";
  } catch (error) {
    showApiError(error, "拒收失败");
  } finally {
    actingLineId.value = "";
  }
}

onLoad((options) => {
  directId.value = String(options?.id || "");
});

onShow(() => {
  loadList();
  if (directId.value) open(directId.value);
});

onPullDownRefresh(async () => {
  if (current.value) await open(current.value.id);
  else await loadList();
  uni.stopPullDownRefresh();
});
</script>

<template>
  <view class="page-shell handover-page">
    <template v-if="current">
      <view class="back-link" @tap="backToList">
        <text class="back-arrow">‹</text>
        <text>返回交接任务</text>
      </view>

      <view class="detail-summary">
        <view class="summary-top">
          <view class="summary-copy">
            <text class="summary-label">资产交接单</text>
            <text class="summary-no">{{ current.handover_no }}</text>
          </view>
          <text
            class="status-badge large"
            :class="[
              current.status_code,
              { 'has-rejected': rejectedCount > 0 },
            ]"
          >{{
            displayStatusLabel(current)
          }}</text>
        </view>
        <view class="summary-meta">
          <view>
            <text>交出人</text>
            <strong>{{ current.transferor_name_snapshot }}</strong>
          </view>
          <view>
            <text>业务来源</text>
            <strong>{{ sourceLabels[current.source_type_code] }}</strong>
          </view>
          <view>
            <text>提交时间</text>
            <strong>{{ formatDate(current.submitted_at || current.created_at) }}</strong>
          </view>
        </view>
        <view class="progress-block">
          <view class="progress-copy">
            <text>接收进度</text>
            <text>{{ current.received_count }}/{{ current.line_count }} 项</text>
          </view>
          <view class="progress-track">
            <view
              class="progress-value"
              :style="{
                width: `${current.line_count ? (current.received_count / current.line_count) * 100 : 0}%`,
              }"
            />
          </view>
        </view>
      </view>

      <view v-if="pendingCount" class="pending-tip">
        <view class="tip-icon">!</view>
        <view>
          <text>还有 {{ pendingCount }} 项资产等待确认</text>
          <text>请当面核对资产、数量及存放地点后再操作</text>
        </view>
      </view>

      <view v-if="rejectedCount" class="rejected-tip">
        <view class="tip-icon">!</view>
        <view>
          <text>您已拒收 {{ rejectedCount }} 项资产</text>
          <text>正在等待后勤核实处理，重新发起后系统会再次通知您</text>
        </view>
      </view>

      <view v-if="current.remark" class="remark-card">
        <text class="section-caption">交接备注</text>
        <text class="remark-content">{{ current.remark }}</text>
      </view>

      <view class="section-heading">
        <text>交接资产</text>
        <text>共 {{ current.line_count }} 项</text>
      </view>
      <view
        v-for="line in current.lines"
        :key="line.id"
        class="asset-card"
      >
        <view class="asset-head">
          <view class="asset-icon">资</view>
          <view class="asset-copy">
            <text class="asset-name">{{ line.asset_name_snapshot }}</text>
            <text class="asset-no">{{ line.asset_no_snapshot || "批量资产" }}</text>
          </view>
          <text class="line-status" :class="line.status_code">{{
            lineStatusLabel(line)
          }}</text>
        </view>

        <view class="asset-facts">
          <view>
            <text>规格型号</text>
            <strong>{{ line.specification_snapshot || "无规格" }}</strong>
          </view>
          <view>
            <text>交接数量</text>
            <strong class="quantity"
              >{{ formatQuantity(line.quantity) }}
              {{ unitLabel(line.unit_code_snapshot) }}</strong
            >
          </view>
        </view>

        <view class="route-panel">
          <view class="route-side origin">
            <view class="route-title">
              <view class="route-dot" />
              <text>交接前</text>
            </view>
            <text class="route-main">{{ line.from_location_name }}</text>
            <text>{{ line.from_department_name || "未关联部门" }}</text>
            <text>{{ line.from_custodian_name || "无个人保管" }}</text>
          </view>
          <view class="route-arrow">→</view>
          <view class="route-side target">
            <view class="route-title">
              <view class="route-dot" />
              <text>接收后</text>
            </view>
            <text class="route-main">{{ line.to_location_name }}</text>
            <text>{{ line.to_department_name }}</text>
            <text>{{ line.to_custodian_name || "后勤科" }}</text>
          </view>
        </view>

        <view v-if="line.rejection_reason" class="reject-note">
          <text>{{ line.status_code === "rejected" ? "已拒收" : "历史拒收原因" }}</text>
          <text>{{ line.rejection_reason }}</text>
        </view>

        <view v-if="line.can_receive" class="actions">
          <button
            v-if="line.status_code === 'pending'"
            class="action-button reject-button"
            :disabled="Boolean(actingLineId)"
            @tap="openRejectDialog(line)"
          >
            拒收
          </button>
          <button
            class="action-button receive-button"
            :disabled="Boolean(actingLineId)"
            :loading="actingLineId === line.id"
            @tap="receive(line)"
          >
            {{ line.rejection_reason ? "确认重新接收" : "确认接收" }}
          </button>
        </view>
        <view v-else-if="line.status_code === 'rejected'" class="waiting-process">
          <view class="waiting-icon">!</view>
          <view>
            <text>等待后勤处理</text>
            <text>处理完成并重新发起后，您可再次确认或拒收</text>
          </view>
        </view>
        <view v-else-if="line.confirmed_by_name" class="confirmed">
          <view class="confirmed-icon">✓</view>
          <view>
            <text>已确认接收</text>
            <text
              >{{ line.confirmed_by_name }} · {{ formatDate(line.confirmed_at) }}</text
            >
          </view>
        </view>
      </view>
    </template>

    <template v-else>
      <view class="list-intro">
        <view class="intro-icon">
          <text>交</text>
        </view>
        <view class="intro-copy">
          <text class="intro-title">我的资产交接</text>
          <text class="intro-desc">核对并接收指定交接给您的资产</text>
        </view>
        <view class="intro-decoration" />
      </view>

      <view class="business-tip">
        <view class="tip-mark">i</view>
        <text>资产接收后，保管责任将正式转移到您的名下</text>
      </view>

      <view class="status-tabs">
        <view class="status-row">
          <text
            v-for="item in statuses"
            :key="item.value"
            :class="{ active: status === item.value }"
            @tap="filter(item.value)"
            >{{ item.label }}</text
          >
        </view>
      </view>

      <view class="list-heading">
        <text>交接任务</text>
        <text v-if="!loading">{{ rows.length }} 条</text>
      </view>

      <view v-if="loading" class="loading-state">
        <view class="loading-dot" />
        <text>正在加载交接任务</text>
      </view>
      <view v-else-if="!rows.length" class="empty-panel">
        <view class="empty-illustration">✓</view>
        <text>当前没有{{ status ? statusLabels[status] : "" }}交接任务</text>
        <text>新的资产交接提交后会显示在这里</text>
      </view>
      <view v-else>
        <view
          v-for="item in rows"
          :key="item.id"
          class="handover-card"
          @tap="open(item.id)"
        >
          <view class="card-head">
            <view>
              <text class="card-source">{{ sourceLabels[item.source_type_code] }}</text>
              <text class="handover-no">{{ item.handover_no }}</text>
            </view>
            <text
              class="status-badge"
              :class="[
                item.status_code,
                { 'has-rejected': handoverRejectedCount(item) > 0 },
              ]"
            >{{
              displayStatusLabel(item)
            }}</text>
          </view>

          <view class="card-assets">
            <view class="mini-asset-icon">资</view>
            <view class="asset-summary">
              <text v-for="line in item.lines.slice(0, 2)" :key="line.id">
                {{ line.asset_name_snapshot }} × {{ formatQuantity(line.quantity) }}
                {{ unitLabel(line.unit_code_snapshot) }}
              </text>
              <text v-if="item.lines.length > 2"
                >另有 {{ item.lines.length - 2 }} 项资产</text
              >
            </view>
          </view>

          <view class="card-progress">
            <view class="progress-copy">
              <text>接收进度</text>
              <text v-if="handoverRejectedCount(item)" class="progress-rejected">
                已拒收 {{ handoverRejectedCount(item) }} 项
              </text>
              <text v-else>{{ item.received_count }}/{{ item.line_count }}</text>
            </view>
            <view class="progress-track small">
              <view
                class="progress-value"
                :style="{
                  width: `${item.line_count ? (item.received_count / item.line_count) * 100 : 0}%`,
                }"
              />
            </view>
          </view>

          <view class="card-foot">
            <view>
              <text>交出人</text>
              <text>{{ item.transferor_name_snapshot }}</text>
            </view>
            <view>
              <text>提交时间</text>
              <text>{{ formatDate(item.submitted_at || item.created_at) }}</text>
            </view>
            <text class="detail-link">查看详情 ›</text>
          </view>
        </view>
      </view>
    </template>

    <view
      v-if="rejectingLine"
      class="dialog-mask"
      @tap="closeRejectDialog"
      @touchmove.stop.prevent
    >
      <view class="reject-dialog" @tap.stop>
        <view class="dialog-handle" />
        <view class="dialog-head">
          <view class="dialog-icon">!</view>
          <view class="dialog-title-copy">
            <text class="dialog-title">拒收资产</text>
            <text>提交后，交出方可查看拒收原因并重新处理</text>
          </view>
          <view class="dialog-close" @tap.stop="closeRejectDialog">×</view>
        </view>

        <view class="reject-asset-summary">
          <view class="mini-asset-icon">资</view>
          <view>
            <text>{{ rejectingLine.asset_name_snapshot }}</text>
            <text>
              {{ rejectingLine.specification_snapshot || "无规格" }} ·
              {{ formatQuantity(rejectingLine.quantity) }}
              {{ unitLabel(rejectingLine.unit_code_snapshot) }}
            </text>
          </view>
        </view>

        <view class="reason-label">
          <text>拒收原因</text>
          <text>必填</text>
        </view>
        <view class="reason-field" :class="{ error: rejectionError }">
          <textarea
            v-model="rejectionReason"
            :disabled="Boolean(actingLineId)"
            :focus="true"
            :maxlength="200"
            cursor-spacing="28"
            placeholder="请说明资产、数量、状态或交接信息存在的问题"
            placeholder-class="reason-placeholder"
            @input="rejectionError = ''"
          ></textarea>
          <text class="reason-count">{{ rejectionReason.length }}/200</text>
        </view>
        <view v-if="rejectionError" class="reason-error">
          <text>!</text>
          <text>{{ rejectionError }}</text>
        </view>
        <view class="reason-example">
          <text>填写建议</text>
          <text>例如：实物型号不符、数量有误、资产损坏或未实际收到。</text>
        </view>

        <view class="dialog-actions">
          <button
            class="dialog-button cancel"
            :disabled="Boolean(actingLineId)"
            @tap="closeRejectDialog"
          >
            取消
          </button>
          <button
            class="dialog-button submit"
            :disabled="Boolean(actingLineId)"
            :loading="actingLineId === rejectingLine.id"
            @tap="reject"
          >
            提交拒收
          </button>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.handover-page {
  min-height: 100vh;
  padding: 24rpx 24rpx calc(100rpx + env(safe-area-inset-bottom));
  color: #1d3147;
  background: #f3f6fa;
  box-sizing: border-box;
}

.list-intro {
  position: relative;
  display: flex;
  min-height: 132rpx;
  align-items: center;
  gap: 22rpx;
  overflow: hidden;
  padding: 30rpx;
  color: #fff;
  border-radius: 28rpx;
  background: linear-gradient(135deg, #1859b8 0%, #2479df 72%, #3d91ec 100%);
  box-shadow: 0 16rpx 36rpx rgba(23, 92, 184, 0.2);
}

.intro-icon {
  display: grid;
  width: 82rpx;
  height: 82rpx;
  flex: 0 0 82rpx;
  place-items: center;
  border: 1rpx solid rgba(255, 255, 255, 0.35);
  border-radius: 24rpx;
  background: rgba(255, 255, 255, 0.16);
}

.intro-icon text {
  font-size: 34rpx;
  font-weight: 750;
}

.intro-copy,
.summary-copy,
.asset-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.intro-title {
  font-size: 38rpx;
  font-weight: 760;
  letter-spacing: 1rpx;
}

.intro-desc {
  margin-top: 10rpx;
  font-size: 22rpx;
  opacity: 0.85;
}

.intro-decoration {
  position: absolute;
  right: -34rpx;
  bottom: -48rpx;
  width: 180rpx;
  height: 180rpx;
  border: 24rpx solid rgba(255, 255, 255, 0.08);
  border-radius: 50%;
}

.business-tip,
.pending-tip {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 20rpx;
  padding: 18rpx 20rpx;
  color: #4f6b88;
  border: 1rpx solid #dce9f8;
  border-radius: 18rpx;
  background: #edf5ff;
  font-size: 21rpx;
}

.tip-mark,
.tip-icon {
  display: grid;
  width: 34rpx;
  height: 34rpx;
  flex: 0 0 34rpx;
  color: #1769d2;
  border-radius: 50%;
  background: #d8eaff;
  font-size: 20rpx;
  font-weight: 750;
  place-items: center;
}

.status-tabs {
  margin-top: 24rpx;
  padding: 8rpx;
  border: 1rpx solid #e6ebf2;
  border-radius: 20rpx;
  background: #fff;
}

.status-row {
  display: flex;
}

.status-row text {
  flex: 1;
  padding: 16rpx 8rpx;
  color: #748398;
  text-align: center;
  border-radius: 14rpx;
  font-size: 23rpx;
}

.status-row text.active {
  color: #1769d2;
  background: #eaf3ff;
  font-weight: 680;
}

.list-heading,
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 30rpx 4rpx 16rpx;
}

.list-heading text:first-child,
.section-heading text:first-child {
  font-size: 29rpx;
  font-weight: 720;
}

.list-heading text:last-child,
.section-heading text:last-child {
  color: #94a0af;
  font-size: 20rpx;
}

.handover-card,
.asset-card,
.remark-card,
.detail-summary {
  margin-bottom: 20rpx;
  padding: 26rpx;
  border: 1rpx solid #e5ebf2;
  border-radius: 24rpx;
  background: #fff;
  box-shadow: 0 8rpx 26rpx rgba(28, 68, 105, 0.05);
}

.handover-card:active {
  transform: scale(0.992);
  background: #fbfdff;
}

.card-head,
.asset-head,
.summary-top,
.progress-copy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
}

.card-head > view {
  min-width: 0;
}

.card-source,
.handover-no {
  display: block;
}

.card-source {
  color: #73849a;
  font-size: 20rpx;
}

.handover-no {
  max-width: 500rpx;
  margin-top: 7rpx;
  overflow: hidden;
  font-size: 27rpx;
  font-weight: 720;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-badge,
.line-status {
  flex: 0 0 auto;
  padding: 7rpx 16rpx;
  color: #a8660d;
  border-radius: 999rpx;
  background: #fff1d8;
  font-size: 20rpx;
}

.status-badge.large {
  padding: 9rpx 18rpx;
  font-size: 21rpx;
}

.status-badge.completed,
.line-status.received {
  color: #08735c;
  background: #dff7ef;
}

.status-badge.has-rejected {
  color: #b42c35;
  background: #ffeaec;
}

.status-badge.draft,
.status-badge.voided {
  color: #6f7d90;
  background: #eef1f5;
}

.line-status.rejected {
  color: #b42c35;
  background: #ffeaec;
}

.card-assets {
  display: flex;
  align-items: center;
  gap: 18rpx;
  margin-top: 24rpx;
  padding: 20rpx;
  border-radius: 18rpx;
  background: #f6f9fd;
}

.mini-asset-icon,
.asset-icon {
  display: grid;
  color: #1769d2;
  background: #e4f0ff;
  font-weight: 750;
  place-items: center;
}

.mini-asset-icon {
  width: 56rpx;
  height: 56rpx;
  flex: 0 0 56rpx;
  border-radius: 16rpx;
  font-size: 23rpx;
}

.asset-summary {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 7rpx;
  color: #40566e;
  font-size: 22rpx;
}

.asset-summary text:last-child:not(:first-child) {
  color: #8592a3;
}

.card-progress {
  margin-top: 22rpx;
}

.progress-copy {
  color: #7c8999;
  font-size: 20rpx;
}

.progress-copy text:last-child {
  color: #3b5874;
  font-weight: 650;
}

.progress-copy .progress-rejected {
  color: #b42c35;
}

.progress-track {
  height: 12rpx;
  overflow: hidden;
  margin-top: 14rpx;
  border-radius: 999rpx;
  background: #e8edf3;
}

.progress-track.small {
  height: 8rpx;
  margin-top: 10rpx;
}

.progress-value {
  height: 100%;
  min-width: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, #2480e8, #1764cc);
}

.card-foot {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: 16rpx;
  margin-top: 22rpx;
  padding-top: 20rpx;
  padding-right: 108rpx;
  border-top: 1rpx solid #edf1f5;
}

.card-foot view text {
  display: block;
}

.card-foot view text:first-child {
  color: #9aa5b3;
  font-size: 18rpx;
}

.card-foot view text:last-child {
  margin-top: 5rpx;
  color: #53677e;
  font-size: 20rpx;
}

.detail-link {
  position: absolute;
  right: 0;
  bottom: 2rpx;
  color: #1769d2;
  font-size: 20rpx;
}

.loading-state,
.empty-panel {
  display: flex;
  min-height: 340rpx;
  align-items: center;
  justify-content: center;
  color: #8996a6;
  border: 1rpx dashed #dce3ec;
  border-radius: 24rpx;
  background: #fff;
  flex-direction: column;
}

.loading-dot {
  width: 26rpx;
  height: 26rpx;
  margin-bottom: 18rpx;
  border: 5rpx solid #dce9f8;
  border-top-color: #1769d2;
  border-radius: 50%;
}

.empty-illustration {
  display: grid;
  width: 86rpx;
  height: 86rpx;
  margin-bottom: 22rpx;
  color: #4ca783;
  border-radius: 28rpx;
  background: #e8f7f1;
  font-size: 38rpx;
  place-items: center;
}

.empty-panel text:nth-child(2) {
  color: #435970;
  font-size: 26rpx;
  font-weight: 680;
}

.empty-panel text:last-child {
  margin-top: 10rpx;
  font-size: 20rpx;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 8rpx;
  margin: 2rpx 0 18rpx;
  color: #1769d2;
  font-size: 23rpx;
}

.back-arrow {
  margin-top: -3rpx;
  font-size: 38rpx;
  line-height: 1;
}

.detail-summary {
  padding: 30rpx;
  border-color: #dce9f8;
  background: linear-gradient(145deg, #fafdff, #eef6ff);
}

.summary-label,
.summary-no {
  display: block;
}

.summary-label {
  color: #70839a;
  font-size: 20rpx;
}

.summary-no {
  margin-top: 7rpx;
  font-size: 29rpx;
  font-weight: 750;
}

.summary-meta {
  display: grid;
  grid-template-columns: 0.85fr 1.15fr;
  gap: 22rpx;
  margin-top: 28rpx;
  padding-top: 22rpx;
  border-top: 1rpx solid #dce7f3;
}

.summary-meta view:last-child {
  grid-column: 1 / -1;
}

.summary-meta text,
.summary-meta strong {
  display: block;
}

.summary-meta text {
  color: #8b98a8;
  font-size: 19rpx;
}

.summary-meta strong {
  margin-top: 6rpx;
  color: #314a63;
  font-size: 22rpx;
  font-weight: 650;
}

.progress-block {
  margin-top: 26rpx;
}

.pending-tip {
  align-items: flex-start;
  margin: 0 0 20rpx;
  color: #795a1d;
  border-color: #f2dfb4;
  background: #fff8e9;
}

.pending-tip .tip-icon {
  color: #a86908;
  background: #ffe8b5;
}

.pending-tip text {
  display: block;
}

.pending-tip text:first-child {
  font-weight: 680;
}

.pending-tip text:last-child {
  margin-top: 6rpx;
  color: #9a7b42;
  font-size: 19rpx;
}

.rejected-tip {
  display: flex;
  align-items: flex-start;
  gap: 16rpx;
  margin: 0 0 20rpx;
  padding: 18rpx 20rpx;
  color: #98343c;
  border: 1rpx solid #f2c8cc;
  border-radius: 18rpx;
  background: #fff1f2;
  font-size: 21rpx;
}

.rejected-tip .tip-icon {
  color: #b52f3a;
  background: #ffdadd;
}

.rejected-tip text {
  display: block;
}

.rejected-tip text:first-child {
  font-weight: 680;
}

.rejected-tip text:last-child {
  margin-top: 6rpx;
  color: #ad6970;
  font-size: 19rpx;
}

.section-caption,
.remark-content {
  display: block;
}

.section-caption {
  font-size: 26rpx;
  font-weight: 700;
}

.remark-content {
  margin-top: 14rpx;
  color: #5e7186;
  font-size: 22rpx;
  line-height: 1.65;
}

.asset-head {
  justify-content: flex-start;
}

.asset-icon {
  width: 68rpx;
  height: 68rpx;
  flex: 0 0 68rpx;
  border-radius: 19rpx;
  font-size: 27rpx;
}

.asset-copy {
  flex: 1;
}

.asset-name,
.asset-no {
  display: block;
}

.asset-name {
  font-size: 28rpx;
  font-weight: 720;
}

.asset-no {
  margin-top: 6rpx;
  color: #98a3b1;
  font-size: 19rpx;
}

.asset-facts {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 16rpx;
  margin-top: 24rpx;
}

.asset-facts view {
  padding: 18rpx;
  border-radius: 16rpx;
  background: #f6f8fb;
}

.asset-facts text,
.asset-facts strong {
  display: block;
}

.asset-facts text {
  color: #929ead;
  font-size: 18rpx;
}

.asset-facts strong {
  margin-top: 7rpx;
  color: #425970;
  font-size: 22rpx;
  font-weight: 650;
}

.asset-facts .quantity {
  color: #1769d2;
}

.route-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34rpx minmax(0, 1fr);
  align-items: center;
  gap: 10rpx;
  margin-top: 24rpx;
  padding: 22rpx;
  border: 1rpx solid #e7edf4;
  border-radius: 18rpx;
}

.route-side {
  min-width: 0;
}

.route-side > text {
  display: block;
  overflow: hidden;
  margin-top: 7rpx;
  color: #8794a4;
  font-size: 18rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-side .route-main {
  margin-top: 13rpx;
  color: #344e68;
  font-size: 22rpx;
  font-weight: 680;
}

.route-title {
  display: flex;
  align-items: center;
  gap: 8rpx;
  color: #718197;
  font-size: 19rpx;
}

.route-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: #9aa8b7;
}

.route-side.target .route-dot {
  background: #1769d2;
}

.route-side.target .route-title {
  color: #1769d2;
}

.route-arrow {
  color: #9babbb;
  text-align: center;
  font-size: 28rpx;
}

.reject-note {
  margin-top: 20rpx;
  padding: 18rpx 20rpx;
  color: #b13d45;
  border-radius: 15rpx;
  background: #fff0f1;
}

.reject-note text {
  display: block;
  font-size: 21rpx;
}

.reject-note text:first-child {
  margin-bottom: 6rpx;
  font-weight: 700;
}

.actions {
  display: flex;
  gap: 16rpx;
  margin-top: 26rpx;
  padding-top: 24rpx;
  border-top: 1rpx solid #edf1f5;
}

.action-button {
  height: 82rpx;
  margin: 0;
  border: 0;
  border-radius: 17rpx;
  font-size: 25rpx;
  font-weight: 650;
  line-height: 82rpx;
}

.action-button::after {
  border: 0;
}

.reject-button {
  width: 34%;
  color: #b13d45;
  background: #fff0f1;
}

.receive-button {
  flex: 1;
  color: #fff;
  background: linear-gradient(135deg, #247ee5, #145fc8);
  box-shadow: 0 9rpx 20rpx rgba(23, 105, 210, 0.2);
}

.receive-button.full {
  width: 100%;
}

.action-button[disabled] {
  opacity: 0.65;
}

.confirmed {
  display: flex;
  align-items: center;
  gap: 14rpx;
  margin-top: 22rpx;
  padding: 17rpx;
  color: #08735c;
  border-radius: 15rpx;
  background: #eaf8f3;
}

.waiting-process {
  display: flex;
  align-items: center;
  gap: 14rpx;
  margin-top: 22rpx;
  padding: 17rpx;
  color: #9b3942;
  border-radius: 15rpx;
  background: #fff1f2;
}

.waiting-icon {
  display: grid;
  width: 38rpx;
  height: 38rpx;
  flex: 0 0 38rpx;
  color: #fff;
  border-radius: 50%;
  background: #cf4b56;
  font-size: 21rpx;
  font-weight: 700;
  place-items: center;
}

.waiting-process text {
  display: block;
}

.waiting-process text:first-child {
  font-size: 22rpx;
  font-weight: 680;
}

.waiting-process text:last-child {
  margin-top: 4rpx;
  color: #b06d73;
  font-size: 18rpx;
}

.confirmed-icon {
  display: grid;
  width: 38rpx;
  height: 38rpx;
  flex: 0 0 38rpx;
  color: #fff;
  border-radius: 50%;
  background: #19a17d;
  font-size: 21rpx;
  place-items: center;
}

.confirmed text {
  display: block;
}

.confirmed text:first-child {
  font-size: 22rpx;
  font-weight: 680;
}

.confirmed text:last-child {
  margin-top: 4rpx;
  color: #589382;
  font-size: 18rpx;
}

.dialog-mask {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 28rpx 24rpx calc(28rpx + env(safe-area-inset-bottom));
  background: rgba(20, 34, 49, 0.58);
  box-sizing: border-box;
}

.reject-dialog {
  position: relative;
  width: 100%;
  max-width: 700rpx;
  padding: 18rpx 28rpx 28rpx;
  border-radius: 30rpx;
  background: #fff;
  box-shadow: 0 24rpx 70rpx rgba(9, 29, 50, 0.24);
  box-sizing: border-box;
}

.dialog-handle {
  width: 66rpx;
  height: 7rpx;
  margin: 0 auto 24rpx;
  border-radius: 99rpx;
  background: #dce2e9;
}

.dialog-head {
  display: flex;
  align-items: flex-start;
  gap: 18rpx;
}

.dialog-icon {
  display: grid;
  width: 66rpx;
  height: 66rpx;
  flex: 0 0 66rpx;
  color: #bd3540;
  border-radius: 20rpx;
  background: #ffeaec;
  font-size: 31rpx;
  font-weight: 760;
  place-items: center;
}

.dialog-title-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.dialog-title {
  color: #23394f;
  font-size: 31rpx;
  font-weight: 750;
}

.dialog-title-copy text:last-child {
  margin-top: 7rpx;
  color: #8996a5;
  font-size: 20rpx;
  line-height: 1.45;
}

.dialog-close {
  display: grid;
  width: 52rpx;
  height: 52rpx;
  flex: 0 0 52rpx;
  color: #8290a0;
  border-radius: 50%;
  background: #f1f4f7;
  font-size: 34rpx;
  line-height: 1;
  place-items: center;
}

.reject-asset-summary {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 28rpx;
  padding: 18rpx 20rpx;
  border: 1rpx solid #e7edf4;
  border-radius: 18rpx;
  background: #f7f9fc;
}

.reject-asset-summary > view:last-child {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.reject-asset-summary text:first-child {
  overflow: hidden;
  color: #354d65;
  font-size: 23rpx;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reject-asset-summary text:last-child {
  margin-top: 5rpx;
  color: #8b98a7;
  font-size: 19rpx;
}

.reason-label {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin: 28rpx 2rpx 12rpx;
}

.reason-label text:first-child {
  color: #30475e;
  font-size: 24rpx;
  font-weight: 680;
}

.reason-label text:last-child {
  padding: 3rpx 9rpx;
  color: #b52f3a;
  border-radius: 8rpx;
  background: #ffeaec;
  font-size: 17rpx;
}

.reason-field {
  position: relative;
  overflow: hidden;
  padding: 20rpx 20rpx 45rpx;
  border: 2rpx solid #dfe6ee;
  border-radius: 18rpx;
  background: #fbfcfe;
  transition: border-color 0.2s, background 0.2s;
}

.reason-field:focus-within {
  border-color: #4b8ee0;
  background: #fff;
}

.reason-field.error {
  border-color: #df6670;
  background: #fffafb;
}

.reason-field textarea {
  width: 100%;
  height: 146rpx;
  color: #263d54;
  background: transparent;
  font-size: 24rpx;
  line-height: 1.55;
}

.reason-placeholder {
  color: #aab3bf;
  font-size: 23rpx;
}

.reason-count {
  position: absolute;
  right: 18rpx;
  bottom: 13rpx;
  color: #a0aab7;
  font-size: 18rpx;
}

.reason-error {
  display: flex;
  align-items: center;
  gap: 7rpx;
  margin: 9rpx 3rpx 0;
  color: #bc3540;
  font-size: 19rpx;
}

.reason-error text:first-child {
  display: grid;
  width: 24rpx;
  height: 24rpx;
  border: 1rpx solid currentColor;
  border-radius: 50%;
  font-size: 16rpx;
  place-items: center;
}

.reason-example {
  margin-top: 15rpx;
  padding: 15rpx 18rpx;
  color: #76879a;
  border-radius: 14rpx;
  background: #f3f7fb;
  font-size: 19rpx;
  line-height: 1.5;
}

.reason-example text:first-child {
  margin-right: 10rpx;
  color: #4b6784;
  font-weight: 680;
}

.dialog-actions {
  display: flex;
  gap: 16rpx;
  margin-top: 26rpx;
}

.dialog-button {
  height: 84rpx;
  margin: 0;
  border: 0;
  border-radius: 18rpx;
  font-size: 25rpx;
  font-weight: 680;
  line-height: 84rpx;
}

.dialog-button::after {
  border: 0;
}

.dialog-button.cancel {
  width: 34%;
  color: #52677d;
  background: #f0f3f7;
}

.dialog-button.submit {
  flex: 1;
  color: #fff;
  background: linear-gradient(135deg, #d6535e, #b52f3a);
  box-shadow: 0 9rpx 20rpx rgba(181, 47, 58, 0.2);
}

.dialog-button[disabled] {
  opacity: 0.65;
}
</style>
