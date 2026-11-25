<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { formatQuantity } from "@/utils/quantity";
import { formatDateTime } from "@/utils/datetime";
import { getHttpErrorMessage } from "@/utils/http";
import {
  approveMaterialRequisition,
  rejectMaterialRequisition,
  requisitionStatusLabels,
  requisitionEventLabels,
  receiptExceptionLabels,
  type MaterialRequisition,
} from "@plugins/inv/web/src/api/inventoryRequisition";
import RequisitionActionDialog from "./RequisitionActionDialog.vue";
const props = defineProps<{ request: MaterialRequisition }>();
const emit = defineEmits<{ (e: "changed"): void }>();
const action = ref<"issue" | "receive" | "exception" | "resolve">("receive");
const actionVisible = ref(false);
const busy = ref(false);
const lineNames = computed(() =>
  Object.fromEntries(
    props.request.lines.map((line) => [
      line.id,
      `${line.item_name_snapshot}（${line.unit_name}）`,
    ]),
  ),
);
function open(value: typeof action.value) {
  action.value = value;
  actionVisible.value = true;
}
async function decide(reject: boolean) {
  if (busy.value) return;
  try {
    const { value } = await ElMessageBox.prompt(
      reject ? "请填写驳回原因" : "可填写审批意见",
      reject ? "驳回申请" : "审批通过",
      {
        inputValue: reject ? "" : "同意领用",
        inputValidator: (value) =>
          ((!reject || Boolean(value?.trim())) &&
            String(value || "").length <= 500) ||
          "请填写500字以内的意见",
      },
    );
    busy.value = true;
    await (reject ? rejectMaterialRequisition : approveMaterialRequisition)(
      props.request.id,
      props.request.version_no,
      value,
    );
    ElMessage.success("审批结果已保存");
    emit("changed");
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(getHttpErrorMessage(error, "审批失败"));
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <h2>{{ request.request_no }}</h2>
  <el-tag>{{ requisitionStatusLabels[request.status_code] }}</el-tag>
  <el-descriptions :column="2" border style="margin-top: 16px">
    <el-descriptions-item v-for="field in request.extension_fields || []" :key="field.label" :label="field.label">{{ field.value }}</el-descriptions-item>
    <el-descriptions-item label="申请人">{{
      request.applicant_name_snapshot
    }}</el-descriptions-item>
    <el-descriptions-item label="申请来源组织">{{ request.applicant_org_name_snapshot || '历史未记录' }}</el-descriptions-item>
    <el-descriptions-item label="所属部门">{{
      request.department_name_snapshot || "—"
    }}</el-descriptions-item>
    <el-descriptions-item label="申请时间">{{
      formatDateTime(request.created_at)
    }}</el-descriptions-item>
    <el-descriptions-item label="提交批次">{{
      request.submission_batch_no
    }}</el-descriptions-item>
    <el-descriptions-item label="发放仓库">{{
      request.warehouse_name
    }}</el-descriptions-item>
    <el-descriptions-item label="出库单号">{{
      request.stock_order_no || "尚未生成"
    }}</el-descriptions-item>
    <el-descriptions-item label="审批人">{{
      request.approved_by_name_snapshot || "—"
    }}</el-descriptions-item>
    <el-descriptions-item label="审批时间">{{
      formatDateTime(request.approved_at, "—")
    }}</el-descriptions-item>
    <el-descriptions-item label="发放人">{{
      request.issued_by_name_snapshot || "—"
    }}</el-descriptions-item>
    <el-descriptions-item label="发放时间">{{
      formatDateTime(request.issued_at, "—")
    }}</el-descriptions-item>
    <el-descriptions-item label="签收人">{{
      request.received_by_name_snapshot || "未记录签收"
    }}</el-descriptions-item>
    <el-descriptions-item label="签收时间">{{
      formatDateTime(request.received_at, "—")
    }}</el-descriptions-item>
    <el-descriptions-item label="领用用途" :span="2">{{
      request.purpose
    }}</el-descriptions-item>
    <el-descriptions-item label="使用地点" :span="2">{{ request.custody_location_note || '流动使用，无固定地点' }}</el-descriptions-item>
    <el-descriptions-item
      v-if="request.approval_note"
      label="审批意见"
      :span="2"
      >{{ request.approval_note }}</el-descriptions-item
    >
  </el-descriptions>
  <template v-if="request.personal_custody_assets?.length">
    <h3>个人保管资产</h3>
    <p>发放保管人：{{ request.applicant_name_snapshot }}；无须固定地点，签收仅确认收货。</p>
    <el-table :data="request.personal_custody_assets" border>
      <el-table-column label="资产编号"><template #default="{ row }">{{ row.asset_no || '历史数量资产' }}</template></el-table-column>
      <el-table-column prop="quantity" label="发放数量" />
    </el-table>
  </template>
  <h3>物资明细</h3>
  <el-table :data="request.lines" border>
    <el-table-column prop="item_no_snapshot" label="物资编码" min-width="120" />
    <el-table-column
      prop="item_name_snapshot"
      label="物资名称"
      min-width="130"
    />
    <el-table-column
      prop="specification_snapshot"
      label="规格"
      min-width="100"
    />
    <el-table-column label="申请数量" width="120"
      ><template #default="{ row }"
        >{{ formatQuantity(row.quantity) }} {{ row.unit_name }}</template
      ></el-table-column
    >
    <el-table-column label="实际发放" width="120"
      ><template #default="{ row }">{{
        row.issued_quantity == null
          ? "未单独记录"
          : `${formatQuantity(row.issued_quantity)} ${row.unit_name}`
      }}</template></el-table-column
    >
  </el-table>
  <h3>操作与照片留档</h3>
  <el-timeline>
    <el-timeline-item
      v-for="event in request.events"
      :key="event.id"
      :timestamp="event.created_at"
      placement="top"
    >
      <strong
        >{{
          requisitionEventLabels[event.event_type_code] || event.event_type_code
        }}
        · {{ event.operator_name_snapshot }}</strong
      >
      <p>{{ event.note }}</p>
      <p v-for="line in event.receipt_lines || []" :key="line.line_id">
        {{ lineNames[line.line_id] }}：收到 {{ line.received_quantity
        }}<template v-if="line.exception_type_code"
          >；{{ receiptExceptionLabels[line.exception_type_code] }}
          {{ line.exception_quantity }}</template
        >
      </p>
      <div class="evidence">
        <el-image
          v-for="photo in event.photos || []"
          :key="photo.id"
          :src="photo.url"
          :preview-src-list="event.photos.map((item) => item.url)"
          :initial-index="event.photos.indexOf(photo)"
          fit="cover"
          preview-teleported
        />
      </div>
    </el-timeline-item>
  </el-timeline>
  <div class="requisition-actions">
    <template
      v-if="
        request.status_code === 'submitted' &&
        hasPerms('inventory_requisition:approve')
      "
      ><el-button type="primary" :disabled="busy" @click="decide(false)"
        >审批通过</el-button
      ><el-button type="danger" plain :disabled="busy" @click="decide(true)"
        >驳回</el-button
      ></template
    >
    <el-button
      v-if="
        request.status_code === 'approved' &&
        hasPerms('inventory_requisition:issue')
      "
      type="success"
      @click="open('issue')"
      >确认发放并出库</el-button
    >
    <template v-if="request.can_receive"
      ><el-button type="primary" @click="open('receive')">确认收货</el-button
      ><el-button type="warning" plain @click="open('exception')"
        >反馈收货异常</el-button
      ></template
    >
    <el-button
      v-if="
        request.status_code === 'receipt_exception' &&
        hasPerms('inventory_requisition:issue')
      "
      type="primary"
      @click="open('resolve')"
      >登记异常处理</el-button
    >
    <el-button @click="emit('changed')">刷新记录与照片</el-button>
  </div>
  <RequisitionActionDialog
    v-model="actionVisible"
    :request="request"
    :action="action"
    @saved="emit('changed')"
  />
</template>
<style scoped>
h3 {
  margin: 24px 0 14px;
}
.evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.evidence .el-image {
  width: 100px;
  height: 100px;
  border-radius: 6px;
}
.requisition-actions {
  position: sticky;
  bottom: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 16px 0;
  background: var(--el-bg-color);
}
.requisition-actions .el-button {
  margin-left: 0;
}
</style>
