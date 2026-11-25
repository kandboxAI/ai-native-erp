<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  getDeliveryCockpit,
  type CockpitFocus,
  type DeliveryCockpit,
  type DeliveryRow,
} from "@plugins/mes/web/src/api/mesCockpit";
import WorkOrderDetail from "../components/WorkOrderDetail.vue";
import {
  formatMesDate,
  mesWorkOrderStatusLabel,
  mesStatusLabel,
  mesStatusType,
  type MesTagType,
} from "../shared";
defineOptions({ name: "MesDashboard" });
const router = useRouter();
const filters = reactive({ keyword: "", customer: "", soon_days: 7 });
const dueDates = ref<string[]>([]),
  focus = ref<CockpitFocus>("outstanding");
const page = ref(1),
  size = ref(20),
  loading = ref(false),
  error = ref("");
const data = ref<DeliveryCockpit>(),
  detailVisible = ref(false),
  orderId = ref("");
let request = 0;
const metrics: {
  key: Exclude<CockpitFocus, "all">;
  label: string;
  note: string;
  tone?: string;
}[] = [
  { key: "outstanding", label: "未交付工单", note: "计划数量尚未全部确认出货" },
  {
    key: "exceptions",
    label: "有未关闭异常",
    note: "关联异常仍在处理或等待复核",
  },
  {
    key: "overdue_exceptions",
    label: "有超时异常",
    note: "包含已交付但异常未关闭的工单",
    tone: "danger",
  },
  {
    key: "overdue",
    label: "已逾期",
    note: "超过交期且仍有未交付数量",
    tone: "danger",
  },
  {
    key: "due_soon",
    label: "近期到期",
    note: "含今天，尚未逾期",
    tone: "warning",
  },
  {
    key: "waiting_quality",
    label: "待检验",
    note: "仍有工序等待检验放行",
    tone: "warning",
  },
  { key: "unplanned", label: "未排程", note: "未开始工序尚未安排时间" },
  {
    key: "released_output",
    label: "已有放行余量",
    note: "末道放行量大于已确认出货量",
  },
];
const focusOptions: { key: CockpitFocus; label: string }[] = [
  { key: "outstanding", label: "待交付" },
  { key: "blocked", label: "需处理" },
  { key: "no_due", label: "未填交期" },
  { key: "delivered", label: "已交付" },
  { key: "all", label: "全部" },
];
const deliveryLabels: Record<
  DeliveryRow["delivery_status"],
  { label: string; type: MesTagType }
> = {
  overdue: { label: "已逾期", type: "danger" },
  due_soon: { label: "近期到期", type: "warning" },
  on_track: { label: "待交付", type: "primary" },
  no_due: { label: "未填交期", type: "info" },
  delivered: { label: "已交付", type: "success" },
};
const riskLabels: Record<string, string> = {
  open_exception: "存在未关闭异常",
  overdue_exception: "异常处理已超时",
  unreleased: "工单未下单",
  paused: "工单已暂停",
  unconfigured: "尚未配置工序",
  waiting_quality: "等待检验放行",
  pending_change: "报工变更待处理",
  blocked_operation: "工序暂停或取消",
  unplanned: "存在未排程工序",
  plan_after_due: "计划结束晚于交期",
  operation_late: "当前工序计划已超时",
};
const selectedTitle = computed(
  () =>
    [...metrics, ...focusOptions].find((item) => item.key === focus.value)
      ?.label || "交付清单",
);
const shortcuts = computed(() =>
  [
    {
      label: "生产排程",
      permission: "mes:schedule:list",
      path: "/mes/scheduling",
    },
    { label: "工序检验", permission: "mes:quality:list", path: "/mes/quality" },
    {
      label: "出货单",
      permission: "mes:shipment:list",
      path: "/mes/shipments",
    },
  ].filter((item) => hasPerms(item.permission)),
);
function quantity(value: string) {
  return value.includes(".")
    ? value.replace(/0+$/, "").replace(/\.$/, "")
    : value;
}
function progress(row: DeliveryRow) {
  return row.operation_count
    ? Math.round((row.completed_operation_count / row.operation_count) * 100)
    : 0;
}
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getDeliveryCockpit({
      ...filters,
      focus: focus.value,
      page: page.value,
      page_size: size.value,
      due_from: dueDates.value?.[0],
      due_to: dueDates.value?.[1],
    });
    if (current === request) data.value = result.data;
  } catch (cause) {
    if (current === request) {
      data.value = undefined;
      error.value = getHttpErrorMessage(cause, "交付驾驶舱加载失败");
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  return load();
}
function selectFocus(value: CockpitFocus) {
  focus.value = value;
  return search();
}
function reset() {
  Object.assign(filters, { keyword: "", customer: "", soon_days: 7 });
  dueDates.value = [];
  focus.value = "outstanding";
  return search();
}
function inspect(row: DeliveryRow) {
  orderId.value = row.id;
  detailVisible.value = true;
}
function selectDay(day: string) {
  dueDates.value = [day, day];
  focus.value = "outstanding";
  return search();
}
onMounted(load);
onBeforeUnmount(() => {
  ++request;
});
</script>
<template>
  <div class="cockpit-page">
    <div class="page-heading">
      <div>
        <h2>交付驾驶舱</h2>
        <p>从交期、生产进度和已确认出货识别需要跟进的工单。</p>
      </div>
      <div class="heading-actions">
        <el-button
          v-for="item in shortcuts"
          :key="item.path"
          @click="router.push(item.path)"
          >{{ item.label }}</el-button
        ><el-button type="primary" :loading="loading" @click="load"
          >刷新数据</el-button
        >
      </div>
    </div>
    <el-card shadow="never" class="filter-panel">
      <el-form inline @submit.prevent="search">
        <el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            placeholder="工单 / 项目 / 货品"
            clearable
            maxlength="128"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="客户"
          ><el-input
            v-model="filters.customer"
            placeholder="客户编号 / 名称"
            clearable
            maxlength="128"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="交期"
          ><el-date-picker
            v-model="dueDates"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 250px"
        /></el-form-item>
        <el-form-item label="近期窗口"
          ><el-select
            v-model="filters.soon_days"
            style="width: 100px"
            @change="search"
            ><el-option
              v-for="day in [3, 7, 14, 30]"
              :key="day"
              :value="day"
              :label="day + ' 天'" /></el-select
        ></el-form-item>
        <el-form-item
          ><el-button type="primary" :disabled="loading" @click="search"
            >查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        >
      </el-form>
      <small
        >统计范围为工作台与工单查询授权范围的交集；按工单计数，同一工单可能同时属于多个关注项。</small
      >
    </el-card>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="error"
      ><template #default
        ><el-button link type="primary" @click="load"
          >重新加载</el-button
        ></template
      ></el-alert
    >
    <div v-loading="loading" class="metric-grid">
      <button
        v-for="item in metrics"
        :key="item.key"
        class="metric"
        :class="[item.tone, { selected: focus === item.key }]"
        :disabled="!data || loading"
        :aria-pressed="focus === item.key"
        @click="selectFocus(item.key)"
      >
        <span
          >{{ item.label
          }}{{
            item.key === "due_soon"
              ? " · " + (data?.soon_days || filters.soon_days) + " 天"
              : ""
          }}</span
        ><strong>{{ data ? data.summary[item.key] : "—" }}</strong
        ><small>{{ item.note }}</small>
      </button>
    </div>
    <el-card v-if="data" shadow="never" class="due-panel">
      <div class="section-heading">
        <strong>近期交期分布</strong
        ><small>各日仍待交付的工单数；今天包含已逾期工单</small>
      </div>
      <div class="due-days">
        <button
          v-for="day in data.due_buckets"
          :key="day.day"
          :disabled="loading"
          @click="selectDay(day.day)"
        >
          <span>{{ day.day.slice(5) }}</span
          ><strong>{{ day.order_count }}</strong>
        </button>
      </div>
    </el-card>
    <el-card shadow="never">
      <div class="section-heading">
        <div>
          <strong>{{ selectedTitle }}</strong
          ><span class="muted"> · {{ data?.total ?? "—" }} 张工单</span>
        </div>
        <div class="focus-actions">
          <el-button
            v-for="item in focusOptions"
            :key="item.key"
            :type="focus === item.key ? 'primary' : 'default'"
            :disabled="loading"
            size="small"
            @click="selectFocus(item.key)"
            >{{ item.label }}
            <span v-if="data"
              >({{
                item.key === "all"
                  ? data.summary.total
                  : data.summary[item.key]
              }})</span
            ></el-button
          >
        </div>
      </div>
      <el-table
        v-loading="loading"
        :data="data?.items || []"
        row-key="id"
        max-height="630"
        empty-text="当前筛选范围没有工单"
      >
        <el-table-column label="工单 / 项目 / 客户" min-width="230" fixed="left"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="inspect(row as DeliveryRow)"
              >{{ row.work_order_no }}</el-button
            >
            <div>
              {{ row.project_name || row.production_order_no || "独立工单" }}
            </div>
            <small
              >{{ row.customer_no || "—" }} {{ row.customer_name }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="产品 / 数量" min-width="210"
          ><template #default="{ row }"
            ><div>{{ row.product_item_name }}</div>
            <small>{{ row.product_item_no }}</small>
            <div>
              计划 {{ quantity(row.planned_quantity) }} {{ row.unit_code }}
            </div></template
          ></el-table-column
        >
        <el-table-column label="交期 / 交付状态" min-width="165"
          ><template #default="{ row }"
            ><div>{{ formatMesDate(row.due_at) }}</div>
            <el-tag
              :type="deliveryLabels[(row as DeliveryRow).delivery_status].type"
              >{{
                deliveryLabels[(row as DeliveryRow).delivery_status].label
              }}</el-tag
            ><small class="status">{{
              mesWorkOrderStatusLabel(row)
            }}</small></template
          ></el-table-column
        >
        <el-table-column label="工序进度 / 当前工序" min-width="210"
          ><template #default="{ row }"
            ><el-progress
              :percentage="progress(row as DeliveryRow)"
              :stroke-width="6"
            /><small
              >{{ row.completed_operation_count }} /
              {{ row.operation_count }} 道工序已完成</small
            >
            <div>
              {{
                row.current_operation_name ||
                (row.operation_count
                  ? row.completed_operation_count === row.operation_count
                    ? "全部工序已完成"
                    : "工序已取消，请核对"
                  : "未配置工序")
              }}
            </div>
            <el-tag
              v-if="row.current_operation_status"
              size="small"
              :type="mesStatusType(row.current_operation_status)"
              >{{
                row.current_operation_status === "draft"
                  ? "待下单"
                  : mesStatusLabel(row.current_operation_status)
              }}</el-tag
            ><small class="status">{{
              row.current_workstation
            }}</small></template
          ></el-table-column
        >
        <el-table-column label="确认出货 / 未交付" min-width="165"
          ><template #default="{ row }"
            ><div>
              已出 {{ quantity(row.shipped_quantity) }} {{ row.unit_code }}
            </div>
            <strong
              >待交 {{ quantity(row.outstanding_quantity) }}
              {{ row.unit_code }}</strong
            >
            <div>
              <small>末道放行 {{ quantity(row.released_good_quantity) }}</small>
            </div></template
          ></el-table-column
        >
        <el-table-column label="需要跟进" min-width="230"
          ><template #default="{ row }"
            ><el-button
              v-if="row.open_exception_count && hasPerms('mes:exception:list')"
              link
              type="danger"
              @click="
                router.push({
                  path: '/mes/exceptions',
                  query: { work_order_id: row.id },
                })
              "
              >未关闭异常 {{ row.open_exception_count }} 项 · 超时
              {{ row.overdue_exception_count }} 项</el-button
            >
            <div v-for="flag in row.risk_flags" :key="flag" class="risk-line">
              {{ riskLabels[flag] || flag }}
            </div>
            <small v-if="!row.risk_flags.length">{{
              row.delivery_status === "delivered"
                ? "计划数量已全部出货"
                : "暂无已识别阻塞"
            }}</small
            ><small v-if="row.latest_planned_end_at"
              >计划结束 {{ formatMesDate(row.latest_planned_end_at) }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="操作" fixed="right" width="95"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="inspect(row as DeliveryRow)"
              >查看工单</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <ListPagination
        v-if="data"
        v-model:current-page="page"
        v-model:page-size="size"
        :disabled="loading"
        :total="data.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="load"
        @size-change="search"
      />
      <p class="footnote">
        末道放行量不等于可出货库存；出货还需校验仓库批次、预留及审批。此处按已确认出货数量判断交付，不包含运输签收，也不预测承诺交期。
      </p>
      <small v-if="data"
        >更新时间：{{ formatMesDate(data.generated_at) }}</small
      >
    </el-card>
    <WorkOrderDetail v-model="detailVisible" :work-order-id="orderId" />
  </div>
</template>
<style scoped>
.cockpit-page {
  padding: 20px;
}

.page-heading,
.section-heading,
.heading-actions,
.focus-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.page-heading {
  margin-bottom: 18px;
}

h2 {
  margin: 0 0 8px;
  font-size: 25px;
}

.page-heading p {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.heading-actions,
.focus-actions {
  gap: 6px;
  justify-content: flex-start;
}

.heading-actions .el-button,
.focus-actions .el-button {
  margin-left: 0;
}

.filter-panel,
.due-panel,
.error {
  margin-bottom: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.metric strong {
  font-size: 30px;
  line-height: 1.15;
}

.metric.danger strong {
  color: var(--el-color-danger);
}

.metric.warning strong {
  color: var(--el-color-warning);
}

.metric.selected {
  border-color: var(--el-color-primary);
  box-shadow: inset 0 3px var(--el-color-primary);
}

.metric:disabled {
  cursor: default;
}

.metric:hover:not(:disabled) {
  border-color: var(--el-color-primary);
}

small,
.muted,
.footnote {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.section-heading {
  margin-bottom: 16px;
}

.due-days {
  display: flex;
  gap: 8px;
  padding-bottom: 4px;
  overflow-x: auto;
}

.due-days button {
  display: flex;
  flex: 1 0 62px;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 10px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
}

.due-days strong {
  font-size: 20px;
}

.status {
  margin-left: 6px;
}

.risk-line {
  font-size: 12px;
  line-height: 1.8;
  color: var(--el-color-warning-dark-2);
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

.footnote {
  margin-top: 18px;
}

@media (width <= 1300px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (width <= 700px) {
  .cockpit-page {
    padding: 12px;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric {
    padding: 12px;
  }

  .pagination {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
