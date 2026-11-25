<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, type UploadUserFile } from "element-plus";
import { discardFile, uploadSelectedFiles } from "@/api/systemFile";
import { getHttpErrorMessage } from "@/utils/http";
import RequisitionAssetSelect from "./RequisitionAssetSelect.vue";
import type { StockAssetTracking } from "../../../api/invAssetManagement";
import {
  issueMaterialRequisition,
  receiveMaterialRequisition,
  resolveMaterialRequisitionException,
  receiptExceptionLabels,
  type MaterialRequisition,
  type ReceiptLine,
} from "@plugins/inv/web/src/api/inventoryRequisition";

const props = defineProps<{
  modelValue: boolean;
  request: MaterialRequisition;
  action: "issue" | "receive" | "exception" | "resolve";
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();
const busy = ref(false);
const note = ref("");
const files = ref<UploadUserFile[]>([]);
const checks = ref<
  Array<
    ReceiptLine & {
      name: string;
      unit: string;
      issued: number;
      quantity: number;
      item_id: string;
      asset_tracking?: StockAssetTracking;
    }
  >
>([]);
const title = computed(
  () =>
    ({
      issue: "确认发放并出库",
      receive: "确认收货",
      exception: "反馈收货异常",
      resolve: "登记异常处理",
    })[props.action],
);
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    note.value = "";
    files.value = [];
    checks.value = props.request.lines.map((line) => ({
      line_id: line.id,
      item_id: line.item_id,
      name: line.item_name_snapshot,
      unit: line.unit_name,
      issued: Number(line.issued_quantity ?? line.quantity),
      quantity: Number(line.quantity),
      received_quantity: Number(line.issued_quantity ?? line.quantity),
      exception_quantity: 0,
      exception_type_code: null,
    }));
  },
);
function updateMissing(value: unknown) {
  const row = value as (typeof checks.value)[number];
  if (row.exception_type_code === "not_received") row.received_quantity = 0;
  if (["shortage", "not_received"].includes(row.exception_type_code || ""))
    row.exception_quantity = Math.max(
      0,
      row.issued - Number(row.received_quantity),
    );
  if (!row.exception_type_code) row.exception_quantity = 0;
}
async function cleanup() {
  const pending = files.value;
  files.value = [];
  await Promise.allSettled(
    pending.map((file) => {
      const id = (file.response as { id?: string })?.id;
      return id ? discardFile(id) : Promise.resolve();
    }),
  );
}
async function save() {
  if (busy.value) return;
  if (props.action === "issue") {
    const mismatch = checks.value.find(
      (row) =>
        row.asset_tracking?.selections.length &&
        Math.abs(
          row.asset_tracking.selections.reduce(
            (sum, asset) => sum + Number(asset.quantity),
            0,
          ) - row.quantity,
        ) > 0.000001,
    );
    if (mismatch)
      return ElMessage.warning(
        `“${mismatch.name}”的已选资产数量须与实际发放数量一致`,
      );
  }
  if (["exception", "resolve"].includes(props.action) && !note.value.trim())
    return ElMessage.warning("请填写说明或处理结果");
  if (
    props.action === "exception" &&
    !checks.value.some((row) => row.exception_type_code)
  )
    return ElMessage.warning("请至少选择一项异常物资");
  if (
    props.action === "exception" &&
    checks.value.some((row) =>
      ["damaged", "wrong_item"].includes(row.exception_type_code || ""),
    ) &&
    !files.value.length
  )
    return ElMessage.warning("破损或错发请上传问题照片");
  busy.value = true;
  try {
    const scene = {
      issue: "requisition_issue",
      receive: "requisition_receive",
      exception: "requisition_exception",
      resolve: "requisition_resolve",
    }[props.action];
    const photo_file_ids: string[] = [];
    for (const file of files.value) {
      const [id] = await uploadSelectedFiles([file], scene);
      file.response = { id };
      photo_file_ids.push(id);
    }
    const data = {
      version_no: props.request.version_no,
      note: note.value.trim(),
      photo_file_ids,
    };
    if (props.action === "issue")
      await issueMaterialRequisition(
        props.request.id,
        data.version_no,
        data.note,
        photo_file_ids,
        checks.value.map((row) => ({
          line_id: row.line_id,
          quantity: row.quantity,
          ...(row.asset_tracking
            ? { tracking: { asset: row.asset_tracking } }
            : {}),
        })),
      );
    else if (props.action === "resolve")
      await resolveMaterialRequisitionException(props.request.id, data);
    else
      await receiveMaterialRequisition(
        props.request.id,
        {
          ...data,
          lines: checks.value.map((row) => ({
            line_id: row.line_id,
            received_quantity: row.received_quantity,
            exception_quantity: row.exception_quantity,
            exception_type_code: row.exception_type_code,
          })),
        },
        props.action === "exception",
      );
    files.value = [];
    ElMessage.success(
      props.action === "issue"
        ? "已发放出库，等待申请人签收"
        : props.action === "resolve"
          ? "已通知申请人重新核对收货"
          : "收货记录已保存",
    );
    emit("update:modelValue", false);
    emit("saved");
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "操作失败，请刷新详情后重试"));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="action === 'issue' ? 'min(1080px, 95vw)' : 'min(850px, 95vw)'"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="cleanup"
  >
    <el-alert
      :closable="false"
      type="info"
      :title="
        action === 'issue'
          ? `确认后按实际数量扣减库存，资产交由${request.applicant_name_snapshot}个人保管，无须固定地点；本申请一次发放，差额请另行申请。`
          : action === 'resolve'
            ? '请先完成实际处理，记录核实结果、补发或退库单号；本操作只留档，不调整库存，之后仍需申请人签收。'
            : '请逐项核对数量、规格和完好情况。签收和异常反馈不会再次扣减库存。'
      "
    />
    <el-table
      v-if="action !== 'resolve'"
      :data="checks"
      class="requisition-action-lines"
      row-key="line_id"
      border
    >
      <el-table-column prop="name" label="物资" min-width="120" />
      <el-table-column
        v-if="action === 'issue'"
        label="关联发放资产"
        min-width="350"
        ><template #default="{ row }">
          <RequisitionAssetSelect
            v-model="row.asset_tracking"
            :item-id="row.item_id"
            :warehouse-id="request.warehouse_id"
            :item-name="row.name"
            :unit="row.unit"
            :quantity="row.quantity"
            :disabled="busy"
          /> </template
      ></el-table-column>
      <el-table-column label="申请 / 发放" width="120"
        ><template #default="{ row }"
          >{{ row.issued }} {{ row.unit }}</template
        ></el-table-column
      >
      <el-table-column v-if="action === 'issue'" label="实际发放" width="170"
        ><template #default="{ row }"
          ><el-input-number
            v-model="row.quantity"
            :min="0.001"
            :max="row.issued"
            :precision="3"
            controls-position="right"
            :disabled="busy" /></template
      ></el-table-column>
      <el-table-column v-else label="实际收到" width="170"
        ><template #default="{ row }"
          ><el-input-number
            v-model="row.received_quantity"
            :min="0"
            :max="row.issued"
            :precision="3"
            controls-position="right"
            :disabled="busy || action === 'receive'"
            @change="updateMissing(row)" /></template
      ></el-table-column>
      <template v-if="action === 'exception'">
        <el-table-column label="异常类型" width="130"
          ><template #default="{ row }"
            ><el-select
              v-model="row.exception_type_code"
              :disabled="busy"
              @change="updateMissing(row)"
              ><el-option :value="null" label="正常" /><el-option
                v-for="(label, key) in receiptExceptionLabels"
                :key="key"
                :value="key"
                :label="label" /></el-select></template
        ></el-table-column>
        <el-table-column label="问题数量" width="170"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.exception_quantity"
              :min="0"
              :max="row.issued"
              :precision="3"
              controls-position="right"
              :disabled="
                busy ||
                !['damaged', 'wrong_item'].includes(
                  row.exception_type_code || '',
                )
              " /></template
        ></el-table-column>
      </template>
    </el-table>
    <p v-if="action === 'receive'">
      提交即确认以上物资已收到，数量、规格及完好情况核对无误。
    </p>
    <el-input
      v-model="note"
      type="textarea"
      :rows="3"
      maxlength="500"
      show-word-limit
      :disabled="busy"
      :placeholder="
        action === 'resolve'
          ? '必填：核实结果、处理方式及相关单号'
          : action === 'exception'
            ? '必填：请说明少发、未收到、错发或破损情况'
            : '备注（选填）'
      "
    />
    <p>照片留档（最多 6 张，单张 2 MB；破损或错发反馈至少 1 张）</p>
    <el-upload
      v-model:file-list="files"
      :auto-upload="false"
      :limit="6"
      list-type="picture-card"
      accept="image/jpeg,image/png,image/webp"
      :disabled="busy"
      @exceed="ElMessage.warning('最多上传6张照片')"
      >＋</el-upload
    >
    <template #footer>
      <div class="erp-form-actions">
        <div class="erp-form-actions__primary">
          <el-button :disabled="busy" @click="emit('update:modelValue', false)"
            >取消</el-button
          ><el-button type="primary" :loading="busy" @click="save">{{
            title
          }}</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.requisition-action-lines {
  margin: 20px 0;
}
</style>
