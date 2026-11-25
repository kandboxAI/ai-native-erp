<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import {
  receiveMaterialRequisition,
  requisitionStatusLabels,
  requisitionEventLabels,
  receiptExceptionLabels,
  type ReceiptLine,
  type RequisitionPhoto,
  approveMaterialRequisition,
  getMaterialRequisition,
  rejectMaterialRequisition,
  withdrawMaterialRequisition,
  type MaterialRequisition,
} from "@plugins/inv/miniprogram/src/api/inventoryRequisition";
import { hasPermission, showApiError } from "@/utils/permissions";

import ImageUploadPicker from "@/components/ImageUploadPicker.vue";
import IssueForm from "./IssueForm.vue";
import { formatQuantity } from "../material/shared/utils/quantity";
import { fileUrl, type ImageUploadItem } from "@/api/systemFile";

const request = ref<MaterialRequisition | null>(null);
const loading = ref(false);
const photoErrors = ref<Record<string, boolean>>({});
const id = ref("");
const issueOpen = ref(false);
const canIssue = computed(() => request.value?.can_issue === true);
const statusLabels = requisitionStatusLabels;
const receiptMode = ref<"receive" | "exception" | null>(null);
const receiptBusy = ref(false);
const receiptNote = ref("");
const receiptPhotos = ref<ImageUploadItem[]>([]);
const checks = ref<
  Array<ReceiptLine & { name: string; unit: string; issued: number }>
>([]);
const exceptionKeys = [
  null,
  "shortage",
  "wrong_item",
  "damaged",
  "not_received",
] as const;
const exceptionOptions = ["正常", "少发", "错发", "破损", "未收到"];
function openReceipt(mode: "receive" | "exception") {
  if (!request.value) return;
  receiptMode.value = mode;
  receiptNote.value = "";
  receiptPhotos.value = [];
  checks.value = request.value.lines.map((line) => ({
    line_id: line.id,
    name: line.item_name_snapshot,
    unit: line.unit_name,
    issued: Number(line.issued_quantity ?? line.quantity),
    received_quantity: Number(line.issued_quantity ?? line.quantity),
    exception_quantity: 0,
    exception_type_code: null,
  }));
}
function updateMissing(row: (typeof checks.value)[number]) {
  if (row.exception_type_code === "not_received") row.received_quantity = 0;
  if (["shortage", "not_received"].includes(row.exception_type_code || ""))
    row.exception_quantity = Math.max(
      0,
      row.issued - Number(row.received_quantity),
    );
  if (!row.exception_type_code) row.exception_quantity = 0;
}
function setException(row: (typeof checks.value)[number], event: unknown) {
  row.exception_type_code =
    exceptionKeys[
      Number((event as { detail: { value: string } }).detail.value)
    ] || null;
  updateMissing(row);
}
function preview(photos: RequisitionPhoto[], photo: RequisitionPhoto) {
  uni.previewImage({
    current: fileUrl(photo.url),
    urls: photos.map((item) => fileUrl(item.url)),
  });
}
function lineName(id: string) {
  const line = request.value?.lines.find((item) => item.id === id);
  return line ? `${line.item_name_snapshot}（${line.unit_name}）` : "物资";
}
async function submitReceipt() {
  if (!request.value || !receiptMode.value || receiptBusy.value) return;
  if (receiptPhotos.value.some((item) => item.status !== "ready"))
    return uni.showToast({ title: "请先完成照片上传", icon: "none" });
  if (
    receiptMode.value === "exception" &&
    (!receiptNote.value.trim() ||
      !checks.value.some((line) => line.exception_type_code))
  )
    return uni.showToast({ title: "请选择异常物资并填写说明", icon: "none" });
  if (
    receiptMode.value === "exception" &&
    checks.value.some((line) =>
      ["damaged", "wrong_item"].includes(line.exception_type_code || ""),
    ) &&
    !receiptPhotos.value.length
  )
    return uni.showToast({ title: "破损或错发请上传问题照片", icon: "none" });
  receiptBusy.value = true;
  const confirmed = await new Promise<boolean>((resolve) =>
    uni.showModal({
      title: receiptMode.value === "receive" ? "确认收货" : "提交收货异常",
      content:
        receiptMode.value === "receive"
          ? "确认已逐项核对数量、规格及完好情况并收到物资？"
          : "确认提交本次异常明细及照片给发放人员核实？",
      success: (result) => resolve(result.confirm),
      fail: () => resolve(false),
    }),
  );
  if (!confirmed) {
    receiptBusy.value = false;
    return;
  }
  try {
    await receiveMaterialRequisition(
      request.value.id,
      {
        version_no: request.value.version_no,
        note: receiptNote.value.trim(),
        photo_file_ids: receiptPhotos.value.map((item) => item.attachment!.id),
        lines: checks.value.map((line) => ({
          line_id: line.line_id,
          received_quantity: Number(line.received_quantity),
          exception_quantity: Number(line.exception_quantity),
          exception_type_code: line.exception_type_code,
        })),
      },
      receiptMode.value === "exception",
    );
    receiptPhotos.value = [];
    receiptMode.value = null;
    uni.showToast({ title: "收货记录已保存", icon: "success" });
    await load();
  } catch (error) {
    showApiError(error, "收货记录提交失败");
  } finally {
    receiptBusy.value = false;
  }
}
const canApprove = computed(() =>
  Boolean(
    request.value?.status_code === "submitted" &&
    hasPermission("inventory_requisition:approve"),
  ),
);
const canWithdraw = computed(() => Boolean(request.value?.can_withdraw));

async function load() {
  if (!id.value || loading.value) return;
  loading.value = true;
  try {
    request.value = await getMaterialRequisition(id.value);
    photoErrors.value = {};
  } catch (error) {
    showApiError(error, "申请详情加载失败");
  } finally {
    loading.value = false;
  }
}

function prompt(title: string, placeholder: string): Promise<string | null> {
  return new Promise((resolve) =>
    uni.showModal({
      title,
      editable: true,
      placeholderText: placeholder,
      success: (result) =>
        resolve(result.confirm ? String(result.content || "") : null),
      fail: () => resolve(null),
    }),
  );
}

async function approve() {
  if (!request.value) return;
  const note = await prompt("审批通过", "可填写审批意见");
  if (note === null) return;
  try {
    request.value = await approveMaterialRequisition(
      request.value.id,
      request.value.version_no,
      note || "同意领用",
    );
    uni.showToast({ title: "审批已通过", icon: "success" });
    await load();
  } catch (error) {
    showApiError(error, "审批失败");
  }
}

async function reject() {
  if (!request.value) return;
  const note = await prompt("驳回申请", "请输入驳回原因");
  if (note === null) return;
  if (!note.trim())
    return uni.showToast({ title: "驳回原因不能为空", icon: "none" });
  try {
    request.value = await rejectMaterialRequisition(
      request.value.id,
      request.value.version_no,
      note.trim(),
    );
    uni.showToast({ title: "申请已驳回", icon: "success" });
  } catch (error) {
    showApiError(error, "驳回失败");
  }
}

async function withdraw() {
  if (!request.value) return;
  const confirmed = await new Promise<boolean>((resolve) =>
    uni.showModal({
      title: "撤回申请",
      content: "确定撤回该物资申请吗？",
      success: (result) => resolve(result.confirm),
      fail: () => resolve(false),
    }),
  );
  if (!confirmed) return;
  try {
    request.value = await withdrawMaterialRequisition(
      request.value.id,
      request.value.version_no,
    );
    uni.showToast({ title: "申请已撤回", icon: "success" });
  } catch (error) {
    showApiError(error, "撤回失败");
  }
}

onLoad((options) => {
  id.value = String(options?.id || "");
  load();
});

async function issued(value: MaterialRequisition) {
  request.value = value;
  issueOpen.value = false;
  await load();
}
</script>

<template>
  <view v-if="request" class="page-shell detail-page">
    <view class="status-card" :class="request.status_code"
      ><text>当前状态</text><text>{{ statusLabels[request.status_code] }}</text
      ><text>{{ request.request_no }}</text></view
    >
    <view class="card section-gap"
      ><text class="purpose">{{ request.purpose }}</text
      ><view class="info"
        ><text>申请人</text><text>{{ request.applicant_name_snapshot }}</text
        ><text>发放仓库</text><text>{{ request.warehouse_name || "—" }}</text
        ><text>当前审批部门</text><text>{{ request.requisition_approval_department_name || '未配置' }}</text
        ><text>申请来源组织</text
        ><text>{{ request.applicant_org_name_snapshot || "历史未记录" }}</text
        ><text>所属部门</text
        ><text>{{ request.department_name_snapshot || "未关联部门" }}</text
        ><text>使用地点</text><text>{{ request.custody_location_note || "流动使用，无固定地点" }}</text
        ><text>申请时间</text><text>{{ request.created_at }}</text
        ><text v-if="request.stock_order_no">出库单号</text
        ><text v-if="request.stock_order_no">{{ request.stock_order_no }}</text
        ><text>签收人</text
        ><text>{{ request.received_by_name_snapshot || "未记录签收" }}</text
        ><text v-if="request.received_at">签收时间</text
        ><text v-if="request.received_at">{{ request.received_at }}</text></view
      ></view
    >
    <view v-if="request.personal_custody_assets?.length" class="card section-gap">
      <text class="title-md">个人保管资产</text>
      <view class="info"><text>发放保管人</text><text>{{ request.applicant_name_snapshot }}</text></view>
      <view v-for="(asset, index) in request.personal_custody_assets" :key="index" class="line">
        <text>{{ asset.asset_no || '历史数量资产' }} × {{ formatQuantity(asset.quantity) }}</text>
      </view>
      <text class="muted">发放时已登记个人保管；签收仅确认收货，不重复扣库或转移责任。</text>
    </view>
    <view class="card section-gap"
      ><text class="title-md">物资明细</text
      ><view
        v-for="(line, index) in request.lines"
        :key="line.id"
        class="line"
        :class="{ divided: index > 0 }"
        ><view class="grow"
          ><text>{{ line.item_name_snapshot }}</text
          ><text
            >{{ line.item_no_snapshot }} ·
            {{ line.specification_snapshot || "无规格" }}</text
          ></view
        ><strong
          >申请 {{ formatQuantity(line.quantity) }} {{ line.unit_name
          }}<text v-if="line.issued_quantity != null"
            >实发 {{ formatQuantity(line.issued_quantity) }} {{ line.unit_name }}</text
          ></strong
        ></view
      ></view
    >
    <view v-if="request.approval_note" class="card section-gap"
      ><text class="title-md">审批意见</text
      ><text class="note">{{ request.approval_note }}</text></view
    >
    <view class="card section-gap"
      ><text class="title-md">流程记录</text
      ><view v-for="event in request.events" :key="event.id" class="event"
        ><view class="dot" /><view class="grow"
          ><text>{{
            requisitionEventLabels[event.event_type_code] ||
            statusLabels[event.to_status_code]
          }}</text
          ><text
            >{{ event.operator_name_snapshot }} · {{ event.created_at }}</text
          ><text v-if="event.note">{{ event.note }}</text>
          <text v-for="line in event.receipt_lines || []" :key="line.line_id"
            >{{ lineName(line.line_id) }}：收到 {{ formatQuantity(line.received_quantity)
            }}<template v-if="line.exception_type_code"
              >；{{ receiptExceptionLabels[line.exception_type_code] }}
              {{ formatQuantity(line.exception_quantity) }}</template
            ></text
          >
          <view v-if="event.photos?.length" class="evidence"
            ><view
              v-for="photo in event.photos || []"
              :key="photo.id"
              class="evidence-photo"
              @tap="photoErrors[photo.id] ? load() : preview(event.photos, photo)"
              ><view v-if="photoErrors[photo.id]" class="photo-error"
                ><view>图片加载失败</view><view>点击重试</view></view
              ><image
                v-else
                :src="fileUrl(photo.url)"
                mode="aspectFill"
                @error="photoErrors[photo.id] = true"
            /></view
          ></view> </view></view
    ></view>
    <IssueForm v-if="issueOpen && canIssue" :key="request.id" :request="request"
      @saved="issued" @cancel="issueOpen = false" />
    <view v-if="receiptMode" class="card section-gap receipt-form">
      <text class="title-md">{{
        receiptMode === "receive" ? "核对并确认收货" : "反馈收货异常"
      }}</text>
      <view v-for="line in checks" :key="line.line_id" class="receipt-line">
        <view class="receipt-line-heading">
          <text class="receipt-line-name">{{ line.name }}</text>
          <text class="receipt-line-meta"
            >发放 {{ line.issued }} {{ line.unit }}</text
          >
        </view>
        <template v-if="receiptMode === 'exception'">
          <view class="receipt-input"
            ><text>实际收到</text
            ><view class="receipt-field-value"
              ><input
                v-model="line.received_quantity"
                type="digit"
                :disabled="receiptBusy"
                @input="updateMissing(line)"
              /><text>{{ line.unit }}</text></view
            ></view
          >
          <picker
            :range="exceptionOptions"
            :value="exceptionKeys.indexOf(line.exception_type_code)"
            :disabled="receiptBusy"
            @change="setException(line, $event)"
            ><view class="receipt-input"
              ><text>异常类型</text
              ><view class="receipt-field-value"
                ><text>{{
                  line.exception_type_code
                    ? receiptExceptionLabels[line.exception_type_code]
                    : "正常"
                }}</text
                ><text class="receipt-chevron">›</text></view
              ></view
            ></picker
          >
          <view v-if="line.exception_type_code" class="receipt-input"
            ><text>问题数量</text
            ><view class="receipt-field-value"
              ><input
                v-model="line.exception_quantity"
                type="digit"
                :disabled="
                  receiptBusy ||
                  !['damaged', 'wrong_item'].includes(line.exception_type_code)
                "
              /><text>{{ line.unit }}</text></view
            ></view
          >
        </template>
      </view>
      <view class="receipt-note-field">
        <text class="receipt-field-label">{{
          receiptMode === "exception" ? "异常说明（必填）" : "收货备注（选填）"
        }}</text>
        <textarea
          v-model="receiptNote"
          class="receipt-note"
          maxlength="500"
          :disabled="receiptBusy"
          :placeholder="
            receiptMode === 'exception'
              ? '必填：异常说明；破损或错发请上传照片'
              : '可补充本次收货情况'
          "
        />
      </view>
      <view class="receipt-photos">
        <ImageUploadPicker
          :key="receiptMode"
          v-model="receiptPhotos"
          :scene="
            receiptMode === 'exception'
              ? 'requisition_exception'
              : 'requisition_receive'
          "
          :title="
            receiptMode === 'exception'
              ? '异常照片（破损、错发必填）'
              : '收货照片（选填）'
          "
          :disabled="receiptBusy"
        />
      </view>
      <view class="receipt-form-actions">
        <button
          class="btn-primary"
          :loading="receiptBusy"
          :disabled="receiptBusy"
          @tap="submitReceipt"
        >
          {{ receiptMode === "receive" ? "确认无误并签收" : "提交异常反馈" }}
        </button>
        <button
          class="btn-ghost"
          :disabled="receiptBusy"
          @tap="receiptMode = null"
        >
          取消
        </button>
      </view>
    </view>
    <view
      v-if="request.can_receive && !receiptMode"
      class="section-gap receipt-buttons"
      ><button class="btn-primary" @tap="openReceipt('receive')">
        确认收货</button
      ><button class="btn-ghost" @tap="openReceipt('exception')">
        反馈收货异常
      </button></view
    >
    <view class="detail-refresh"
      ><text v-if="request.status_code === 'receipt_exception'"
        >已反馈收货异常，等待发放人员核实处理。处理完成后请再次核对收货。</text
      ><button
        class="refresh-button"
        :disabled="loading || receiptBusy || issueOpen"
        @tap="load"
      >
        刷新记录与照片
      </button></view
    >
    <view v-if="(canApprove || canWithdraw || canIssue) && !issueOpen" class="actions"
      ><template v-if="canApprove"
        ><button class="btn-ghost danger" @tap="reject">驳回</button
        ><button class="btn-primary" @tap="approve">审批通过</button></template
      ><button v-if="canIssue" class="btn-primary" :disabled="loading" @tap="issueOpen = true">确认发放</button
      ><button v-else-if="canWithdraw" class="btn-ghost" @tap="withdraw">
        撤回申请
      </button></view
    >
    <view v-if="request.status_code === 'approved' && !canIssue && !loading" class="card section-gap">
      <text class="muted">如需发放，请联系管理员核对本账号的领用发放权限及该仓库的管理范围。</text>
    </view>
  </view>
  <view v-else class="page-shell empty-state"
    ><text>{{ loading ? "正在加载..." : "未找到申请" }}</text></view
  >
</template>

<style scoped lang="scss">
.evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 12rpx;
}
.evidence-photo {
  flex: 0 0 auto;
  width: 150rpx;
  height: 150rpx;
  overflow: hidden;
  background: #f2f5f9;
  border-radius: 10rpx;
}
.evidence-photo image {
  display: block;
  width: 100%;
  height: 100%;
}
.photo-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #718096;
  font-size: 22rpx;
  line-height: 1.6;
  text-align: center;
}
.receipt-line {
  padding: 24rpx 0;
  border-bottom: 1rpx solid #edf1f5;
}
.receipt-line-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16rpx;
  line-height: 1.5;
}
.receipt-line-name {
  flex: 1;
  min-width: 0;
  font-size: 27rpx;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.receipt-line-meta {
  flex: 0 0 auto;
  color: #718096;
  font-size: 24rpx;
}
.receipt-input {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 80rpx;
  gap: 20rpx;
  padding: 12rpx 0;
  font-size: 25rpx;
}
.receipt-input > text {
  flex: 0 0 auto;
  color: #718096;
}
.receipt-field-value {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12rpx;
  min-width: 0;
}
.receipt-input input {
  width: 160rpx;
  height: 64rpx;
  padding: 0 16rpx;
  text-align: right;
  background: #f5f7fa;
  border: 1rpx solid #e7ecf3;
  border-radius: 12rpx;
  font-size: 26rpx;
}
.receipt-chevron {
  color: #98a3b1;
  font-size: 34rpx;
}
.receipt-note-field,
.receipt-photos {
  margin-top: 28rpx;
}
.receipt-field-label {
  display: block;
  margin-bottom: 14rpx;
  font-size: 25rpx;
  font-weight: 600;
}
.receipt-note {
  display: block;
  box-sizing: border-box;
  width: 100%;
  height: 180rpx;
  padding: 20rpx 22rpx;
  color: #26364a;
  background: #f5f7fa;
  border: 1rpx solid #e7ecf3;
  border-radius: 16rpx;
  font-size: 26rpx;
  line-height: 1.6;
}
.receipt-form-actions {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 32rpx;
}
.receipt-form-actions .btn-primary {
  flex: 1;
  min-width: 0;
}
.receipt-form-actions .btn-ghost {
  flex: 0 0 148rpx;
}
.receipt-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18rpx;
}
.receipt-form-actions button,
.receipt-buttons button {
  margin: 0;
  padding: 0 20rpx;
  font-size: 26rpx;
  white-space: nowrap;
}
.detail-refresh {
  margin-top: 24rpx;
  color: #718096;
  font-size: 23rpx;
  line-height: 1.6;
}
.detail-refresh > text {
  display: block;
  margin-bottom: 12rpx;
}
.refresh-button {
  width: auto;
  margin: 0 auto;
  padding: 8rpx 24rpx;
  color: #718096;
  background: transparent;
  font-size: 24rpx;
  line-height: 48rpx;
}
.detail-page {
  padding-bottom: 150rpx;
}
.status-card {
  padding: 32rpx;
  color: #fff;
  background: linear-gradient(135deg, #1769e0, #458de9);
  border-radius: 28rpx;
}
.status-card.approved {
  background: linear-gradient(135deg, #c46b16, #e8a13e);
}
.status-card.issued {
  background: linear-gradient(135deg, #08735c, #19a47d);
}
.status-card.rejected,
.status-card.withdrawn {
  background: linear-gradient(135deg, #687588, #929cac);
}
.status-card text {
  display: block;
}
.status-card text:nth-child(2) {
  margin: 7rpx 0;
  font-size: 39rpx;
  font-weight: 720;
}
.status-card text:first-child,
.status-card text:last-child {
  font-size: 20rpx;
  opacity: 0.8;
}
.purpose {
  display: block;
  margin-bottom: 20rpx;
  font-size: 30rpx;
  font-weight: 680;
}
.info {
  display: grid;
  grid-template-columns: 130rpx minmax(0, 1fr);
  gap: 14rpx;
  padding-top: 18rpx;
  border-top: 1rpx solid #edf1f5;
  font-size: 21rpx;
}
.info text:nth-child(odd) {
  color: #8a95a5;
}
.info text:nth-child(even) {
  min-width: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.line {
  display: flex;
  align-items: center;
  padding: 20rpx 0;
}
.line.divided {
  border-top: 1rpx solid #edf1f5;
}
.line text {
  display: block;
}
.line text:first-child {
  font-weight: 650;
}
.line text:last-child {
  margin-top: 5rpx;
  color: #8b96a6;
  font-size: 20rpx;
}
.line strong {
  flex: 0 0 auto;
  max-width: 45%;
  margin-left: 16rpx;
  color: #1769e0;
  text-align: right;
}
.note {
  display: block;
  margin-top: 16rpx;
  color: #556378;
  line-height: 1.65;
}
.event {
  display: flex;
  gap: 17rpx;
  margin-top: 22rpx;
}
.dot {
  flex: 0 0 auto;
  width: 18rpx;
  height: 18rpx;
  margin-top: 8rpx;
  background: #1769e0;
  border: 6rpx solid #e5efff;
  border-radius: 50%;
}
.event text {
  display: block;
}
.event text:first-child {
  font-weight: 650;
}
.event text:nth-child(2) {
  margin-top: 5rpx;
  color: #8b96a6;
  font-size: 19rpx;
}
.event text:nth-child(3) {
  margin-top: 6rpx;
  color: #536176;
  font-size: 21rpx;
}
.actions {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 5;
  display: flex;
  gap: 14rpx;
  padding: 18rpx 28rpx calc(18rpx + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -8rpx 24rpx rgba(26, 48, 79, 0.08);
}
.actions button {
  flex: 1;
  margin: 0;
}
.danger {
  color: #d84554;
  border-color: #f0b8bf;
}
</style>
