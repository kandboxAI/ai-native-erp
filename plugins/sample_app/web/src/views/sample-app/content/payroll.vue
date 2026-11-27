<script setup lang="ts">
import { useBusinessContext } from "@plugins/sample_app/web/src/api/sample_appContext";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, ref, computed, unref, watch } from "vue";
import { useOrganizationLifetime } from "@plugins/sample_app/web/src/api/sample_appContext";
import { ElMessage, ElMessageBox } from "element-plus";
import { getFileUrl, type FileItem } from "@/api/systemFile";
import {
  useSampleApi,
  deleteSampleRecord,
  type PayrollBatch,
  type PayslipRow,
  type ProjectRow,
  type SoftwareClaimRow,
} from "@plugins/sample_app/web/src/api/sample_app";
const {
  calculatePayroll,
  closePayroll,
  exportPayroll,
  getPayroll,
  listProjects,
  listSoftwareClaims,
  updatePayslip,
} = useSampleApi();

const view = ref<"payroll" | "software">("payroll");
const claims = ref<SoftwareClaimRow[]>([]);
const claimPage = ref(1);
const claimPageSize = ref(20);
const claimTotal = ref(0);
const claimDetail = ref<SoftwareClaimRow | null>(null);
const claimDetailVisible = ref(false);
const claimStatusLabels: Record<string, string> = {
  preparing: "准备中",
  ready: "待员工确认",
  approved: "已确认·待核算",
  applied: "已写入工资",
};
const claimSourceLabels: Record<string, string> = {
  wechat: "微信",
  alipay: "支付宝",
  bank_card: "信用卡",
  invoice: "Invoice",
};
const claimSummary = computed(() => {
  const applied = claims.value.reduce(
    (sum, row) => sum + Number(row.applied_amount || 0),
    0,
  );
  return {
    count: claimTotal.value,
    pageApplied: applied.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
  };
});
function openClaimDetail(row: SoftwareClaimRow) {
  claimDetail.value = row;
  claimDetailVisible.value = true;
}
async function openClaimFile(file: FileItem) {
  const result = await getFileUrl(file.id);
  if (result.code === 0)
    window.open(result.data.url, "_blank", "noopener,noreferrer");
}

const context = useBusinessContext()!;
const month = ref(new Date().toISOString().slice(0, 7));
async function loadClaims() {
  const requestedMonth = month.value;
  try {
    const response = await listSoftwareClaims(requestedMonth, {
      page: claimPage.value,
      page_size: claimPageSize.value,
      org_id: context.operationOrg.value || undefined,
    });
    if (requestedMonth !== month.value || !isCurrentOrganization()) return;
    if (response.code !== 0) throw new Error(response.message);
    claims.value = response.data.items;
    claimTotal.value = response.data.total;
    claimPage.value = response.data.page;
    claimPageSize.value = response.data.page_size;
  } catch (error) {
    if (isCurrentOrganization())
      ElMessage.error(
        error instanceof Error ? error.message : "软件报销加载失败",
      );
  }
}
watch([claimPage, claimPageSize], () => {
  if (view.value === "software") void loadClaims();
});
watch(
  () => context.operationOrg.value,
  () => {
    claimPage.value = 1;
    if (view.value === "software") void loadClaims();
  },
);
const loadedStatus = ref("");
const status = computed(() => {
  if (!context.operationOrg.value) return loadedStatus.value;
  return (
    rows.value.find((row) => row.org_id === context.operationOrg.value)
      ?.payroll_status_code || ""
  );
});
const rows = ref<PayslipRow[]>([]);
const batches = ref<PayrollBatch[]>([]);
const loadedMonth = ref("");
const deletingDraft = ref(false);
const draftBatch = computed(() =>
  loadedMonth.value === month.value && !loading.value
    ? batches.value.find(
        (batch) =>
          batch.org_id === context.operationOrg.value &&
          batch.status_code === "draft",
      )
    : undefined,
);
const projects = ref<ProjectRow[]>([]);
const loading = ref(false);
const isCurrentOrganization = useOrganizationLifetime();
const editable = [
  "bonus_amount",
  "software_amount",
  "travel_amount",
  "other_amount",
  "adjust_amount",
  "other_deduction_amount",
] as const;

async function load() {
  const requestedMonth = month.value;
  void loadClaims();
  batches.value = [];
  loading.value = true;
  try {
    const response = await getPayroll(requestedMonth);
    if (requestedMonth !== month.value) return;
    if (response.code !== 0) throw new Error(response.message);
    loadedStatus.value = response.data.status_code;
    rows.value = response.data.lines;
    batches.value = response.data.batches || [];
    loadedMonth.value = requestedMonth;
    const projectResponse = await listProjects();
    if (projectResponse.code === 0) projects.value = projectResponse.data;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "工资册加载失败");
  } finally {
    loading.value = false;
  }
}

async function deleteDraft() {
  const batch = draftBatch.value;
  if (!batch || deletingDraft.value) return;
  deletingDraft.value = true;
  try {
    try {
      await ElMessageBox.confirm(
        `删除 ${batch.org_name} ${loadedMonth.value} 的草稿工资册？该批次的工资明细及手工调整也会删除。`,
        "删除草稿工资册",
        { type: "warning" },
      );
    } catch {
      return;
    }
    if (!isCurrentOrganization() || draftBatch.value?.id !== batch.id) return;
    const result = await deleteSampleRecord("payrolls", batch.id);
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    ElMessage.success("草稿工资册已删除");
    await load();
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : "删除草稿工资册失败",
    );
  } finally {
    deletingDraft.value = false;
  }
}

async function calculate() {
  if (!context.operationOrg.value) {
    ElMessage.warning("请先在筛选栏选择所属组织");
    return;
  }
  const response = await calculatePayroll(month.value);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  ElMessage.success(
    response.data.warnings.length
      ? response.data.warnings.join("；")
      : `已核算 ${response.data.count} 人`,
  );
  await load();
}

async function saveRow(row: PayslipRow) {
  const response = await updatePayslip(row.id, {
    project_id: row.project_id || null,
    task_name: row.task_name,
    bonus_amount: row.bonus_amount,
    software_amount: row.software_amount,
    travel_amount: row.travel_amount,
    other_amount: row.other_amount,
    adjust_amount: row.adjust_amount,
    tax_amount: row.tax_amount,
    other_deduction_amount: row.other_deduction_amount,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  ElMessage.success("已保存，并按填写金额重算应发与实发");
  await load();
}

async function closeMonth() {
  const closingOrg = context.operationOrg.value;
  if (!context.operationOrg.value) {
    ElMessage.warning("请先在筛选栏选择要封账的组织");
    return;
  }
  try {
    await ElMessageBox.confirm("封账后本月不能再重算。", "封账");
  } catch {
    return;
  }
  if (!isCurrentOrganization() || context.operationOrg.value !== closingOrg)
    return;
  const response = await closePayroll(month.value);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  ElMessage.success("已封账");
  await load();
}

async function download() {
  const response = await exportPayroll(month.value);
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob([response.data.content], { type: "text/csv;charset=utf-8" }),
  );
  link.download = response.data.filename;
  link.click();
}

onMounted(load);
const claimColumns = computed<TableColumnList>(() => [
  { prop: "employee_no", label: "编号", width: "120", fixed: true },
  { prop: "full_name", label: "姓名", width: "100", fixed: true },
  { prop: "period_month", label: "工资月", width: "100" },
  { prop: "item_count", label: "明细条数", width: "100", align: "right" },
  { prop: "claimed_amount", label: "申报合计", width: "120", align: "right" },
  { prop: "applied_amount", label: "计入工资", width: "120", align: "right" },
  { label: "状态", width: "140", slot: "claimStatus" },
  { label: "凭证", width: "110", slot: "claimFiles" },
  { label: "操作", width: "110", fixed: "right", slot: "claimActions" },
]);
const tableColumns0 = computed<TableColumnList>(() => [
  {
    prop: "payroll_status_code",
    label: "工资册状态",
    minWidth: 110,
    formatter: (_row, _column, value) =>
      value === "closed" ? "已封账" : "草稿",
  },
  { prop: "employee_no", label: "编号", width: "120", fixed: true },
  { prop: "full_name", label: "姓名", width: "100", fixed: true },
  { label: "项目", width: "180", slot: "cell0_2" },
  { prop: "base_amount", label: "基本", width: "100", align: "right" },
  { prop: "performance_amount", label: "绩效", width: "100", align: "right" },
  { prop: "overtime_amount", label: "加班费", width: "100", align: "right" },
  ...unref(editable).map((key) => ({
    label: {
      bonus_amount: "奖金",
      software_amount: "软件报销",
      travel_amount: "出差补贴",
      other_amount: "其他补贴",
      adjust_amount: "补扣",
      other_deduction_amount: "其他代扣",
    }[key],
    width: 170,
    slot: `cell0_6_${key}`,
  })),
  { prop: "gross_amount", label: "应发", width: "110", align: "right" },
  { label: "个税", width: 170, slot: "cell0_6_tax_amount" },
  {
    prop: "pension_employee_amount",
    label: "个人养老",
    width: "120",
    align: "right",
  },
  {
    prop: "unemployment_employee_amount",
    label: "个人失业",
    width: "120",
    align: "right",
  },
  {
    prop: "medical_employee_amount",
    label: "个人医疗",
    width: "120",
    align: "right",
  },
  {
    prop: "housing_employee_amount",
    label: "个人公积金",
    width: "120",
    align: "right",
  },
  { prop: "net_amount", label: "实发", width: "110", align: "right" },
  {
    prop: "pension_employer_amount",
    label: "企业养老",
    width: "120",
    align: "right",
  },
  {
    prop: "unemployment_employer_amount",
    label: "企业失业",
    width: "120",
    align: "right",
  },
  {
    prop: "injury_employer_amount",
    label: "企业工伤",
    width: "120",
    align: "right",
  },
  {
    prop: "medical_employer_amount",
    label: "企业医疗",
    width: "120",
    align: "right",
  },
  {
    prop: "housing_employer_amount",
    label: "企业公积金",
    width: "120",
    align: "right",
  },
  {
    prop: "employer_cost_amount",
    label: "企业成本",
    width: "120",
    align: "right",
  },
  { prop: "bank_name", label: "开户行", width: "140" },
  { prop: "account_no_masked", label: "账号", width: "160" },
  { label: "操作", width: "90", fixed: "right", slot: "cell0_13" },
]);
</script>

<template>
  <section class="sample-page">
    <el-radio-group v-model="view" class="mb-3">
      <el-radio-button value="payroll">工资明细</el-radio-button>
      <el-radio-button value="software">软件报销</el-radio-button>
    </el-radio-group>
    <BusinessTable
      v-if="view === 'payroll'"
      v-model:organization="context.operationOrg.value"
      :loading="loading"
      :data="rows"
      :columns="tableColumns0"
      title="工资核算"
      @refresh="load"
    >
      <template #filters
        ><el-form-item label="核算月份："
          ><el-date-picker
            v-model="month"
            type="month"
            value-format="YYYY-MM"
            @change="load" /></el-form-item
      ></template>
      <template #buttons
        ><el-tag v-if="status">{{
          status === "mixed"
            ? "各组织状态不同"
            : status === "closed"
              ? "已封账"
              : "草稿"
        }}</el-tag>
        <el-button
          type="primary"
          :disabled="!context.operationOrg.value || status === 'closed'"
          @click="calculate"
          >核算</el-button
        >
        <el-button :disabled="!context.operationOrg.value" @click="closeMonth"
          >封账</el-button
        >
        <el-button
          v-if="draftBatch"
          type="danger"
          plain
          :loading="deletingDraft"
          @click="deleteDraft"
          >删除草稿工资册</el-button
        >
        <el-button @click="download">导出</el-button></template
      >
      <template #cell0_2="{ row }"
        ><el-select
          v-model="row.project_id"
          clearable
          filterable
          :disabled="row.payroll_status_code === 'closed'"
          @change="
            (id) => {
              row.task_name =
                projects.find((item) => item.id === id)?.project_name ||
                row.task_name;
            }
          "
          ><el-option
            v-for="item in projects.filter(
              (item) => item.org_id === row.org_id,
            )"
            :key="item.id"
            :label="item.project_name"
            :value="item.id" /></el-select
      ></template>
      <template v-for="key in editable" :key="key" #[`cell0_6_${key}`]="{ row }"
        ><el-input-number
          v-model="row[key]"
          :min="0"
          :precision="2"
          :disabled="row.payroll_status_code === 'closed'"
          controls-position="right"
      /></template>
      <template #cell0_6_tax_amount="{ row }"
        ><el-input-number
          v-model="row.tax_amount"
          :min="0"
          :precision="2"
          :disabled="row.payroll_status_code === 'closed'"
          controls-position="right"
      /></template>
      <template #cell0_13="{ row }"
        ><el-button
          link
          type="primary"
          :disabled="row.payroll_status_code === 'closed'"
          @click="saveRow(row as PayslipRow)"
          >保存</el-button
        ></template
      >
    </BusinessTable>
    <BusinessTable
      v-else
      v-model:organization="context.operationOrg.value"
      v-model:page="claimPage"
      v-model:page-size="claimPageSize"
      :loading="loading"
      :data="claims"
      :columns="claimColumns"
      :total="claimTotal"
      pagination-mode="server"
      title="软件报销"
      @refresh="loadClaims"
    >
      <template #filters
        ><el-form-item label="工资月："
          ><el-date-picker
            v-model="month"
            type="month"
            value-format="YYYY-MM"
            :clearable="false"
            @change="
              () => {
                claimPage = 1;
                load();
              }
            " /></el-form-item
      ></template>
      <template #summary
        >{{ month }} · 共 {{ claimSummary.count }} 人提交，本页计入工资
        {{ claimSummary.pageApplied }} 元</template
      >
      <template #claimStatus="{ row }">{{
        claimStatusLabels[row.status_code] || row.status_code
      }}</template>
      <template #claimFiles="{ row }"
        >{{ row.attachments.length }} / {{ row.declared_file_count }}</template
      >
      <template #claimActions="{ row }"
        ><el-button link type="primary" @click="openClaimDetail(row)"
          >查看明细</el-button
        ></template
      >
    </BusinessTable>
    <el-dialog
      v-model="claimDetailVisible"
      title="软件报销明细"
      width="640px"
      destroy-on-close
    >
      <template v-if="claimDetail">
        <el-descriptions :column="2" border class="mb-4"
          ><el-descriptions-item label="姓名">{{
            claimDetail.full_name
          }}</el-descriptions-item
          ><el-descriptions-item label="工资月">{{
            claimDetail.period_month
          }}</el-descriptions-item
          ><el-descriptions-item label="申报合计"
            >{{ claimDetail.claimed_amount }} 元</el-descriptions-item
          ><el-descriptions-item label="计入工资"
            >{{ claimDetail.applied_amount }} 元</el-descriptions-item
          ></el-descriptions
        >
        <p class="mb-2">消费明细</p>
        <el-table :data="claimDetail.items" size="small" class="mb-4">
          <el-table-column prop="occurred_on" label="扣款/交易日" width="120" />
          <el-table-column prop="billing_month" label="所属工资月" width="110" />
          <el-table-column prop="merchant_name" label="商户" />
          <el-table-column label="来源" width="100">
            <template #default="{ row }">{{
              claimSourceLabels[row.source_code] || row.source_code
            }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="110" align="right" />
        </el-table>
        <p class="mb-2">凭证原件</p>
        <div
          v-for="file in claimDetail.attachments"
          :key="file.id"
          class="mb-1"
        >
          <el-button link type="primary" @click="openClaimFile(file)">{{
            file.file_name
          }}</el-button>
        </div>
        <p
          v-if="!claimDetail.attachments.length"
          class="text-sm text-gray-500"
        >
          {{
            claimDetail.status_code === "ready" ||
            claimDetail.status_code === "preparing"
              ? "凭证尚未经员工确认绑定，确认后显示原件。"
              : "暂无凭证原件。"
          }}
        </p>
      </template>
    </el-dialog>
  </section>
</template>
