<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  getStockAssetTargetOptions,
  listStockAssetBindings,
  type AssetOptions,
  type StockAssetBinding,
  type StockAssetTracking,
  type StockAssetChoice,
} from "../../api/invAssetManagement";
import { assetLocationOptions } from "../../utils/assetLocationAliases";

const props = defineProps<{
  modelValue?: StockAssetTracking;
  itemId: string;
  warehouseId?: string | null;
  orgId?: string | null;
  selectionPurpose?: "movement" | "stock_return" | "loan_return";
  personalCustody?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: StockAssetTracking];
}>();
const open = ref(false);
const loading = ref(false);
const bindings = ref<StockAssetBinding[]>([]);
const options = ref<AssetOptions | null>(null);
const rows = ref<StockAssetChoice[]>([]);
const savedLabels = ref<Record<string, string>>({});
const selected = ref("");
const page = ref(1);
const total = ref(0);
let request = 0;
let contextRequest = 0;
watch(
  () => [props.itemId, props.warehouseId, props.orgId, props.selectionPurpose],
  () => {
    request++;
    contextRequest++;
    open.value = false;
    emit("update:modelValue", { selections: [] });
  },
);
const canTransfer = computed(() => hasPerms("asset_register:transfer"));
const copy = computed(() => props.personalCustody ? {
  button: "选择发放资产", selected: "发放资产", title: "选择本次交给申领人的资产",
  hint: "按实际发放数量选择实物。发放后由申领人个人保管，不要求固定地点；责任部门优先使用申领人部门，未关联部门时保留原责任部门。"
} : props.selectionPurpose === "stock_return" ? {
  button: "选择退库资产", selected: "退库资产", title: "选择本次退库的原资产",
  hint: "仅在已有资产退库时选择已领用的原实物，数量须与本行退库数量一致。沿用原资产编号，入库位置取目标仓库，不重复建卡。新收货请保留自动登记。"
} : props.selectionPurpose === "loan_return" ? {
  button: "选择归还资产", selected: "归还资产", title: "选择本次归还的原资产",
  hint: "请选择本次原借出明细对应的实物，数量须与归还数量一致。归还沿用原资产编号，不新建卡片。"
} : {
  button: "关联资产", selected: "", title: "关联本次流转的实物资产",
  hint: "资产物料须选择已确认的实物，数量须与本次单据一致。领用、借出须指定交付位置；调拨位置取目标仓库。"
});
const buttonLabel = computed(() => props.modelValue?.selections.length
  ? (copy.value.selected ? `已选 ${props.modelValue.selections.length} 项${copy.value.selected}` : `已关联 ${props.modelValue.selections.length} 项`)
  : copy.value.button);
async function loadBindings() {
  const token = ++request;
  loading.value = true;
  try {
    const response = await listStockAssetBindings({
      item_id: props.itemId,
      warehouse_id: props.warehouseId || undefined,
      page: page.value,
      page_size: 20,
    });
    if (token !== request || !open.value) return;
    bindings.value = response.data.items;
    total.value = response.data.total;
  } catch (error) {
    if (token === request && open.value) ElMessage.error(getHttpErrorMessage(error, "实物选项加载失败"));
  } finally {
    if (token === request) loading.value = false;
  }
}
async function show() {
  if (!props.itemId) return ElMessage.warning("请先选择物料");
  const token = ++contextRequest;
  savedLabels.value = {
    ...savedLabels.value,
    ...Object.fromEntries(
      (props.modelValue?.selections || [])
        .filter((row) => row.asset_label)
        .map((row) => [row.binding_id, row.asset_label || ""]),
    ),
  };
  rows.value = (props.modelValue?.selections || []).map((row) => ({
    binding_id: row.binding_id,
    quantity: Number(row.quantity),
    target_location_id: row.target_location_id,
    department_id: row.department_id,
    custodian_user_id: row.custodian_user_id,
  }));
  bindings.value = [];
  options.value = null;
  selected.value = "";
  page.value = 1;
  open.value = true;
  await loadBindings();
  if (!open.value || token !== contextRequest) return;
  if (props.personalCustody) return;
  try {
    const response = await getStockAssetTargetOptions(props.orgId || undefined);
    if (open.value && token === contextRequest) options.value = response.data;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "交付目标选项加载失败"));
  }
}
function add() {
  const binding = bindings.value.find((row) => row.id === selected.value);
  if (!binding || rows.value.some((row) => row.binding_id === binding.id))
    return;
  savedLabels.value[binding.id] = binding.asset_no || "数量资产";
  rows.value.push({
    binding_id: binding.id,
    quantity: 1,
    target_location_id: null,
    department_id: null,
    custodian_user_id: null,
  });
  selected.value = "";
}
function label(id: string) {
  const binding = bindings.value.find((row) => row.id === id);
  return binding
    ? `${binding.asset_no || "数量资产"} · 可选 ${binding.quantity}`
    : savedLabels.value[id] || "已选实物（保存记录）";
}
function save() {
  emit("update:modelValue", {
    selections: rows.value.map((row) => ({
      ...row,
      quantity: String(row.quantity),
    })),
  });
  open.value = false;
}
onScopeDispose(() => { request++; contextRequest++; open.value = false; });
</script>

<template>
  <el-button v-if="canTransfer" link type="primary" @click="show">
    {{ buttonLabel }}
  </el-button>
  <el-dialog
    v-model="open"
    :title="copy.title"
    width="min(1100px, 96vw)"
    append-to-body
    @closed="request++"
  >
    <el-alert
      type="info"
      :closable="false"
      :title="copy.hint"
    />
    <div class="stock-choice">
      <el-select
        v-model="selected"
        placeholder="选择实物"
        filterable
        :loading="loading"
        style="width: 330px"
      >
        <el-option
          v-for="binding in bindings"
          :key="binding.id"
          :value="binding.id"
          :label="`${binding.asset_no || '数量资产'} · ${binding.quantity} · ${binding.stock_status_code}`"
          :disabled="
            binding.registration_status_code !== 'confirmed' ||
            !['idle', 'in_use'].includes(binding.status_code)
          "
        />
      </el-select>
      <el-button @click="add">添加</el-button>
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadBindings"
      />
    </div>
    <ReListTable
      list-key="asset-stock-selections"
      :list-controls="false"
      :data="rows"
      border
      row-key="binding_id"
    >
      <el-table-column label="实物" min-width="170"
        ><template #default="{ row }">{{
          label(row.binding_id)
        }}</template></el-table-column
      >
      <el-table-column label="数量" width="140"
        ><template #default="{ row }"
          ><el-input-number
            v-model="row.quantity"
            :min="0.001"
            :precision="3"
            controls-position="right"
            style="width: 120px" /></template
      ></el-table-column>
      <el-table-column v-if="!personalCustody" label="交付位置" min-width="180"
        ><template #default="{ row }">
          <el-select
            v-model="row.target_location_id"
            filterable
            clearable
            placeholder="领用、借出必选"
          >
            <el-option
              v-for="location in assetLocationOptions(options?.locations || [])"
              :key="location.id"
              :value="location.physical_location_id || location.id"
              :label="location.location_name"
            />
          </el-select> </template
      ></el-table-column>
      <el-table-column v-if="!personalCustody" label="责任部门" min-width="180"
        ><template #default="{ row }">
          <el-select
            v-model="row.department_id"
            filterable
            placeholder="请选择责任部门"
            ><el-option
              v-for="department in options?.departments || []"
              :key="department.id"
              :value="department.id"
              :label="department.department_name"
          /></el-select> </template
      ></el-table-column>
      <el-table-column v-if="!personalCustody" label="保管人" min-width="160"
        ><template #default="{ row }">
          <el-select
            v-model="row.custodian_user_id"
            filterable
            clearable
            placeholder="可选"
            ><el-option
              v-for="user in options?.users || []"
              :key="user.id"
              :value="user.id"
              :label="user.display_name"
          /></el-select> </template
      ></el-table-column>
      <el-table-column width="70"
        ><template #default="{ $index }"
          ><el-button link type="danger" @click="rows.splice($index, 1)"
            >移除</el-button
          ></template
        ></el-table-column
      >
    </ReListTable>
    <template #footer
      ><el-button @click="open = false">取消</el-button
      ><el-button type="primary" @click="save">保存选择</el-button></template
    >
  </el-dialog>
</template>

<style scoped>
.stock-choice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
</style>
