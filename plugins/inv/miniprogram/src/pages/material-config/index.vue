<template>
  <view class="page-shell placeholder-page">
    <view class="placeholder-card card">
      <view class="placeholder-icon">配</view>
      <text class="placeholder-tag">管理端功能</text>
      <text class="placeholder-title">物资配置</text>
      <text class="placeholder-copy">
        移动端物资配置尚未接入。请在管理端维护物料、仓库、库位与单据类型；审批规则在系统管理的审批流程中维护。
      </text>
      <view class="placeholder-note">
        <view class="note-dot" />
        <text>移动端仍可使用库存查询和已开通的业务操作</text>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.placeholder-page {
  display: flex;
  min-height: 100vh;
  align-items: flex-start;
  justify-content: center;
  padding-top: 90rpx;
}

.placeholder-card {
  display: flex;
  width: 100%;
  min-height: 500rpx;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 54rpx 40rpx;
  text-align: center;
}

.placeholder-icon {
  display: flex;
  width: 94rpx;
  height: 94rpx;
  align-items: center;
  justify-content: center;
  color: #7952c7;
  background: #f0eaff;
  border-radius: 30rpx;
  font-size: 36rpx;
  font-weight: 750;
}

.placeholder-tag {
  margin-top: 24rpx;
  padding: 6rpx 14rpx;
  color: #7952c7;
  background: #f0eaff;
  border-radius: 99rpx;
  font-size: 20rpx;
}

.placeholder-title {
  margin-top: 18rpx;
  color: var(--hq-ink);
  font-size: 32rpx;
  font-weight: 750;
}

.placeholder-copy {
  max-width: 560rpx;
  margin-top: 18rpx;
  color: var(--hq-body);
  font-size: 24rpx;
  line-height: 1.75;
}

.placeholder-note {
  display: flex;
  align-items: center;
  margin-top: 34rpx;
  padding: 17rpx 20rpx;
  color: var(--hq-muted);
  background: #f6f8fb;
  border-radius: 18rpx;
  font-size: 21rpx;
}

.note-dot {
  width: 9rpx;
  height: 9rpx;
  margin-right: 11rpx;
  background: #7952c7;
  border-radius: 50%;
}
</style>
