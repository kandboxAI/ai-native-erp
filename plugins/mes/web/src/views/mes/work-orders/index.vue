<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import {
  getMesWorkOrders,
  getMesProductionOrders,
  getMesOrderDefinition,
  commandMesWorkOrder,
  placeMesProductionOrder,
  type MesWorkOrder,
  type MesProductionOrder,
  type MesOrderDefinition,
  type MesOrderAction,
  type MesListParams,
  type MesOperationProgress,
} from "@plugins/mes/web/src/api/mes";
import { hasPerms, getToken } from "@/utils/auth";
import { message } from "@/utils/message";
import {
  formatMesDate,
  mesStatusType,
  mesProcessingTypeLabel,
  mesPercent,
  isMesOverdue,
  mesWorkOrderStatusKey,
  mesWorkOrderStatusLabel,
  mesProjectOrderStatusKey,
  mesProjectOrderStatusLabel,
  mesPendingProjectOrders,
  canPlaceMesProject,
} from "../shared";
import WorkOrderCreate from "../components/WorkOrderCreate.vue";
import ProductionOrderEditor from "../components/ProductionOrderEditor.vue";
import WorkOrderDetail from "../components/WorkOrderDetail.vue";
import WorkOrderProcessChanges from "../components/WorkOrderProcessChanges.vue";
import OrderActions from "../components/OrderActions.vue";
import RemoteSelect from "../components/RemoteSelect.vue";
import OperationRouteProgress from "../components/OperationRouteProgress.vue";
import OperationReportsDialog from "../components/OperationReportsDialog.vue";
import { openWorkOrderCard } from "./printCard";
import { loadMesViews, saveMesViews, type MesSavedView } from "./savedViews";

defineOptions({ name: "MesWorkOrders" });
const props = defineProps<{ repairOnly?: boolean }>();
const route = useRoute(),
  router = useRouter();
const sourceVisible = ref(false);
const operationReportsVisible = ref(false);
const reportContext = ref<{
  work_order_id: string;
  work_order_no: string;
  operation: MesOperationProgress;
}>();
function openOperationReports(
  order: MesWorkOrder,
  operation: MesOperationProgress,
) {
  if (!hasPerms("mes:production_report:list")) return;
  reportContext.value = {
    work_order_id: order.id,
    work_order_no: order.work_order_no,
    operation,
  };
  operationReportsVisible.value = true;
}
const sourceId = ref("");
async function sourceOptions(keyword: string) {
  const result = await getMesWorkOrders({
    keyword,
    page_size: 50,
    repair_source_only: true,
  });
  return result.data.items.map((row) => ({
    value: row.id,
    label: `${row.work_order_no} · ${row.product_item_name}`,
  }));
}
async function newRepair() {
  if (!sourceId.value || busyId.value) return;
  await handleCommand("repair", { id: sourceId.value });
  if (createVisible.value) sourceVisible.value = false;
}
const rows = ref<MesWorkOrder[]>([]);
const projects = ref<MesProductionOrder[]>([]);
const viewMode = ref<"project" | "product">("product");
const total = ref(0),
  page = ref(1),
  pageSize = ref(10);
const loading = ref(false),
  error = ref("");
const emptyFilters = () => ({
  keyword: "",
  status_code: "",
  priority_code: "",
  customer: "",
  creator: "",
  order_type_code: "",
  processing_type_code: "",
  configuration: "",
  overdue_only: false,
});
const filters = reactive(emptyFilters());
const dueRange = ref<string[]>([]),
  createdRange = ref<string[]>([]);
const projectVisible = ref(false),
  createVisible = ref(false),
  detailVisible = ref(false);
const purpose = ref<"create" | "edit" | "copy" | "repair">("create");
const editorStep = ref<"product" | "operations">("product");
const processChangesVisible = ref(false);
const processChangeOrderId = ref("");
const definition = ref<MesOrderDefinition>();
const projectPurpose = ref<"edit" | "copy">();
const initialProject = ref<MesProductionOrder>();
const copyProducts = ref<MesOrderDefinition[]>([]);
const orderId = ref(""),
  busyId = ref("");
const statuses = [
  { value: "unconfigured", label: "未配置" },
  { value: "ready", label: "待下单" },
  { value: "ordered", label: "已下单" },
  { value: "paused", label: "已暂停" },
  { value: "completed", label: "已完结" },
  { value: "cancelled", label: "已取消" },
];
const currentUser = getToken()?.userId;
const savedViews = ref(loadMesViews(localStorage, currentUser));
const selectedView = ref("");
let request = 0;
function query(): MesListParams {
  return {
    ...filters,
    production_order_id:
      typeof route.query.production_order_id === "string"
        ? route.query.production_order_id
        : undefined,
    ...(props.repairOnly ? { order_type_code: "repair" } : {}),
    created_from: createdRange.value?.[0],
    created_to: createdRange.value?.[1],
    due_from: dueRange.value?.[0],
    due_to: dueRange.value?.[1],
  };
}
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const params = { ...query(), page: page.value, page_size: pageSize.value };
    if (viewMode.value === "project") {
      const res = await getMesProductionOrders(params);
      if (current === request) {
        projects.value = res.data.items;
        total.value = res.data.total;
      }
    } else {
      const res = await getMesWorkOrders(params);
      if (current === request) {
        rows.value = res.data.items;
        total.value = res.data.total;
      }
    }
  } catch (cause: any) {
    if (current === request) {
      rows.value = [];
      projects.value = [];
      total.value = 0;
      error.value = cause?.message || "工单加载失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function reset() {
  Object.assign(filters, emptyFilters());
  dueRange.value = [];
  createdRange.value = [];
  selectedView.value = "";
  search();
}
function created(id?: string) {
  search();
  if (id) {
    orderId.value = id;
    detailVisible.value = true;
  }
}
function newProject() {
  projectPurpose.value = undefined;
  initialProject.value = undefined;
  copyProducts.value = [];
  projectVisible.value = true;
}
async function projectCommand(
  action: "edit" | "copy" | "place",
  row: Record<string, any>,
) {
  if (busyId.value) return;
  busyId.value = row.id;
  try {
    if (action === "place") {
      if (!canPlaceMesProject(row as MesProductionOrder)) {
        message("请先为全部未下单货品配置工序", { type: "warning" });
        return;
      }
      await ElMessageBox.confirm(
        `确认下单：${row.production_order_no}？已有下单货品保持不变，本次不报工、不记库存。`,
        "整单下单",
        {
          type: "warning",
          confirmButtonText: "确认",
          cancelButtonText: "取消",
        },
      );
      await placeMesProductionOrder(row.id, {
        version_no: row.version_no,
        orders: mesPendingProjectOrders(row as MesProductionOrder).map(
          (order) => ({ id: order.id, version_no: order.version_no }),
        ),
      });
      message("下单成功", { type: "success" });
      await load();
      return;
    }
    copyProducts.value =
      action === "copy"
        ? await Promise.all(
            row.orders.map(
              async (order: MesWorkOrder) =>
                (await getMesOrderDefinition(order.id)).data,
            ),
          )
        : [];
    initialProject.value = row as MesProductionOrder;
    projectPurpose.value = action;
    projectVisible.value = true;
  } catch (cause: any) {
    if (!["cancel", "close"].includes(cause))
      message(cause?.message || "工单操作失败", { type: "warning" });
  } finally {
    busyId.value = "";
  }
}
async function handleCommand(action: string, row: Record<string, any>) {
  if (busyId.value) return;
  if (action === "process_changes") {
    processChangeOrderId.value = row.id;
    processChangesVisible.value = true;
    return;
  }
  if (action === "detail") {
    orderId.value = row.id;
    detailVisible.value = true;
    return;
  }
  busyId.value = row.id;
  try {
    if (["edit", "copy", "repair", "configure_operations"].includes(action)) {
      definition.value = (await getMesOrderDefinition(row.id)).data;
      editorStep.value =
        action === "configure_operations" ? "operations" : "product";
      purpose.value =
        action === "configure_operations"
          ? "edit"
          : (action as typeof purpose.value);
      createVisible.value = true;
      return;
    }
    if (action === "print" || action === "download") {
      await openWorkOrderCard(row.id, action === "download");
      return;
    }
    const labels = {
      place: "下单",
      publish: "下单",
      withdraw: "撤回下单",
      pause: "暂停生产",
      resume: "恢复生产",
      complete: "完结工单",
      cancel: "取消工单",
      delete: "删除未执行工单",
    };
    if (!(action in labels)) return;
    let note: string | undefined;
    if (["complete", "cancel", "delete"].includes(action)) {
      const result = await ElMessageBox.prompt(
        action === "complete"
          ? "未完成工序将被取消，实际产量保留。请填写完结理由。"
          : "保留操作历史。请填写操作理由。",
        `${labels[action]} · ${row.work_order_no}`,
        {
          inputType: "textarea",
          inputPattern: /\S/,
          inputErrorMessage: "请填写理由",
          confirmButtonText: "确认",
          cancelButtonText: "取消",
        },
      );
      note = result.value;
    } else
      await ElMessageBox.confirm(
        `确认${labels[action]}：${row.work_order_no}？`,
        "工单操作",
        {
          type: "warning",
          confirmButtonText: "确认",
          cancelButtonText: "取消",
        },
      );
    await commandMesWorkOrder(
      row.id,
      action as MesOrderAction,
      row.version_no,
      note,
    );
    message("工单操作已完成", { type: "success" });
    await load();
  } catch (cause: any) {
    if (!["cancel", "close"].includes(cause))
      message(cause?.message || "操作失败，请刷新后重试", { type: "warning" });
  } finally {
    busyId.value = "";
  }
}
async function saveView() {
  try {
    const result = await ElMessageBox.prompt(
      "保存当前筛选条件到本浏览器、当前账号下（最多 10 个）",
      "保存工单视图",
      {
        inputPattern: /^\S.{0,39}$/,
        inputErrorMessage: "请输入 1–40 字的名称",
      },
    );
    const next: MesSavedView = {
      name: result.value.trim(),
      mode: viewMode.value,
      filters: query(),
    };
    const others = savedViews.value.filter((row) => row.name !== next.name);
    if (others.length >= 10) {
      message("视图已满，请先删除一个视图", { type: "warning" });
      return;
    }
    if (getToken()?.userId !== currentUser)
      throw new Error("登录状态已变化，请重新登录");
    saveMesViews(localStorage, currentUser, [...others, next]);
    savedViews.value = [...others, next];
    selectedView.value = next.name;
  } catch (cause: any) {
    if (!["cancel", "close"].includes(cause))
      message(cause?.message || "视图保存失败", { type: "warning" });
  }
}
function applyView(name: string) {
  const view = savedViews.value.find((row) => row.name === name);
  if (!view) return;
  Object.assign(filters, emptyFilters(), view.filters);
  viewMode.value = props.repairOnly ? "product" : view.mode;
  dueRange.value = view.filters.due_from
    ? [view.filters.due_from, view.filters.due_to || view.filters.due_from]
    : [];
  createdRange.value = view.filters.created_from
    ? [
        view.filters.created_from,
        view.filters.created_to || view.filters.created_from,
      ]
    : [];
  search();
}
function removeView() {
  if (!selectedView.value || getToken()?.userId !== currentUser) return;
  try {
    const values = savedViews.value.filter(
      (row) => row.name !== selectedView.value,
    );
    saveMesViews(localStorage, currentUser, values);
    savedViews.value = values;
    selectedView.value = "";
  } catch {
    message("视图删除失败", { type: "warning" });
  }
}
onMounted(load);
watch(() => route.query.production_order_id, search);
</script>

<template>
  <div class="mes-page">
    <div class="page-heading">
      <div>
        <h2>{{ repairOnly ? "返修工单" : "生产工单" }}</h2>
        <p>
          {{
            repairOnly
              ? "关联原工单，独立安排返修工序和数量，保留原工单的生产记录。"
              : "按项目统一管理多种产品，按产品独立配置工序和跟踪生产。"
          }}
        </p>
      </div>
      <div v-if="hasPerms('mes:work_order:create')" class="heading-actions">
        <el-button
          v-if="!repairOnly && hasPerms('mes:sales_order:list')"
          @click="router.push('/mes/sales-orders')"
          >客户订单</el-button
        >
        <el-button
          type="primary"
          @click="repairOnly ? (sourceVisible = true) : newProject()"
          >{{
            repairOnly ? "＋ 从原工单生成返修" : "＋ 新增生产工单"
          }}</el-button
        >
      </div>
    </div>
    <el-card shadow="never">
      <div class="view-toolbar">
        <el-radio-group v-if="!repairOnly" v-model="viewMode" @change="search"
          ><el-radio-button value="project">工单 / 项目</el-radio-button
          ><el-radio-button value="product"
            >货品 / 执行工单</el-radio-button
          ></el-radio-group
        ><el-select
          v-model="selectedView"
          placeholder="已保存视图"
          clearable
          style="width: 180px"
          @change="applyView"
          ><el-option
            v-for="view in savedViews"
            :key="view.name"
            :value="view.name"
            :label="view.name" /></el-select
        ><el-button @click="saveView">保存当前视图</el-button
        ><el-button v-if="selectedView" link type="danger" @click="removeView"
          >删除视图</el-button
        >
      </div>
      <el-form inline class="filters" @submit.prevent="search">
        <el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            clearable
            maxlength="128"
            placeholder="项目 / 工单 / 产品"
            @keyup.enter="search" /></el-form-item
        ><el-form-item label="客户"
          ><el-input
            v-model="filters.customer"
            clearable
            maxlength="128"
            placeholder="客户编号 / 名称"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="创建人"
          ><el-input
            v-model="filters.creator"
            clearable
            maxlength="128"
            placeholder="按创建人姓名查找"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-select
            v-model="filters.status_code"
            clearable
            placeholder="全部"
            style="width: 150px"
            ><el-option
              v-for="item in statuses"
              :key="item.value"
              :value="item.value"
              :label="item.label" /></el-select></el-form-item
        ><el-form-item v-if="!repairOnly" label="工单类型"
          ><el-select
            v-model="filters.order_type_code"
            clearable
            placeholder="全部"
            style="width: 125px"
            ><el-option label="普通生产" value="production" /><el-option
              label="返修生产"
              value="repair" /></el-select
        ></el-form-item>
        <el-form-item label="货品类型"
          ><el-select
            v-model="filters.processing_type_code"
            clearable
            placeholder="全部"
            style="width: 120px"
            ><el-option label="自制" value="in_house" /><el-option
              label="委外"
              value="outsourced" /><el-option
              label="采购"
              value="purchased" /></el-select
        ></el-form-item>
        <el-form-item label="优先级"
          ><el-select
            v-model="filters.priority_code"
            clearable
            placeholder="全部"
            style="width: 100px"
            ><el-option label="紧急" value="urgent" /><el-option
              label="高"
              value="high" /><el-option label="普通" value="normal" /><el-option
              label="低"
              value="low" /></el-select></el-form-item
        ><el-form-item label="配置"
          ><el-select
            v-model="filters.configuration"
            clearable
            placeholder="全部"
            style="width: 120px"
            ><el-option label="已配置工序" value="configured" /><el-option
              label="未配置工序"
              value="unconfigured" /></el-select
        ></el-form-item>
        <el-form-item label="交期"
          ><el-date-picker
            v-model="dueRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 245px" /></el-form-item
        ><el-form-item label="创建日期"
          ><el-date-picker
            v-model="createdRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 245px" /></el-form-item
        ><el-form-item
          ><el-checkbox v-model="filters.overdue_only" @change="search"
            >仅看逾期</el-checkbox
          ></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        >
      </el-form>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        show-icon
        :closable="false"
        ><el-button link type="primary" @click="load"
          >重新加载</el-button
        ></el-alert
      >
      <el-table
        v-if="viewMode === 'project'"
        v-loading="loading"
        :data="projects"
        row-key="id"
        empty-text="暂无生产项目；历史独立工单请切换货品视图"
      >
        <el-table-column type="expand"
          ><template #default="{ row }"
            ><el-table :data="row.orders" class="child-table"
              ><el-table-column
                prop="work_order_no"
                label="产品工单号"
                min-width="190" /><el-table-column
                prop="product_item_name"
                label="产品"
                min-width="180" /><el-table-column label="计划" width="120"
                ><template #default="{ row: item }"
                  >{{ item.planned_quantity }} {{ item.unit_name }}</template
                ></el-table-column
              ><el-table-column label="货品类型" width="100"
                ><template #default="{ row: item }">{{
                  mesProcessingTypeLabel(item.processing_type_code)
                }}</template></el-table-column
              ><el-table-column label="工序进度 / 工艺路线" min-width="520"
                ><template #default="{ row: item }"
                  ><OperationRouteProgress
                    :order="item as MesWorkOrder"
                    :can-view-reports="hasPerms('mes:production_report:list')"
                    @view-reports="
                      openOperationReports(item as MesWorkOrder, $event)
                    " /></template></el-table-column
              ><el-table-column label="状态" width="110"
                ><template #default="{ row: item }"
                  ><el-tag :type="mesStatusType(mesWorkOrderStatusKey(item))">{{
                    mesWorkOrderStatusLabel(item)
                  }}</el-tag></template
                ></el-table-column
              ><el-table-column label="操作" min-width="265"
                ><template #default="{ row: item }"
                  ><OrderActions
                    :order="item"
                    :disabled="!!busyId"
                    @command="
                      handleCommand
                    " /></template></el-table-column></el-table></template
        ></el-table-column>
        <el-table-column
          prop="production_order_no"
          label="工单 / 项目编号"
          min-width="190"
        /><el-table-column
          prop="project_name"
          label="项目名称"
          min-width="180"
        /><el-table-column
          prop="customer_name"
          label="客户"
          min-width="140"
        /><el-table-column label="工单状态" width="110">
          <template #default="{ row }"
            ><el-tag
              :type="
                mesStatusType(
                  mesProjectOrderStatusKey(row as MesProductionOrder),
                )
              "
              >{{
                mesProjectOrderStatusLabel(row as MesProductionOrder)
              }}</el-tag
            ></template
          > </el-table-column
        ><el-table-column label="货品款数" min-width="155"
          ><template #default="{ row }">
            {{ row.product_count }}
            <el-tooltip
              v-if="row.is_import_incomplete"
              :content="row.note"
              placement="top"
              ><el-tag type="warning" size="small"
                >已导 {{ row.product_count }} / 原
                {{ row.source_product_count_snapshot }}</el-tag
              ></el-tooltip
            >
          </template></el-table-column
        ><el-table-column label="配置情况" width="110"
          ><template #default="{ row }"
            >{{ row.configured_count }} / {{ row.product_count }}</template
          ></el-table-column
        ><el-table-column label="下单情况" width="110"
          ><template #default="{ row }"
            >{{ row.released_count }} / {{ row.product_count }}</template
          ></el-table-column
        ><el-table-column label="项目进度" min-width="180"
          ><template #default="{ row }"
            ><el-progress
              :percentage="mesPercent(row.completed_count, row.product_count)"
            /><small
              >完成 {{ row.completed_count }} /
              {{ row.product_count }} 款</small
            ></template
          ></el-table-column
        ><el-table-column label="创建时间" min-width="170"
          ><template #default="{ row }">{{
            formatMesDate(row.created_at)
          }}</template></el-table-column
        >
        <el-table-column label="项目操作" min-width="235" fixed="right"
          ><template #default="{ row }"
            ><el-button
              v-if="
                hasPerms('mes:work_order:manage') &&
                mesPendingProjectOrders(row as MesProductionOrder).length
              "
              link
              type="primary"
              :disabled="
                !!busyId || !canPlaceMesProject(row as MesProductionOrder)
              "
              :title="
                !canPlaceMesProject(row as MesProductionOrder)
                  ? '请先为全部未下单货品配置工序'
                  : '为全部待下单货品下单'
              "
              @click="projectCommand('place', row)"
              >下单</el-button
            ><el-button
              v-if="hasPerms('mes:work_order:manage')"
              link
              type="primary"
              :disabled="!!busyId"
              @click="projectCommand('edit', row)"
              >资料 / 追加产品</el-button
            ><el-button
              v-if="hasPerms('mes:work_order:create')"
              link
              type="primary"
              :disabled="!!busyId"
              @click="projectCommand('copy', row)"
              >复制</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        empty-text="暂无符合条件的工单"
      >
        <el-table-column label="工单 / 产品" min-width="240"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="handleCommand('detail', row)"
              >{{ row.work_order_no }}</el-button
            >
            <div>{{ row.product_item_name }}</div>
            <small>{{ row.product_item_no }}</small></template
          ></el-table-column
        ><el-table-column label="项目 / 客户" min-width="170"
          ><template #default="{ row }"
            ><div>{{ row.project_name || "独立执行工单" }}</div>
            <small>{{ row.customer_name || "—" }}</small></template
          ></el-table-column
        ><el-table-column label="工单类型" width="95"
          ><template #default="{ row }">{{
            row.order_type_code === "repair" ? "返修" : "生产"
          }}</template></el-table-column
        ><el-table-column label="货品类型" width="100"
          ><template #default="{ row }"
            ><el-tag
              :type="
                row.processing_type_code === 'outsourced' ? 'warning' : 'info'
              "
              >{{ mesProcessingTypeLabel(row.processing_type_code) }}</el-tag
            ></template
          ></el-table-column
        ><el-table-column label="计划数量" min-width="110"
          ><template #default="{ row }"
            >{{ row.planned_quantity }} {{ row.unit_name }}</template
          ></el-table-column
        ><el-table-column label="工序进度 / 工艺路线" min-width="520"
          ><template #default="{ row }"
            ><OperationRouteProgress
              :order="row as MesWorkOrder"
              :can-view-reports="hasPerms('mes:production_report:list')"
              @view-reports="
                openOperationReports(row as MesWorkOrder, $event)
              " /></template></el-table-column
        ><el-table-column
          prop="priority_label"
          label="优先级"
          width="85"
        /><el-table-column label="状态" width="105"
          ><template #default="{ row }"
            ><el-tag :type="mesStatusType(mesWorkOrderStatusKey(row))">{{
              mesWorkOrderStatusLabel(row)
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="交付时间" min-width="170"
          ><template #default="{ row }"
            ><span :class="{ urgent: isMesOverdue(row) }"
              >{{ formatMesDate(row.due_at)
              }}{{ isMesOverdue(row) ? " · 逾期" : "" }}</span
            ></template
          ></el-table-column
        ><el-table-column
          prop="creator_name"
          label="创建人"
          min-width="110"
        /><el-table-column label="操作" min-width="265" fixed="right"
          ><template #default="{ row }"
            ><OrderActions
              :order="row"
              :disabled="!!busyId"
              @command="handleCommand" /></template
        ></el-table-column>
      </el-table>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        class="pagination"
        layout="total, sizes, prev, pager, next"
        :total="total"
        @current-change="load"
        @size-change="search"
      />
    </el-card>
    <el-dialog
      v-model="sourceVisible"
      title="选择返修来源工单"
      width="min(560px, 95vw)"
      append-to-body
    >
      <RemoteSelect
        v-model="sourceId"
        :load-options="sourceOptions"
        placeholder="按原工单号或产品查找"
      />
      <p>仅可选择已下单且有权查看的工单。返修数量不能超过来源工单计划数量。</p>
      <template #footer
        ><el-button @click="sourceVisible = false">取消</el-button
        ><el-button
          type="primary"
          :loading="!!busyId"
          :disabled="!sourceId"
          @click="newRepair"
          >配置返修</el-button
        ></template
      >
    </el-dialog>
    <OperationReportsDialog
      v-model="operationReportsVisible"
      :context="reportContext"
    />
    <ProductionOrderEditor
      v-model="projectVisible"
      :purpose="projectPurpose"
      :initial-project="initialProject"
      :copy-products="copyProducts"
      @created="created()"
    /><WorkOrderCreate
      v-model="createVisible"
      :purpose="purpose"
      :step="editorStep"
      :initial-order="definition"
      @created="created"
    /><WorkOrderDetail v-model="detailVisible" :work-order-id="orderId" />
    <WorkOrderProcessChanges v-model="processChangesVisible" :order-id="processChangeOrderId"
      @changed="load" @repair="id => { processChangesVisible = false; handleCommand('detail', { id }); }" />
  </div>
</template>

<style scoped>
.mes-page {
  padding: 20px;
}

.page-heading,
.view-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.heading-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.order-source {
  margin-bottom: 18px;
}

.page-heading {
  justify-content: space-between;
  margin-bottom: 22px;
}

.view-toolbar {
  margin-bottom: 22px;
}

h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 650;
}

p,
small {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.urgent {
  color: var(--el-color-danger);
}

.pagination {
  justify-content: flex-end;
  margin-top: 20px;
}

.child-table {
  padding: 10px 30px;
}
</style>
