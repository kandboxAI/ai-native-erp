<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import StatusBadge from "@plugins/mes/miniprogram/src/pages/production-report/shared/components/StatusBadge.vue";
import {
  getProductionTask,
  holdProductionTask,
  productionTaskStatusLabel,
  releaseProductionTask,
  submitProductionReport,
  trackInProductionTask,
  trackOutProductionTask,
  type ProductionTaskDetail,
} from "@plugins/mes/miniprogram/src/api/mesProduction";
import { confirmAction, showApiError } from "@/utils/permissions";
import { uid } from "@plugins/mes/miniprogram/src/pages/production-report/shared/utils/date";

const id = ref("");
const loading = ref(true);
const acting = ref(false);
const actionMode = ref<"" | "report" | "hold">("");
const row = ref<ProductionTaskDetail | null>(null);

const reportForm = reactive({
  good_quantity: "",
  scrap_quantity: "0",
  rework_quantity: "0",
  labor_minutes: "",
  machine_minutes: "",
  exception_type_code: "",
  note: "",
});
const holdNote = ref("");

const statusText = computed(() =>
  productionTaskStatusLabel(row.value?.status_code, row.value?.status_label),
);
const canTrackIn = computed(() =>
  Boolean(parentAllowsExecution.value && row.value && ["pending", "dispatched"].includes(row.value.status_code)),
);
const parentAllowsExecution = computed(() => !row.value?.work_order_status_code || ["released", "in_progress"].includes(row.value.work_order_status_code));
const canReport = computed(() =>
  Boolean(parentAllowsExecution.value && row.value && row.value.status_code === "in_progress"),
);
const canHold = computed(() =>
  Boolean(parentAllowsExecution.value && row.value && ["in_progress", "dispatched"].includes(row.value.status_code)),
);
const canRelease = computed(() => parentAllowsExecution.value && row.value?.status_code === "paused");
const canTrackOut = computed(() =>
  Boolean(parentAllowsExecution.value && row.value && ["in_progress", "paused"].includes(row.value.status_code)),
);

onLoad((options) => {
  id.value = String(options?.id || "");
});
onShow(load);

async function load() {
  if (!id.value) return;
  loading.value = true;
  try {
    row.value = await getProductionTask(id.value);
  } catch (error) {
    row.value = null;
    showApiError(error, "生产任务加载失败");
  } finally {
    loading.value = false;
  }
}

function resetForms() {
  Object.assign(reportForm, {
    good_quantity: "",
    scrap_quantity: "0",
    rework_quantity: "0",
    labor_minutes: "",
    machine_minutes: "",
    exception_type_code: "",
    note: "",
  });
  holdNote.value = "";
}

function openReport() {
  if (!row.value) return;
  resetForms();
  const remain = Math.max(
    0,
    Number(row.value.planned_quantity) - Number(row.value.good_quantity),
  );
  reportForm.good_quantity = remain ? String(remain) : "";
  actionMode.value = "report";
}

function openHold() {
  holdNote.value = "";
  actionMode.value = "hold";
}

function closeAction() {
  actionMode.value = "";
}

function numberValue(value: string) {
  const result = Number(value);
  return Number.isFinite(result) && result >= 0 ? result : 0;
}

async function execute(
  operation: (current: ProductionTaskDetail) => Promise<ProductionTaskDetail>,
  successMessage: string,
) {
  if (!row.value || acting.value) return;
  acting.value = true;
  try {
    row.value = await operation(row.value);
    actionMode.value = "";
    uni.showToast({ title: successMessage, icon: "success" });
  } catch (error) {
    showApiError(error);
  } finally {
    acting.value = false;
  }
}

async function trackIn() {
  if (!row.value || !(await confirmAction("开始执行", "确认在当前工作站开始这道工序？"))) return;
  await execute(
    (current) =>
      trackInProductionTask(current.id, {
        version_no: current.version_no,
      }),
    "已开始执行",
  );
}

async function submitHold() {
  if (!row.value || !holdNote.value.trim()) {
    uni.showToast({ title: "请填写暂停原因", icon: "none" });
    return;
  }
  await execute(
    (current) =>
      holdProductionTask(current.id, {
        version_no: current.version_no,
        execution_id: current.current_execution?.id,
        note: holdNote.value.trim(),
      }),
    "任务已暂停",
  );
}

async function release() {
  if (!row.value || !(await confirmAction("恢复执行", "确认解除暂停并恢复这道工序？"))) return;
  await execute(
    (current) =>
      releaseProductionTask(current.id, {
        version_no: current.version_no,
        execution_id: current.current_execution?.id,
      }),
    "任务已恢复",
  );
}

async function submitReport() {
  if (!row.value) return;
  const good = numberValue(reportForm.good_quantity);
  const scrap = numberValue(reportForm.scrap_quantity);
  const rework = numberValue(reportForm.rework_quantity);
  if (good + scrap + rework <= 0) {
    uni.showToast({ title: "请至少填写一项产出数量", icon: "none" });
    return;
  }
  await execute(
    (current) =>
      submitProductionReport(current.id, {
        version_no: current.version_no,
        execution_id: current.current_execution?.id,
        good_quantity: good,
        scrap_quantity: scrap,
        rework_quantity: rework,
        labor_minutes: reportForm.labor_minutes
          ? numberValue(reportForm.labor_minutes)
          : undefined,
        machine_minutes: reportForm.machine_minutes
          ? numberValue(reportForm.machine_minutes)
          : undefined,
        exception_type_code: reportForm.exception_type_code || undefined,
        note: reportForm.note.trim() || undefined,
        idempotency_key: uid("MES-REPORT"),
      }),
    "报工已提交",
  );
}

async function trackOut() {
  if (!row.value || !(await confirmAction("结束本次执行", "确认完工？提交后将结束当前执行区间。"))) return;
  await execute(
    (current) =>
      trackOutProductionTask(current.id, {
        version_no: current.version_no,
        execution_id: current.current_execution?.id,
      }),
    "已结束本次执行",
  );
}

function quantity(value: number, unit: string) {
  return `${value} ${unit}`;
}
</script>

<template>
  <view class="page">
    <view v-if="loading" class="empty">正在加载任务…</view>
    <template v-else-if="row">
      <view class="hero">
        <view class="grow">
          <text class="eyebrow">{{ row.work_order_no }}</text>
          <text class="title">{{ row.operation_name }}</text>
          <text class="subtitle">工序 {{ row.operation_no }} · {{ row.product_item_name }}</text>
        </view>
        <StatusBadge :status="statusText" />
      </view>

      <view class="card progress-card">
        <view v-if="!parentAllowsExecution">工单未发布、已暂停或已结束，当前不可执行生产操作。状态以刷新后的服务端结果为准。</view>
        <view class="progress-head">
          <view>
            <text class="card-label">完成进度</text>
            <text class="progress-number">{{ row.good_quantity }}<text> / {{ row.planned_quantity }}</text></text>
          </view>
          <text class="unit">{{ row.unit_name }}</text>
        </view>
        <view class="progress-track"><view class="progress-bar" :style="{ width: `${Math.min(100, row.planned_quantity ? row.good_quantity / row.planned_quantity * 100 : 0)}%` }" /></view>
        <view class="quantity-row">
          <text>合格 {{ quantity(row.good_quantity, row.unit_name) }}</text>
          <text>报废 {{ quantity(row.scrap_quantity, row.unit_name) }}</text>
          <text>返工 {{ quantity(row.rework_quantity, row.unit_name) }}</text>
        </view>
      </view>

      <view class="card">
        <text class="section-title">任务信息</text>
        <view class="info"><text>产品物料</text><text>{{ row.product_item_no }} · {{ row.product_item_name }}</text></view>
        <view class="info"><text>工作中心</text><text>{{ row.work_center_name || "未分配" }}</text></view>
        <view class="info"><text>工作站</text><text>{{ row.workstation_name || "按现场分配" }}</text></view>
        <view class="info"><text>交期</text><text>{{ row.due_at || "未设置" }}</text></view>
        <view class="description" v-if="row.operation_description"><text>工艺说明</text><text>{{ row.operation_description }}</text></view>
        <view class="skill-line" v-if="row.required_skills?.length"><text>技能要求</text><text>{{ row.required_skills.join("、") }}</text></view>
      </view>

      <view class="card" v-if="row.material_requirements.length">
        <text class="section-title">物料要求</text>
        <view v-for="material in row.material_requirements" :key="material.id" class="material-row">
          <view class="grow"><text class="material-name">{{ material.item_no }} · {{ material.item_name }}</text><text class="material-sub">已领/耗用 {{ material.consumed_quantity }} / {{ material.required_quantity }} {{ material.unit_name }}</text></view>
          <text class="material-state">{{ material.is_lot_controlled || material.is_serial_controlled ? "需追溯" : "普通" }}</text>
        </view>
      </view>

      <view class="card" v-if="row.current_execution">
        <text class="section-title">当前执行</text>
        <view class="info"><text>开始时间</text><text>{{ row.current_execution.tracked_in_at }}</text></view>
        <view class="info"><text>生产人员</text><text>{{ row.current_execution.production_person_name || row.current_execution.worker_name || "当前登录人员" }}</text></view>
        <view class="info" v-if="row.current_execution.production_person_name"><text>录入账号</text><text>{{ row.current_execution.worker_name || "—" }}</text></view>
        <view class="info"><text>工作站</text><text>{{ row.current_execution.workstation_name || row.workstation_name || "现场工作站" }}</text></view>
      </view>

      <view v-if="actionMode === 'report'" class="card action-card">
        <text class="section-title">提交现场报工</text>
        <view class="field"><text>合格数量 *</text><input v-model="reportForm.good_quantity" type="digit" placeholder="请输入合格数量" /></view>
        <view class="field"><text>报废数量</text><input v-model="reportForm.scrap_quantity" type="digit" placeholder="0" /></view>
        <view class="field"><text>返工数量</text><input v-model="reportForm.rework_quantity" type="digit" placeholder="0" /></view>
        <view class="field"><text>人工工时（分钟）</text><input v-model="reportForm.labor_minutes" type="digit" placeholder="选填" /></view>
        <view class="field"><text>机器工时（分钟）</text><input v-model="reportForm.machine_minutes" type="digit" placeholder="选填" /></view>
        <view class="field"><text>异常说明</text><textarea v-model="reportForm.note" maxlength="1000" placeholder="数量异常、缺料、设备停机等请说明" /></view>
        <view class="form-actions"><button class="ghost" @tap="closeAction">取消</button><button class="primary" :loading="acting" @tap="submitReport">提交报工</button></view>
      </view>

      <view v-if="actionMode === 'hold'" class="card action-card">
        <text class="section-title">暂停任务</text>
        <view class="field"><text>暂停原因 *</text><textarea v-model="holdNote" maxlength="500" placeholder="例如：设备换型、缺料、待质量判定" /></view>
        <view class="form-actions"><button class="ghost" @tap="closeAction">取消</button><button class="warning" :loading="acting" @tap="submitHold">确认暂停</button></view>
      </view>

      <view v-if="!actionMode" class="bottom-actions">
        <button v-if="canTrackIn" class="primary" :loading="acting" @tap="trackIn">开工</button>
        <button v-if="canReport" class="success" :loading="acting" @tap="openReport">报工</button>
        <button v-if="canHold" class="warning" :loading="acting" @tap="openHold">暂停</button>
        <button v-if="canRelease" class="primary" :loading="acting" @tap="release">恢复</button>
        <button v-if="canTrackOut" class="ghost" :loading="acting" @tap="trackOut">完工</button>
      </view>

      <view class="card timeline-card" v-if="row.events.length">
        <text class="section-title">执行记录</text>
        <view v-for="(event, index) in row.events" :key="event.id" class="timeline-item">
          <view class="timeline-dot" :class="{ last: index === row.events.length - 1 }" />
          <view class="grow"><text class="timeline-title">{{ event.event_label || event.event_type_code }}</text><text class="timeline-note" v-if="event.note">{{ event.note }}</text><text class="timeline-meta">{{ event.actor_name_snapshot || "系统" }} · {{ event.created_at }}</text></view>
        </view>
      </view>
    </template>
    <view v-else class="empty">任务不存在或当前账号无权查看</view>
  </view>
</template>

<style scoped lang="scss">
.page { min-height: 100vh; padding: 22rpx 22rpx 150rpx; box-sizing: border-box; color: #263c53; background: #f3f6fa; }
.hero { display: flex; align-items: center; gap: 16rpx; margin-bottom: 18rpx; padding: 28rpx; color: #fff; border-radius: 22rpx; background: linear-gradient(145deg, #094e9f, #2084dd); }
.grow { flex: 1; min-width: 0; }
.eyebrow, .title, .subtitle { display: block; }
.eyebrow { font-size: 18rpx; opacity: .72; letter-spacing: 1rpx; }
.title { margin-top: 8rpx; font-size: 34rpx; font-weight: 720; }
.subtitle { margin-top: 8rpx; font-size: 20rpx; opacity: .82; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card { margin-bottom: 18rpx; padding: 25rpx; border: 1rpx solid #e5ebf2; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 26rpx rgba(28,68,105,.04); }
.section-title { display: block; margin-bottom: 12rpx; font-size: 28rpx; font-weight: 700; }
.progress-head { display: flex; align-items: flex-end; justify-content: space-between; }
.card-label { display: block; color: #8290a0; font-size: 20rpx; }
.progress-number { display: block; margin-top: 5rpx; color: #1769d2; font-size: 46rpx; font-weight: 750; }
.progress-number text { color: #9aa6b4; font-size: 24rpx; font-weight: 500; }
.unit { color: #708196; font-size: 21rpx; }
.progress-track { height: 14rpx; margin-top: 18rpx; overflow: hidden; border-radius: 99rpx; background: #eaf0f6; }
.progress-bar { height: 100%; border-radius: 99rpx; background: linear-gradient(90deg, #1769d2, #35a2e9); }
.quantity-row { display: flex; justify-content: space-between; margin-top: 16rpx; color: #718196; font-size: 19rpx; }
.info { display: flex; padding: 15rpx 0; border-bottom: 1rpx solid #edf1f5; font-size: 22rpx; }
.info text:first-child { width: 160rpx; color: #8995a5; }
.info text:last-child { flex: 1; color: #334f6d; }
.description { margin-top: 17rpx; padding: 18rpx; border-radius: 15rpx; background: #f6f8fb; }
.description text, .skill-line text { display: block; font-size: 22rpx; line-height: 1.55; }
.description text:first-child, .skill-line text:first-child { margin-bottom: 6rpx; color: #8793a3; font-size: 20rpx; }
.skill-line { margin-top: 17rpx; padding-top: 17rpx; border-top: 1rpx solid #edf1f5; }
.material-row { display: flex; align-items: center; gap: 12rpx; padding: 16rpx 0; border-bottom: 1rpx solid #edf1f5; }
.material-name, .material-sub { display: block; }
.material-name { color: #334f6d; font-size: 22rpx; }
.material-sub { margin-top: 6rpx; color: #8c98a5; font-size: 19rpx; }
.material-state { padding: 6rpx 10rpx; color: #1769d2; border-radius: 99rpx; background: #eaf3ff; font-size: 18rpx; white-space: nowrap; }
.field { padding: 16rpx 0; border-bottom: 1rpx solid #edf1f5; }
.field > text { display: block; margin-bottom: 10rpx; color: #69798b; font-size: 21rpx; }
.field input { height: 66rpx; font-size: 24rpx; line-height: 66rpx; }
.field textarea { width: 100%; min-height: 140rpx; padding: 15rpx; box-sizing: border-box; border-radius: 14rpx; background: #f6f8fb; font-size: 23rpx; }
.form-actions { display: flex; gap: 14rpx; margin-top: 22rpx; }
.form-actions button, .bottom-actions button { flex: 1; font-size: 22rpx; }
.primary, .success, .warning, .ghost { border: 0; border-radius: 16rpx; }
.primary { color: #fff; background: #1769d2; }
.success { color: #fff; background: #159869; }
.warning { color: #7c5610; background: #fff0cc; }
.ghost { color: #55677a; background: #edf1f5; }
.bottom-actions { position: fixed; right: 0; bottom: 0; left: 0; z-index: 5; display: flex; gap: 14rpx; padding: 18rpx 22rpx calc(18rpx + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -6rpx 20rpx rgba(20,45,75,.08); }
.timeline-item { position: relative; display: flex; gap: 18rpx; padding: 10rpx 0 24rpx; }
.timeline-dot { width: 18rpx; height: 18rpx; margin-top: 7rpx; border: 5rpx solid #d9e8fb; border-radius: 50%; background: #1769d2; }
.timeline-dot::after { position: absolute; top: 31rpx; bottom: 0; left: 9rpx; width: 2rpx; background: #dfe7f0; content: ""; }
.timeline-dot.last::after { display: none; }
.timeline-title, .timeline-note, .timeline-meta { display: block; }
.timeline-title { font-size: 23rpx; }
.timeline-note { margin-top: 6rpx; color: #536b84; font-size: 21rpx; line-height: 1.5; }
.timeline-meta { margin-top: 7rpx; color: #94a0ae; font-size: 18rpx; }
.empty { display: flex; min-height: 500rpx; align-items: center; justify-content: center; color: #8793a2; flex-direction: column; }
</style>
