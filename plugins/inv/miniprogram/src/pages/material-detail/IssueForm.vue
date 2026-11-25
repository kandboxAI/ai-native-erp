<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import ImageUploadPicker from "@/components/ImageUploadPicker.vue";
import type { ImageUploadItem } from "@/api/systemFile";
import { hasPermission, showApiError } from "@/utils/permissions";
import { formatQuantity } from "../material/shared/utils/quantity";
import {
  issueMaterialRequisition,
  listRequisitionAssetBindings,
  type MaterialRequisition,
  type RequisitionAssetBinding,
  type RequisitionIssuePayload,
} from "@plugins/inv/miniprogram/src/api/inventoryRequisition";

const props = defineProps<{ request: MaterialRequisition }>();
const emit = defineEmits<{ saved: [request: MaterialRequisition]; cancel: [] }>();
type Choice = { binding: RequisitionAssetBinding; quantity: string };
type IssueLine = {
  id: string; item_id: string; name: string; unit: string;
  requested: string; quantity: string; requires_asset_selection: boolean;
  choices: Choice[]; opened: boolean; keyword: string;
  options: RequisitionAssetBinding[]; total: number; page: number;
  loading: boolean; error: string; token: number;
};
const lines = ref<IssueLine[]>(props.request.lines.map((line) => ({
  id: line.id, item_id: line.item_id, name: line.item_name_snapshot, unit: line.unit_name,
  requested: line.quantity, quantity: formatQuantity(line.quantity),
  requires_asset_selection: line.requires_asset_selection === true,
  choices: [], opened: false, keyword: "", options: [], total: 0, page: 1,
  loading: false, error: "", token: 0,
})));
const version = props.request.version_no;
const busy = ref(false);
const note = ref("");
const photos = ref<ImageUploadItem[]>([]);
const canTransfer = computed(() => hasPermission("asset_register:transfer"));
let active = true;
onBeforeUnmount(() => { active = false; });

function quantity(value: string | number) {
  const text = String(value).trim();
  if (!/^\d+(?:\.\d{1,3})?$/.test(text)) return 0;
  const result = Math.round(Number(text) * 1000);
  return Number.isSafeInteger(result) && result > 0 ? result : 0;
}
function selectedQuantity(line: IssueLine) {
  return line.choices.reduce((sum, choice) => sum + quantity(choice.quantity), 0) / 1000;
}
function available(binding: RequisitionAssetBinding) {
  return binding.stock_status_code === "available" && binding.registration_status_code === "confirmed"
    && ["idle", "in_use"].includes(binding.status_code) && quantity(binding.quantity) > 0
    && (binding.management_mode !== "individual" || quantity(binding.quantity) === 1000);
}
function isSelected(line: IssueLine, id: string) {
  return line.choices.some((choice) => choice.binding.id === id);
}
async function loadAssets(line: IssueLine, page = 1) {
  if (!canTransfer.value || busy.value) return;
  const token = ++line.token;
  line.loading = true;
  line.error = "";
  line.options = [];
  try {
    const result = await listRequisitionAssetBindings({
      item_id: line.item_id, warehouse_id: props.request.warehouse_id,
      keyword: line.keyword.trim() || undefined, page, page_size: 20,
    });
    if (!active || token !== line.token) return;
    line.options = result.items;
    line.total = result.total;
    line.page = page;
  } catch (error) {
    if (active && token === line.token)
      line.error = error instanceof Error ? error.message : "资产加载失败，请重试";
  } finally {
    if (active && token === line.token) line.loading = false;
  }
}
function openAssets(line: IssueLine) {
  if (busy.value || !canTransfer.value) return;
  line.opened = !line.opened;
  if (line.opened) void loadAssets(line);
}
function toggleAsset(line: IssueLine, binding: RequisitionAssetBinding) {
  if (busy.value || !canTransfer.value) return;
  if (isSelected(line, binding.id)) {
    line.choices = line.choices.filter((choice) => choice.binding.id !== binding.id);
    return;
  }
  if (!available(binding)) return;
  if (line.choices.length >= 200)
    return uni.showToast({ title: "每行最多关联200条实物，请调整实发数量", icon: "none" });
  const remaining = quantity(line.quantity) - Math.round(selectedQuantity(line) * 1000);
  const amount = binding.management_mode === "individual" ? 1000 : Math.min(quantity(binding.quantity), remaining);
  if (amount <= 0 || amount > remaining)
    return uni.showToast({ title: "已选数量已达到实际发放量", icon: "none" });
  line.choices.push({ binding, quantity: String(amount / 1000) });
}
function validationError(): string {
  if (!props.request.can_issue || !hasPermission("inventory_requisition:issue")) return "当前申请不可发放，请刷新详情";
  for (const line of lines.value) {
    const amount = quantity(line.quantity);
    if (!amount || amount > quantity(line.requested)) return `“${line.name}”实发量须大于零、不超过申请量，最多三位小数`;
    if (line.requires_asset_selection && !canTransfer.value) return "发放资产需资产流转权限，请联系管理员配置";
    if (line.requires_asset_selection && !line.choices.length) return `请为“${line.name}”选择发放资产`;
    if (!line.choices.length) continue;
    if (!canTransfer.value) return "缺少资产流转权限";
    if (line.choices.some(({ binding, quantity: value }) => !available(binding) || !quantity(value)
      || quantity(value) > quantity(binding.quantity) || (binding.management_mode === "individual" && quantity(value) !== 1000)))
      return `“${line.name}”的资产数量无效，请重新核对`;
    if (Math.round(selectedQuantity(line) * 1000) !== amount) return `“${line.name}”已选资产数量须与实发量一致`;
  }
  if (photos.value.some((photo) => photo.status !== "ready" || !photo.attachment)) return "请先完成照片上传";
  return "";
}
async function submit() {
  if (busy.value) return;
  const error = validationError();
  if (error) return uni.showToast({ title: error, icon: "none" });
  busy.value = true;
  // 确认期间锁定表单，提交版本和本次完整明细保持一致。
  const data: RequisitionIssuePayload = {
    version_no: version, note: note.value.trim(),
    photo_file_ids: photos.value.map((photo) => photo.attachment!.id),
    lines: lines.value.map((line) => ({
      line_id: line.id, quantity: line.quantity.trim(),
      ...(line.choices.length ? { tracking: { asset: { selections: line.choices.map((choice) => ({
        binding_id: choice.binding.id, quantity: choice.quantity.trim(),
      })) } } } : {}),
    })),
  };
  const confirmed = await new Promise<boolean>((resolve) => uni.showModal({
    title: "确认发放并出库",
    content: `确认向${props.request.applicant_name_snapshot}发放以上物资？将按实发量扣减库存，所选资产交由申请人保管。本申请只发放一次，差额需另行申请。`,
    success: (result) => resolve(result.confirm), fail: () => resolve(false),
  }));
  if (!active || !confirmed) { busy.value = false; return; }
  try {
    const result = await issueMaterialRequisition(props.request.id, data);
    if (!active) return;
    photos.value = [];
    await nextTick();
    uni.showToast({ title: "已发放，等待申请人签收", icon: "success" });
    emit("saved", result);
  } catch (error) {
    showApiError(error, "发放失败，请核对数量、资产和当前单据状态");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <view class="card section-gap issue-form">
    <text class="title-md">确认发放物资</text>
    <text class="issue-hint">按实际数量出库；关联资产交由申请人个人保管。每张申请只发放一次，少发差额请另行申请。</text>
    <view v-for="line in lines" :key="line.id" class="issue-line">
      <text class="line-title">{{ line.name }}</text>
      <text class="requested-quantity">申请数量：{{ formatQuantity(line.requested) }} {{ line.unit }}</text>
      <view class="quantity-field">
        <text class="quantity-label">实发数量</text>
        <view class="quantity-control">
          <input v-model="line.quantity" class="quantity-input" type="digit" :disabled="busy" @blur="line.quantity = formatQuantity(line.quantity)" />
          <text class="quantity-unit">{{ line.unit }}</text>
        </view>
      </view>
      <template v-if="line.requires_asset_selection">
        <text v-if="!canTransfer" class="issue-error">该物资需关联资产，当前账号缺少资产流转权限，请联系管理员。</text>
        <template v-else>
          <button class="btn-ghost asset-button" :disabled="busy" @tap="openAssets(line)">
            {{ line.opened ? '收起资产列表' : '选择发放资产' }}（已选 {{ selectedQuantity(line) }} {{ line.unit }}）
          </button>
          <view v-for="choice in line.choices" :key="choice.binding.id" class="selected-asset">
            <text>{{ choice.binding.asset_no || '历史数量资产' }}</text>
            <view class="selected-controls">
              <input v-if="choice.binding.management_mode === 'batch'" v-model="choice.quantity" class="batch-quantity-input" type="digit" :disabled="busy" @blur="choice.quantity = formatQuantity(choice.quantity)" />
              <text v-else>1</text><text>{{ line.unit }}</text>
              <button class="btn-ghost" size="mini" :disabled="busy" @tap="toggleAsset(line, choice.binding)">移除</button>
            </view>
          </view>
          <view v-if="line.opened" class="asset-browser">
            <view class="asset-search">
              <input v-model="line.keyword" maxlength="128" :disabled="busy" placeholder="搜索资产编号、序列号或名称" confirm-type="search" @confirm="loadAssets(line)" />
              <button class="btn-ghost" size="mini" :disabled="busy || line.loading" @tap="loadAssets(line)">搜索</button>
            </view>
            <text v-if="line.loading" class="issue-hint">正在加载资产...</text>
            <view v-else-if="line.error" class="issue-error">
              <text>{{ line.error }}</text><button class="btn-ghost" size="mini" :disabled="busy" @tap="loadAssets(line)">重试</button>
            </view>
            <template v-else>
              <text v-if="!line.options.length" class="issue-hint">暂无匹配资产，请核对本仓库已确认的入库资产或更换搜索条件。</text>
              <button v-for="binding in line.options" :key="binding.id" class="asset-option"
                :class="{ selected: isSelected(line, binding.id) }"
                :disabled="busy || (!isSelected(line, binding.id) && !available(binding))" @tap="toggleAsset(line, binding)">
                <text>{{ binding.asset_no || '历史数量资产' }} · {{ isSelected(line, binding.id) ? '已选' : available(binding) ? '可发放' : '暂不可发放' }}</text>
                <text v-if="binding.serial_no">序列号：{{ binding.serial_no }}</text>
                <text>可用数量 {{ formatQuantity(binding.quantity) }} {{ line.unit }}</text>
              </button>
              <view v-if="line.total > 20" class="asset-pagination">
                <button class="btn-ghost" size="mini" :disabled="busy || line.page <= 1" @tap="loadAssets(line, line.page - 1)">上一页</button>
                <text>{{ line.page }} / {{ Math.ceil(line.total / 20) }}</text>
                <button class="btn-ghost" size="mini" :disabled="busy || line.page * 20 >= line.total" @tap="loadAssets(line, line.page + 1)">下一页</button>
              </view>
            </template>
          </view>
        </template>
      </template>
    </view>
    <text class="field-label">发放备注（选填）</text>
    <textarea v-model="note" class="issue-note" maxlength="500" :disabled="busy" placeholder="可填写实际交付情况" />
    <ImageUploadPicker v-model="photos" scene="requisition_issue" title="发放照片（选填）" :disabled="busy" />
    <view class="issue-actions">
      <button class="btn-ghost" :disabled="busy" @tap="emit('cancel')">取消</button>
      <button class="btn-primary" :loading="busy" :disabled="busy" @tap="submit">确认发放并出库</button>
    </view>
  </view>
</template>

<style scoped lang="scss">
.issue-form { min-width: 0; }
.issue-hint, .issue-error { display: block; margin: 16rpx 0; font-size: 23rpx; line-height: 1.6; }
.issue-hint { color: #718096; }
.issue-error { color: #b54735; }
.issue-line { padding: 24rpx 0; border-bottom: 1rpx solid #edf1f5; }
.line-title, .field-label { display: block; color: #26364a; font-size: 27rpx; font-weight: 650; line-height: 1.6; overflow-wrap: anywhere; }
.requested-quantity { display: block; margin-top: 10rpx; color: #718096; font-size: 24rpx; line-height: 1.6; }
.quantity-field, .quantity-control, .selected-controls, .asset-search, .asset-pagination { display: flex; align-items: center; gap: 16rpx; }
.quantity-field { justify-content: space-between; margin-top: 20rpx; color: #536176; font-size: 25rpx; }
.quantity-label, .quantity-unit { flex: 0 0 auto; }
.quantity-control { box-sizing: border-box; width: 320rpx; min-width: 0; height: 88rpx; padding: 0 20rpx; background: #f5f8fc; border: 1rpx solid #dce5f0; border-radius: 14rpx; }
.quantity-input { box-sizing: border-box; flex: 1; min-width: 0; width: 0; height: 84rpx; padding: 0; color: #162238; font-size: 32rpx; line-height: 84rpx; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; outline: none; }
.quantity-unit { color: #718096; font-size: 25rpx; }
.batch-quantity-input { box-sizing: border-box; width: 200rpx; height: 76rpx; padding: 0 18rpx; color: #162238; background: #fff; border: 1rpx solid #dce5f0; border-radius: 12rpx; font-size: 28rpx; line-height: 76rpx; text-align: right; }
.asset-button { width: 100%; margin-top: 20rpx; font-size: 24rpx; }
.selected-asset { margin-top: 14rpx; padding: 16rpx; background: #f0f7ff; border-radius: 12rpx; font-size: 23rpx; }
.selected-asset > text { display: block; overflow-wrap: anywhere; }
.selected-controls { flex-wrap: wrap; justify-content: flex-end; margin-top: 16rpx; }
.selected-controls button, .asset-search button, .asset-pagination button { flex: 0 0 auto; margin: 0; }
.asset-browser { margin-top: 18rpx; }
.asset-search input { box-sizing: border-box; flex: 1; min-width: 0; width: 0; height: 80rpx; padding: 0 18rpx; color: #26364a; background: #f2f5f9; border: 1rpx solid #e7ecf3; border-radius: 12rpx; font-size: 24rpx; line-height: 80rpx; }
.asset-option { display: block; width: 100%; margin: 14rpx 0; padding: 18rpx; color: #536176; background: #f7f9fc; border: 1rpx solid #e5ebf3; border-radius: 12rpx; text-align: left; font-size: 23rpx; line-height: 1.6; }
.asset-option text { display: block; overflow-wrap: anywhere; }
.asset-option.selected { color: #1769e0; background: #edf5ff; border-color: #1769e0; }
.asset-pagination { justify-content: space-between; margin-top: 18rpx; color: #718096; font-size: 23rpx; }
.field-label { margin: 24rpx 0 16rpx; }
.issue-note { display: block; box-sizing: border-box; width: 100%; height: 180rpx; min-height: 180rpx; padding: 20rpx; margin-bottom: 28rpx; color: #26364a; background: #f5f8fc; border: 1rpx solid #e7ecf3; border-radius: 14rpx; font-size: 26rpx; line-height: 1.6; }
.issue-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 16rpx; padding-top: 28rpx; margin-top: 28rpx; border-top: 1rpx solid #edf1f5; }
.issue-actions button { flex: 0 0 auto; margin: 0; padding: 0 24rpx; font-size: 25rpx; }
.issue-actions .btn-primary { min-width: 270rpx; }
.quantity-control:focus-within { border-color: #1769e0; box-shadow: 0 0 0 3rpx rgba(23, 105, 224, 0.1); }
.batch-quantity-input:focus, .asset-search input:focus, .issue-note:focus { border-color: #1769e0; outline: none; }
</style>
