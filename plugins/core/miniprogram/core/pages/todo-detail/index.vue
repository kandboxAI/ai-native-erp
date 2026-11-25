<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { requestApi } from "@/api/client";
import { confirmAction, hasPermission } from "@/utils/permissions";

interface Detail {
  task_name: string;
  status_code: string;
  business_summary?: string;
  business_detail?: { fields?: { label: string; value: string; type?: string }[] };
}

const id = ref("");
const detail = ref<Detail | null>(null);
const error = ref("");
const busy = ref(false);
const loading = ref(false);
const comment = ref("");

function statusLabel(status: string) {
  if (status === "pending") return "待处理";
  if (status === "completed") return "已完成";
  if (status === "rejected") return "已驳回";
  return status || "未知";
}

async function load() {
  loading.value = true;
  try {
    error.value = "";
    detail.value = await requestApi<Detail>({
      path: `/api/workflow_task/detail/${encodeURIComponent(id.value)}`,
    });
  } catch (reason) {
    detail.value = null;
    error.value = reason instanceof Error ? reason.message : "详情加载失败";
  } finally {
    loading.value = false;
  }
}

onLoad((options) => {
  id.value = String(options?.id || "");
  if (id.value) void load();
  else error.value = "缺少待办编号";
});

async function act(action: "complete" | "reject") {
  if (action === "reject" && !comment.value.trim()) {
    error.value = "请填写驳回原因";
    return;
  }
  if (
    busy.value ||
    !(await confirmAction(
      "确认办理",
      action === "complete" ? "确认通过此待办？" : "确认驳回此待办？",
    ))
  )
    return;
  busy.value = true;
  try {
    await requestApi({
      path: `/api/workflow_task/${action}/${encodeURIComponent(id.value)}`,
      method: "POST",
      data: { comment: comment.value.trim() },
    });
    await load();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "办理失败";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <view class="page-shell detail-page">
    <view v-if="loading" class="state-panel">
      <view class="state-icon">…</view>
      <text>正在加载待办详情</text>
    </view>

    <view v-else-if="error && !detail" class="state-panel state-panel--error" @tap="load">
      <view class="state-icon">!</view>
      <text class="state-title">详情加载失败</text>
      <text class="state-copy">{{ error }}，点击重试</text>
    </view>

    <template v-else-if="detail">
      <view class="detail-head card">
        <view class="row between">
          <text class="detail-title">{{ detail.task_name || "待办详情" }}</text>
          <text class="status-tag" :class="`status-tag--${detail.status_code}`">
            {{ statusLabel(detail.status_code) }}
          </text>
        </view>
        <text class="detail-summary">
          {{ detail.business_summary || "暂无业务摘要" }}
        </text>
      </view>

      <view class="detail-card card">
        <text class="block-title">业务信息</text>
        <view
          v-for="(field, index) in detail.business_detail?.fields || []"
          :key="index"
          class="field-row"
        >
          <text class="field-label">{{ field.label }}</text>
          <image v-if="field.type === 'avatar' && field.value" class="field-avatar" :src="field.value" mode="aspectFill" />
          <text v-else class="field-value">{{ field.value || "—" }}</text>
        </view>
        <view v-if="!detail.business_detail?.fields?.length" class="empty-fields">
          暂无更多业务字段
        </view>
      </view>

      <view v-if="detail.status_code === 'pending'" class="action-card card">
        <text class="block-title">办理意见</text>
        <textarea
          v-model="comment"
          class="comment-input"
          maxlength="200"
          placeholder="同意时选填，驳回时必须填写原因"
        />
        <text v-if="error" class="inline-error">{{ error }}</text>
        <view v-if="hasPermission('workflow_task:complete')" class="action-row">
          <button
            class="action-button action-button--reject"
            :disabled="busy"
            @tap="act('reject')"
          >
            驳回
          </button>
          <button
            class="action-button action-button--approve"
            :disabled="busy"
            @tap="act('complete')"
          >
            {{ busy ? "处理中…" : "通过" }}
          </button>
        </view>
        <view v-else class="permission-note">当前账号没有办理此任务的权限</view>
      </view>
    </template>
  </view>
</template>

<style scoped lang="scss">
.detail-page {
  padding-top: 28rpx;
  padding-bottom: 48rpx;
}

.detail-head {
  padding: 32rpx;
  border-top: 7rpx solid var(--hq-primary);
}

.detail-title {
  min-width: 0;
  flex: 1;
  margin-right: 18rpx;
  color: var(--hq-ink);
  font-size: 32rpx;
  font-weight: 750;
  line-height: 1.45;
}

.detail-summary {
  display: block;
  margin-top: 20rpx;
  color: var(--hq-body);
  font-size: 25rpx;
  line-height: 1.65;
}

.status-tag {
  flex: 0 0 auto;
  padding: 7rpx 14rpx;
  color: #b56c12;
  background: #fff1df;
  border-radius: 99rpx;
  font-size: 20rpx;
}

.status-tag--completed {
  color: #15895e;
  background: #e4f7ef;
}

.status-tag--rejected {
  color: #bd414b;
  background: #fff0f1;
}

.detail-card,
.action-card {
  padding: 30rpx;
}

.block-title {
  display: block;
  margin-bottom: 18rpx;
  color: var(--hq-ink);
  font-size: 28rpx;
  font-weight: 750;
}

.field-avatar { width: 112rpx; height: 112rpx; flex-shrink: 0; border-radius: 50%; }

.field-row {
  display: flex;
  align-items: flex-start;
  padding: 18rpx 0;
  border-bottom: 1rpx solid #eef2f6;
}

.field-row:last-child {
  border-bottom: 0;
}

.field-label {
  width: 190rpx;
  flex: 0 0 190rpx;
  color: var(--hq-muted);
  font-size: 23rpx;
  line-height: 1.55;
}

.field-value {
  min-width: 0;
  flex: 1;
  color: var(--hq-ink);
  font-size: 24rpx;
  line-height: 1.55;
  text-align: right;
  word-break: break-all;
}

.empty-fields,
.permission-note {
  padding: 22rpx;
  color: var(--hq-muted);
  background: #f7f9fc;
  border-radius: 18rpx;
  font-size: 23rpx;
  text-align: center;
}

.comment-input {
  width: 100%;
  min-height: 190rpx;
  padding: 22rpx 24rpx;
  color: var(--hq-ink);
  background: #f6f8fb;
  border: 2rpx solid transparent;
  border-radius: 20rpx;
  font-size: 25rpx;
  line-height: 1.6;
}

.inline-error {
  display: block;
  margin-top: 14rpx;
  color: var(--hq-danger);
  font-size: 22rpx;
}

.action-row {
  display: flex;
  gap: 18rpx;
  margin-top: 24rpx;
}

.action-button {
  height: 84rpx;
  flex: 1;
  margin: 0;
  border-radius: 22rpx;
  font-size: 27rpx;
  font-weight: 700;
  line-height: 84rpx;
}

.action-button--reject {
  color: var(--hq-danger);
  background: #fff0f1;
}

.action-button--approve {
  color: #fff;
  background: linear-gradient(135deg, #2177ea, #0e55c3);
  box-shadow: 0 12rpx 26rpx rgba(23, 105, 224, 0.2);
}

.state-panel {
  display: flex;
  min-height: 360rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40rpx;
  color: var(--hq-muted);
  background: #fff;
  border: 1rpx solid var(--hq-line);
  border-radius: 28rpx;
  text-align: center;
}

.state-panel--error {
  background: #fffafa;
  border-color: #f5dfe1;
}

.state-icon {
  display: flex;
  width: 76rpx;
  height: 76rpx;
  align-items: center;
  justify-content: center;
  margin-bottom: 18rpx;
  color: var(--hq-primary);
  background: var(--hq-primary-soft);
  border-radius: 24rpx;
  font-size: 31rpx;
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
</style>
