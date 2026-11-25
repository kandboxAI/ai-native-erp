<template>
  <div v-loading="loading" class="order-form" :class="{ 'inbound-form': form === 'inbound' }">
    <el-form
      ref="formRef"
      :model="header"
      :label-width="form === 'inbound' ? undefined : '108px'"
      :label-position="form === 'inbound' ? 'top' : 'right'"
      class="order-form-header"
    >
      <div v-if="form === 'inbound'" class="section-title">基本信息</div>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :md="form === 'inbound' ? 6 : 8">
          <el-form-item label="单据类型" required>
            <el-select
              v-model="header.order_type_id"
              placeholder="请选择"
              style="width: 100%"
              :disabled="isEdit"
            >
              <el-option
                v-for="t in types"
                :key="t.id"
              :label="t.type_name"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :md="form === 'inbound' ? 6 : 8">
          <el-form-item :label="text.dateLabel" required>
            <el-date-picker
              v-model="header.business_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col v-if="needFrom" :xs="24" :sm="12" :md="8">
          <el-form-item
            :label="direction === 'status' ? '仓库' : '来源仓库'"
            required
          >
            <el-select
              v-model="header.from_warehouse_id"
              filterable
              placeholder="组织 / 仓库"
              style="width: 100%"
              @change="onFromWarehouseChange"
            >
              <el-option
                v-for="l in warehouses"
                :key="l.id"
                :label="l.label"
                :value="l.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="needTo" :xs="24" :sm="12" :md="form === 'inbound' ? 6 : 8">
          <el-form-item
            :label="direction === 'adjust' ? '盘点仓库' : '目标仓库'"
            required
          >
            <el-select
              v-model="header.to_warehouse_id"
              filterable
              placeholder="组织 / 仓库"
              style="width: 100%"
              @change="onToWarehouseChange"
            >
              <el-option
                v-for="l in targetWarehouses"
                :key="l.id"
                :label="l.label"
                :value="l.id"
              />
            </el-select>
          </el-form-item>
        </el-col>

        <el-col v-if="form === 'inbound'" :xs="24" :sm="12" :md="6">
          <el-form-item
            label="供应商"
            :required="isRequired('counterparty_name_snapshot')"
          >
            <el-select
              v-model="header.supplier_id"
              filterable
              clearable
              placeholder="选择供应商"
              style="width: 100%"
            >
              <el-option
                v-for="s in suppliers"
                :key="s.id"
                :label="s.supplier_name"
                :value="s.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="form === 'outbound'" :xs="24" :sm="12" :md="8">
          <el-form-item
            label="领用部门"
            :required="isRequired('department_id')"
          >
            <el-select
              v-model="header.department_id"
              filterable
              clearable
              placeholder="选择部门"
              style="width: 100%"
            >
              <el-option
                v-for="d in personnel.departments"
                :key="d.id"
                :label="d.department_name"
                :value="d.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col
          v-if="form === 'outbound' || form === 'lend'"
          :xs="24"
          :sm="12"
          :md="8"
        >
          <el-form-item
            :label="text.counterparty"
            :required="isRequired('counterparty_name_snapshot')"
          >
            <el-select
              v-model="counterpartyValue"
              filterable
              allow-create
              clearable
              default-first-option
              placeholder="选择人员或输入姓名"
              style="width: 100%"
            >
              <el-option
                v-for="u in personnel.users"
                :key="u.user_id"
                :label="userLabel(u)"
                :value="u.user_id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="form === 'lend'" :xs="24" :sm="12" :md="8">
          <el-form-item
            label="预计归还"
            :required="isRequired('expected_return_date')"
          >
            <el-date-picker
              v-model="header.expected_return_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col v-if="form === 'damage'" :xs="24" :sm="12" :md="8">
          <el-form-item
            label="处理方式"
            :required="isRequired('handling_method_code')"
          >
            <el-select
              v-model="header.handling_method_code"
              clearable
              style="width: 100%"
            >
              <el-option
                v-for="o in meta.inv_handling_method || []"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col
          v-if="form === 'outbound' || form === 'lend' || isRequired('purpose')"
          :xs="24"
          :sm="12"
          :md="8"
        >
          <el-form-item label="用途" :required="isRequired('purpose')">
            <el-input v-model="header.purpose" maxlength="200" />
          </el-form-item>
        </el-col>
        <el-col
          v-if="form === 'damage' || isRequired('reason')"
          :xs="24"
          :md="16"
        >
          <el-form-item label="原因" :required="isRequired('reason')">
            <el-input v-model="header.reason" maxlength="500" />
          </el-form-item>
        </el-col>
        <el-col :xs="24">
          <el-form-item label="备注">
            <el-input
              v-model="header.remark"
              type="textarea"
              :rows="form === 'inbound' ? 1 : 2"
              :autosize="form === 'inbound' ? { minRows: 1, maxRows: 3 } : false"
              :placeholder="form === 'inbound' ? '补充本次入库的说明（选填）' : undefined"
              maxlength="500"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="lines-toolbar">
      <div>
        <span class="lines-title">{{ form === 'inbound' ? '入库明细' : '明细' }} <span class="line-count">{{ lines.length }} 行</span></span>
        <p v-if="form === 'inbound'" class="lines-description">展开每行的补充信息，可填写批次、日期和备注</p>
      </div>
      <div class="line-actions">
        <el-button data-list-action="create" :size="form === 'inbound' ? 'default' : 'small'" type="primary" plain @click="addLine"
          >添加明细</el-button
        >
      </div>
    </div>
    <ReListTable
      list-key="OrderForm-0"
      :list-controls="false"
      :list-refresh="loadOrder"
      :data="lines"
      border
      size="small"
      row-key="key"
      class="lines-table"
    >
      <el-table-column v-if="form === 'inbound'" type="expand" label="补充" width="56">
        <template #default="{ row }">
          <div class="line-details">
            <div class="line-details-title">{{ row.item_name || '本行物料' }} · 补充信息</div>
            <el-form :model="row" label-position="top" class="line-details-form">
              <el-row :gutter="16">
                <el-col :xs="24" :sm="8">
                  <el-form-item label="批次号"><el-input v-model="row.lot_no" maxlength="64" placeholder="选填" /></el-form-item>
                </el-col>
                <el-col :xs="24" :sm="8">
                  <el-form-item label="生产日期"><el-date-picker v-model="row.production_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" /></el-form-item>
                </el-col>
                <el-col :xs="24" :sm="8">
                  <el-form-item label="有效期至"><el-date-picker v-model="row.expiry_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" /></el-form-item>
                </el-col>
                <el-col :span="24">
                  <el-form-item label="明细备注"><el-input v-model="row.remark" maxlength="500" placeholder="补充该物料的说明（选填）" /></el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>
        </template>
      </el-table-column>
      <el-table-column type="index" label="#" :width="form === 'inbound' ? 44 : 48" />
      <el-table-column label="物料" :min-width="form === 'inbound' ? 320 : 240">
        <template #default="{ row }">
          <el-select
            v-model="row.item_id"
            filterable
            remote
            :remote-method="(q: string) => searchItems(q)"
            :loading="itemLoading"
            :disabled="
              !currentType ||
              (usesApplicableWarehouses && (!header.to_warehouse_id || availabilityLoading)) ||
              (needFrom && (!header.from_warehouse_id || availabilityLoading))
            "
            :placeholder="
              usesApplicableWarehouses && !header.to_warehouse_id
                ? '请先选择目标仓库'
                : needFrom && !header.from_warehouse_id
                ? '请先选择来源仓库'
                : '搜索物料名称 / 编号'
            "
            style="width: 100%"
            :popper-class="form === 'inbound' ? 'inventory-inbound-item-options' : undefined"
            @change="(id: string) => onItemChange(row as FormLine, id)"
          >
            <el-option
              v-for="o in itemChoices(row as FormLine)"
              :key="o.id"
              :label="form === 'inbound' ? o.item_name : `${o.item_name}${o.specification ? ' ' + o.specification : ''}（${o.item_no}）`"
              :value="o.id"
              :disabled="needFrom && (o.available_quantity == null || toNumber(o.available_quantity) <= 0)"
            >
              <template v-if="form === 'inbound'">
                <div class="item-option-name">{{ o.item_name }}</div>
                <div class="item-option-meta">{{ [o.specification, o.item_no].filter(Boolean).join(' · ') }}</div>
              </template>
              <template v-else>{{ `${o.item_name}${o.specification ? ' ' + o.specification : ''}（${o.item_no}）` }}</template>
            </el-option>
          </el-select>
          <template v-if="form === 'inbound' && row.item_id">
            <div class="material-meta">
              <span v-if="row.specification">{{ row.specification }}</span>
              <span class="material-code">{{ row.item_no }}</span>
            </div>
            <div v-if="row.is_asset_managed || row.asset_tracking?.selections?.length || canSelectExistingAsset" class="asset-registration">
              <template v-if="isPurchaseInbound && row.asset_tracking?.selections?.length">
                <div class="asset-error">采购入库应登记新资产，请清除原资产关联或改用其他入库办理退库。</div>
                <el-button link type="danger" @click="clearAssetSelection(row as FormLine)">清除错误关联</el-button>
              </template>
              <template v-if="row.is_asset_managed && !row.asset_tracking?.selections?.length">
                <div class="asset-registration-heading"><span class="asset-status">自动登记</span><span>逐件编号</span></div>
                <div class="responsibility-editor">
                  <span class="responsibility-label">责任部门</span>
                  <WarehouseDepartmentSelect :model-value="assetDepartment(row as FormLine)"
                    :org-id="orgOf(header.to_warehouse_id)" :permission-key="isEdit ? 'inventory_inbound:update' : 'inventory_inbound:create'"
                    @update:model-value="value => setAssetDepartment(row as FormLine, value)" />
                </div>
              </template>
              <StockAssetTrackingEditor v-if="canSelectExistingAsset" v-model="row.asset_tracking" :item-id="row.item_id"
                :warehouse-id="null" :selection-purpose="assetSelectionPurpose"
                :org-id="orgOf(header.to_warehouse_id)" />
            </div>
            <span v-else-if="row.is_asset_managed === false" class="material-kind">普通物料</span>
            <div v-if="row.lot_no || row.production_date || row.expiry_date || row.remark" class="line-extra-summary">
              <span v-if="row.lot_no">批次：{{ row.lot_no }}</span>
              <span v-if="row.production_date">生产：{{ row.production_date }}</span>
              <span v-if="row.expiry_date">有效期至：{{ row.expiry_date }}</span>
              <span v-if="row.remark">已填写备注</span>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column v-if="form !== 'inbound'" prop="unit_code" label="单位" width="70">
        <template #default="{ row }">{{ unitLabel(row.unit_code) }}</template>
      </el-table-column>
      <el-table-column v-if="form !== 'inbound'" label="资产关联" width="130">
        <template #default="{ row }">
          <StockAssetTrackingEditor v-if="canSelectExistingAsset" v-model="row.asset_tracking" :item-id="row.item_id"
            :warehouse-id="needFrom ? header.from_warehouse_id : null"
            :selection-purpose="assetSelectionPurpose"
            :org-id="orgOf(header.from_warehouse_id || header.to_warehouse_id)" />
        </template>
      </el-table-column>
      <el-table-column
        v-if="showAvailable"
        prop="available_quantity"
        label="可用"
        width="80"
        align="right"
      >
        <template #default="{ row }">{{
          row.available_quantity == null
            ? "—"
            : formatQuantity(row.available_quantity)
        }}</template>
      </el-table-column>
      <el-table-column
        v-if="direction === 'adjust'"
        label="实盘数量"
        width="130"
      >
        <template #default="{ row }">
          <el-input-number
            v-model="row.counted_quantity"
            :min="0"
            :precision="3"
            :controls="false"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column v-else label="数量" :width="form === 'inbound' ? 136 : 130">
        <template #default="{ row }">
          <div :class="{ 'quantity-editor': form === 'inbound' }">
          <el-input-number
            v-model="row.quantity"
            :min="0"
            :precision="3"
            :controls="false"
            style="width: 100%"
          />
          <span v-if="form === 'inbound'" class="quantity-unit">{{ row.unit_code ? unitLabel(row.unit_code) : '单位' }}</span>
          </div>
        </template>
      </el-table-column>
      <template v-if="direction === 'in'">
        <el-table-column label="单价" :width="form === 'inbound' ? 120 : 110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.unit_price"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="金额" :width="form === 'inbound' ? 116 : 100" align="right">
          <template #default="{ row }">{{
            formatMoney((row.quantity || 0) * (row.unit_price || 0))
          }}</template>
        </el-table-column>
        <template v-if="form !== 'inbound'">
        <el-table-column label="批次号" width="130">
          <template #default="{ row }"
            ><el-input v-model="row.lot_no" placeholder="选填"
          /></template>
        </el-table-column>
        <el-table-column label="生产日期" width="150">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.production_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </template>
        </el-table-column>
        <el-table-column label="有效期至" width="150">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.expiry_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </template>
        </el-table-column>
        </template>
      </template>
      <el-table-column
        v-else-if="direction !== 'adjust'"
        label="批次"
        width="170"
      >
        <template #default="{ row }">
          <el-select
            v-model="row.lot_id"
            :disabled="
              !row.item_id ||
              (needFrom && (!header.from_warehouse_id || availabilityLoading))
            "
            clearable
            placeholder="自动（先进先出）"
            style="width: 100%"
            @visible-change="(v: boolean) => v && loadLots(row as FormLine)"
          >
            <el-option
              v-for="lot in row.lots || []"
              :key="lot.id"
              :label="`${lot.lot_no}（可用 ${formatQuantity(lot.available_quantity)}${lot.expiry_date ? '，至 ' + lot.expiry_date : ''}）`"
              :value="lot.id"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column v-if="form !== 'inbound'" label="备注" min-width="120">
        <template #default="{ row }"
          ><el-input v-model="row.remark"
        /></template>
      </el-table-column>
      <el-table-column :label="form === 'inbound' ? '操作' : ''" :width="form === 'inbound' ? 80 : 60" fixed="right" align="center">
        <template #default="{ $index }">
          <el-button
            data-list-action="delete"
            link
            type="danger"
            @click="lines.splice($index, 1)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </ReListTable>

    <div class="form-footer">
      <div v-if="form === 'inbound'" class="order-summary">
        <span class="summary-label">合计金额</span>
        <strong>{{ formatMoney(totalAmount) }}</strong>
        <span class="summary-count">共 {{ lines.filter(line => line.item_id).length }} 项物料</span>
      </div>
      <span v-else-if="direction === 'in'" class="total"
        >合计金额：{{ formatMoney(totalAmount) }}</span
      >
      <div class="footer-actions">
      <el-button data-action="neutral" @click="emit('cancel')">取消</el-button>
      <el-button :data-action="form === 'inbound' ? 'neutral' : 'primary'" :loading="saving" @click="save('draft')">保存草稿</el-button>
      <el-button
        v-if="currentType?.is_approval_required"
        data-action="primary"
        type="warning"
        :loading="saving"
        @click="save('submit')"
        >保存并提交审批</el-button
      >
      <el-button
        v-else-if="canForm(form, 'confirm')"
        data-action="primary"
        type="primary"
        :loading="saving"
        @click="save('confirm')"
      >
        {{ isAssetInbound ? '确认入库并登记' : '保存并确认' }}
      </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import {
  confirmStockOrder,
  createStockOrder,
  formatMoney,
  formatQuantity,
  getStockOrder,
  listItemOptions,
  listWarehouseOptions,
  listLotOptions,
  listPersonnelOptions,
  listStockOrderTypeOptions,
  submitStockOrder,
  toNumber,
  updateStockOrder,
  type ItemOption,
  type WarehouseOption,
  type LotOption,
  type PersonnelOptions,
  type StockOrder,
  type StockOrderForm,
  type StockOrderLineWrite,
  type StockOrderType,
} from "@plugins/inv/web/src/api/inventoryManagement";
import {
  listSupplierOptions,
  type SupplierOption,
} from "@plugins/inv/web/src/api/invGoodsManagement";
import type { InboundFormLine } from "@plugins/inv/web/src/api/invInboundList";
import { FORM_TEXT, canForm, useInventoryMeta } from "./common";
import { preferredWarehouseId, rememberWarehouse } from "./warehouseContext";
import StockAssetTrackingEditor from "../../asset-management/StockAssetTrackingEditor.vue";
import WarehouseDepartmentSelect from "./WarehouseDepartmentSelect.vue";

type FormLine = InboundFormLine & {
  is_asset_managed?: boolean;
  asset_tracking?: import("../../../api/invAssetManagement").StockAssetTracking;
  lot_id?: string | null;
  counted_quantity?: number | null;
  lots?: LotOption[];
};

const props = defineProps<{
  form: StockOrderForm;
  orderId?: string | null;
  assetOnly?: boolean;
  warehouseScopeKey?: string;
  initialTypeNo?: string;
}>();
const emit = defineEmits<{ saved: [order: StockOrder]; cancel: [] }>();

const { meta, loadMeta, unitLabel } = useInventoryMeta();
const text = computed(() => FORM_TEXT[props.form]);
const isEdit = computed(() => Boolean(props.orderId));

const loading = ref(false);
const saving = ref(false);
const types = ref<StockOrderType[]>([]);
const warehouseOptions = ref<WarehouseOption[]>([]);
const allWarehouses = ref<WarehouseOption[]>([]);
const suppliers = ref<SupplierOption[]>([]);
const personnel = ref<PersonnelOptions>({ departments: [], users: [] });
const itemOptions = ref<ItemOption[]>([]);
const itemLoading = ref(false);
const availabilityLoading = ref(false);
const lines = ref<FormLine[]>([]);
const counterpartyValue = ref<string>("");

const header = reactive({
  order_type_id: "",
  business_date: dayjs().format("YYYY-MM-DD"),
  from_warehouse_id: "" as string | null,
  to_warehouse_id: "" as string | null,
  supplier_id: "" as string | null,
  department_id: "" as string | null,
  purpose: "",
  reason: "",
  handling_method_code: "" as string | null,
  expected_return_date: "" as string | null,
  remark: "",
});

const currentType = computed(() =>
  types.value.find((t) => t.id === header.order_type_id),
);
const direction = computed(() => currentType.value?.direction_code ?? "in");
const isAssetInbound = computed(() => props.form === "inbound" && props.assetOnly === true);
const isPurchaseInbound = computed(() => props.form === "inbound" && currentType.value?.type_no === "PURCHASE_IN");
const usesApplicableWarehouses = computed(() => props.form === "inbound" && !props.warehouseScopeKey);
const canSelectExistingAsset = computed(() => Boolean(currentType.value) && !isPurchaseInbound.value && !isAssetInbound.value);
const assetSelectionPurpose = computed(() => props.form === "return" ? "loan_return" : direction.value === "in" ? "stock_return" : "movement");
const warehouses = computed(() => {
  const allowed =
    currentType.value?.required_field_config?.warehouse_type_codes;
  return Array.isArray(allowed) && allowed.length
    ? warehouseOptions.value.filter((w) =>
        allowed.includes(w.warehouse_type_code),
      )
    : warehouseOptions.value;
});
const needFrom = computed(() =>
  ["out", "move", "status"].includes(direction.value),
);
const needTo = computed(() =>
  ["in", "move", "adjust"].includes(direction.value),
);
const showAvailable = computed(() => needFrom.value);
const targetWarehouses = computed(() =>
  direction.value === "move" ? allWarehouses.value : warehouses.value,
);
const totalAmount = computed(() =>
  lines.value.reduce((s, l) => s + (l.quantity || 0) * (l.unit_price || 0), 0),
);
const isRequired = (field: string) =>
  currentType.value?.required_fields?.includes(field) ?? false;
const userLabel = (u: PersonnelOptions["users"][number]) =>
  u.department_name
    ? `${u.display_name}（${u.department_name}）`
    : u.display_name;

let lineSeq = 0;
function newLine(): FormLine {
  lineSeq += 1;
  return {
    key: `l${Date.now()}${lineSeq}`,
    item_id: "",
    item_no: "",
    item_name: "",
    unit_code: "",
    quantity: 1,
    unit_price: 0,
  };
}
function addLine() {
  lines.value.push(newLine());
}

function stockWarehouseId() {
  return needFrom.value ? header.from_warehouse_id || undefined : undefined;
}

function stockStatusCode() {
  return currentType.value?.default_from_status_code || "available";
}

let itemRequest = 0;
let availabilityRequest = 0;
let personnelRequest = 0;
let lotRequest = 0;
let disposed = false;
const lotRequests = new WeakMap<FormLine, number>();

function sameStockContext(warehouseId: string | undefined, status: string) {
  return (
    !disposed &&
    warehouseId === stockWarehouseId() &&
    status === stockStatusCode()
  );
}

function resetLots(row: FormLine) {
  lotRequests.set(row, ++lotRequest);
  row.lot_id = null;
  row.lots = [];
}

function clearItem(row: FormLine) {
  resetLots(row);
  Object.assign(row, {
    item_id: "", item_no: "", item_name: "", specification: null,
    unit_code: "", available_quantity: null, unit_price: 0,
    is_asset_managed: false, asset_tracking: undefined
  });
}

async function searchItems(keyword = "") {
  const request = ++itemRequest;
  const warehouseId = stockWarehouseId();
  const inboundId = usesApplicableWarehouses.value ? header.to_warehouse_id || undefined : undefined;
  const status = stockStatusCode();
  if (!currentType.value || (needFrom.value && !warehouseId) || (usesApplicableWarehouses.value && !inboundId)) {
    itemOptions.value = [];
    itemLoading.value = false;
    return;
  }
  itemLoading.value = true;
  try {
    const res = await listItemOptions({
      keyword: keyword || undefined,
      is_asset_managed: isAssetInbound.value ? true : undefined,
      warehouse_id: warehouseId,
      inbound_warehouse_id: inboundId,
      inbound_action: inboundId ? (isEdit.value ? "update" : "create") : undefined,
      in_stock_only: needFrom.value,
      stock_status_code: needFrom.value ? status : undefined,
      limit: 50,
    });
    if (request !== itemRequest || !sameStockContext(warehouseId, status) || (usesApplicableWarehouses.value && inboundId !== (header.to_warehouse_id || undefined)))
      return;
    if (res.code !== 0) throw new Error(res.message);
    itemOptions.value = res.data.items;
  } catch (error) {
    if (request === itemRequest && sameStockContext(warehouseId, status) && (!usesApplicableWarehouses.value || inboundId === (header.to_warehouse_id || undefined))) {
      itemOptions.value = [];
      ElMessage.error(getHttpErrorMessage(error, "加载仓库物料失败"));
    }
  } finally {
    if (request === itemRequest) itemLoading.value = false;
  }
}

function itemChoices(row: FormLine): ItemOption[] {
  const list = [...itemOptions.value];
  if (row.item_id && !list.some((o) => o.id === row.item_id)) {
    list.unshift({
      id: row.item_id,
      item_no: row.item_no,
      item_name: row.item_name,
      specification: row.specification,
      unit_code: row.unit_code,
      available_quantity: row.available_quantity,
      is_lot_controlled: false,
    });
  }
  return list;
}

function onItemChange(row: FormLine, id: string) {
  row.asset_tracking = undefined;
  if (!id) return clearItem(row);
  const option = itemOptions.value.find(o => o.id === id);
  if (!option) return;
  row.is_asset_managed = option.is_asset_managed;
  row.item_no = option.item_no;
  row.item_name = option.item_name;
  row.specification = option.specification;
  row.unit_code = option.unit_code;
  row.available_quantity = option.available_quantity ?? null;
  resetLots(row);
  if (direction.value === "in" && !row.unit_price)
    row.unit_price = toNumber(option.unit_price);
}

async function loadLots(row: FormLine) {
  const request = ++lotRequest;
  lotRequests.set(row, request);
  const itemId = row.item_id;
  const warehouseId = stockWarehouseId();
  const status = stockStatusCode();
  if (!itemId || (needFrom.value && !warehouseId)) return;
  try {
    const res = await listLotOptions({
      item_id: itemId,
      warehouse_id: warehouseId,
      stock_status_code: status,
    });
    if (
      lotRequests.get(row) !== request ||
      row.item_id !== itemId ||
      !sameStockContext(warehouseId, status)
    )
      return;
    if (res.code !== 0) throw new Error(res.message);
    row.lots = res.data.items;
  } catch (error) {
    if (
      lotRequests.get(row) === request &&
      row.item_id === itemId &&
      sameStockContext(warehouseId, status)
    ) {
      row.lots = [];
      ElMessage.error(getHttpErrorMessage(error, "加载仓库批次失败"));
    }
  }
}

async function refreshAvailable(clearInvalid = false) {
  const request = ++availabilityRequest;
  const warehouseId = stockWarehouseId();
  const status = stockStatusCode();
  const selected = lines.value
    .filter((row) => row.item_id)
    .map((row) => ({ row, itemId: row.item_id }));
  if (!warehouseId || !selected.length) {
    availabilityLoading.value = false;
    return;
  }
  availabilityLoading.value = true;
  try {
    const results = await Promise.all(
      [...new Set(selected.map((value) => value.itemId))].map(
        async (itemId) => {
          const res = await listItemOptions({
            item_id: itemId,
            warehouse_id: warehouseId,
            stock_status_code: status,
            limit: 1,
          });
          if (res.code !== 0) throw new Error(res.message);
          return res.data.items[0];
        },
      ),
    );
    if (
      request !== availabilityRequest ||
      !sameStockContext(warehouseId, status)
    )
      return;
    const quantities = new Map(
      results
        .filter(Boolean)
        .map((item) => [item!.id, item!.available_quantity]),
    );
    let cleared = 0;
    selected.forEach(({ row, itemId }) => {
      if (row.item_id !== itemId || !lines.value.includes(row)) return;
      row.available_quantity = quantities.get(itemId) ?? 0;
      if (clearInvalid && toNumber(row.available_quantity) <= 0) {
        clearItem(row);
        cleared += 1;
      }
    });
    if (cleared)
      ElMessage.warning(
        `${cleared} 行物料在所选仓库无可用库存，已清除，请重新选择`,
      );
  } catch (error) {
    if (
      request === availabilityRequest &&
      sameStockContext(warehouseId, status)
    ) {
      ElMessage.error(getHttpErrorMessage(error, "刷新仓库库存失败"));
    }
  } finally {
    if (request === availabilityRequest) availabilityLoading.value = false;
  }
}

async function loadPersonnel(orgId?: string) {
  const request = ++personnelRequest;
  if (props.form !== "outbound" && props.form !== "lend") return;
  const res = await listPersonnelOptions(orgId);
  if (!disposed && request === personnelRequest && res.code === 0)
    personnel.value = res.data;
}

function orgOf(warehouseId?: string | null) {
  return [...warehouses.value, ...allWarehouses.value].find(l => l.id === warehouseId)?.org_id;
}

async function onFromWarehouseChange() {
  const warehouseId = stockWarehouseId();
  const status = stockStatusCode();
  itemOptions.value = [];
  if (!needFrom.value) {
    availabilityRequest += 1;
    availabilityLoading.value = false;
    await searchItems();
    return;
  }
  lines.value.forEach((row) => {
    resetLots(row);
    row.asset_tracking = undefined;
    row.available_quantity = null;
    if (!header.from_warehouse_id) clearItem(row);
  });
  const orgId = orgOf(header.from_warehouse_id);
  if (!orgId) {
    personnelRequest += 1;
    personnel.value = { departments: [], users: [] };
  }
  try {
    await Promise.all([
      orgId ? loadPersonnel(orgId) : Promise.resolve(),
      searchItems(),
      refreshAvailable(true),
    ]);
  } catch (error) {
    if (sameStockContext(warehouseId, status))
      ElMessage.error(getHttpErrorMessage(error, "刷新仓库数据失败"));
  }
}
let inboundRequest = 0;
async function refreshInboundItems() {
  if (!usesApplicableWarehouses.value) return;
  const request = ++inboundRequest;
  const warehouseId = header.to_warehouse_id;
  const selected = lines.value.filter(row => row.item_id).map(row => ({ row, itemId: row.item_id }));
  ++itemRequest;
  itemOptions.value = [];
  availabilityLoading.value = selected.length > 0;
  try {
    const results = await Promise.all([...new Set(selected.map(value => value.itemId))].map(async itemId => {
      if (!warehouseId) return undefined;
      const result = await listItemOptions({ item_id: itemId, inbound_warehouse_id: warehouseId,
        inbound_action: isEdit.value ? "update" : "create", limit: 1 });
      if (result.code !== 0) throw new Error(result.message);
      return result.data.items[0];
    }));
    if (disposed || request !== inboundRequest || warehouseId !== header.to_warehouse_id) return;
    const allowed = new Set(results.filter(Boolean).map(item => item!.id));
    let cleared = 0;
    for (const { row, itemId } of selected) {
      if (row.item_id === itemId && lines.value.includes(row) && !allowed.has(itemId)) {
        clearItem(row);
        cleared++;
      }
    }
    if (cleared) ElMessage.warning(`目标仓库已变更，已清除 ${cleared} 行不适用的物料，请重新选择`);
  } catch (error) {
    if (request === inboundRequest) ElMessage.error(getHttpErrorMessage(error, "核对目标仓库适用物料失败"));
  } finally {
    if (request === inboundRequest) availabilityLoading.value = false;
  }
  if (request === inboundRequest && warehouseId === header.to_warehouse_id) await searchItems();
}

let toWarehouseRequest = 0;
async function onToWarehouseChange() {
  const request = ++toWarehouseRequest;
  if (usesApplicableWarehouses.value) rememberWarehouse(header.to_warehouse_id || "");
  await refreshInboundItems();
  if (disposed || request !== toWarehouseRequest) return;
  if (props.form === "inbound") lines.value.forEach(row => {
    if (row.asset_tracking?.registration) row.asset_tracking = undefined;
  });
  if (!needFrom.value) {
    try { await loadPersonnel(orgOf(header.to_warehouse_id)); }
    catch (error) { ElMessage.error(getHttpErrorMessage(error, "加载资产责任部门失败")); }
  }
}

function assetDepartment(row: FormLine): string | null {
  return row.asset_tracking?.registration?.department_id
    ?? [...warehouses.value, ...allWarehouses.value].find(w => w.id === header.to_warehouse_id)?.default_asset_department_id ?? null;
}
function setAssetDepartment(row: FormLine, value?: string | null) {
  row.asset_tracking = { selections: [], registration: { department_id: value || null } };
}
function clearAssetSelection(row: FormLine) {
  row.asset_tracking = undefined;
}

function buildLines(): StockOrderLineWrite[] {
  return lines.value
    .filter((l) => l.item_id)
    .map((l) => ({
      item_id: l.item_id,
      ...(l.asset_tracking ? { tracking: { asset: l.asset_tracking } } : {}),
      quantity: direction.value === "adjust" ? null : l.quantity,
      counted_quantity:
        direction.value === "adjust" ? (l.counted_quantity ?? 0) : null,
      unit_price: direction.value === "in" ? l.unit_price : null,
      lot_id: direction.value === "in" ? null : l.lot_id || null,
      lot_no: direction.value === "in" ? l.lot_no || null : null,
      production_date:
        direction.value === "in" ? l.production_date || null : null,
      expiry_date: direction.value === "in" ? l.expiry_date || null : null,
      remark: l.remark || null,
    }));
}

function buildHeader() {
  const userId = personnel.value.users.find(
    (u) => u.user_id === counterpartyValue.value,
  )?.user_id;
  return {
    business_date: header.business_date || null,
    from_warehouse_id: needFrom.value ? header.from_warehouse_id || null : null,
    to_warehouse_id: needTo.value ? header.to_warehouse_id || null : null,
    supplier_id: props.form === "inbound" ? header.supplier_id || null : null,
    counterparty_user_id: userId ?? null,
    counterparty_name_snapshot: userId ? null : counterpartyValue.value || null,
    department_id: header.department_id || null,
    purpose: header.purpose || null,
    reason: header.reason || null,
    handling_method_code: header.handling_method_code || null,
    expected_return_date: header.expected_return_date || null,
    remark: header.remark || null,
  };
}

async function save(mode: "draft" | "submit" | "confirm") {
  if (!header.order_type_id) return ElMessage.warning("请选择单据类型");
  if (needTo.value && !header.to_warehouse_id) return ElMessage.warning("请先选择目标仓库");
  if (needFrom.value && !header.from_warehouse_id) return ElMessage.warning("请先选择来源仓库");
  if (availabilityLoading.value) return ElMessage.warning("正在刷新所选仓库库存，请稍候");
  const payloadLines = buildLines();
  if (!payloadLines.length) return ElMessage.warning("请至少添加一行明细");
  if (isAssetInbound.value && lines.value.some(l => l.item_id && (l.is_asset_managed !== true || l.asset_tracking?.selections?.length))) {
    return ElMessage.warning("此入口仅用于新增资产，请选择已纳入资产管理的物料；已有资产退库请到入库管理办理");
  }
  if (props.form === "inbound" && lines.value.some(l => l.item_id && l.is_asset_managed && !l.asset_tracking?.selections?.length && !Number.isInteger(l.quantity))) {
    return ElMessage.warning("逐件编号的资产数量必须为整数，例如 10 台电脑会生成 10 个独立编号");
  }
  if (isPurchaseInbound.value && lines.value.some(l => l.asset_tracking?.selections?.length)) {
    return ElMessage.warning("采购入库不能关联已有资产，请清除错误关联或改用其他入库办理退库");
  }
  if (mode !== "draft" && props.form === "inbound" && lines.value.some(l => l.item_id && l.is_asset_managed
    && !l.asset_tracking?.selections?.length && !assetDepartment(l))) {
    return ElMessage.warning("请为资产物料选择责任部门，或先配置仓库责任部门");
  }
  if (
    direction.value !== "adjust" &&
    payloadLines.some((l) => !toNumber(l.quantity))
  ) {
    return ElMessage.warning("明细数量必须大于 0");
  }
  saving.value = true;
  try {
    let res;
    if (isEdit.value && props.orderId) {
      res = await updateStockOrder(props.orderId, {
        ...buildHeader(),
        lines: payloadLines,
      });
      if (res.code === 0 && mode !== "draft") {
        res =
          mode === "confirm"
            ? await confirmStockOrder(props.orderId)
            : await submitStockOrder(props.orderId);
      }
    } else {
      res = await createStockOrder({
        order_type_id: header.order_type_id,
        ...buildHeader(),
        lines: payloadLines,
        submit: mode === "submit",
        confirm: mode === "confirm",
      });
    }
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success(
      mode === "confirm"
        ? isAssetInbound.value ? "已入库并登记资产" : "已确认记账"
        : mode === "submit"
          ? "已提交"
          : "已保存",
    );
    emit("saved", res.data);
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "保存失败"));
  } finally {
    saving.value = false;
  }
}

async function loadOrder(id: string) {
  const res = await getStockOrder(id);
  if (res.code !== 0) throw new Error(res.message);
  const o = res.data;
  header.order_type_id = o.order_type_id;
  header.business_date = o.business_date;
  header.from_warehouse_id = o.from_warehouse_id ?? "";
  header.to_warehouse_id = o.to_warehouse_id ?? "";
  header.supplier_id = (o.flex_form?.supplier_id as string) ?? "";
  header.department_id = o.department_id ?? "";
  header.purpose = o.purpose ?? "";
  header.reason = o.reason ?? "";
  header.handling_method_code = o.handling_method_code ?? "";
  header.expected_return_date = o.expected_return_date ?? "";
  header.remark = o.remark ?? "";
  counterpartyValue.value =
    (o.flex_form?.counterparty_user_id as string) ||
    o.counterparty_name_snapshot ||
    "";
  lines.value = (o.lines ?? []).map((l) => ({
    ...newLine(),
    item_id: l.item_id,
    is_asset_managed: l.is_asset_managed,
    asset_tracking: l.tracking?.asset ? { registration: l.tracking.asset.registration, selections: (l.tracking.asset.selections ?? []).map(({ asset_label, ...selection }) => selection) } : undefined,
    item_no: l.item_no ?? "",
    item_name: l.item_name ?? "",
    specification: l.specification,
    unit_code: l.unit_code,
    quantity: toNumber(l.quantity),
    unit_price: toNumber(l.unit_price),
    counted_quantity:
      l.counted_quantity == null ? null : toNumber(l.counted_quantity),
    lot_id: l.lot_id,
    lot_no: l.lot_no,
    production_date: l.production_date,
    expiry_date: l.expiry_date,
    remark: l.remark,
  }));
  await loadPersonnel(o.org_id);
  await refreshAvailable();
}

watch(
  () => header.order_type_id,
  () => {
    const previousFrom = header.from_warehouse_id;
    const previousTo = header.to_warehouse_id;
    if (!needFrom.value) header.from_warehouse_id = "";
    if (!needTo.value) header.to_warehouse_id = "";
    if (!isEdit.value) {
      if (!warehouses.value.some((w) => w.id === header.from_warehouse_id))
        header.from_warehouse_id =
          needFrom.value && warehouses.value.length === 1
            ? warehouses.value[0].id
            : "";
      if (!targetWarehouses.value.some((w) => w.id === header.to_warehouse_id))
        header.to_warehouse_id =
          needTo.value && targetWarehouses.value.length === 1
            ? targetWarehouses.value[0].id
            : "";
      if (previousFrom !== header.from_warehouse_id) {
        lines.value.forEach((line) => {
          line.available_quantity = undefined;
          line.lot_id = null;
          line.lots = [];
        });
      }
      if (!loading.value) {
        if (needFrom.value) onFromWarehouseChange();
        else if (previousTo !== header.to_warehouse_id) onToWarehouseChange();
        else void searchItems();
      }
    }
  },
);

onBeforeUnmount(() => {
  disposed = true;
  itemRequest += 1;
  availabilityRequest += 1;
  personnelRequest += 1;
});

onMounted(async () => {
  loading.value = true;
  try {
    await loadMeta();
    const [typeRes, locRes, allRes] = await Promise.all([
      listStockOrderTypeOptions({
        form: props.form,
        warehouse_scope_key: props.warehouseScopeKey,
      }),
      listWarehouseOptions({ warehouse_scope_key: props.warehouseScopeKey }),
      listWarehouseOptions({
        all_orgs: true,
        warehouse_scope_key: props.warehouseScopeKey,
      }),
    ]);
    types.value =
      typeRes.code === 0
        ? typeRes.data.items.filter(
            (t) => !t.is_source_managed || !!props.orderId,
          )
        : [];
    warehouseOptions.value = locRes.code === 0 ? locRes.data.items : [];
    allWarehouses.value = allRes.code === 0 ? allRes.data.items : [];
    if (props.form === "inbound") {
      const res = await listSupplierOptions();
      suppliers.value = res.code === 0 ? res.data.items : [];
    }
    if (props.orderId) {
      await loadOrder(props.orderId);
    } else {
      const initial = props.initialTypeNo
        ? types.value.find((t) => t.type_no === props.initialTypeNo)
        : types.value[0];
      if (!initial)
        throw new Error("所选单据类型尚未配置或已停用，请先同步租户配置");
      header.order_type_id = initial.id;
      if (usesApplicableWarehouses.value) {
        header.to_warehouse_id = preferredWarehouseId(targetWarehouses.value);
      } else if (warehouses.value.length === 1) {
        header.from_warehouse_id = warehouses.value[0].id;
        header.to_warehouse_id = warehouses.value[0].id;
      }
      await loadPersonnel(
        orgOf(header.from_warehouse_id || header.to_warehouse_id),
      );
      addLine();
    }
    await searchItems();
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "加载失败"));
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped lang="scss">
.order-form-header {
  margin-bottom: 4px;
}

.lines-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0;
}

.lines-title {
  font-weight: 600;
  color: #334155;
}

.form-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 16px;
}

.total {
  margin-right: auto;
  font-weight: 600;
  color: #0f172a;
}

.footer-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.inbound-form {
  --el-component-size-small: 32px;

  .order-form-header {
    padding: 16px;
    margin-bottom: 20px;
    background: var(--el-fill-color-lighter);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
  }
  .section-title {
    margin-bottom: 14px;
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
  .order-form-header :deep(.el-form-item) {
    margin-bottom: 14px;
  }
  .order-form-header :deep(.el-col:last-child .el-form-item) {
    margin-bottom: 0;
  }
  :deep(.el-form-item__label) {
    height: auto;
    padding-bottom: 6px;
    margin-bottom: 0;
    font-size: 13px;
    line-height: 20px;
  }
  .lines-toolbar {
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin: 0 0 12px;
  }
  .lines-title {
    display: inline-flex;
    gap: 8px;
    align-items: center;
    font-size: 15px;
  }
  .line-count {
    padding: 1px 8px;
    font-size: 12px;
    font-weight: 400;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-radius: 4px;
  }
  .lines-description {
    margin: 5px 0 0;
    font-size: 12px;
    line-height: 18px;
    color: var(--el-text-color-secondary);
  }
  .line-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .line-actions :deep(.el-button + .el-button),
  .footer-actions :deep(.el-button + .el-button) {
    margin-left: 0;
  }
  .lines-table {
    border-radius: 6px;
  }
  .lines-table :deep(.el-input__inner) {
    font-variant-numeric: tabular-nums;
  }
  .lines-table :deep(.el-input-number .el-input__inner) {
    text-align: right;
  }
  .lines-table :deep(.el-table__expanded-cell) {
    padding: 0 !important;
  }
  .material-meta,
  .line-extra-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 12px;
    margin-top: 6px;
    font-size: 12px;
    line-height: 18px;
    color: var(--el-text-color-secondary);
    word-break: break-word;
  }
  .material-code {
    color: var(--el-text-color-placeholder);
  }
  .material-kind {
    display: inline-block;
    margin-top: 6px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .asset-registration {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: center;
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--el-border-color-extra-light);
  }
  .asset-registration-heading {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }
  .asset-status {
    padding: 1px 6px;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-radius: 4px;
  }
  .asset-error {
    flex-basis: 100%;
    color: var(--el-color-danger);
  }
  .responsibility-editor {
    display: flex;
    flex: 1 1 220px;
    gap: 8px;
    align-items: center;
    min-width: 0;
  }
  .responsibility-label {
    flex-shrink: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .responsibility-editor :deep(.el-select) {
    flex: 1;
    min-width: 0;
  }
  .quantity-editor {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .quantity-editor :deep(.el-input-number) {
    flex: 1;
    min-width: 0;
  }
  .quantity-unit {
    flex-shrink: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .line-details {
    padding: 16px 24px;
    background: var(--el-fill-color-lighter);
  }
  .line-details-title {
    margin-bottom: 12px;
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
  .line-details-form :deep(.el-form-item) {
    margin-bottom: 12px;
  }
  .line-details-form :deep(.el-col:last-child .el-form-item) {
    margin-bottom: 0;
  }
  .form-footer {
    flex-wrap: wrap;
    gap: 16px;
    padding-top: 18px;
    margin-top: 18px;
    border-top: 1px solid var(--el-border-color-lighter);
  }
  .order-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: baseline;
    margin-right: auto;
  }
  .summary-label {
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }
  .order-summary strong {
    font-size: 22px;
    font-weight: 600;
    line-height: 30px;
    color: var(--el-text-color-primary);
    font-variant-numeric: tabular-nums;
  }
  .summary-count {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  @media (width <= 600px) {
    .order-form-header {
      padding: 12px;
    }
    .lines-toolbar {
      align-items: flex-start;
    }
    .line-details {
      padding: 12px;
    }
    .form-footer {
      align-items: stretch;
    }
    .order-summary {
      flex-basis: 100%;
    }
    .footer-actions {
      flex: 1;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
  }
}

:global(.inventory-inbound-item-options .el-select-dropdown__item) {
  height: auto;
  min-height: 52px;
  padding-top: 7px;
  padding-bottom: 7px;
  line-height: 20px;
}
.item-option-name {
  font-size: 13px;
}
.item-option-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
