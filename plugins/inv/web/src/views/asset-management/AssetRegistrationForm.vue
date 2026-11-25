<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import { formatMoney } from "@plugins/inv/web/src/api/inventoryManagement";
import {
  getAssetRegistrationOptions,
  registerAssets,
  type AssetItemOption,
  type AssetRegistrationOptions,
} from "@plugins/inv/web/src/api/invAssetManagement";
import AssetItemSelect from "./AssetItemSelect.vue";

const emit = defineEmits<{ saved: []; cancel: []; busy: [value: boolean] }>();
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const options = ref<AssetRegistrationOptions>();
const selectedItem = ref<AssetItemOption>();
const form = reactive({
  org_id: "",
  asset_no: "",
  item_id: "",
  quantity: 1,
  warehouse_id: "",
  department_id: "",
  custodian_user_id: "",
  location_id: "",
  original_amount: null as number | null,
  acquired_date: "",
  status_code: "idle" as "idle" | "in_use",
  remark: "",
});
const warehouse = computed(() =>
  options.value?.warehouses.find((row) => row.id === form.warehouse_id),
);
const totalAmount = computed(() =>
  form.original_amount == null ? null : form.original_amount * form.quantity,
);
const unit = computed(
  () =>
    options.value?.md_unit.find(
      (row) => row.value === selectedItem.value?.unit_code,
    )?.label || "件",
);
const locationLabel = computed(
  () =>
    options.value?.locations.find(
      (row) => (row.physical_location_id || row.id) === form.location_id,
    )?.location_name || "",
);
let request = 0;

function clearResponsibility() {
  form.department_id = "";
  form.custodian_user_id = "";
  form.location_id = "";
}

function selectItem(item: AssetItemOption) {
  if (selectedItem.value?.id === item.id) return;
  selectedItem.value = item;
  const price =
    item.unit_price == null || item.unit_price === ""
      ? null
      : Number(item.unit_price);
  form.original_amount =
    price != null && Number.isFinite(price) && price >= 0 ? price : null;
}

async function loadOptions(orgId?: string) {
  const token = ++request;
  loading.value = true;
  error.value = "";
  options.value = undefined;
  form.item_id = "";
  selectedItem.value = undefined;
  form.original_amount = null;
  form.warehouse_id = "";
  clearResponsibility();
  try {
    const result = await getAssetRegistrationOptions(orgId);
    if (request !== token) return;
    if (result.code !== 0) throw new Error(result.message);
    options.value = result.data;
    form.org_id = result.data.org_id;
  } catch (cause) {
    if (request === token)
      error.value = getHttpErrorMessage(cause, "资产登记选项加载失败");
  } finally {
    if (request === token) loading.value = false;
  }
}

function changeWarehouse() {
  clearResponsibility();
  if (!warehouse.value) return;
  const defaults = warehouse.value;
  form.department_id = options.value?.departments.some(
    (row) => row.value === defaults.default_asset_department_id,
  )
    ? defaults.default_asset_department_id!
    : "";
  form.custodian_user_id = options.value?.users.some(
    (row) => row.value === defaults.default_asset_custodian_user_id,
  )
    ? defaults.default_asset_custodian_user_id!
    : "";
  form.location_id = defaults.location_id || "";
  form.status_code = "idle";
}

async function save() {
  if (saving.value || loading.value || !options.value) return;
  if (!form.org_id || !form.item_id)
    return ElMessage.warning("请选择所属组织和资产物品");
  if (!selectedItem.value?.default_asset_type_code)
    return ElMessage.warning("请先在物料档案配置该物品的资产类型");
  if (
    !Number.isInteger(form.quantity) ||
    form.quantity < 1 ||
    form.quantity > 1000
  )
    return ElMessage.warning("数量须为 1 至 1000 的整数");
  if (!form.department_id || !form.custodian_user_id || !form.location_id)
    return ElMessage.warning("请填写责任部门、资产保管人和资产位置");
  saving.value = true;
  emit("busy", true);
  try {
    const result = await registerAssets({
      ...form,
      asset_no: form.quantity === 1 ? form.asset_no.trim() || null : null,
      warehouse_id: form.warehouse_id || null,
      acquired_date: form.acquired_date || null,
      original_amount: form.original_amount ?? null,
      remark: form.remark.trim() || null,
    });
    if (result.code !== 0) throw new Error(result.message);
    ElMessage.success(
      `已登记 ${result.data.registered_quantity} 件资产${result.data.stock_order_id ? "并同步入库" : ""}`,
    );
    emit("saved");
  } catch (cause) {
    ElMessage.error(getHttpErrorMessage(cause, "资产登记失败"));
  } finally {
    saving.value = false;
    emit("busy", false);
  }
}

onMounted(() => loadOptions());
onBeforeUnmount(() => {
  request++;
});
</script>

<template>
  <div v-loading="loading" class="asset-registration-form">
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      class="options-error"
    >
      <el-button
        link
        type="primary"
        @click="loadOptions(form.org_id || undefined)"
        >重新加载</el-button
      >
    </el-alert>
    <p class="form-description">
      每件实物独立编号，支持一次登记多件；选择仓库后同步入库。
    </p>
    <el-form
      :model="form"
      label-position="top"
      class="registration-fields"
      @submit.prevent="save"
    >
      <section
        class="registration-section"
        aria-labelledby="asset-registration-info"
      >
        <div class="section-heading">
          <h3 id="asset-registration-info">资产信息</h3>
          <span>编号留空自动生成</span>
        </div>
        <el-row :gutter="16">
          <el-col
            v-if="(options?.organizations.length || 0) > 1"
            :xs="24"
            :sm="12"
          >
            <el-form-item label="所属组织" required>
              <el-select
                v-model="form.org_id"
                class="w-full"
                @change="loadOptions($event)"
              >
                <el-option
                  v-for="row in options?.organizations || []"
                  :key="row.id"
                  :value="row.id"
                  :label="row.org_name"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col
            :xs="24"
            :sm="(options?.organizations.length || 0) > 1 ? 12 : 24"
          >
            <el-form-item label="资产物品" required>
              <AssetItemSelect
                v-model="form.item_id"
                :org-id="form.org_id"
                :disabled="!options || loading"
                permission-key="asset_register:create"
                @select="selectItem"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="资产编号">
              <el-input
                :model-value="form.quantity > 1 ? '' : form.asset_no"
                :disabled="form.quantity > 1"
                maxlength="64"
                :placeholder="
                  form.quantity > 1
                    ? '多件资产自动逐件编号'
                    : '留空自动生成，也可手动填写'
                "
                @update:model-value="form.asset_no = $event"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="6">
            <el-form-item label="数量" required>
              <el-input-number
                v-model="form.quantity"
                :min="1"
                :max="1000"
                :precision="0"
                controls-position="right"
                class="w-full"
              />
              <span class="field-hint">按 {{ unit }} 逐件编号</span>
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="6">
            <el-form-item label="单件原值（元）">
              <el-input-number
                v-model="form.original_amount"
                :min="0"
                :precision="2"
                :controls="false"
                placeholder="未知可留空"
                class="w-full"
              />
              <span class="field-hint">默认物料单价，可修改</span>
            </el-form-item>
          </el-col>
        </el-row>
      </section>
      <section
        class="registration-section"
        aria-labelledby="asset-registration-responsibility"
      >
        <div class="section-heading">
          <h3 id="asset-registration-responsibility">责任与存放</h3>
          <span>{{ form.warehouse_id ? "在库登记" : "现场登记" }}</span>
        </div>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="目标仓库（选填）">
              <el-select
                v-model="form.warehouse_id"
                clearable
                filterable
                class="w-full"
                placeholder="不选仓库，直接登记实际位置"
                @change="changeWarehouse"
              >
                <el-option
                  v-for="row in options?.warehouses || []"
                  :key="row.id"
                  :value="row.id"
                  :label="row.warehouse_name"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="资产位置" required>
              <el-input
                v-if="form.warehouse_id"
                :model-value="locationLabel"
                readonly
                placeholder="请先在仓库档案配置有效的统一位置"
              />
              <el-select
                v-else
                v-model="form.location_id"
                filterable
                placeholder="请选择实际存放或使用位置"
                class="w-full"
              >
                <el-option
                  v-for="row in options?.locations || []"
                  :key="row.id"
                  :value="row.physical_location_id || row.id"
                  :label="row.location_name"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="责任部门" required>
              <el-select
                v-model="form.department_id"
                filterable
                clearable
                placeholder="请选择责任部门"
                class="w-full"
              >
                <el-option
                  v-for="row in options?.departments || []"
                  :key="row.value"
                  :value="row.value"
                  :label="row.label"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="资产保管人" required>
              <el-select
                v-model="form.custodian_user_id"
                filterable
                clearable
                placeholder="请选择资产保管人"
                class="w-full"
              >
                <el-option
                  v-for="row in options?.users || []"
                  :key="row.value"
                  :value="row.value"
                  :label="row.label"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <p class="section-hint">
          {{
            form.warehouse_id
              ? "按仓库配置带出位置与责任信息，未配置的部门或保管人可在此补选。"
              : "不选仓库时只登记资产，请填写实际位置、责任部门和保管人。"
          }}
        </p>
      </section>
      <el-collapse class="more-information">
        <el-collapse-item title="更多信息（选填）" name="more">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12">
              <el-form-item label="购置日期"
                ><el-date-picker
                  v-model="form.acquired_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  class="w-full"
              /></el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="资产状态">
                <el-select
                  v-model="form.status_code"
                  :disabled="Boolean(form.warehouse_id)"
                  class="w-full"
                >
                  <el-option label="闲置" value="idle" /><el-option
                    label="在用"
                    value="in_use"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
      <el-form-item label="备注" class="remark-field">
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="2"
          maxlength="1000"
          show-word-limit
          placeholder="补充资产用途或其他说明（选填）"
        />
      </el-form-item>
    </el-form>
    <div class="registration-footer">
      <div class="registration-summary">
        <strong>共 {{ form.quantity || 0 }} 件</strong
        ><span
          >原值合计：{{
            totalAmount == null ? "未填写" : formatMoney(totalAmount)
          }}</span
        >
      </div>
      <div class="footer-actions">
        <el-button
          data-action="neutral"
          :disabled="saving"
          @click="emit('cancel')"
          >取消</el-button
        >
        <el-button
          data-action="primary"
          type="primary"
          :loading="saving"
          :disabled="loading || !options"
          @click="save"
          >保存并登记</el-button
        >
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.asset-registration-form {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100dvh - 142px);
}
.form-description {
  flex-shrink: 0;
  margin: 16px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 20px;
}
.registration-fields {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}
.registration-section {
  padding: 16px 16px 0;
  margin-bottom: 14px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.section-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.section-heading h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 20px;
  font-weight: 600;
}
.section-heading > span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.section-hint {
  margin: -2px 0 14px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}
.w-full {
  width: 100%;
}
.field-hint {
  display: block;
  width: 100%;
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}
.more-information {
  margin: 0 0 12px;
  border-top: 0;
}
.more-information :deep(.el-collapse-item__header) {
  height: 40px;
  font-size: 13px;
  line-height: 40px;
}
.more-information :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}
.registration-footer {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  margin-top: 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.registration-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  align-items: baseline;
}
.registration-summary strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}
.registration-summary span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.footer-actions {
  display: flex;
  gap: 8px;
}
.footer-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
.options-error {
  flex-shrink: 0;
  margin-top: 16px;
}
.asset-registration-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.asset-registration-form :deep(.el-form-item__label) {
  height: auto;
  padding-bottom: 6px;
  margin-bottom: 0;
  font-size: 13px;
  line-height: 20px;
}
.asset-registration-form :deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.remark-field {
  margin-bottom: 0 !important;
}
@media (width <= 600px) {
  .asset-registration-form {
    max-height: calc(100dvh - 126px);
  }
  .registration-section {
    padding: 12px 12px 0;
  }
  .form-description {
    margin: 12px 0;
  }
  .registration-summary {
    display: block;
  }
  .registration-summary span {
    display: block;
    margin-top: 4px;
    font-size: 12px;
  }
  .footer-actions {
    margin-left: auto;
  }
}
</style>
