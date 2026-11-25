<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status: string }>();

const tone = computed(() => {
  if (
    [
      "正常",
      "出勤",
      "已批准",
      "已处理",
      "已销假",
      "无需处理",
      "已通过",
      "已确认",
      "已确认参会",
      "已完成",
      "已反馈",
      "待验收",
      "已办",
      "已读"
    ].includes(props.status)
  )
    return "success";
  if (
    ["已驳回", "已退回", "缺卡", "缺勤", "异常", "红灯"].includes(props.status)
  )
    return "danger";
  if (["迟到", "早退", "待处理", "待补充材料", "草稿", "未读"].includes(props.status))
    return "warning";
  if (props.status.includes("待") || props.status === "请假") return "primary";
  return "neutral";
});
</script>

<template>
  <text class="badge" :class="`badge--${tone}`">{{ status }}</text>
</template>

<style scoped lang="scss">
.badge {
  display: inline-flex;
  height: 46rpx;
  align-items: center;
  padding: 0 17rpx;
  border-radius: 99rpx;
  font-size: 21rpx;
  font-weight: 600;
  line-height: 46rpx;
  white-space: nowrap;
}

.badge--success {
  color: #087b4a;
  background: #e7f8f0;
}
.badge--danger {
  color: #c83241;
  background: #fff0f1;
}
.badge--warning {
  color: #a76500;
  background: #fff5df;
}
.badge--primary {
  color: #1769e0;
  background: #eaf2ff;
}
.badge--neutral {
  color: #68768a;
  background: #eef1f5;
}
</style>
