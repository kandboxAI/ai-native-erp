<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, reactive, ref, watch } from "vue";
import {
  customerName,
  workOrderLabels,
  type CustomerOrder,
  type OrderLine,
  type DemoState,
  type WorkOrder,
  remainingQuantity,
  allocatedQuantity,
} from "./model";
import type { LocalDrawings } from "./files";
import { hasPerms } from "@/utils/auth";
import type { FormInstance } from "element-plus";
import type { MesOption } from "@plugins/mes/web/src/api/mes";
import WorkOrderOperations from "../components/WorkOrderOperations.vue";
import { useWorkOrderOperations } from "../work-orders/useWorkOrderOperations";
import {
  operationDrafts,
  operationPayload,
  type OperationForm,
} from "../work-orders/operationDefinitions";
import { previewOrgId } from "./operationCatalog";
import { useMesSalesStoreHook } from "./store";

const releaseVisible = defineModel<boolean>("releaseVisible", {
  default: false,
});
const detailVisible = defineModel<boolean>("detailVisible", { default: false });
const props = defineProps<{
  state: DemoState;
  order?: CustomerOrder;
  workOrder?: WorkOrder;
  productionNo?: string;
  files: LocalDrawings;
  canConfigure: boolean;
  onGenerate: (choices: { order_line_id: string; quantity: number }[]) => void;
  onConfigure: (configuration: OperationForm) => void;
  onRelease: () => void;
  onComplete?: () => void;
  onQualityRelease?: () => void;
  onShip?: () => void;
}>();
const choices = ref<{ id: string; quantity: number; selected: boolean }[]>([]);
const generating = ref(false);
const configuration = reactive<OperationForm>({
  org_id: previewOrgId,
  product_item_id: "",
  planned_quantity: 1,
  process_template_id: null,
  process_template_version_snapshot: null,
  operations: [],
});
const formRef = ref<FormInstance>();
const saving = ref(false),
  unit = ref("");
const productOption = ref<MesOption>();
const configurationLocked = computed(
  () =>
    !props.canConfigure ||
    !props.workOrder ||
    !["unconfigured", "configured"].includes(props.workOrder.status),
);
const selected = computed(() => choices.value.filter((row) => row.selected));
watch(releaseVisible, (value) => {
  if (value && props.order) {
    generating.value = false;
    choices.value = props.order.lines.map((row) => {
      const quantity = remainingQuantity(props.state, row);
      return { id: row.id, quantity, selected: quantity > 0 };
    });
  }
});
watch(
  () => [detailVisible.value, props.workOrder?.id],
  () => {
    const value = detailVisible.value;
    if (value) {
      const order = props.workOrder;
      if (!order) return;
      Object.assign(configuration, {
        org_id: previewOrgId,
        product_item_id: `preview-product:${order.snapshot.drawing_no}:${order.snapshot.drawing_revision}`,
        planned_quantity: order.quantity,
        process_template_id: order.process_template_id || null,
        process_template_version_snapshot:
          order.process_template_version_snapshot || null,
        operations: operationDrafts(order.operations),
      });
      unit.value = order.snapshot.unit;
      productOption.value = {
        value: configuration.product_item_id,
        label: order.snapshot.drawing_no,
      };
      formRef.value?.clearValidate();
    }
  },
  { immediate: true },
);
const operationsEditor = useWorkOrderOperations(configuration, {
  visible: detailVisible,
  configurationLocked,
  saving,
  manage: computed(() => true),
  canSaveRoutes: computed(
    () => props.canConfigure && hasPerms("mes:process_template:manage"),
  ),
  unit,
  productOption,
  formRef,
  source: useMesSalesStoreHook().operationCatalog,
});
const hasUnsavedConfiguration = computed(() => {
  if (!props.workOrder) return false;
  try {
    return (
      JSON.stringify({
        operations: operationPayload(configuration.operations),
        id: configuration.process_template_id,
        version: configuration.process_template_version_snapshot,
      }) !==
      JSON.stringify({
        operations: operationPayload(props.workOrder.operations),
        id: props.workOrder.process_template_id || null,
        version: props.workOrder.process_template_version_snapshot || null,
      })
    );
  } catch {
    return true;
  }
});
function generate() {
  if (!releaseVisible.value || generating.value) return;
  generating.value = true;
  try {
    props.onGenerate(
      selected.value.map((row) => ({
        order_line_id: row.id,
        quantity: row.quantity,
      })),
    );
  } catch (cause) {
    generating.value = false;
    actionMessage((cause as Error).message);
  }
}
async function configure() {
  if (saving.value || configurationLocked.value) return;
  saving.value = true;
  try {
    if (!configuration.operations.length) throw Error("请至少配置一道工序");
    if (!(await formRef.value?.validate().catch(() => false))) return;
    props.onConfigure(configuration);
  } catch (cause) {
    actionMessage((cause as Error).message);
  } finally {
    saving.value = false;
  }
}
function release() {
  try {
    if (hasUnsavedConfiguration.value)
      throw Error("请先保存当前工序配置，再下达生产");
    props.onRelease();
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function productionAction(action?: () => void) {
  try {
    action?.();
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function openFile(file: WorkOrder["snapshot"]["files"][number]) {
  try {
    const url = props.files.url(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
</script>

<template>
  <el-dialog
    v-model="releaseVisible"
    title="分批生成生产工单"
    width="1080px"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
  >
    <div v-if="order" class="sales-prototype">
      <p>
        <strong>{{ order.order_no }}</strong> ·
        {{ customerName(order.customer_id) }}
      </p>
      <el-alert
        type="info"
        :closable="false"
        title="本次只生成一张生产工单，包含勾选的全部货品及本次数量；剩余货品或数量可在下次生成另一张工单。当前由前端暂存，尚未写入数据库。"
      />
      <el-table :data="order.lines" row-key="id" border class="prototype-table">
        <el-table-column label="选择" width="60"
          ><template #default="{ row, $index }"
            ><el-checkbox
              v-model="choices[$index].selected"
              :disabled="!remainingQuantity(state, row as OrderLine)"
              :aria-label="`生产 ${row.snapshot.drawing_no}`" /></template
        ></el-table-column>
        <el-table-column label="货品 / 报价来源" min-width="260"
          ><template #default="{ row }"
            ><strong>{{ row.snapshot.drawing_no }}</strong
            ><small
              >{{ row.quote_no }} · R{{ row.quote_revision }} · 图纸
              {{ row.snapshot.drawing_revision }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="订购数量" width="120"
          ><template #default="{ row }"
            >{{ row.quantity }} {{ row.snapshot.unit }}</template
          ></el-table-column
        >
        <el-table-column label="已下达数量" width="120"
          ><template #default="{ row }">{{
            allocatedQuantity(state, row.id)
          }}</template></el-table-column
        >
        <el-table-column label="待下达数量" width="120"
          ><template #default="{ row }">{{
            remainingQuantity(state, row as OrderLine)
          }}</template></el-table-column
        >
        <el-table-column label="本次生产数量" width="190"
          ><template #default="{ row, $index }"
            ><el-input-number
              :key="`quantity-${choices[$index].selected}`"
              v-model="choices[$index].quantity"
              :disabled="
                !choices[$index].selected ||
                !remainingQuantity(state, row as OrderLine)
              "
              :min="0.001"
              :max="remainingQuantity(state, row as OrderLine) || 0.001"
              :precision="3"
              controls-position="right" /></template
        ></el-table-column>
      </el-table>
    </div>
    <template #footer
      ><el-button @click="releaseVisible = false">取消</el-button
      ><el-button type="primary" :disabled="!selected.length" @click="generate"
        >生成本次工单</el-button
      ></template
    >
  </el-dialog>
  <section
    v-if="detailVisible"
    class="sales-editor-page"
    aria-label="工单货品详情"
  >
    <header class="prototype-heading">
      <div>
        <h2>工单货品详情</h2>
        <p>生产工单 {{ productionNo || "—" }} · 当前为前端流程验证。</p>
      </div>
      <el-button @click="detailVisible = false">返回货品列表</el-button>
    </header>
    <div v-if="workOrder" class="sales-prototype">
      <h3>货品明细 {{ workOrder.work_order_no }}</h3>
      <el-tag>{{ workOrderLabels[workOrder.status] }}</el-tag>
      <el-descriptions :column="2" border
        ><el-descriptions-item label="图号">{{
          workOrder.snapshot.drawing_no
        }}</el-descriptions-item
        ><el-descriptions-item label="图纸版本">{{
          workOrder.snapshot.drawing_revision
        }}</el-descriptions-item
        ><el-descriptions-item label="描述" :span="2">{{
          workOrder.snapshot.description
        }}</el-descriptions-item
        ><el-descriptions-item label="本批数量"
          >{{ workOrder.quantity }}
          {{ workOrder.snapshot.unit }}</el-descriptions-item
        ><el-descriptions-item label="交期">{{
          workOrder.due_date
        }}</el-descriptions-item
        ><el-descriptions-item label="材料" :span="2">{{
          workOrder.snapshot.quoted_material
        }}</el-descriptions-item
        ><el-descriptions-item label="处理要求" :span="2">{{
          workOrder.snapshot.surface_treatment
        }}</el-descriptions-item></el-descriptions
      >
      <p class="prototype-muted">
        生产资料使用接单时确认的版本；报价修订不回写这里的快照。可整批登记演示完工，再由检验人员确认放行，用于验证直接发货；这些操作不生成真实报工、检验或库存记录。
      </p>
      <div class="prototype-file-list">
        <el-button
          v-for="file in workOrder.snapshot.files"
          :key="file.id"
          link
          type="primary"
          @click="openFile(file)"
          >{{ file.name }}{{ file.is_demo ? "（示例）" : "" }}</el-button
        >
      </div>
      <el-alert
        type="info"
        :closable="false"
        title="当前仅使用演示工艺、设备、人员和路线；保存工序、另存路线及下达均不写入业务数据库。"
      />
      <el-descriptions v-if="workOrder.completed_at" :column="2" border>
        <el-descriptions-item label="演示完工时间">{{
          new Date(workOrder.completed_at).toLocaleString()
        }}</el-descriptions-item>
        <el-descriptions-item label="演示检验放行">{{
          workOrder.quality_released_at
            ? new Date(workOrder.quality_released_at).toLocaleString()
            : "待检验"
        }}</el-descriptions-item>
      </el-descriptions>
      <el-form
        ref="formRef"
        :model="configuration"
        label-position="top"
        :disabled="configurationLocked || saving"
      >
        <WorkOrderOperations :editor="operationsEditor" />
      </el-form>
    </div>
    <footer class="prototype-footer sales-page-footer">
      <el-button @click="detailVisible = false">关闭</el-button
      ><template v-if="workOrder && canConfigure && !configurationLocked"
        ><el-button
          :disabled="configurationLocked || saving"
          :loading="saving"
          @click="configure"
          >保存工序</el-button
        ><el-button
          type="primary"
          :disabled="
            workOrder.status !== 'configured' ||
            hasUnsavedConfiguration ||
            saving
          "
          @click="release"
          >下达生产</el-button
        ></template
      >
      <el-button
        v-if="
          workOrder?.status === 'released' &&
          onComplete &&
          hasPerms('mes:production_report:create')
        "
        type="primary"
        @click="productionAction(onComplete)"
        >登记完工（演示）</el-button
      >
      <el-button
        v-if="
          workOrder?.status === 'waiting_quality' &&
          onQualityRelease &&
          hasPerms('mes:quality:inspect')
        "
        type="primary"
        @click="productionAction(onQualityRelease)"
        >检验放行（演示）</el-button
      >
      <el-button
        v-if="
          workOrder?.status === 'completed' &&
          onShip &&
          hasPerms('mes:shipment:list') &&
          hasPerms('mes:shipment:manage')
        "
        type="primary"
        @click="productionAction(onShip)"
        >单项发货</el-button
      >
    </footer>
  </section>
</template>
