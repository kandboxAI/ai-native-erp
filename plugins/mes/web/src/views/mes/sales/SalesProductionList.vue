<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import {
  configureWorkOrder,
  completeDemoWorkOrder,
  releaseDemoQuality,
  cancelDemoWorkOrder,
  customerName,
  releaseWorkOrder,
  productionProgress,
  productionLabels,
  type WorkOrder,
  type ProductionStatus,
} from "./model";
import { useMesSalesStoreHook } from "./store";
import ProductionDialogs from "./ProductionDialogs.vue";
import SalesProductionItems from "./SalesProductionItems.vue";
import { productionShipment } from "./shipmentModel";
import type { OperationForm } from "../work-orders/operationDefinitions";

const route = useRoute(),
  router = useRouter();
const session = useMesSalesStoreHook();
const { state, files } = session;
onActivated(session.ensureSession);
const keyword = ref(""),
  status = ref("");
const detailVisible = ref(false),
  selected = ref<WorkOrder>();
onDeactivated(() => {
  detailVisible.value = false;
});
const selectedProduction = computed(() =>
  state.productions.find((project) =>
    route.query.production_id
      ? project.id === route.query.production_id
      : project.orders.some((row) => row.id === route.query.work_order_id),
  ),
);
const selectedSource = computed(() =>
  state.orders.find((row) => row.id === selectedProduction.value?.order_id),
);
const selectedProgress = computed(() =>
  selectedProduction.value
    ? productionProgress(selectedProduction.value)
    : undefined,
);
const selectedShipment = computed(() =>
  productionShipment(state, selectedProduction.value?.id || ""),
);
const canShip = computed(
  () => hasPerms("mes:shipment:list") && hasPerms("mes:shipment:manage"),
);
const rows = computed(() =>
  state.productions
    .filter(
      (project) =>
        !route.query.sales_order_id ||
        project.order_id === route.query.sales_order_id,
    )
    .map((project) => ({
      ...project,
      source: state.orders.find((order) => order.id === project.order_id),
      progress: productionProgress(project),
      shipment: productionShipment(state, project.id),
    }))
    .filter(
      (row) =>
        (!status.value || row.progress.status === status.value) &&
        [
          row.production_no,
          row.source?.order_no,
          customerName(row.customer_id),
          ...row.orders.flatMap((item) => [
            item.work_order_no,
            item.snapshot.drawing_no,
            item.snapshot.description,
          ]),
        ]
          .join(" ")
          .toLowerCase()
          .includes(keyword.value.trim().toLowerCase()),
    ),
);
function openProduction(id: string) {
  const query = { ...route.query };
  query.production_id = id;
  delete query.work_order_id;
  router.push({ path: route.path, query });
}
function open(id: string) {
  const production = state.productions.find((project) =>
    project.orders.some((row) => row.id === id),
  );
  if (production)
    router.push({
      path: route.path,
      query: {
        ...route.query,
        production_id: production.id,
        work_order_id: id,
      },
    });
}
function restoreDetail() {
  if (
    route.path !== "/mes/work-orders" ||
    route.query.source !== "customer_order"
  )
    return;
  selected.value = selectedProduction.value?.orders.find(
    (row) => row.id === route.query.work_order_id,
  );
  detailVisible.value = !!selected.value;
  if (route.query.work_order_id && !selected.value) {
    ElMessage.info("当前货品暂存数据已清空或不属于本张工单，请重新打开");
    closeDetail();
  } else if (route.query.production_id && !selectedProduction.value) {
    ElMessage.info("当前工单暂存数据已清空，请返回客户订单重新生成");
    closeProduction();
  }
}
function closeDetail() {
  const query = { ...route.query };
  delete query.work_order_id;
  if (selectedProduction.value)
    query.production_id = selectedProduction.value.id;
  router.push({ path: route.path, query });
}
function closeProduction() {
  const query = { ...route.query };
  delete query.work_order_id;
  delete query.production_id;
  router.push({ path: route.path, query });
}
watch(
  () => [
    route.path,
    route.query.source,
    route.query.work_order_id,
    route.query.production_id,
  ],
  restoreDetail,
  { immediate: true },
);
onActivated(restoreDetail);
function configure(configuration: OperationForm) {
  if (!hasPerms("mes:work_order:manage")) throw Error("缺少工单管理权限");
  configureWorkOrder(selected.value, configuration);
  ElMessage.success("货品工序已配置");
}
function release() {
  if (!hasPerms("mes:work_order:manage")) throw Error("缺少工单管理权限");
  releaseWorkOrder(selected.value);
  ElMessage.success("货品已下达生产，当前状态由前端暂存");
}
function complete() {
  if (!hasPerms("mes:production_report:create")) throw Error("缺少报工权限");
  completeDemoWorkOrder(selected.value);
  ElMessage.success("已登记本项货品演示完工，待检验放行");
}
function qualityRelease() {
  if (!hasPerms("mes:quality:inspect")) throw Error("缺少检验放行权限");
  releaseDemoQuality(selected.value);
  ElMessage.success("本项货品演示检验已放行，可创建出货单");
}
function ship(id: string) {
  if (!hasPerms("mes:shipment:list") || !hasPerms("mes:shipment:manage"))
    return;
  router.push({
    path: "/mes/shipments",
    query: { source: "customer_order", create: "1", work_order_id: id },
  });
}
function shipProduction(id: string) {
  if (!canShip.value) return;
  const plan = productionShipment(state, id);
  if (!plan.is_ready) {
    ElMessage.info(plan.reason);
    return;
  }
  router.push({
    path: "/mes/shipments",
    query: { source: "customer_order", create: "1", production_id: id },
  });
}
async function cancel(id: string) {
  if (!hasPerms("mes:work_order:manage")) return;
  try {
    await ElMessageBox.confirm(
      "仅取消本项货品，对应数量恢复为客户订单的待下达数量，不影响同一工单内其他货品。",
      "取消货品",
      { type: "warning" },
    );
    const item = state.productions
      .flatMap((project) => project.orders)
      .find((row) => row.id === id);
    if (item) cancelDemoWorkOrder(item);
  } catch (cause) {
    if (cause instanceof Error) ElMessage.warning(cause.message);
  }
}
function clearOrderFilter() {
  const query = { ...route.query };
  delete query.sales_order_id;
  router.replace({ path: route.path, query });
}
</script>
<template>
  <div class="sales-prototype sales-production-list">
    <template v-if="!detailVisible">
      <el-alert
        type="info"
        :closable="false"
        title="一次生成一张生产工单，包含本次选择的全部货品；货品各自配置工序、生产和出货。当前为前端暂存，刷新后清空。"
      />
      <section
        v-if="selectedProduction"
        class="sales-editor-page"
        aria-label="客户订单生产工单详情"
      >
        <header class="prototype-heading">
          <div>
            <h2>{{ selectedProduction.production_no }}</h2>
            <p>
              {{ customerName(selectedProduction.customer_id) }} · 客户订单
              {{ selectedSource?.order_no }} ·
              {{ selectedProduction.orders.length }} 项货品
            </p>
          </div>
          <el-tag>{{ productionLabels[selectedProgress.status] }}</el-tag>
          <div class="prototype-toolbar">
            <el-button
              v-if="canShip"
              type="primary"
              :disabled="!selectedShipment.is_ready"
              @click="shipProduction(selectedProduction.id)"
              >整单发货</el-button
            >
            <el-button @click="closeProduction">返回工单列表</el-button>
          </div>
        </header>
        <p class="prototype-muted">
          已配置 {{ selectedProgress.configured_count }} /
          {{ selectedProgress.product_count }} 项有效货品，已完成
          {{ selectedProgress.completed_count }}
          项。各货品数量和工艺独立，选择货品进入工序配置。
        </p>
        <p class="prototype-muted">
          {{
            selectedShipment.reason ||
            "全部待发货品已就绪，整单发货将一次带出本工单全部剩余数量。"
          }}；如需先发部分货品，可使用下方“单项发货”。
        </p>
        <SalesProductionItems
          :items="selectedProduction.orders"
          :state="state"
          :on-open="open"
          :on-cancel="cancel"
          :on-ship="ship"
        />
      </section>
      <template v-else>
        <el-form inline class="prototype-toolbar" @submit.prevent>
          <el-form-item label="搜索"
            ><el-input
              v-model="keyword"
              clearable
              placeholder="工单、图号、客户订单或客户"
          /></el-form-item>
          <el-form-item label="工单状态"
            ><el-select
              v-model="status"
              clearable
              placeholder="全部状态"
              style="width: 160px"
              ><el-option
                v-for="(label, key) in productionLabels"
                :key="key"
                :label="label"
                :value="key" /></el-select
          ></el-form-item>
          <el-form-item
            ><el-button
              @click="
                keyword = '';
                status = '';
              "
              >重置</el-button
            ><el-button
              v-if="route.query.sales_order_id"
              @click="clearOrderFilter"
              >查看全部客户订单工单</el-button
            ></el-form-item
          >
        </el-form>
        <el-table :data="rows" row-key="id" stripe>
          <el-table-column type="expand"
            ><template #default="{ row }"
              ><div class="production-expanded-items">
                <SalesProductionItems
                  :items="row.orders"
                  :state="state"
                  :on-open="open"
                  :on-cancel="cancel"
                  :on-ship="ship"
                /></div></template
          ></el-table-column>
          <el-table-column label="生产工单" min-width="160"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="openProduction(row.id)">{{
                row.production_no
              }}</el-button></template
            ></el-table-column
          >
          <el-table-column label="客户 / 客户订单" min-width="230"
            ><template #default="{ row }"
              >{{ customerName(row.customer_id)
              }}<small
                >{{ row.source?.order_no }} ·
                {{ row.source?.customer_po_no || "未填写采购单号" }}</small
              ></template
            ></el-table-column
          >
          <el-table-column label="本次货品" width="130"
            ><template #default="{ row }"
              >{{ row.orders.length }} 项货品<small
                v-if="row.orders.length !== row.progress.product_count"
                >含取消
                {{ row.orders.length - row.progress.product_count }} 项</small
              ></template
            ></el-table-column
          >
          <el-table-column label="工序配置" width="140"
            ><template #default="{ row }"
              >{{ row.progress.configured_count }} /
              {{ row.progress.product_count }} 项已配置</template
            ></el-table-column
          >
          <el-table-column label="生产进度" width="140"
            ><template #default="{ row }"
              >{{ row.progress.completed_count }} /
              {{ row.progress.product_count }} 项已完成</template
            ></el-table-column
          >
          <el-table-column label="工单状态" width="130"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.progress.status === 'completed'
                    ? 'success'
                    : row.progress.status === 'cancelled'
                      ? 'info'
                      : 'primary'
                "
                >{{
                  productionLabels[row.progress.status as ProductionStatus]
                }}</el-tag
              ></template
            ></el-table-column
          >
          <el-table-column label="操作" width="240" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="openProduction(row.id)"
                >查看货品</el-button
              ><el-tooltip
                v-if="canShip"
                :content="row.shipment.reason || '一次发出本工单全部剩余货品'"
                placement="top"
                ><span
                  ><el-button
                    link
                    type="primary"
                    :disabled="!row.shipment.is_ready"
                    @click="shipProduction(row.id)"
                    >整单发货</el-button
                  ></span
                ></el-tooltip
              ></template
            ></el-table-column
          >
          <template #empty
            ><el-empty
              description="暂无生产工单，请先在客户订单中选择本次货品生成工单"
          /></template>
        </el-table>
      </template>
    </template>
    <ProductionDialogs
      v-model:detail-visible="detailVisible"
      :state="state"
      :work-order="selected"
      :production-no="selectedProduction?.production_no"
      :files="files"
      :can-configure="hasPerms('mes:work_order:manage')"
      :on-generate="() => {}"
      :on-configure="configure"
      :on-release="release"
      :on-complete="complete"
      :on-quality-release="qualityRelease"
      :on-ship="() => ship(selected.id)"
      @update:detail-visible="
        (value) => {
          if (!value) closeDetail();
        }
      "
    />
  </div>
</template>
<style src="./prototype.css" />
<style scoped>
.production-expanded-items {
  padding: 16px 24px;
}
</style>
