<template>
  <div class="sys-module sys-page inv-order-page list-page">
    <section class="list-section">
      <ReListHeading data-list-key="OrderListPage-0">
        <template #title>{{ title }}</template>
      </ReListHeading>
      <section class="list-query-panel">
        <div class="tab-toolbar order-toolbar list-filters">
          <el-form :model="filters" inline class="tab-filter" @submit.prevent>
            <el-form-item>
              <el-input
                v-model="filters.keyword"
                clearable
                placeholder="请输入单号 / 往来方 / 备注"
                class="filter-keyword"
                @keyup.enter="search"
              />
            </el-form-item>
            <el-form-item>
              <el-select
                v-model="filters.item_id"
                filterable
                remote
                clearable
                :remote-method="searchItems"
                placeholder="请选择物料"
                class="filter-item"
              >
                <el-option
                  v-for="o in itemOptions"
                  :key="o.id"
                  :label="`${o.item_name}（${o.item_no}）`"
                  :value="o.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-select
                v-model="filters.org_id"
                clearable
                filterable
                placeholder="请选择所属组织"
                class="filter-org"
              >
                <el-option
                  v-for="o in orgOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-select
                v-model="filters.order_type_id"
                clearable
                placeholder="请选择单据类型"
                class="filter-type"
              >
                <el-option
                  v-for="t in types"
                  :key="t.id"
                  :label="t.type_name"
                  :value="t.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-select
                v-model="filters.status_code"
                clearable
                placeholder="请选择状态"
                class="filter-status"
              >
                <el-option
                  v-for="(lbl, key) in STOCK_ORDER_STATUS_LABELS"
                  :key="key"
                  :label="lbl"
                  :value="key"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-date-picker
                v-model="dateRange"
                type="daterange"
                range-separator="-"
                :start-placeholder="`${text.dateLabel}开始`"
                :end-placeholder="`${text.dateLabel}结束`"
                value-format="YYYY-MM-DD"
                clearable
                class="filter-date"
              />
            </el-form-item>
            <el-form-item v-if="form === 'lend'">
              <el-select
                v-model="filters.has_unreturned"
                clearable
                placeholder="请选择归还情况"
                class="filter-return"
              >
                <el-option label="未归还完" :value="true" />
                <el-option label="已全部归还" :value="false" />
              </el-select>
            </el-form-item>
            <el-form-item class="toolbar-actions">
              <el-button data-list-query="search" type="primary" @click="search"
                >搜索</el-button
              >
              <el-button data-list-query="reset" @click="reset">重置</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div>
          <ReListTable
            v-loading="loading"
            :list-heading="false"
            list-key="OrderListPage-0"
            :list-refresh="load"
            :data="rows"
            row-key="id"
            class="data-table"
          >
            <el-table-column
              prop="order_no"
              label="单号"
              min-width="158"
              show-overflow-tooltip
            />
            <el-table-column prop="order_type_name" label="类型" width="92" />
            <el-table-column
              prop="org_name"
              label="组织"
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="showFrom"
              prop="from_warehouse"
              label="来源仓库"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                row.from_warehouse?.label ?? "—"
              }}</template>
            </el-table-column>
            <el-table-column
              v-if="showTo"
              prop="to_warehouse"
              label="目标仓库"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                row.to_warehouse?.label ?? "—"
              }}</template>
            </el-table-column>
            <el-table-column
              v-if="form !== 'transfer'"
              prop="counterparty_name_snapshot"
              :label="text.counterparty"
              min-width="104"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                dash(row.counterparty_name_snapshot)
              }}</template>
            </el-table-column>
            <el-table-column
              v-if="form === 'outbound'"
              prop="department_name"
              label="领用部门"
              min-width="100"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                dash(row.department_name)
              }}</template>
            </el-table-column>
            <el-table-column
              v-if="form === 'damage'"
              prop="handling_method_code"
              label="处理方式"
              width="100"
            >
              <template #default="{ row }">{{
                label("inv_handling_method", row.handling_method_code) || "—"
              }}</template>
            </el-table-column>
            <el-table-column
              v-if="form === 'lend'"
              prop="expected_return_date"
              label="预计归还"
              width="110"
            >
              <template #default="{ row }">{{
                dash(row.expected_return_date)
              }}</template>
            </el-table-column>
            <el-table-column
              prop="item_summaries"
              label="物料明细"
              min-width="260"
            >
              <template #default="{ row }">
                <OrderItemSummary
                  :items="row.item_summaries ?? []"
                  :unit-label="unitLabel"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="form === 'inbound'"
              prop="total_amount"
              label="金额"
              width="100"
              align="right"
            >
              <template #default="{ row }">{{
                formatMoney(row.total_amount)
              }}</template>
            </el-table-column>
            <el-table-column
              prop="business_date"
              :label="text.dateLabel"
              width="104"
            />
            <el-table-column
              prop="status_code"
              label="状态"
              width="84"
              align="center"
            >
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status_code)" size="small">{{
                  statusLabel(row.status_code)
                }}</el-tag>
                <div v-if="row.reversal_of_order_id" class="muted">冲销单</div>
              </template>
            </el-table-column>
            <el-table-column
              label="操作"
              width="130"
              fixed="right"
              align="center"
            >
              <template #default="{ row }">
                <div class="operation-cell">
                  <el-button
                    data-action="view"
                    link
                    type="primary"
                    class="operation-link"
                    @click="openDetail(row as StockOrder)"
                    >详情</el-button
                  >
                  <el-button
                    v-if="rowActions(row as StockOrder).length === 1"
                    link
                    :type="rowActions(row as StockOrder)[0].tone"
                    :data-action="
                      ROW_ACTION_COLOR[rowActions(row as StockOrder)[0].command]
                    "
                    @click="
                      handleRowAction(
                        row as StockOrder,
                        rowActions(row as StockOrder)[0].command,
                      )
                    "
                  >
                    {{ rowActions(row as StockOrder)[0].label }}
                  </el-button>
                  <el-dropdown
                    v-else-if="rowActions(row as StockOrder).length > 1"
                    trigger="click"
                    @command="
                      (command) =>
                        handleRowAction(row as StockOrder, command as UiAction)
                    "
                  >
                    <el-button
                      data-action="neutral"
                      link
                      type="primary"
                      class="operation-link"
                    >
                      更多<el-icon class="more-icon"><ArrowDown /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item
                          v-for="item in rowActions(row as StockOrder)"
                          :key="item.command"
                          :command="item.command"
                          :data-action="ROW_ACTION_COLOR[item.command]"
                          :class="`order-action-${item.tone}`"
                        >
                          {{ item.label }}
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
            </el-table-column>

            <template #list-pagination
              ><div class="table-footer">
                <ReListPagination
                  v-model:current-page="page"
                  v-model:page-size="pageSize"
                  :total="total"
                  @current-change="load"
                  @size-change="search"
                /></div
            ></template>
            <template #list-actions>
              <ActionButton
                v-for="type in createTypeOptions"
                :key="type.id"
                intent="create"
                :data-list-action="`create-${type.type_no}`"
                @click="goCreate(type.type_no)"
                >{{ type.type_name }}</ActionButton
              >
              <el-button
                v-if="canForm(form, 'create')"
                data-list-action="create"
                type="primary"
                round
                :icon="Plus"
                @click="goCreate()"
              >
                新建{{ text.noun }}
              </el-button>
              <el-button
                v-if="canForm(form, 'list')"
                data-list-action="export"
                round
                :icon="Download"
                :loading="exporting"
                @click="exportCsv"
              >
                导出{{ text.noun }}
              </el-button></template
            ></ReListTable
          >
        </div>
      </section>
    </section>

    <el-dialog
      v-model="formVisible"
      :title="editingId ? `编辑${text.noun}` : `新建${text.noun}`"
      width="1200px"
      destroy-on-close
      align-center
    >
      <OrderForm
        :form="form"
        :warehouse-scope-key="warehouseScopeKey"
        :initial-type-no="creatingTypeNo"
        :order-id="editingId"
        @saved="onSaved"
        @cancel="formVisible = false"
      />
    </el-dialog>

    <OrderDetailDialog v-model="detailVisible" :order-id="detailId" />

    <el-dialog
      v-model="returnVisible"
      title="办理归还"
      width="760px"
      destroy-on-close
      align-center
    >
      <div v-loading="returnLoading">
        <ReListTable
          list-key="OrderListPage-1"
          :list-controls="false"
          :data="returnLines"
          border
          size="small"
        >
          <el-table-column prop="item_name" label="物料" min-width="140" />
          <el-table-column
            prop="quantity"
            label="借出"
            width="80"
            align="right"
          >
            <template #default="{ row }">{{
              formatQuantity(row.quantity)
            }}</template>
          </el-table-column>
          <el-table-column
            prop="returned_quantity"
            label="已归还"
            width="80"
            align="right"
          >
            <template #default="{ row }">{{
              formatQuantity(row.returned_quantity)
            }}</template>
          </el-table-column>
          <el-table-column label="资产关联" width="130"><template #default="{ row }">
            <StockAssetTrackingEditor v-model="row.return_tracking" :item-id="row.item_id" :warehouse-id="row.from_warehouse_id || returnWarehouseId" :org-id="row.org_id" />
          </template></el-table-column>
          <el-table-column label="本次归还" width="150">
            <template #default="{ row }">
              <el-input-number
                v-model="row.return_quantity"
                :min="0"
                :max="toNumber(row.unreturned_quantity)"
                :precision="3"
                :controls="false"
                style="width: 100%"
              />
            </template>
          </el-table-column>
        </ReListTable>
        <el-input
          v-model="returnRemark"
          placeholder="备注（选填）"
          class="mt-2"
        />
      </div>
      <template #footer>
        <el-button data-action="neutral" @click="returnVisible = false"
          >取消</el-button
        >
        <el-button
          data-action="success"
          type="primary"
          :loading="returnSaving"
          @click="submitReturn"
          >确认归还</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import ActionButton from "@/components/ActionButton/index.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowDown, Download, Plus } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import { downloadCsvText } from "@plugins/inv/web/src/views/inventory/shared/utils/download";
import {
  STOCK_ORDER_STATUS_LABELS,
  approveStockOrder,
  confirmStockOrder,
  deleteStockOrder,
  formatMoney,
  formatQuantity,
  getStockOrder,
  listItemOptions,
  listStockOrderTypeOptions,
  listStockOrders,
  previewStockOrderWarnings,
  rejectStockOrder,
  returnLendOrder,
  reverseStockOrder,
  submitStockOrder,
  toNumber,
  voidStockOrder,
  type ItemOption,
  type StockOrder,
  type StockOrderForm,
  type StockOrderLine,
  type StockOrderListParams,
  type StockOrderType,
} from "@plugins/inv/web/src/api/inventoryManagement";
import OrderDetailDialog from "./OrderDetailDialog.vue";
import OrderForm from "./OrderForm.vue";
import StockAssetTrackingEditor from "../../asset-management/StockAssetTrackingEditor.vue";
import OrderItemSummary from "./OrderItemSummary.vue";
import {
  FORM_TEXT,
  canForm,
  dash,
  statusLabel,
  statusTagType,
  useInventoryMeta,
  useOrgOptions,
} from "./common";

const props = defineProps<{
  form: StockOrderForm;
  title: string;
  description?: string;
  /** 新建 / 编辑使用独立页面（入库、出库）；不传时用弹窗 */
  formRoute?: string;
  warehouseScopeKey?: string;
  /** 上层业务提供快捷收发类型；未传时保持 inv 默认表单。 */
  createTypeNos?: string[];
}>();

const router = useRouter();
const route = useRoute();
const warehouseScopeKey = computed(
  () =>
    props.warehouseScopeKey ||
    (typeof route.meta.warehouse_scope_key === "string"
      ? route.meta.warehouse_scope_key
      : undefined),
);
const creatingTypeNo = ref<string>();
const createTypeOptions = computed(() =>
  canForm(props.form, "create")
    ? types.value.filter(
        (t) =>
          props.createTypeNos?.includes(t.type_no) &&
          t.is_active &&
          !t.is_source_managed,
      )
    : [],
);
const text = computed(() => FORM_TEXT[props.form]);
const showFrom = computed(() =>
  ["outbound", "transfer", "lend", "damage"].includes(props.form),
);
const showTo = computed(() => ["inbound", "transfer"].includes(props.form));
const { orgOptions, loadOrgOptions } = useOrgOptions();
const { loadMeta, label, unitLabel } = useInventoryMeta();

const loading = ref(false);
const exporting = ref(false);
const rows = ref<StockOrder[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const types = ref<StockOrderType[]>([]);
const itemOptions = ref<ItemOption[]>([]);
const dateRange = ref<[string, string] | null>(null);
const filters = reactive({
  keyword: "",
  item_id: "",
  org_id: "",
  order_type_id: "",
  status_code: "",
  has_unreturned: undefined as boolean | undefined,
});

const formVisible = ref(false);
const editingId = ref<string | null>(null);
const detailVisible = ref(false);
const detailId = ref<string | null>(null);

function params(): StockOrderListParams {
  return {
    warehouse_scope_key: warehouseScopeKey.value,
    form: props.form,
    page: page.value,
    page_size: pageSize.value,
    keyword: filters.keyword || undefined,
    item_id: filters.item_id || undefined,
    org_id: filters.org_id || undefined,
    order_type_id: filters.order_type_id || undefined,
    status_code: filters.status_code || undefined,
    has_unreturned: filters.has_unreturned,
    business_date_start: dateRange.value?.[0],
    business_date_end: dateRange.value?.[1],
  };
}

async function load() {
  loading.value = true;
  try {
    const res = await listStockOrders(params());
    if (res.code !== 0) throw new Error(res.message);
    rows.value = res.data.items;
    total.value = res.data.total;
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载列表失败"));
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

function reset() {
  Object.assign(filters, {
    keyword: "",
    item_id: "",
    org_id: "",
    order_type_id: "",
    status_code: "",
    has_unreturned: undefined,
  });
  dateRange.value = null;
  search();
}

async function searchItems(keyword: string) {
  const res = await listItemOptions({
    keyword: keyword || undefined,
    limit: 50,
  });
  if (res.code === 0) itemOptions.value = res.data.items;
}

function goCreate(typeNo?: string) {
  creatingTypeNo.value = typeNo;
  if (props.formRoute && !warehouseScopeKey.value) {
    router.push({ path: props.formRoute });
    return;
  }
  editingId.value = null;
  formVisible.value = true;
}

function goEdit(row: StockOrder) {
  if (props.formRoute && !warehouseScopeKey.value) {
    router.push({ path: props.formRoute, query: { id: row.id } });
    return;
  }
  editingId.value = row.id;
  formVisible.value = true;
}

function onSaved() {
  formVisible.value = false;
  load();
}

function openDetail(row: StockOrder) {
  detailId.value = row.id;
  detailVisible.value = true;
}

type Action =
  "submit" | "approve" | "reject" | "confirm" | "void" | "delete" | "reverse";
type UiAction = Action | "edit" | "return";
const ROW_ACTION_COLOR = {
  edit: "edit",
  submit: "primary",
  confirm: "success",
  approve: "success",
  reject: "warning",
  delete: "danger",
  void: "danger",
  reverse: "danger",
  return: "success",
} as const;

type ActionTone = "primary" | "danger";
type RowAction = {
  command: UiAction;
  label: string;
  tone: ActionTone;
};

const ACTION_TEXT: Record<Action, string> = {
  submit: "提交审批",
  approve: "审批通过",
  reject: "驳回",
  confirm: "确认记账",
  void: "作废",
  delete: "删除",
  reverse: "冲销",
};

function rowActions(row: StockOrder): RowAction[] {
  const actions: RowAction[] = [];

  if (row.status_code === "draft") {
    if (canForm(props.form, "update")) {
      actions.push({ command: "edit", label: "编辑", tone: "primary" });
    }
    if (row.order_type?.is_approval_required && canForm(props.form, "create")) {
      actions.push({ command: "submit", label: "提交", tone: "primary" });
    }
    if (
      !row.order_type?.is_approval_required &&
      canForm(props.form, "confirm")
    ) {
      actions.push({ command: "confirm", label: "确认", tone: "primary" });
    }
    if (canForm(props.form, "delete")) {
      actions.push({ command: "delete", label: "删除", tone: "danger" });
    }
  } else if (
    row.status_code === "submitted" &&
    canForm(props.form, "approve")
  ) {
    actions.push(
      { command: "approve", label: "通过", tone: "primary" },
      { command: "reject", label: "驳回", tone: "danger" },
    );
  } else if (row.status_code === "approved" && canForm(props.form, "confirm")) {
    actions.push({ command: "confirm", label: "确认", tone: "primary" });
  }

  if (
    ["draft", "submitted", "approved"].includes(row.status_code) &&
    canForm(props.form, "update")
  ) {
    actions.push({ command: "void", label: "作废", tone: "danger" });
  }

  if (row.status_code === "confirmed" && !row.reversal_of_order_id) {
    if (props.form === "lend" && canForm(props.form, "confirm")) {
      actions.push({ command: "return", label: "归还", tone: "primary" });
    }
    if (canForm(props.form, "confirm")) {
      actions.push({ command: "reverse", label: "冲销", tone: "danger" });
    }
  }

  return actions;
}

function handleRowAction(row: StockOrder, command: UiAction) {
  if (command === "edit") {
    goEdit(row);
    return;
  }
  if (command === "return") {
    openReturn(row);
    return;
  }
  act(row, command);
}

async function act(row: StockOrder, action: Action) {
  let reason: string | undefined;
  try {
    if (action === "void" || action === "reject" || action === "reverse") {
      const { value } = await ElMessageBox.prompt(
        `请输入${ACTION_TEXT[action]}原因`,
        `${ACTION_TEXT[action]} ${row.order_no}`,
        {
          confirmButtonClass:
            action === "reject" ? "app-button-warning" : "app-button-danger",
          inputPlaceholder: "选填",
          confirmButtonText: "确定",
          cancelButtonText: "取消",
        },
      );
      reason = value || undefined;
    } else {
      let message = `确定${ACTION_TEXT[action]}「${row.order_no}」吗？`;
      if (action === "confirm") {
        message += "确认后将生成库存流水并更新库存，不能再修改。";
        if (props.form === "inbound") {
          const preview = await previewStockOrderWarnings(row.id);
          const warnings = preview.code === 0 ? preview.data.warnings : [];
          if (warnings.length) {
            message += `\n以下物料确认后将达到库存上限：${warnings.map((w) => w.item_name).join("、")}`;
          }
        }
      }
      await ElMessageBox.confirm(message, ACTION_TEXT[action], {
        confirmButtonClass:
          action === "delete" ? "app-button-danger" : "app-button-success",
        type: action === "delete" ? "warning" : "info",
      });
    }
  } catch {
    return;
  }
  try {
    const handlers: Record<
      Action,
      () => Promise<{ code: number; message: string }>
    > = {
      submit: () => submitStockOrder(row.id),
      approve: () => approveStockOrder(row.id),
      reject: () => rejectStockOrder(row.id, reason),
      confirm: () => confirmStockOrder(row.id),
      void: () => voidStockOrder(row.id, reason),
      delete: () => deleteStockOrder(row.id),
      reverse: () => reverseStockOrder(row.id, reason),
    };
    const res = await handlers[action]();
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success(`${ACTION_TEXT[action]}成功`);
    load();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, `${ACTION_TEXT[action]}失败`));
  }
}

// ───────── 借出归还 ─────────
type ReturnLine = StockOrderLine & { return_quantity: number; return_tracking?: import("../../../api/invAssetManagement").StockAssetTracking };
const returnVisible = ref(false);
const returnLoading = ref(false);
const returnSaving = ref(false);
const returnOrderId = ref("");
const returnWarehouseId = ref<string | null>(null);
const returnLines = ref<ReturnLine[]>([]);
const returnRemark = ref("");

async function openReturn(row: StockOrder) {
  returnOrderId.value = row.id;
  returnRemark.value = "";
  returnLines.value = [];
  returnVisible.value = true;
  returnLoading.value = true;
  try {
    const res = await getStockOrder(row.id);
    if (res.code !== 0) throw new Error(res.message);
    returnWarehouseId.value = res.data.from_warehouse_id || res.data.to_warehouse_id || null;
    returnLines.value = (res.data.lines ?? []).map(l => ({
      ...l,
      return_quantity: toNumber(l.unreturned_quantity),
    }));
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载借出单失败"));
  } finally {
    returnLoading.value = false;
  }
}

async function submitReturn() {
  const lines = returnLines.value
    .filter(l => l.return_quantity > 0)
    .map(l => ({ source_line_id: l.id, quantity: l.return_quantity, ...(l.return_tracking ? { tracking: { asset: l.return_tracking } } : {}) }));
  if (!lines.length) return ElMessage.warning("请填写归还数量");
  returnSaving.value = true;
  try {
    const res = await returnLendOrder(returnOrderId.value, {
      lines,
      remark: returnRemark.value || null,
    });
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success(`已归还，归还单 ${res.data.order_no}`);
    returnVisible.value = false;
    load();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "归还失败"));
  } finally {
    returnSaving.value = false;
  }
}

// ───────── 导出 ─────────
function csvCell(value: unknown) {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function exportCsv() {
  exporting.value = true;
  try {
    const all: StockOrder[] = [];
    for (let p = 1; p <= 20; p += 1) {
      const res = await listStockOrders({
        ...params(),
        page: p,
        page_size: 100,
      });
      if (res.code !== 0) throw new Error(res.message);
      all.push(...res.data.items);
      if (all.length >= res.data.total || !res.data.items.length) break;
    }
    const header = [
      "单号",
      "类型",
      "组织",
      "来源仓库",
      "目标仓库",
      "往来方",
      "领用部门",
      "物料及数量（含单位）",
      "金额",
      "业务日期",
      "状态",
      "确认时间",
      "备注",
    ];
    const lines = all.map((r) =>
      [
        r.order_no,
        r.order_type_name,
        r.org_name,
        r.from_warehouse?.label,
        r.to_warehouse?.label,
        r.counterparty_name_snapshot,
        r.department_name,
        (r.item_summaries ?? [])
          .map(
            (item) =>
              `${item.item_name} ${formatQuantity(item.quantity)} ${unitLabel(item.unit_code) || "单位缺失"}`,
          )
          .join("\n"),
        r.total_amount,
        r.business_date,
        statusLabel(r.status_code),
        r.confirmed_at,
        r.remark,
      ]
        .map(csvCell)
        .join(","),
    );
    downloadCsvText(
      `${props.title}.csv`,
      [header.join(","), ...lines].join("\n"),
    );
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "导出失败"));
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadMeta(), loadOrgOptions(), searchItems("")]);
  const res = await listStockOrderTypeOptions({
    warehouse_scope_key: warehouseScopeKey.value,
    form: props.form,
    include_inactive: true,
  });
  types.value = res.code === 0 ? res.data.items : [];
  load();
});

defineExpose({ reload: load });
</script>

<style scoped lang="scss">
.scene-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.scene-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.inv-order-page {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.order-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.tab-filter {
  display: flex;
  flex: 1 1 100%;
  flex-wrap: wrap;
  min-width: 0;
}

.tab-filter :deep(.el-form-item) {
  margin-right: 8px;
  margin-bottom: 8px;
}

.filter-keyword {
  width: 210px;
}

.filter-item {
  width: 180px;
}

.filter-org {
  width: 160px;
}

.filter-type,
.filter-return {
  width: 140px;
}

.filter-status {
  width: 110px;
}

.filter-date {
  width: 240px;
}

.toolbar-actions :deep(.el-form-item__content) {
  flex-wrap: wrap;
}

.data-table {
  width: 100%;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 0;
}

.operation-cell {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.operation-link.el-button {
  height: auto;
  padding: 0;
}

.more-icon {
  margin-left: 2px;
  font-size: 12px;
}

:global(.order-action-danger) {
  color: var(--el-color-danger);
}

.muted {
  font-size: 12px;
  color: #94a3b8;
}

.mt-2 {
  margin-top: 8px;
}

@media (width <= 560px) {
  .tab-filter :deep(.el-form-item),
  .filter-keyword,
  .filter-item,
  .filter-org,
  .filter-type,
  .filter-status,
  .filter-date,
  .filter-return {
    width: 100%;
    margin-right: 0;
  }
}
</style>

<style lang="scss">
@use "@/views/system/system-styles.scss" as *;
</style>
