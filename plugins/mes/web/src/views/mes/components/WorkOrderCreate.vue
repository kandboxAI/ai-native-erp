<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import type { FormInstance } from "element-plus";
import {
  createMesWorkOrder,
  getMesProductOptions,
  getMesOrgOptions,
  type MesOption,
  type MesOrderDefinition,
  updateMesWorkOrder,
} from "@plugins/mes/web/src/api/mes";
import { message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import RemoteSelect from "./RemoteSelect.vue";
import { hasPerms } from "@/utils/auth";
import WorkOrderOperations from "./WorkOrderOperations.vue";
import { useWorkOrderOperations } from "../work-orders/useWorkOrderOperations";
import {
  operation,
  operationPayload,
} from "../work-orders/operationDefinitions";
import { systemOperationCatalog } from "../work-orders/operationCatalog";
import ProductDrawingFiles from "./ProductDrawingFiles.vue";
import {
  uploadProductDrawings,
  releaseProductDrawings,
  markProductDrawingsBound,
  type ProductDrawing,
} from "../work-orders/productDrawings";

const props = defineProps<{
  purpose?: "create" | "edit" | "copy" | "repair" | "configure";
  initialOrder?: MesOrderDefinition;
  reworkReportId?: string;
  maxQuantity?: number;
  orgId?: string;
  step?: "product" | "operations";
}>();
const operationStep = computed(() => props.step === "operations");
const configurationLocked = computed(
  () => props.purpose === "edit" && !props.initialOrder?.can_edit_configuration,
);
const dialogTitle = computed(
  () =>
    ({
      edit: "变更生产工单",
      copy: "复制生产工单",
      repair: "生成返修工单",
      configure: "填写货品资料",
    })[props.purpose || ""] || "创建生产工单",
);
const editorTitle = computed(() =>
  operationStep.value ? "配置工序" : dialogTitle.value,
);

const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{
  created: [workOrderId: string];
  configured: [definition: MesOrderDefinition];
}>();
const formRef = ref<FormInstance>();
const saving = ref(false);
const drawingFiles = ref<ProductDrawing[]>([]);
const drawingRevision = ref("");
function drawingRemoved(file: ProductDrawing) {
  if (props.purpose !== "configure") releaseProductDrawings([file]);
}
const unit = ref("");
const productOption = ref<MesOption>();
function initial() {
  return {
    org_id: "",
    work_order_no: "",
    product_item_id: "",
    planned_quantity: 1,
    processing_type_code: "in_house" as "in_house" | "outsourced" | "purchased",
    priority_code: "normal",
    due_at: "",
    note: "",
    source_work_order_id: null as string | null,
    process_template_id: null as string | null,
    process_template_version_snapshot: null as number | null,
    operations: operationStep.value ? [operation(1)] : [],
  };
}
const form = reactive(initial());
const operationsEditor = useWorkOrderOperations(form, {
  visible: computed(() => visible.value && operationStep.value),
  configurationLocked,
  saving,
  manage: computed(() => props.purpose === "edit"),
  canSaveRoutes: computed(() => hasPerms("mes:process_template:manage")),
  unit,
  productOption,
  formRef,
  source: systemOperationCatalog,
});
const { revealOperation } = operationsEditor;
const required = (label: string) => ({
  required: true,
  message: `请填写${label}`,
  trigger: "change",
});
watch(visible, (value) => {
  if (props.purpose !== "configure") releaseProductDrawings(drawingFiles.value);
  drawingFiles.value = [];
  if (value) {
    drawingFiles.value =
      props.purpose === "configure"
        ? (props.initialOrder?.drawing_files || []).map((file) => ({ ...file }))
        : [];
    drawingRevision.value =
      props.purpose === "configure"
        ? props.initialOrder?.drawing_revision_label || ""
        : "";
    Object.assign(form, initial());
    if (props.initialOrder) {
      const data = props.initialOrder;
      Object.assign(form, {
        org_id: data.org_id || props.orgId || "",
        work_order_no: data.work_order_no || "",
        product_item_id: data.product_item_id || "",
        planned_quantity: data.planned_quantity || 1,
        processing_type_code: data.processing_type_code || "in_house",
        priority_code: data.priority_code || "normal",
        due_at: data.due_at || "",
        note: data.note || "",
        source_work_order_id: data.source_work_order_id || null,
        process_template_id: data.process_template_id || null,
        process_template_version_snapshot:
          data.process_template_version_snapshot || null,
        operations: (data.operations || []).map((row, index) => ({
          ...operation(index + 1),
          ...row,
          assigned_user_id: row.assigned_user_id || "",
          work_center_name: row.work_center_name || "",
          workstation_name: row.workstation_name || "",
          operation_description: row.operation_description || "",
        })),
      });
      if (props.purpose === "copy" || props.purpose === "repair") {
        form.work_order_no = "";
        form.process_template_id = null;
        form.process_template_version_snapshot = null;
      }
      if (props.purpose === "repair") {
        form.source_work_order_id = data.id;
        form.operations.forEach((row) => {
          row.planned_quantity = undefined;
        });
      }
      if (props.purpose === "repair" && props.maxQuantity)
        form.planned_quantity = Math.min(
          form.planned_quantity,
          props.maxQuantity,
        );
    }
    if (!form.org_id) form.org_id = props.orgId || "";
    unit.value = props.initialOrder?.unit_name || "";
    productOption.value = undefined;
    formRef.value?.clearValidate();
  }
});
function productSelected(value?: MesOption) {
  productOption.value = value;
  unit.value = value?.unit || "";
}
onBeforeUnmount(() => {
  if (props.purpose !== "configure") releaseProductDrawings(drawingFiles.value);
});
async function submit(publish = false) {
  if (saving.value) return;
  if (operationStep.value && configurationLocked.value) {
    message("工单已执行，不能修改工序", { type: "warning" });
    return;
  }
  // Creating product records and releasing executable work are separate steps.
  if (!operationStep.value) publish = false;
  saving.value = true;
  if (publish && !form.operations.length) {
    message("下单前请至少添加一道工序", { type: "warning" });
    saving.value = false;
    return;
  }
  const valid = await formRef.value?.validate().catch(async (fields) => {
    const path = Object.keys(fields || {}).find((key) =>
      /^operations\.\d+\./.test(key),
    );
    if (path) {
      await revealOperation(form.operations[Number(path.split(".")[1])].key);
      formRef.value?.scrollToField(path);
    }
    return false;
  });
  if (!valid) {
    saving.value = false;
    return;
  }
  const numbers = form.operations.map((row) => row.operation_no.trim());
  if (new Set(numbers).size !== numbers.length) {
    const duplicateIndex = numbers.findIndex(
      (number, index) => numbers.indexOf(number) !== index,
    );
    revealOperation(form.operations[duplicateIndex].key);
    message("工序编号不能重复", { type: "warning" });
    saving.value = false;
    return;
  }
  try {
    if (props.maxQuantity && form.planned_quantity > props.maxQuantity)
      throw new Error("返修数量超过可安排数量，请调整后重试");
    const payload: MesOrderDefinition = {
      org_id: form.org_id,
      work_order_no: form.work_order_no.trim(),
      product_item_id: form.product_item_id,
      planned_quantity: form.planned_quantity,
      processing_type_code: form.processing_type_code,
      priority_code: form.priority_code,
      publish,
      source_work_order_id: form.source_work_order_id,
      rework_report_id:
        props.purpose === "repair" ? props.reworkReportId : undefined,
      process_template_id: form.process_template_id,
      process_template_version_snapshot: form.process_template_version_snapshot,
      note: form.note,
      due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
      operations: operationPayload(form.operations),
    };
    if (props.purpose === "configure") {
      payload.drawing_files = drawingFiles.value.map((file) => ({ ...file }));
      if (drawingFiles.value.length)
        payload.drawing_revision_label = drawingRevision.value.trim();
      payload.product_label =
        props.initialOrder?.product_item_id === form.product_item_id
          ? props.initialOrder.product_label
          : productOption.value?.label;
      payload.unit_name = unit.value;
      emit("configured", payload);
      visible.value = false;
      return;
    }
    if (props.purpose !== "edit" && drawingFiles.value.length) {
      payload.drawing_attachment_ids = await uploadProductDrawings(
        drawingFiles.value,
      );
      payload.drawing_revision_label = drawingRevision.value.trim();
    }
    const response =
      props.purpose === "edit"
        ? await updateMesWorkOrder(props.initialOrder.id, {
            ...payload,
            version_no: props.initialOrder.version_no,
          })
        : await createMesWorkOrder(payload);
    message(
      props.purpose === "edit"
        ? "工单变更已保存"
        : publish
          ? "工单已下单"
          : form.operations.length
            ? "工单已保存，状态为待下单"
            : "工单已保存，状态为未配置",
      { type: "success" },
    );
    markProductDrawingsBound(drawingFiles.value);
    visible.value = false;
    emit("created", response.data.work_order_id);
  } catch (error: any) {
    message(getHttpErrorMessage(error, "创建失败，请检查工单内容后重试"), {
      type: "warning",
    });
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="mes-work-order-dialog"
    :title="editorTitle"
    top="4vh"
    width="min(1100px, 96vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    destroy-on-close
    append-to-body
  >
    <el-form
      ref="formRef"
      :model="form"
      label-position="top"
      :disabled="saving"
    >
      <el-descriptions v-if="operationStep" :column="2" border>
        <el-descriptions-item label="产品工单号">{{
          form.work_order_no
        }}</el-descriptions-item>
        <el-descriptions-item label="生产产品">{{
          initialOrder?.product_label || form.product_item_id
        }}</el-descriptions-item>
        <el-descriptions-item label="计划数量"
          >{{ form.planned_quantity }} {{ unit }}</el-descriptions-item
        >
        <el-descriptions-item label="货品类型">{{
          form.processing_type_code === "outsourced" ? "委外" : "自制"
        }}</el-descriptions-item>
      </el-descriptions>
      <div v-else class="basic-grid">
        <el-form-item
          v-if="!initialOrder?.org_id"
          label="所属组织"
          prop="org_id"
          :rules="required('所属组织')"
          ><RemoteSelect
            v-model="form.org_id"
            :load-options="getMesOrgOptions"
            placeholder="选择组织"
            auto-select-single
        /></el-form-item>
        <el-form-item
          label="工单号"
          prop="work_order_no"
          :rules="[
            {
              required: true,
              whitespace: true,
              message: '请填写工单号',
              trigger: 'blur',
            },
          ]"
          ><el-input
            v-model="form.work_order_no"
            :disabled="configurationLocked"
            maxlength="64"
            placeholder="输入唯一工单号"
        /></el-form-item>
        <el-form-item
          label="生产产品"
          prop="product_item_id"
          :rules="required('生产产品')"
          ><RemoteSelect
            v-model="form.product_item_id"
            :disabled="configurationLocked || purpose === 'repair'"
            :initial-option="
              productOption ||
              (initialOrder?.product_item_id
                ? {
                    value: initialOrder.product_item_id,
                    label:
                      initialOrder.product_label ||
                      initialOrder.product_item_id,
                  }
                : undefined)
            "
            :load-options="getMesProductOptions"
            placeholder="按物料编号或名称查找"
            @select="productSelected"
        /></el-form-item>
        <el-form-item
          :label="`计划数量${unit ? `（${unit}）` : ''}`"
          prop="planned_quantity"
          :rules="required('计划数量')"
          ><el-input-number
            v-model="form.planned_quantity"
            :disabled="configurationLocked"
            :min="0.001"
            :max="
              purpose === 'repair'
                ? maxQuantity || initialOrder?.planned_quantity
                : undefined
            "
            :precision="3"
            :controls="false"
        /></el-form-item>
        <el-form-item
          label="货品类型"
          prop="processing_type_code"
          :rules="required('货品类型')"
        >
          <el-select
            v-model="form.processing_type_code"
            :disabled="configurationLocked"
          >
            <el-option label="自制" value="in_house" /><el-option
              label="委外"
              value="outsourced"
            />
            <el-option label="采购" value="purchased" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级"
          ><el-select v-model="form.priority_code"
            ><el-option label="普通" value="normal" /><el-option
              label="高"
              value="high" /><el-option label="紧急" value="urgent" /><el-option
              label="低"
              value="low" /></el-select
        ></el-form-item>
        <el-form-item label="交付时间"
          ><el-date-picker
            v-model="form.due_at"
            type="datetime"
            placeholder="选择交付时间"
        /></el-form-item>
      </div>
      <el-form-item v-if="!operationStep" label="工单说明"
        ><el-input
          v-model="form.note"
          type="textarea"
          :rows="2"
          maxlength="4000"
      /></el-form-item>
      <el-alert
        v-if="configurationLocked"
        :title="
          operationStep
            ? '工单已有执行记录，工序配置不可修改。'
            : '工单已有执行记录，仅允许修改交期、优先级和说明。'
        "
        type="info"
        :closable="false"
      />
      <section v-if="purpose !== 'edit' && !operationStep">
        <h3>产品图纸与模型</h3>
        <ProductDrawingFiles
          v-model="drawingFiles"
          :disabled="saving"
          @removed="drawingRemoved"
        />
        <el-form-item v-if="drawingFiles.length" label="图纸自身版次（选填）">
          <el-input
            v-model="drawingRevision"
            maxlength="128"
            placeholder="按文件实际标注填写，如 A、B；系统修订号自动生成"
          />
        </el-form-item>
      </section>
      <p v-else>图纸与模型请在工单详情的“工单图纸”中维护。</p>
      <WorkOrderOperations v-if="operationStep" :editor="operationsEditor" />
      <p class="publish-note">
        {{
          operationStep
            ? "保存工序后变为待下单，点击列表“下单”进入生产；下单只改变状态，不记录产量或库存。"
            : "先保存工单与货品资料，未配置工序时显示“未配置”，后续由工艺人员配置并下单。"
        }}
      </p>
    </el-form>
    <template #footer
      ><el-button :disabled="saving" @click="visible = false">取消</el-button
      ><template v-if="purpose === 'edit' || purpose === 'configure'"
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="operationStep && configurationLocked"
          @click="submit(false)"
          >{{
            purpose === "configure"
              ? "确认货品"
              : operationStep
                ? "保存工序"
                : "保存变更"
          }}</el-button
        ></template
      ><template v-else
        ><el-button type="primary" :loading="saving" @click="submit(false)"
          >创建工单</el-button
        ></template
      ></template
    >
  </el-dialog>
</template>

<style scoped>
:global(.mes-work-order-dialog .el-dialog__body) {
  max-height: calc(92dvh - 150px);
  overflow-y: auto;
}

.basic-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 20px;
}

.el-input-number,
.el-date-editor {
  width: 100%;
}

.publish-note {
  margin-top: 16px;
}

p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

@media (width <= 760px) {
  .basic-grid {
    grid-template-columns: 1fr;
  }
}
</style>
