<script setup lang="ts">
import FlexFields from "../components/FlexFields.vue";
import OrganizationField from "../components/OrganizationField.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, reactive, ref, computed, unref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  useSampleApi,
  type ProjectContract,
  type FlexField,
  type ProjectRow,
  flexDisplay,
  deleteSampleRecord,
} from "@plugins/sample_app/web/src/api/sample_app";
const {
  createContract,
  createProjectCost,
  createReceipt,
  createReceiptPlan,
  getProject,
  listFlexFields,
  listProjects,
  saveProject,
} = useSampleApi();
const flexFields = ref<FlexField[]>([]);
const deletingPlan = ref(false);
async function deletePlan(id: string) {
  if (deletingPlan.value) return;
  deletingPlan.value = true;
  try {
    try {
      await ElMessageBox.confirm(
        "确认删除这条回款计划？实际到账记录将保留。",
        "删除确认",
        { type: "warning" },
      );
    } catch {
      return;
    }
    const result = await deleteSampleRecord("receipt-plans", id);
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    ElMessage.success("已删除");
    await refreshLedger();
  } catch {
    ElMessage.error("删除失败，请刷新核对后重试");
  } finally {
    deletingPlan.value = false;
  }
}

const statuses = [
  { value: "active", label: "进行中" },
  { value: "closed", label: "结项" },
  { value: "abandoned", label: "放弃" },
  { value: "voided", label: "废止" },
];
const rows = ref<ProjectRow[]>([]);
const visible = ref(false);
const ledger = ref(false);
const detail = ref<
  | (ProjectRow & {
      contracts: ProjectContract[];
      costs: Array<{
        id: string;
        cost_name: string;
        amount: number;
        occurred_on: string;
      }>;
    })
  | null
>(null);
const form = reactive({
  org_id: "",
  id: "",
  project_name: "",
  customer_name: "",
  status_code: "active",
  pipeline_amount: 0,
  flex_form: {} as Record<string, string | number | boolean | null>,
});
const contract = reactive({
  org_id: "",
  contract_no: "",
  currency_code: "CNY",
  total_amount: 0,
});
const plan = reactive({
  org_id: "",
  contract_id: "",
  plan_month: new Date().toISOString().slice(0, 7),
  amount: 0,
});
const receipt = reactive({
  org_id: "",
  contract_id: "",
  received_on: new Date().toISOString().slice(0, 10),
  amount: 0,
  remark: "",
});
const cost = reactive({
  org_id: "",
  cost_name: "",
  amount: 0,
  occurred_on: new Date().toISOString().slice(0, 10),
});

function statusLabel(code: string) {
  return statuses.find((item) => item.value === code)?.label || code;
}

async function load() {
  loading.value = true;
  try {
    const response = await listProjects();
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    rows.value = response.data;
    const fieldRows = await listFlexFields("project");
    if (fieldRows.code === 0) flexFields.value = fieldRows.data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, {
    org_id: "",
    id: "",
    project_name: "",
    customer_name: "",
    status_code: "active",
    pipeline_amount: 0,
    flex_form: {},
  });
  visible.value = true;
}

function openEdit(row: ProjectRow) {
  Object.assign(form, {
    org_id: row.org_id || "",
    id: row.id,
    project_name: row.project_name,
    customer_name: row.customer_name || "",
    status_code: row.status_code,
    pipeline_amount: row.pipeline_amount,
    flex_form: { ...(row.flex_form || {}) },
  });
  visible.value = true;
}

async function submitProject() {
  const response = await saveProject({
    ...form,
    customer_name: form.customer_name || null,
    id: form.id || undefined,
    flex_form: form.flex_form,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  visible.value = false;
  await load();
  if (detail.value && response.data.id === detail.value.id)
    await openLedger(response.data);
}

async function openLedger(row: { id: string }) {
  const response = await getProject(row.id);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  detail.value = response.data;
  for (const child of [contract, plan, receipt, cost])
    child.org_id = response.data.org_id || "";
  plan.contract_id = response.data.contracts[0]?.id || "";
  receipt.contract_id = plan.contract_id;
  ledger.value = true;
}

async function refreshLedger() {
  if (detail.value) await openLedger(detail.value);
  await load();
}

async function submitContract() {
  if (!detail.value) return;
  const response = await createContract(detail.value.id, contract);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  contract.contract_no = "";
  contract.total_amount = 0;
  await refreshLedger();
}

async function submitPlan() {
  const response = await createReceiptPlan(plan.contract_id, {
    plan_month: plan.plan_month,
    amount: plan.amount,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  await refreshLedger();
}

async function submitReceipt() {
  const response = await createReceipt(receipt.contract_id, {
    received_on: receipt.received_on,
    amount: receipt.amount,
    remark: receipt.remark,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  receipt.amount = 0;
  receipt.remark = "";
  await refreshLedger();
}

async function submitCost() {
  if (!detail.value) return;
  const response = await createProjectCost(detail.value.id, cost);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  cost.cost_name = "";
  cost.amount = 0;
  await refreshLedger();
}

onMounted(load);
const loading = ref(false);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "project_name", label: "项目", minWidth: "140" },
  { prop: "customer_name", label: "客户", width: "140" },
  { label: "状态", width: "90", slot: "cell0_2" },
  {
    prop: "pipeline_amount",
    label: "管道（元）",
    width: "120",
    align: "right",
  },
  { prop: "receivable_cny", label: "人民币应收", width: "120" },
  { prop: "receivable_usd", label: "美元应收", width: "110" },
  { prop: "labor_cost", label: "人力成本", width: "110", align: "right" },
  { prop: "direct_cost", label: "直接成本", width: "110", align: "right" },
  { prop: "gross_profit_cny", label: "人民币毛利", width: "120" },
  ...flexFields.value
    .filter((field) => field.is_active)
    .map((field) => ({
      label: field.field_name,
      minWidth: 120,
      formatter: (row: ProjectRow) =>
        flexDisplay(row.flex_form?.[field.field_key], field.value_type_code),
    })),
  {
    prop: "remark",
    label: "来源备注 / 待确认",
    minWidth: "240",
    showOverflowTooltip: true,
  },
  { label: "操作", width: "140", slot: "cell0_10" },
]);
const tableColumns1 = computed<TableColumnList>(() => [
  { prop: "contract_no", label: "合同编号" },
  { prop: "currency_code", label: "币种", width: "80" },
  { prop: "total_amount", label: "总价", align: "right" },
  { prop: "received_amount", label: "已收", align: "right" },
  { prop: "receivable_amount", label: "应收", align: "right" },
  { label: "计划", slot: "cell1_5" },
  { label: "到账", slot: "cell1_6" },
]);
const tableColumns2 = computed<TableColumnList>(() => [
  { prop: "occurred_on", label: "日期", width: "120" },
  { prop: "cost_name", label: "直接成本", align: "right" },
  { prop: "amount", label: "金额（元）", align: "right" },
]);
</script>

<template>
  <section class="sample-page">
    <BusinessTable
      :data="rows"
      :loading="loading"
      :columns="tableColumns0"
      delete-resource="projects"
      title="项目台账"
      @refresh="load"
    >
      <template #buttons
        ><el-button type="primary" @click="openCreate"
          >新建项目</el-button
        ></template
      >
      <template #cell0_2="{ row }"
        ><el-tag
          :type="row.status_code === 'active' ? 'primary' : 'info'"
          effect="plain"
          >{{ statusLabel(row.status_code) }}</el-tag
        ></template
      >
      <template #cell0_10="{ row }">
        <el-button link type="primary" @click="openEdit(row as ProjectRow)"
          >编辑</el-button
        >
        <el-button link type="primary" @click="openLedger(row as ProjectRow)"
          >合同与回款</el-button
        >
      </template>
    </BusinessTable>
    <p class="mt-3 text-sm text-gray-500">
      应收 = 合同总价 − 已收款，人民币和美元分开。毛利 = 人民币已收款 −
      工资归集的企业成本 − 直接成本。美元不换算。
    </p>

    <el-dialog v-model="visible" title="项目" width="520px">
      <el-form label-width="90px"
        ><OrganizationField v-model="form.org_id" :disabled="!!form.id" />
        <el-form-item label="名称"
          ><el-input v-model="form.project_name"
        /></el-form-item>
        <el-form-item label="客户"
          ><el-input v-model="form.customer_name"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-select v-model="form.status_code"
            ><el-option
              v-for="item in statuses"
              :key="item.value"
              :label="item.label"
              :value="item.value" /></el-select
        ></el-form-item>
        <el-form-item label="管道金额"
          ><el-input-number
            v-model="form.pipeline_amount"
            :min="0"
            :precision="2"
        /></el-form-item>
        <FlexFields
          v-model="form.flex_form"
          form-key="project"
          @fields="flexFields = $event"
        />
      </el-form>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" @click="submitProject"
          >保存</el-button
        ></template
      >
    </el-dialog>

    <el-dialog
      v-model="ledger"
      :title="detail ? detail.project_name : '项目'"
      width="920px"
    >
      <template v-if="detail">
        <p class="mb-3 text-sm">
          已收人民币 {{ detail.received_cny }}，应收人民币
          {{ detail.receivable_cny }}，应收美元
          {{ detail.receivable_usd }}，人力成本
          {{ detail.labor_cost }}，直接成本 {{ detail.direct_cost }}，毛利
          {{ detail.gross_profit_cny }}。
        </p>
        <BusinessTable
          :organization-filter-visible="false"
          :data="detail.contracts"
          :loading="loading"
          :columns="tableColumns1"
          delete-resource="contracts"
          title="合同与回款"
          @refresh="refreshLedger"
          :searchable="false"
        >
          <template #cell1_5="{ row }">
            <div v-for="item in row.plans" :key="item.id">
              {{ item.plan_month.slice(0, 7) }} {{ item.amount }}
              <el-button
                link
                type="danger"
                :disabled="deletingPlan"
                @click="deletePlan(item.id)"
                >删除</el-button
              >
            </div>
          </template>
          <template #cell1_6="{ row }">{{
            row.receipts
              .map(
                (item: { received_on: string; amount: number }) =>
                  `${item.received_on} ${item.amount}`,
              )
              .join("；")
          }}</template>
        </BusinessTable>
        <el-collapse class="business-entry-form"
          ><el-collapse-item title="新增合同" name="entry-0"
            ><el-form inline class="mt-4"
              ><OrganizationField
                v-model="contract.org_id"
                disabled
              /><el-form-item label="合同编号"
                ><el-input
                  v-model="contract.contract_no"
                  placeholder="合同编号"
                  style="width: 140px"
              /></el-form-item>
              <el-form-item label="币种"
                ><el-select
                  v-model="contract.currency_code"
                  style="width: 110px"
                  ><el-option label="人民币" value="CNY" /><el-option
                    label="美元"
                    value="USD" /></el-select
              ></el-form-item>
              <el-form-item label="合同总额"
                ><el-input-number
                  v-model="contract.total_amount"
                  :min="0"
                  :precision="2"
              /></el-form-item>
              <el-form-item label=""
                ><el-button @click="submitContract"
                  >添加合同</el-button
                ></el-form-item
              ></el-form
            ></el-collapse-item
          ></el-collapse
        >
        <el-collapse class="business-entry-form"
          ><el-collapse-item title="添加回款计划" name="entry-1"
            ><el-form inline
              ><OrganizationField v-model="plan.org_id" disabled /><el-form-item
                label="合同"
                ><el-select
                  v-model="plan.contract_id"
                  placeholder="合同"
                  style="width: 180px"
                  ><el-option
                    v-for="item in detail.contracts"
                    :key="item.id"
                    :label="item.contract_no"
                    :value="item.id" /></el-select
              ></el-form-item>
              <el-form-item label="计划月份"
                ><el-date-picker
                  v-model="plan.plan_month"
                  type="month"
                  value-format="YYYY-MM"
              /></el-form-item>
              <el-form-item label="金额（元）"
                ><el-input-number v-model="plan.amount" :min="0" :precision="2"
              /></el-form-item>
              <el-form-item label=""
                ><el-button :disabled="!plan.contract_id" @click="submitPlan"
                  >添加回款计划</el-button
                ></el-form-item
              ></el-form
            ></el-collapse-item
          ></el-collapse
        >
        <el-collapse class="business-entry-form"
          ><el-collapse-item title="登记实际回款" name="entry-2"
            ><el-form inline
              ><OrganizationField
                v-model="receipt.org_id"
                disabled
              /><el-form-item label="合同"
                ><el-select
                  v-model="receipt.contract_id"
                  placeholder="合同"
                  style="width: 180px"
                  ><el-option
                    v-for="item in detail.contracts"
                    :key="item.id"
                    :label="item.contract_no"
                    :value="item.id" /></el-select
              ></el-form-item>
              <el-form-item label="收款日期"
                ><el-date-picker
                  v-model="receipt.received_on"
                  type="date"
                  value-format="YYYY-MM-DD"
              /></el-form-item>
              <el-form-item label="金额（元）"
                ><el-input-number
                  v-model="receipt.amount"
                  :min="0"
                  :precision="2"
              /></el-form-item>
              <el-form-item label="备注"
                ><el-input
                  v-model="receipt.remark"
                  placeholder="备注"
                  style="width: 140px"
              /></el-form-item>
              <el-form-item label=""
                ><el-button
                  :disabled="!receipt.contract_id"
                  @click="submitReceipt"
                  >登记收款</el-button
                ></el-form-item
              ></el-form
            ></el-collapse-item
          ></el-collapse
        >
        <BusinessTable
          :organization-filter-visible="false"
          :data="detail.costs"
          class="mt-4"
          :loading="loading"
          :columns="tableColumns2"
          delete-resource="project-costs"
          title="项目直接成本"
          @refresh="refreshLedger"
          :searchable="false"
        >
        </BusinessTable>
        <el-collapse class="business-entry-form"
          ><el-collapse-item title="新增项目成本" name="entry-3"
            ><el-form inline class="mt-3"
              ><OrganizationField v-model="cost.org_id" disabled /><el-form-item
                label="费用名称"
                ><el-input
                  v-model="cost.cost_name"
                  placeholder="费用名称"
                  style="width: 160px"
              /></el-form-item>
              <el-form-item label="金额（元）"
                ><el-input-number v-model="cost.amount" :min="0" :precision="2"
              /></el-form-item>
              <el-form-item label="发生日期"
                ><el-date-picker
                  v-model="cost.occurred_on"
                  type="date"
                  value-format="YYYY-MM-DD"
              /></el-form-item>
              <el-form-item label=""
                ><el-button @click="submitCost"
                  >添加直接成本</el-button
                ></el-form-item
              ></el-form
            ></el-collapse-item
          ></el-collapse
        >
      </template>
    </el-dialog>
  </section>
</template>
