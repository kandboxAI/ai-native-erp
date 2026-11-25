<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  createMaterialRequisition,
  getMaterialRequisitionOptions,
  listAvailableMaterials,
  type MaterialOption,
  type RequisitionWarehouseOption,
} from "@plugins/inv/miniprogram/src/api/inventoryRequisition";
import { showApiError } from "@/utils/permissions";
import { formatQuantity } from "../material/shared/utils/quantity";

import ImageUploadPicker from "@/components/ImageUploadPicker.vue";
import { discardFile, type ImageUploadItem } from "@/api/systemFile";
const photos = ref<ImageUploadItem[]>([]);
const loading = ref(false);
const warehouseState = ref<"loading" | "ready" | "empty" | "error">("loading");
const submitting = ref(false);
const keyword = ref("");
const purpose = ref("");
const custodyLocationNote = ref("");
const warehouseId = ref("");
const warehouses = ref<RequisitionWarehouseOption[]>([]);
const approvalDepartmentName = computed(() => warehouses.value.find((item) => item.id === warehouseId.value)?.requisition_approval_department_name);
const materials = ref<MaterialOption[]>([]);
const quantities = ref<Record<string, number>>({});
const optionKey = (item: MaterialOption) => `${item.warehouse_id}:${item.id}`;
const selectedCount = computed(
  () =>
    Object.values(quantities.value).filter((value) => Number(value) > 0).length,
);

async function load() {
  if (!warehouseId.value) return;
  loading.value = true;
  try {
    materials.value = (
      await listAvailableMaterials(keyword.value.trim(), warehouseId.value)
    ).items;
  } catch (error) {
    showApiError(error, "可领用物资加载失败");
  } finally {
    loading.value = false;
  }
}

async function initialize() {
  if (submitting.value) return;
  warehouseState.value = "loading";
  loading.value = true;
  try {
    const options = await getMaterialRequisitionOptions();
    warehouses.value = options.warehouses;
    warehouseId.value = options.warehouses[0]?.id || "";
    warehouseState.value = warehouseId.value ? "ready" : "empty";
    if (!warehouseId.value) {
      uni.showToast({ title: "暂无可申请仓库", icon: "none" });
      return;
    }
    await load();
  } catch (error) {
    warehouseState.value = "error";
    showApiError(error, "申请仓库加载失败");
  } finally {
    loading.value = false;
  }
}

function changeWarehouse(id: string) {
  if (submitting.value) return;
  if (warehouseId.value === id) return;
  for (const item of photos.value)
    if (item.attachment)
      void discardFile(item.attachment.id).catch(() => undefined);
  photos.value = [];
  warehouseId.value = id;
  quantities.value = {};
  materials.value = [];
  load();
}

function change(item: MaterialOption, delta: number) {
  const key = optionKey(item);
  const current = Number(quantities.value[key] || 0);
  quantities.value[key] = Math.max(
    0,
    Math.min(Number(item.available_quantity), current + delta),
  );
}

function quantityOf(item: MaterialOption) {
  return Number(quantities.value[optionKey(item)] || 0);
}

function inputQuantity(item: MaterialOption, event: unknown) {
  const value = Number(
    (event as { detail: { value: string } }).detail.value || 0,
  );
  quantities.value[optionKey(item)] = Math.max(
    0,
    Math.min(
      Number(item.available_quantity),
      Number.isFinite(value) ? value : 0,
    ),
  );
}

function clearKeyword() {
  if (!keyword.value) return;
  keyword.value = "";
  load();
}

async function submit() {
  if (submitting.value) return;
  if (photos.value.some((item) => item.status !== "ready"))
    return uni.showToast({
      title: "请等待照片上传完成或移除失败照片",
      icon: "none",
    });
  const lines = materials.value
    .filter((item) => Number(quantities.value[optionKey(item)]) > 0)
    .map((item) => ({
      item_id: item.id,
      warehouse_id: item.warehouse_id,
      quantity: Number(quantities.value[optionKey(item)]),
    }));
  if (!purpose.value.trim())
    return uni.showToast({ title: "请填写领用用途", icon: "none" });
  if (!warehouseId.value)
    return uni.showToast({ title: "请选择申请仓库", icon: "none" });
  if (!lines.length)
    return uni.showToast({ title: "请至少选择一种物资", icon: "none" });
  submitting.value = true;
  try {
    const result = await createMaterialRequisition({
      photo_file_ids: photos.value.map((item) => item.attachment!.id),
      warehouse_id: warehouseId.value,
      purpose: purpose.value.trim(),
      custody_location_note: custodyLocationNote.value.trim() || undefined,
      lines,
    });
    photos.value = [];
    const firstRequest = result.requests[0];
    if (!firstRequest) throw new Error("申请提交成功，但未返回申请单");
    uni.showToast({
      title:
        result.requests.length > 1
          ? `已拆分为${result.requests.length}张申请`
          : "申请已提交",
      icon: "success",
    });
    setTimeout(
      () =>
        uni.redirectTo({
          url: `/pages/material-detail/index?id=${firstRequest.id}`,
        }),
      500,
    );
  } catch (error) {
    showApiError(error, "申请提交失败");
  } finally {
    submitting.value = false;
  }
}

onMounted(initialize);
</script>

<template>
  <view class="page-shell form-page">
    <view class="card warehouse-card">
      <text class="title-md">申请仓库</text>
      <view v-if="warehouses.length > 1" class="warehouse-options">
        <view
          v-for="warehouse in warehouses"
          :key="warehouse.id"
          :class="{ active: warehouseId === warehouse.id }"
          @tap="changeWarehouse(warehouse.id)"
        >
          <text>{{ warehouse.warehouse_name }}</text>
          <text>{{ warehouse.warehouse_no }}</text>
        </view>
      </view>
      <text v-else class="fixed-warehouse">
        {{
          warehouses[0]?.warehouse_name ||
          (warehouseState === "loading"
            ? "正在加载..."
            : warehouseState === "error"
              ? "仓库加载失败"
              : "暂无可申请仓库")
        }}
      </text>
      <view
        v-if="warehouseState === 'empty' || warehouseState === 'error'"
        class="warehouse-empty-hint"
      >
        <text>{{
          warehouseState === "empty"
            ? "当前账号的授权组织内没有可申请的有效仓库，请联系管理员核对账号组织、组织访问范围及仓库状态。"
            : "请检查网络或联系管理员核对申领权限后重试。"
        }}</text>
        <button class="btn-ghost btn-sm" @tap="initialize">重新加载仓库</button>
      </view>
    </view>
    <view v-if="warehouseId" class="card section-gap">
      <text>审批部门：{{ approvalDepartmentName || '未配置' }}</text>
    </view>
    <view class="card purpose-card"
      ><text class="title-md">领用用途</text
      ><textarea
        v-model="purpose"
        class="textarea"
        maxlength="1000"
        placeholder="请说明使用场景或用途"
      />
    </view>
    <view class="card section-gap purpose-card">
      <text class="title-md">使用地点（选填）</text>
      <text class="muted">资产发放后由你个人保管，无须固定存放地点。</text>
      <textarea v-model="custodyLocationNote" class="textarea" maxlength="200"
        :disabled="submitting" placeholder="可填写常用地点，例如办公室、教室；流动使用可留空" />
    </view>
    <view class="card section-gap"
      ><ImageUploadPicker
        v-model="photos"
        scene="requisition_apply"
        title="申请照片（选填）"
        :disabled="submitting"
    /></view>
    <view class="material-section">
      <view class="section-heading">
        <text class="title-md">选择物资</text>
        <text class="result-count">{{
          loading ? "查询中" : `${materials.length} 项可用`
        }}</text>
      </view>
      <view class="search-row">
        <view class="search-input-wrap">
          <text class="search-icon">⌕</text>
          <input
            v-model="keyword"
            class="search-input"
            placeholder="名称、编码或规格"
            confirm-type="search"
            :disabled="loading || !warehouseId"
            @confirm="load"
          />
          <text v-if="keyword" class="clear-search" @tap="clearKeyword">×</text>
        </view>
        <button
          class="search-button"
          :loading="loading"
          :disabled="loading || !warehouseId"
          @tap="load"
        >
          搜索
        </button>
      </view>
    </view>
    <view v-if="loading" class="card empty-state">
      <text>正在查询可领用物资...</text>
    </view>
    <view v-else class="material-list">
      <view
        v-for="item in materials"
        :key="optionKey(item)"
        class="card material-card"
        :class="{ selected: quantityOf(item) > 0 }"
      >
        <view class="grow">
          <text class="material-name">{{ item.item_name }}</text>
          <text class="material-meta"
            >{{ item.warehouse_name }} · {{ item.category_name || "未分类" }} ·
            {{ item.specification || "无规格" }}</text
          >
          <text class="stock"
            >可用 {{ formatQuantity(item.available_quantity) }} {{ item.unit_name }}</text
          >
        </view>
        <view class="counter">
          <button
            class="counter-button"
            :disabled="quantityOf(item) <= 0"
            @tap="change(item, -1)"
          >
            −
          </button>
          <input
            class="quantity-input"
            type="digit"
            :value="quantityOf(item)"
            @input="inputQuantity(item, $event)"
          />
          <button
            class="counter-button"
            :disabled="quantityOf(item) >= Number(item.available_quantity)"
            @tap="change(item, 1)"
          >
            ＋
          </button>
        </view>
      </view>
      <view v-if="!materials.length" class="card empty-state">
        <text>{{ keyword ? "未找到匹配的可领用物资" : "暂无可领用物资" }}</text>
      </view>
    </view>
    <view class="submit-bar"
      ><text>已选 {{ selectedCount }} 种</text
      ><button
        class="btn-primary"
        :loading="submitting"
        :disabled="submitting || !warehouseId || selectedCount === 0"
        @tap="submit"
      >
        提交申请
      </button></view
    >
  </view>
</template>

<style scoped lang="scss">
.form-page {
  padding-bottom: 150rpx;
}
.warehouse-card {
  margin-bottom: 18rpx;
}
.warehouse-options {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14rpx;
  margin-top: 18rpx;
}
.warehouse-options view {
  padding: 20rpx;
  color: #66758a;
  background: #f4f7fb;
  border: 2rpx solid transparent;
  border-radius: 16rpx;
}
.warehouse-options view.active {
  color: #1769e0;
  background: #edf4ff;
  border-color: #1769e0;
}
.warehouse-options text {
  display: block;
}
.warehouse-options text:last-child {
  margin-top: 5rpx;
  font-size: 19rpx;
  opacity: 0.75;
}
.fixed-warehouse {
  display: block;
  margin-top: 16rpx;
  color: #1769e0;
}
.warehouse-empty-hint {
  margin-top: 18rpx;
  color: #8b96a6;
  font-size: 23rpx;
  line-height: 1.6;
}
.warehouse-empty-hint button {
  margin: 20rpx 0 0;
}
.purpose-card .textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 150rpx;
  margin-top: 18rpx;
  padding: 20rpx;
  background: #f5f7fa;
  border-radius: 16rpx;
}
.material-section {
  margin: 22rpx 0 18rpx;
  padding: 24rpx;
  background: #fff;
  border: 1rpx solid rgba(24, 50, 86, 0.05);
  border-radius: 24rpx;
  box-shadow: 0 10rpx 30rpx rgba(22, 58, 105, 0.05);
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.result-count {
  color: #8793a4;
  font-size: 22rpx;
}
.search-row {
  display: flex;
  align-items: stretch;
  gap: 14rpx;
  margin-top: 18rpx;
}
.search-input-wrap {
  display: flex;
  flex: 1;
  min-width: 0;
  height: 82rpx;
  align-items: center;
  padding: 0 20rpx;
  background: #f5f7fa;
  border: 2rpx solid transparent;
  border-radius: 18rpx;
}
.search-icon {
  flex: none;
  margin-right: 12rpx;
  color: #8290a3;
  font-size: 30rpx;
}
.search-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  font-size: 26rpx;
}
.clear-search {
  display: flex;
  width: 44rpx;
  height: 44rpx;
  flex: none;
  align-items: center;
  justify-content: center;
  color: #8996a8;
  font-size: 32rpx;
}
.search-button {
  display: flex;
  width: 112rpx;
  min-width: 112rpx;
  height: 82rpx;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
  color: #fff;
  background: #1769e0;
  border-radius: 18rpx;
  box-shadow: 0 8rpx 18rpx rgba(23, 105, 224, 0.2);
  font-size: 24rpx;
  font-weight: 600;
  line-height: 82rpx;
}
.search-button[disabled] {
  color: rgba(255, 255, 255, 0.78);
  background: #79a9eb;
  box-shadow: none;
}
.material-card {
  display: flex;
  align-items: center;
  gap: 20rpx;
  border: 2rpx solid transparent;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}
.material-list .card + .card {
  margin-top: 14rpx;
}
.material-card.selected {
  background: #fbfdff;
  border-color: #b9d4fa;
}
.material-name,
.material-meta,
.stock {
  display: block;
}
.material-name {
  font-size: 27rpx;
  font-weight: 680;
}
.material-meta {
  margin-top: 6rpx;
  color: #8793a4;
  font-size: 20rpx;
}
.stock {
  margin-top: 8rpx;
  color: #16866b;
  font-size: 20rpx;
}
.counter {
  display: flex;
  flex: none;
  align-items: center;
  gap: 4rpx;
}
.counter-button {
  display: flex;
  width: 58rpx;
  min-width: 58rpx;
  height: 58rpx;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
  color: #1769e0;
  background: #edf4ff;
  border-radius: 12rpx;
  font-size: 28rpx;
  line-height: 58rpx;
}
.counter-button[disabled] {
  color: #b6c0ce;
  background: #f3f5f8;
}
.quantity-input {
  width: 68rpx;
  height: 58rpx;
  color: #26364c;
  font-size: 24rpx;
  text-align: center;
}
.submit-bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 28rpx calc(18rpx + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -8rpx 24rpx rgba(26, 48, 79, 0.08);
}
.submit-bar > text {
  color: #627086;
  font-size: 22rpx;
}
.submit-bar button {
  width: 280rpx;
  margin: 0;
}
</style>
