<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import {
  getMesReportDetail,
  createMesReportChange,
  type MesReportDetail,
  type MesReportChangeBody,
} from "@plugins/mes/web/src/api/mes";
import WorkflowStarterSelector from "@/components/WorkflowStarterSelector/index.vue";
import { message, actionMessage } from "@/utils/message";
const props = defineProps<{ reportId?: string }>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ submitted: [] }>();
const detail = ref<MesReportDetail>(),
  loading = ref(false),
  saving = ref(false),
  error = ref("");
const selector = ref<InstanceType<typeof WorkflowStarterSelector>>();
const form = reactive({
  change_type_code: "replace" as "replace" | "reverse",
  good_quantity: 0,
  scrap_quantity: 0,
  rework_quantity: 0,
  labor_minutes: undefined as number | undefined,
  machine_minutes: undefined as number | undefined,
  reason: "",
});
let request = 0,
  fingerprint = "",
  key = "";
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  detail.value = undefined;
  key = "";
  fingerprint = "";
  try {
    const result = await getMesReportDetail(props.reportId);
    if (current === request) {
      detail.value = result.data;
      Object.assign(form, {
        change_type_code: "replace",
        good_quantity: result.data.good_quantity,
        scrap_quantity: result.data.scrap_quantity,
        rework_quantity: result.data.rework_quantity,
        labor_minutes: result.data.labor_minutes ?? undefined,
        machine_minutes: result.data.machine_minutes ?? undefined,
        reason: "",
      });
    }
  } catch (cause: any) {
    if (current === request) error.value = cause?.message || "报工读取失败";
  } finally {
    if (current === request) loading.value = false;
  }
}
async function submit() {
  if (saving.value || !detail.value || detail.value.status_code !== "posted")
    return;
  if (
    !form.reason.trim() ||
    (form.change_type_code === "replace" &&
      form.good_quantity + form.scrap_quantity + form.rework_quantity <= 0)
  ) {
    message("请填写理由及有效产出数量，清空报工请选冲销", { type: "warning" });
    return;
  }
  saving.value = true;
  try {
    const choices = await selector.value.collect(detail.value.org_id);
    if (choices === null) return;
    const facts = {
      ...form,
      reason: form.reason.trim(),
      ...(form.change_type_code === "reverse"
        ? {
            good_quantity: 0,
            scrap_quantity: 0,
            rework_quantity: 0,
            labor_minutes: null,
            machine_minutes: null,
          }
        : {}),
    };
    const serialized = JSON.stringify(facts);
    if (fingerprint !== serialized) {
      fingerprint = serialized;
      key = crypto.randomUUID();
    }
    await createMesReportChange(detail.value.id, {
      ...facts,
      idempotency_key: key,
      starter_choices: choices,
    } as MesReportChangeBody);
    message("变更申请已提交，审批通过后才回算产量和工时", { type: "success" });
    visible.value = false;
    emit("submitted");
  } catch (cause: any) {
    actionMessage(cause?.message || "提交失败，内容已保留，可重试");
  } finally {
    saving.value = false;
  }
}
watch(
  () => [visible.value, props.reportId],
  () => {
    if (visible.value && props.reportId) load();
    else ++request;
  },
);
</script>
<template>
  <el-dialog
    v-model="visible"
    title="申请报工更正 / 冲销"
    width="min(730px, 96vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    append-to-body
    destroy-on-close
  >
    <div v-loading="loading">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      /><template v-if="detail"
        ><p>
          {{ detail.report_no }} · {{ detail.work_order_no }} ·
          {{ detail.operation_name }}
        </p>
        <p>
          原合格 / 报废 / 返工：{{ detail.good_quantity }} /
          {{ detail.scrap_quantity }} / {{ detail.rework_quantity }}
          {{ detail.unit_name }}
        </p>
        <el-alert
          title="原报工数值会保留。审批通过后将其标记为已冲销，并追加更正报工；审批期间工单生产操作暂停。已有后续执行或返修安排时不能直接更正。"
          type="info"
          :closable="false"
        /><el-form
          :disabled="saving || detail.status_code !== 'posted'"
          label-position="top"
          ><el-form-item label="申请类型"
            ><el-radio-group v-model="form.change_type_code"
              ><el-radio-button value="replace">更正数值</el-radio-button
              ><el-radio-button value="reverse"
                >全部冲销</el-radio-button
              ></el-radio-group
            ></el-form-item
          >
          <div v-if="form.change_type_code === 'replace'" class="grid">
            <el-form-item
              v-for="field in [
                { key: 'good_quantity', label: '合格数量' },
                { key: 'scrap_quantity', label: '报废数量' },
                { key: 'rework_quantity', label: '返工数量' },
                { key: 'labor_minutes', label: '人工工时（分钟）' },
                { key: 'machine_minutes', label: '机器工时（分钟）' },
              ]"
              :key="field.key"
              :label="field.label"
              ><el-input-number
                v-model="form[field.key]"
                :min="0"
                :precision="3"
                :controls="false"
            /></el-form-item>
          </div>
          <el-form-item label="变更理由（必填）"
            ><el-input
              v-model="form.reason"
              type="textarea"
              :rows="3"
              maxlength="1000" /></el-form-item
        ></el-form>
        <p v-if="detail.status_code !== 'posted'">
          当前报工不是可变更的已入账状态。
        </p></template
      >
    </div>
    <WorkflowStarterSelector ref="selector" business-type="mes_report_change" />
    <template #footer
      ><el-button :disabled="saving" @click="visible = false">取消</el-button
      ><el-button
        type="primary"
        :loading="saving"
        :disabled="!detail || detail.status_code !== 'posted'"
        @click="submit"
        >提交审批</el-button
      ></template
    >
  </el-dialog>
</template>
<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0 16px;
}

.el-input-number {
  width: 100%;
}

.el-form {
  margin-top: 18px;
}
</style>
