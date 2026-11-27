<script setup lang="ts">
import {
  uploadSelectedFiles,
  getFileUrl,
  type FileItem,
} from "@/api/systemFile";
import type { UploadUserFile } from "element-plus";
import { watch as watchFormOrganization } from "vue";

import OrganizationField from "../components/OrganizationField.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, reactive, ref, computed, watch } from "vue";
import { useOrganizationLifetime } from "@plugins/sample_app/web/src/api/sample_appContext";
import { ElMessage } from "element-plus";
import {
  useSampleApi,
  type CashAccount,
  type CashCheckpoint,
  type CashEntry,
  type EmployeeOption,
  type FixedCostRow,
  type LoanRow,
  type LoanRepayment,
  type ReimbursementRow,
} from "@plugins/sample_app/web/src/api/sample_app";
const {
  chargeFixedCost,
  createCashAccount,
  createCashBalance,
  createCashEntry,
  createFixedCost,
  createLoan,
  createReimbursement,
  addReimbursementFiles,
  actReimbursement,
  getCashLedger,
  importCashEntries,
  listEmployees,
  listFixedCosts,
  listLoans,
  listLoanRepayments,
  listReimbursements,
  repayLoan,
} = useSampleApi();

const invoiceFiles = ref<UploadUserFile[]>([]);
const attachmentClaim = ref<ReimbursementRow | null>(null);
const attachmentDialog = ref(false);
const invoiceOptions = {
  maxBytes: 20 * 1024 * 1024,
  types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
};
async function uploadInvoices() {
  const ids: string[] = [];
  for (const file of invoiceFiles.value) {
    const [id] = await uploadSelectedFiles(
      [file],
      "sample_app_invoice",
      invoiceOptions,
    );
    // 单据保存失败时复用已完成上传，避免重试产生重复附件。
    file.response = { id };
    ids.push(id);
  }
  return ids;
}
async function openInvoice(file: FileItem) {
  const result = await getFileUrl(file.id);
  if (result.code === 0)
    window.open(result.data.url, "_blank", "noopener,noreferrer");
}
function showInvoices(row: ReimbursementRow) {
  attachmentClaim.value = row;
  invoiceFiles.value = [];
  attachmentDialog.value = true;
}
async function appendInvoices() {
  if (!attachmentClaim.value || !invoiceFiles.value.length || saving.value)
    return;
  saving.value = true;
  try {
    const ids = await uploadInvoices();
    const result = await addReimbursementFiles(attachmentClaim.value.id, ids);
    if (result.code !== 0) throw new Error(result.message);
    attachmentDialog.value = false;
    await reload();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "附件保存失败");
  } finally {
    saving.value = false;
  }
}
const importDialog = ref(false);
const cashImport = reactive({ org_id: "" });
const month = ref<string | null>(null);
const debtMonth = ref<string | null>(null);
const claimMonth = ref<string | null>(null);
const claimOrg = ref("");
const claimPage = ref(1);
const claimPageSize = ref(20);
const claimTotal = ref(0);
const claimKeyword = ref("");
const matchesMonth = (date: string, period: string | null) =>
  !period || date?.slice(0, 7) === period;
const accounts = ref<CashAccount[]>([]);
const entries = ref<CashEntry[]>([]);
const checkpoints = ref<CashCheckpoint[]>([]);

const employees = ref<EmployeeOption[]>([]);
const loans = ref<LoanRow[]>([]);
const reimbursements = ref<ReimbursementRow[]>([]);
const costs = ref<FixedCostRow[]>([]);
const incomeCategories = [
  ["project_receipt", "项目回款"],
  ["outsourcing_income", "外包收入"],
  ["commission", "返佣"],
  ["interest", "利息"],
  ["other_income", "其他收入"],
];
const expenseCategories = [
  ["payroll_social", "工资社保"],
  ["fee_interest", "手续费利息"],
  ["other_expense", "其他支出"],
];
const fixedCategories = [
  ["cloud", "云资源"],
  ["rent", "房租"],
  ["property", "物业"],
  ["heating", "供暖"],
  ["other", "其他"],
];
const categoryLabel: Record<string, string> = Object.fromEntries([
  ...incomeCategories,
  ...expenseCategories,
  ["loan_repayment", "借款还款"],
  ["loan_disbursement", "个人借款"],
  ["employee_payable_settlement", "偿还个人往来欠款"],
  ["reimbursement", "报销"],
  ["fixed_cost", "固定支出"],
]);
const account = reactive({
  org_id: "",
  account_name: "",
  account_type_code: "bank",
  opening_balance: 0,
  opening_on: new Date().toISOString().slice(0, 10),
});
const entry = reactive({
  org_id: "",
  account_id: "",
  occurred_on: new Date().toISOString().slice(0, 10),
  direction_code: "income",
  category_code: "other_income",
  amount: 0,
  summary: "",
});
const checkpoint = reactive({
  org_id: "",
  account_id: "",
  balance_on: new Date().toISOString().slice(0, 10),
  balance_kind_code: "month_end",
  amount: 0,
});
const loan = reactive({
  org_id: "",
  debt_type_code: "company_payable" as LoanRow["debt_type_code"],
  employee_id: "",
  account_id: "",
  amount: 0,
  borrowed_on: new Date().toISOString().slice(0, 10),
  remark: "",
});
const repayment = reactive({
  org_id: "",
  loan_id: "",
  account_id: "",
  amount: 0,
  repaid_on: new Date().toISOString().slice(0, 10),
  request_key: "",
});
const debtTypeFilter = ref("");
const debtStatusFilter = ref("");
const debtDialog = ref(false);
const repaymentDialog = ref(false);
const repaymentHistoryDialog = ref(false);
const debtSubmitting = ref(false);
const repaymentSubmitting = ref(false);
const repaymentHistoryLoading = ref(false);
const selectedDebt = ref<LoanRow | null>(null);
const repaymentHistory = ref<LoanRepayment[]>([]);
const debtTypeLabels = {
  company_payable: "公司欠往来方",
  employee_loan: "往来方欠公司",
};
const debtStatusLabels = {
  unpaid: "未偿还",
  partial: "部分偿还",
  settled: "已结清",
};
const filteredDebts = computed(() =>
  loans.value.filter(
    (row) =>
      matchesMonth(row.borrowed_on, debtMonth.value) &&
      (!debtTypeFilter.value || row.debt_type_code === debtTypeFilter.value) &&
      (!debtStatusFilter.value ||
        row.repayment_status_code === debtStatusFilter.value),
  ),
);

function openDebt() {
  Object.assign(loan, {
    debt_type_code: "company_payable",
    employee_id: "",
    account_id: "",
    amount: 0,
    borrowed_on: new Date().toISOString().slice(0, 10),
    remark: "",
  });
  debtDialog.value = true;
}

function openRepayment(row: LoanRow) {
  selectedDebt.value = row;
  Object.assign(repayment, {
    org_id: row.org_id || "",
    loan_id: row.id,
    account_id: "",
    amount: row.outstanding_amount,
    repaid_on: new Date().toISOString().slice(0, 10),
    request_key: crypto.randomUUID(),
  });
  repaymentDialog.value = true;
}

async function submitDebt() {
  if (debtSubmitting.value || !isCurrentOrganization()) return;
  if (
    !loan.employee_id ||
    !loan.borrowed_on ||
    loan.amount <= 0 ||
    (loan.debt_type_code === "employee_loan" && !loan.account_id)
  ) {
    ElMessage.warning("请选择往来对象，填写日期、正数金额及必要的借出账户");
    return;
  }
  debtSubmitting.value = true;
  try {
    const response = await createLoan({
      ...loan,
      account_id:
        loan.debt_type_code === "company_payable" ? null : loan.account_id,
    });
    if (!isCurrentOrganization()) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    debtDialog.value = false;
    ElMessage.success("往来款已登记");
    await reload();
  } catch {
    if (isCurrentOrganization()) ElMessage.error("登记失败，请核对后重试");
  } finally {
    debtSubmitting.value = false;
  }
}

async function submitRepayment() {
  if (
    repaymentSubmitting.value ||
    !selectedDebt.value ||
    !isCurrentOrganization()
  )
    return;
  if (
    !repayment.account_id ||
    !repayment.repaid_on ||
    repayment.amount <= 0 ||
    repayment.amount > selectedDebt.value.outstanding_amount
  ) {
    ElMessage.warning("请选择收付账户、日期，金额须大于0且不超过未还余额");
    return;
  }
  repaymentSubmitting.value = true;
  try {
    const response = await repayLoan(repayment.loan_id, repayment);
    if (!isCurrentOrganization()) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    repaymentDialog.value = false;
    ElMessage.success("已登记本次还款并生成资金流水");
    await reload();
  } catch {
    if (isCurrentOrganization())
      ElMessage.error(
        "登记失败或结果尚未确认，可使用本次表单重试，系统会防止重复记账",
      );
  } finally {
    repaymentSubmitting.value = false;
  }
}

let repaymentHistoryRequest = 0;
async function showRepaymentHistory(row: LoanRow) {
  const request = ++repaymentHistoryRequest;
  selectedDebt.value = row;
  repaymentHistory.value = [];
  repaymentHistoryDialog.value = true;
  repaymentHistoryLoading.value = true;
  try {
    const response = await listLoanRepayments(row.id);
    if (!isCurrentOrganization() || request !== repaymentHistoryRequest) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    repaymentHistory.value = response.data;
  } catch {
    if (isCurrentOrganization() && request === repaymentHistoryRequest)
      ElMessage.error("还款明细加载失败");
  } finally {
    if (request === repaymentHistoryRequest)
      repaymentHistoryLoading.value = false;
  }
}
const claim = reactive({
  org_id: "",
  employee_id: "",
  amount: 0,
  subject: "",
  occurred_on: new Date().toISOString().slice(0, 10),
});
const fixed = reactive({
  org_id: "",
  account_id: "",
  cost_name: "",
  category_code: "cloud",
  monthly_amount: 0,
});
const postAccount = ref("");
const props = withDefaults(
  defineProps<{
    page?: "entries" | "accounts" | "balances" | "debts" | "claims" | "costs";
  }>(),
  { page: "entries" },
);
const formDialog = ref("");
const saving = ref(false);
const selectedClaim = ref<ReimbursementRow | null>(null);
const selectedCost = ref<FixedCostRow | null>(null);
const postingMonth = ref("");
const directionFilter = ref("");
const accountFilter = ref("");
const claimStatusFilter = ref("");
const differencesOnly = ref(false);
const filteredEntries = computed(() =>
  entries.value.filter(
    (row) =>
      (!directionFilter.value ||
        row.direction_code === directionFilter.value) &&
      (!accountFilter.value || row.account_id === accountFilter.value),
  ),
);
const filteredCheckpoints = computed(() =>
  checkpoints.value.filter(
    (row) => !differencesOnly.value || Math.abs(row.difference) >= 0.005,
  ),
);

const money = (value: number | string) =>
  Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const total = (rows: any[], field: string) =>
  rows.reduce((sum, row) => sum + Number(row[field] || 0), 0);
function flowHint(rows: CashEntry[]) {
  const income = total(
    rows.filter((row) => row.direction_code === "income"),
    "amount",
  );
  const expense = total(
    rows.filter((row) => row.direction_code === "expense"),
    "amount",
  );
  return (
    (month.value || "全部账期") +
    " · 收入 " +
    money(income) +
    " 元，支出 " +
    money(expense) +
    " 元，净流入 " +
    money(income - expense) +
    " 元"
  );
}
function debtHint(rows: LoanRow[]) {
  return (
    (debtMonth.value ? debtMonth.value + "发生" : "全部往来") +
    " · 公司待付 " +
    money(
      total(
        rows.filter((row) => row.debt_type_code === "company_payable"),
        "outstanding_amount",
      ),
    ) +
    " 元，往来方待还 " +
    money(
      total(
        rows.filter((row) => row.debt_type_code === "employee_loan"),
        "outstanding_amount",
      ),
    ) +
    " 元"
  );
}
function resetLedgerFilters() {
  month.value = null;
  directionFilter.value = "";
  accountFilter.value = "";
  differencesOnly.value = false;
  void reload();
}

const formTitles: Record<string, string> = {
  account: "新增资金账户",
  entry: "登记收支流水",
  checkpoint: "登记实际余额",
  claim: "新增费用报销",
  fixed: "新增固定成本",
  post: "报销付款入账",
  charge: "固定成本入账",
};
const today = () => new Date().toISOString().slice(0, 10);
function openForm(kind: string) {
  invoiceFiles.value = [];
  Object.assign(account, {
    account_name: "",
    account_type_code: "bank",
    opening_balance: 0,
    opening_on: today(),
  });
  Object.assign(entry, {
    account_id: "",
    occurred_on: today(),
    direction_code: "income",
    category_code: "other_income",
    amount: 0,
    summary: "",
  });
  Object.assign(checkpoint, {
    account_id: "",
    balance_on: today(),
    balance_kind_code: "month_end",
    amount: 0,
  });
  Object.assign(claim, {
    employee_id: "",
    amount: 0,
    subject: "",
    occurred_on: today(),
  });
  Object.assign(fixed, {
    account_id: "",
    cost_name: "",
    category_code: "cloud",
    monthly_amount: 0,
  });
  postAccount.value = "";
  formDialog.value = kind;
}
function openPost(row: ReimbursementRow) {
  selectedClaim.value = row;
  openForm("post");
}
function openCharge(row: FixedCostRow) {
  selectedCost.value = row;
  postingMonth.value = new Date().toISOString().slice(0, 7);
  openForm("charge");
}
async function submitForm() {
  if (saving.value || !isCurrentOrganization()) return;
  const kind = formDialog.value;
  const positive = (n: number) => Number.isFinite(n) && n > 0;
  const valid = {
    account:
      !!account.account_name.trim() &&
      !!account.opening_on &&
      Number.isFinite(account.opening_balance),
    entry: !!entry.account_id && !!entry.occurred_on && positive(entry.amount),
    checkpoint:
      !!checkpoint.account_id &&
      !!checkpoint.balance_on &&
      Number.isFinite(checkpoint.amount),
    claim:
      !!claim.employee_id &&
      !!claim.subject.trim() &&
      !!claim.occurred_on &&
      positive(claim.amount),
    fixed:
      !!fixed.account_id &&
      !!fixed.cost_name.trim() &&
      positive(fixed.monthly_amount),
    post: !!postAccount.value && !!selectedClaim.value,
    charge: !!postingMonth.value && !!selectedCost.value,
  }[kind];
  if (!valid) {
    ElMessage.warning("请完整填写信息，并核对金额和日期");
    return;
  }
  const actions: Record<
    string,
    () => Promise<{ code: number; message: string }>
  > = {
    account: () =>
      createCashAccount({
        ...account,
        account_name: account.account_name.trim(),
      }),
    entry: () => createCashEntry({ ...entry }),
    checkpoint: () => createCashBalance({ ...checkpoint }),
    claim: async () => {
      const file_ids = await uploadInvoices();
      return createReimbursement({
        ...claim,
        subject: claim.subject.trim(),
        file_ids,
      });
    },
    fixed: () =>
      createFixedCost({ ...fixed, cost_name: fixed.cost_name.trim() }),
    post: () =>
      actReimbursement(selectedClaim.value!.id, {
        action: "post",
        account_id: postAccount.value,
      }),
    charge: () => chargeFixedCost(selectedCost.value!.id, postingMonth.value),
  };
  saving.value = true;
  try {
    const response = await actions[kind]();
    if (!isCurrentOrganization()) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    formDialog.value = "";
    ElMessage.success("已保存");
    await reload();
  } catch {
    if (isCurrentOrganization())
      ElMessage.error("操作结果未确认，请刷新核对后再操作");
  } finally {
    saving.value = false;
  }
}
const isCurrentOrganization = useOrganizationLifetime();
const reimbursementStatus: Record<string, string> = {
  draft: "草稿",
  submitted: "已提交",
  posted: "已入账",
  rejected: "已驳回",
};

let ledgerRequest = 0;
async function loadLedger() {
  const request = ++ledgerRequest;
  const response = await getCashLedger(month.value);
  if (!isCurrentOrganization() || request !== ledgerRequest) return;
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  accounts.value = response.data.accounts;
  entries.value = response.data.entries;
  checkpoints.value = response.data.checkpoints;
}

async function loadRest() {
  const requests: Array<{
    label: string;
    load: () => Promise<any>;
    assign: (rows: any[]) => void;
  }> = [];
  if (["debts", "claims"].includes(props.page))
    requests.push({
      label: "员工选项",
      load: listEmployees,
      assign: (rows) => {
        employees.value = rows;
      },
    });
  if (props.page === "debts")
    requests.push({
      label: "借款与欠款",
      load: listLoans,
      assign: (rows) => {
        loans.value = rows;
      },
    });
  if (props.page === "costs")
    requests.push({
      label: "固定成本",
      load: listFixedCosts,
      assign: (rows) => {
        costs.value = rows;
      },
    });
  const results = await Promise.allSettled(
    requests.map((request) => request.load()),
  );
  if (!isCurrentOrganization()) return;
  results.forEach((result, index) => {
    if (result.status === "fulfilled" && result.value.code === 0)
      requests[index].assign(result.value.data);
    else ElMessage.error(requests[index].label + "加载失败，请刷新重试");
  });
}

async function loadClaims() {
  if (props.page !== "claims") return;
  const response = await listReimbursements({
    page: claimPage.value,
    page_size: claimPageSize.value,
    keyword: claimKeyword.value || undefined,
    status_code: claimStatusFilter.value || undefined,
    occurred_month: claimMonth.value || undefined,
    org_id: claimOrg.value || undefined,
  });
  if (!isCurrentOrganization()) return;
  if (response.code !== 0) throw new Error(response.message);
  reimbursements.value = response.data.items;
  claimTotal.value = response.data.total;
  claimPage.value = response.data.page;
  claimPageSize.value = response.data.page_size;
}

async function reload() {
  loading.value = true;
  try {
    await Promise.all([loadLedger(), loadRest(), loadClaims()]);
  } catch {
    if (isCurrentOrganization())
      ElMessage.error("部分资金数据加载失败，请刷新重试");
  } finally {
    loading.value = false;
  }
}

watch([claimPage, claimPageSize], () => {
  if (props.page !== "claims") return;
  void loadClaims().catch(() => {
    if (isCurrentOrganization()) ElMessage.error("费用报销加载失败，请刷新重试");
  });
});
watch([claimMonth, claimStatusFilter, claimOrg], () => {
  if (props.page !== "claims") return;
  claimPage.value = 1;
  void loadClaims().catch(() => {
    if (isCurrentOrganization()) ElMessage.error("费用报销加载失败，请刷新重试");
  });
});

async function run(action: () => Promise<{ code: number; message: string }>) {
  if (saving.value || !isCurrentOrganization()) return;
  saving.value = true;
  try {
    const response = await action();
    if (!isCurrentOrganization()) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    ElMessage.success("已保存");
    await reload();
  } catch {
    if (isCurrentOrganization()) ElMessage.error("操作失败，请刷新后重试");
  } finally {
    saving.value = false;
  }
}

function importFile(event: Event) {
  const selectedOrg = cashImport.org_id;
  if (!selectedOrg) {
    ElMessage.warning("请先选择导入资料所属组织");
    return;
  }
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async () => {
    if (!isCurrentOrganization()) return;
    try {
      const lines = String(reader.result || "")
        .replace(/^\uFEFF/, "")
        .split(/\r?\n/)
        .slice(1)
        .filter(Boolean);
      const rows = lines.map((line) => {
        const [
          occurred_on,
          account_name,
          direction_code,
          category_code,
          amount,
          summary,
        ] = line.split(",");
        return {
          occurred_on: occurred_on.trim(),
          account_name: account_name.trim(),
          direction_code: direction_code.trim(),
          category_code: category_code.trim(),
          amount: Number(amount),
          summary: summary?.trim(),
        };
      });
      const response = await importCashEntries(rows, selectedOrg);
      if (!isCurrentOrganization()) return;
      if (response.code !== 0) {
        ElMessage.error(response.message);
        return;
      }
      importDialog.value = false;
      ElMessage.success(`已导入 ${response.data.saved} 笔`);
      await reload();
    } catch {
      if (isCurrentOrganization())
        ElMessage.error("导入失败，请核对 CSV 格式后重试");
    }
  };
  reader.onerror = () => {
    if (isCurrentOrganization()) ElMessage.error("无法读取文件，请重试");
  };
  reader.readAsText(file, "utf-8");
}

function downloadTemplate() {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob(["\ufeff日期,账户,方向,分类,金额,摘要\n"], {
      type: "text/csv;charset=utf-8",
    }),
  );
  link.download = "资金流水导入模板.csv";
  link.click();
}

onMounted(reload);
const loading = ref(false);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "account_name", label: "账户" },
  { label: "类型", width: "110", slot: "cell0_1" },
  {
    prop: "month_income",
    label: month.value ? "账期收入" : "累计收入",
    align: "right",
  },
  {
    prop: "month_expense",
    label: month.value ? "账期支出" : "累计支出",
    align: "right",
  },
  { prop: "book_balance", label: "账面余额", align: "right" },
]);
const tableColumns1 = computed<TableColumnList>(() => [
  { prop: "occurred_on", label: "日期", width: "120" },
  { prop: "account_name", label: "账户" },
  { label: "方向", width: "80", slot: "cell1_2" },
  { label: "分类", slot: "cell1_3" },
  { prop: "amount", label: "金额", align: "right" },
  { prop: "summary", label: "摘要" },
]);
const tableColumns2 = computed<TableColumnList>(() => [
  { prop: "account_name", label: "账户" },
  { prop: "balance_on", label: "日期", width: "120", align: "right" },
  { label: "时点", width: "80", slot: "cell2_2" },
  { prop: "amount", label: "登记余额", align: "right" },
  { prop: "calculated_balance", label: "流水推算", align: "right" },
  { label: "差额（元）", slot: "difference", align: "right" },
]);
const tableColumns3 = computed<TableColumnList>(() => [
  { label: "欠款类型", slot: "debtType", minWidth: 140 },
  { prop: "full_name", label: "往来对象" },
  { prop: "employee_no", label: "编号" },
  { prop: "borrowed_on", label: "发生日期" },
  { prop: "amount", label: "原始金额", align: "right" },
  { prop: "repaid_amount", label: "已还", align: "right" },
  { prop: "outstanding_amount", label: "未还", align: "right" },
  { prop: "remark", label: "备注" },
  { label: "偿还状态", slot: "debtStatus", minWidth: 120 },
  { label: "操作", slot: "debtActions", width: 210 },
]);
const repaymentColumns: TableColumnList = [
  { prop: "repaid_on", label: "还款日期" },
  { prop: "account_name", label: "收付账户" },
  { prop: "amount", label: "还款金额（元）" },
];
const tableColumns4 = computed<TableColumnList>(() => [
  { prop: "full_name", label: "报销人" },
  { prop: "occurred_on", label: "发生日期", width: "120" },
  { prop: "subject", label: "事由" },
  { prop: "amount", label: "金额", align: "right" },
  { label: "状态", width: "90", slot: "cell4_4" },
  { label: "操作", width: 300, slot: "cell4_5" },
]);
const tableColumns5 = computed<TableColumnList>(() => [
  { prop: "cost_name", label: "费用" },
  { label: "付款账户", slot: "costAccount" },
  { label: "类别", slot: "cell5_1" },
  { prop: "monthly_amount", label: "每月金额", align: "right" },
  { label: "操作", width: "120", slot: "cell5_3" },
]);

watchFormOrganization(
  () => entry.org_id,
  () => {
    entry.account_id = "";
  },
  { flush: "sync" },
);
watchFormOrganization(
  () => checkpoint.org_id,
  () => {
    checkpoint.account_id = "";
  },
  { flush: "sync" },
);
watchFormOrganization(
  () => loan.org_id,
  () => {
    loan.employee_id = "";
    loan.account_id = "";
  },
  { flush: "sync" },
);
watchFormOrganization(
  () => repayment.org_id,
  () => {
    repayment.account_id = "";
  },
  { flush: "sync" },
);
watchFormOrganization(
  () => claim.org_id,
  () => {
    claim.employee_id = "";
  },
  { flush: "sync" },
);
watchFormOrganization(
  () => fixed.org_id,
  () => {
    fixed.account_id = "";
  },
  { flush: "sync" },
);
</script>

<template>
  <section class="sample-page funds-page">
    <div v-if="props.page === 'entries'">
      <BusinessTable
        :data="filteredEntries"
        :loading="loading"
        :columns="tableColumns1"
        title="收支流水"
        @refresh="reload"
        @reset="resetLedgerFilters"
        ><template #summary="{ rows }">{{ flowHint(rows) }}</template>
        <template #filters
          ><el-form-item label="账期："
            ><el-date-picker
              v-model="month"
              type="month"
              value-format="YYYY-MM"
              clearable
              placeholder="全部账期"
              style="width: 150px"
              @change="reload"
          /></el-form-item>
          <el-form-item label="资金账户："
            ><el-select
              v-model="accountFilter"
              clearable
              placeholder="全部账户"
              style="width: 160px"
              ><el-option
                v-for="item in accounts"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="收支方向："
            ><el-select
              v-model="directionFilter"
              clearable
              placeholder="全部方向"
              style="width: 140px"
              ><el-option label="收入" value="income" /><el-option
                label="支出"
                value="expense" /></el-select
          ></el-form-item>
        </template>
        <template #buttons
          ><el-button @click="downloadTemplate">下载模板</el-button
          ><label class="cursor-pointer text-sm"
            >导入 CSV<input
              class="hidden"
              type="file"
              accept=".csv,text/csv"
              @change="importFile" /></label
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openForm('entry')"
            >登记流水</el-button
          ></template
        >
        <template #cell1_2="{ row }"
          ><el-tag
            :type="row.direction_code === 'income' ? 'success' : 'danger'"
            effect="plain"
            >{{ row.direction_code === "income" ? "收入" : "支出" }}</el-tag
          ></template
        >
        <template #cell1_3="{ row }">{{
          categoryLabel[row.category_code] || row.category_code
        }}</template>
      </BusinessTable>
      <p class="funds-note">
        {{
          month ? month + " 账期" : "全部账期"
        }}的收支。项目合同回款请在项目页面登记；这里的手工流水只影响资金账。
      </p>
    </div>
    <div v-if="props.page === 'accounts'">
      <BusinessTable
        :data="accounts"
        :loading="loading"
        :columns="tableColumns0"
        delete-resource="accounts"
        title="资金账户"
        @refresh="reload"
        @reset="resetLedgerFilters"
        ><template #filters
          ><el-form-item label="账期："
            ><el-date-picker
              v-model="month"
              type="month"
              value-format="YYYY-MM"
              clearable
              placeholder="全部账期"
              style="width: 150px"
              @change="reload" /></el-form-item></template
        ><template #summary="{ rows }"
          >{{ month || "全部账期" }} · 共 {{ rows.length }} 个账户，{{
            month ? "月末" : "当前"
          }}账面余额 {{ money(total(rows, "book_balance")) }} 元</template
        >
        <template #buttons
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openForm('account')"
            >新增账户</el-button
          ></template
        >
        <template #cell0_1="{ row }"
          ><el-tag
            effect="plain"
            :type="row.account_type_code === 'treasury' ? 'warning' : 'primary'"
            >{{
              row.account_type_code === "treasury" ? "公司金库" : "银行账户"
            }}</el-tag
          ></template
        >
      </BusinessTable>
      <p class="funds-note">
        账户收支按筛选账期统计；未选账期时，显示全部收支与当前账面余额。
      </p>
    </div>
    <div v-if="props.page === 'balances'">
      <BusinessTable
        :data="filteredCheckpoints"
        :loading="loading"
        :columns="tableColumns2"
        delete-resource="account-balances"
        title="余额核对"
        @refresh="reload"
        @reset="resetLedgerFilters"
        ><template #filters
          ><el-form-item label="账期："
            ><el-date-picker
              v-model="month"
              type="month"
              value-format="YYYY-MM"
              clearable
              placeholder="全部账期"
              style="width: 150px"
              @change="reload" /></el-form-item
          ><el-form-item label="核对结果："
            ><el-switch
              v-model="differencesOnly"
              active-text="仅看有差额" /></el-form-item></template
        ><template #summary="{ rows }"
          >{{ month || "全部账期" }} · {{ rows.length }} 条核对记录，{{
            rows.filter((row) => Math.abs(row.difference) >= 0.005).length
          }}
          条存在差额</template
        >

        <template #buttons
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openForm('checkpoint')"
            >登记实际余额</el-button
          ></template
        >
        <template #cell2_2="{ row }">{{
          row.balance_kind_code === "mid_month" ? "月中" : "月末"
        }}</template>
        <template #difference="{ row }"
          ><el-tag
            :type="Math.abs(row.difference) < 0.005 ? 'success' : 'danger'"
            effect="plain"
            >{{ Number(row.difference).toFixed(2) }}</el-tag
          ></template
        >
      </BusinessTable>
      <p class="funds-note">
        登记银行或金库的实际余额，与流水推算值核对。登记核对记录不会自动调整流水。
      </p>
    </div>
    <div v-if="props.page === 'debts'">
      <BusinessTable
        :data="filteredDebts"
        :loading="loading"
        :columns="tableColumns3"
        title="个人往来款"
        @refresh="reload"
        @reset="
          debtMonth = null;
          debtTypeFilter = '';
          debtStatusFilter = '';
        "
        ><template #summary="{ rows }">{{ debtHint(rows) }}</template>
        <template #filters
          ><el-form-item label="发生账期："
            ><el-date-picker
              v-model="debtMonth"
              type="month"
              value-format="YYYY-MM"
              clearable
              placeholder="全部账期"
              style="width: 150px"
          /></el-form-item>
          <el-form-item label="欠款类型："
            ><el-select
              v-model="debtTypeFilter"
              clearable
              placeholder="全部类型"
              style="width: 170px"
              ><el-option
                v-for="(label, value) in debtTypeLabels"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
          <el-form-item label="偿还状态："
            ><el-select
              v-model="debtStatusFilter"
              clearable
              placeholder="全部状态"
              style="width: 170px"
              ><el-option
                v-for="(label, value) in debtStatusLabels"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
        </template>
        <template #buttons
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openDebt"
            >新增往来款</el-button
          ></template
        >
        <template #debtType="{ row }"
          ><el-tag
            :type="
              row.debt_type_code === 'company_payable' ? 'warning' : 'primary'
            "
            effect="plain"
            >{{
              debtTypeLabels[row.debt_type_code as keyof typeof debtTypeLabels]
            }}</el-tag
          ></template
        >
        <template #debtStatus="{ row }"
          ><el-tag
            :type="
              row.repayment_status_code === 'settled'
                ? 'success'
                : row.repayment_status_code === 'partial'
                  ? 'warning'
                  : 'info'
            "
            >{{
              debtStatusLabels[
                row.repayment_status_code as keyof typeof debtStatusLabels
              ]
            }}</el-tag
          ></template
        >
        <template #debtActions="{ row }"
          ><el-button
            link
            type="primary"
            :disabled="row.outstanding_amount <= 0"
            @click="openRepayment(row as LoanRow)"
            >登记还款</el-button
          ><el-button
            link
            type="primary"
            @click="showRepaymentHistory(row as LoanRow)"
            >还款明细</el-button
          ></template
        >
      </BusinessTable>
      <el-alert
        title="资金归属于所选公司，往来对象可在其他公司任职；公司欠往来方在实际付款时记支出，往来方欠公司在借出时记支出、归还时记收入。请勿与报销或工资支付重复登记。"
        type="info"
        :closable="false"
        show-icon
      />

      <el-dialog
        v-model="debtDialog"
        title="新增个人往来款"
        width="560px"
        :close-on-click-modal="false"
        :close-on-press-escape="!debtSubmitting"
        :show-close="!debtSubmitting"
        destroy-on-close
      >
        <el-form label-width="110px" :disabled="debtSubmitting"
          ><OrganizationField v-model="loan.org_id" />
          <el-form-item label="欠款类型" required
            ><el-select
              v-model="loan.debt_type_code"
              @change="loan.account_id = ''"
              ><el-option
                v-for="(label, value) in debtTypeLabels"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
          <el-form-item label="往来对象" required
            ><el-select
              v-model="loan.employee_id"
              filterable
              placeholder="选择往来对象，可选择其他授权公司的人员"
              ><el-option
                v-for="item in employees"
                :key="item.id"
                :label="
                  item.full_name + ' · ' + (item.org_name || '未标注任职公司')
                "
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item
            v-if="loan.debt_type_code === 'employee_loan'"
            label="借出账户"
            required
            ><el-select
              v-model="loan.account_id"
              placeholder="实际借出资金的账户"
              ><el-option
                v-for="item in accounts.filter(
                  (item) => !loan.org_id || item.org_id === loan.org_id,
                )"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="金额（元）" required
            ><el-input-number v-model="loan.amount" :min="0.01" :precision="2"
          /></el-form-item>
          <el-form-item label="发生日期" required
            ><el-date-picker
              v-model="loan.borrowed_on"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="欠款事由"
            ><el-input
              v-model="loan.remark"
              type="textarea"
              :rows="3"
              maxlength="255"
              placeholder="例如法人垫款、个人借款用途或待付款项"
          /></el-form-item>
        </el-form>
        <el-alert
          v-if="loan.debt_type_code === 'company_payable'"
          title="此处只登记公司对往来方的待付欠款，不代表公司收到借款，也不自动生成资金流水。"
          type="info"
          :closable="false"
        />
        <template #footer
          ><el-button :disabled="debtSubmitting" @click="debtDialog = false"
            >取消</el-button
          ><el-button
            type="primary"
            :loading="debtSubmitting"
            @click="submitDebt"
            >确认登记</el-button
          ></template
        >
      </el-dialog>

      <el-dialog
        v-model="repaymentDialog"
        title="登记还款"
        width="560px"
        :close-on-click-modal="false"
        :close-on-press-escape="!repaymentSubmitting"
        :show-close="!repaymentSubmitting"
        destroy-on-close
      >
        <template v-if="selectedDebt">
          <el-descriptions :column="1" border class="mb-4"
            ><el-descriptions-item label="往来对象">{{
              selectedDebt.full_name
            }}</el-descriptions-item
            ><el-descriptions-item label="欠款类型">{{
              debtTypeLabels[selectedDebt.debt_type_code]
            }}</el-descriptions-item
            ><el-descriptions-item label="尚未偿还"
              >{{
                money(selectedDebt.outstanding_amount)
              }}
              元</el-descriptions-item
            ></el-descriptions
          >
          <el-form label-width="110px" :disabled="repaymentSubmitting"
            ><OrganizationField v-model="repayment.org_id" disabled />
            <el-form-item
              :label="
                selectedDebt.debt_type_code === 'company_payable'
                  ? '付款账户'
                  : '收款账户'
              "
              required
              ><el-select
                v-model="repayment.account_id"
                placeholder="选择本次实际收付账户"
                ><el-option
                  v-for="item in accounts.filter(
                    (item) =>
                      !repayment.org_id || item.org_id === repayment.org_id,
                  )"
                  :key="item.id"
                  :label="item.account_name"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="本次还款（元）" required
              ><el-input-number
                v-model="repayment.amount"
                :min="0.01"
                :max="selectedDebt.outstanding_amount"
                :precision="2"
            /></el-form-item>
            <el-form-item label="还款日期" required
              ><el-date-picker
                v-model="repayment.repaid_on"
                type="date"
                value-format="YYYY-MM-DD"
            /></el-form-item>
          </el-form>
          <el-alert
            :title="
              selectedDebt.debt_type_code === 'company_payable'
                ? '确认实际付款后提交，系统将生成一笔资金支出。支持分次偿还，全部还清后自动结清。'
                : '确认实际收到还款后提交，系统将生成一笔资金收入。支持分次偿还，全部还清后自动结清。'
            "
            type="info"
            :closable="false"
          />
        </template>
        <template #footer
          ><el-button
            :disabled="repaymentSubmitting"
            @click="repaymentDialog = false"
            >取消</el-button
          ><el-button
            type="primary"
            :loading="repaymentSubmitting"
            @click="submitRepayment"
            >确认还款</el-button
          ></template
        >
      </el-dialog>

      <el-dialog
        v-model="repaymentHistoryDialog"
        title="还款明细"
        width="760px"
        destroy-on-close
      >
        <p v-if="selectedDebt" class="mb-4">
          {{ selectedDebt.full_name }} ·
          {{ debtTypeLabels[selectedDebt.debt_type_code] }} · 原始金额
          {{ money(selectedDebt.amount) }} 元
        </p>
        <BusinessTable
          :organization-filter-visible="false"
          title="实际还款记录"
          :data="repaymentHistory"
          :columns="repaymentColumns"
          :loading="repaymentHistoryLoading"
          :searchable="false"
          @refresh="selectedDebt && showRepaymentHistory(selectedDebt)"
        />
      </el-dialog>
    </div>

    <div v-if="props.page === 'claims'">
      <BusinessTable
        :data="reimbursements"
        :loading="loading"
        :columns="tableColumns4"
        delete-resource="reimbursements"
        title="费用报销"
        pagination-mode="server"
        v-model:organization="claimOrg"
        v-model:page="claimPage"
        v-model:page-size="claimPageSize"
        :total="claimTotal"
        @refresh="reload"
        @search="
          (value) => {
            claimKeyword = value;
            claimPage = 1;
            reload();
          }
        "
        @reset="
          claimMonth = null;
          claimStatusFilter = '';
          claimKeyword = '';
          claimOrg = '';
          claimPage = 1;
          reload();
        "
        ><template #summary="{ rows }"
          >{{ claimMonth || "全部账期" }} · 共 {{ claimTotal }} 笔，本页金额
          {{ money(total(rows, "amount")) }} 元</template
        >

        <template #filters
          ><el-form-item label="发生账期："
            ><el-date-picker
              v-model="claimMonth"
              type="month"
              value-format="YYYY-MM"
              clearable
              placeholder="全部账期"
              style="width: 150px" /></el-form-item
          ><el-form-item label="报销状态："
            ><el-select
              v-model="claimStatusFilter"
              clearable
              placeholder="全部状态"
              style="width: 160px"
              ><el-option
                v-for="(label, value) in reimbursementStatus"
                :key="value"
                :label="label"
                :value="value" /></el-select></el-form-item
        ></template>
        <template #buttons
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openForm('claim')"
            >新增报销</el-button
          ></template
        >
        <template #cell4_4="{ row }"
          ><el-tag
            :type="
              row.status_code === 'posted'
                ? 'success'
                : row.status_code === 'rejected'
                  ? 'danger'
                  : 'info'
            "
            >{{
              reimbursementStatus[row.status_code] || row.status_code
            }}</el-tag
          ></template
        >
        <template #cell4_5="{ row }">
          <el-button link type="primary" @click="showInvoices(row)"
            >发票（{{ row.attachments?.length || 0 }}）</el-button
          >
          <el-button
            v-if="['draft', 'rejected'].includes(row.status_code)"
            link
            type="primary"
            :disabled="saving"
            @click="run(() => actReimbursement(row.id, { action: 'submit' }))"
            >提交</el-button
          >
          <el-button
            v-if="row.status_code === 'submitted'"
            link
            type="danger"
            :disabled="saving"
            @click="run(() => actReimbursement(row.id, { action: 'reject' }))"
            >驳回</el-button
          >
          <el-button
            v-if="row.status_code === 'submitted'"
            link
            type="primary"
            :disabled="saving"
            @click="openPost(row)"
            >付款入账</el-button
          >
        </template>
      </BusinessTable>
      <p class="funds-note">
        报销人可在其他公司任职；费用和付款归属于所选公司。草稿提交后可付款入账，实际付款时生成资金支出。
      </p>
    </div>
    <div v-if="props.page === 'costs'">
      <BusinessTable
        :data="costs"
        :loading="loading"
        :columns="tableColumns5"
        delete-resource="fixed-costs"
        title="固定成本"
        @refresh="reload"
      >
        <template #buttons
          ><el-button
            type="primary"
            :icon="useRenderIcon('ri/add-line')"
            @click="openForm('fixed')"
            >新增固定成本</el-button
          ></template
        >
        <template #cell5_1="{ row }">{{
          Object.fromEntries(fixedCategories)[row.category_code] ||
          row.category_code
        }}</template>
        <template #costAccount="{ row }">{{
          accounts.find((item) => item.id === row.account_id)?.account_name ||
          "—"
        }}</template>
        <template #cell5_3="{ row }"
          ><el-button link type="primary" @click="openCharge(row)"
            >登记入账</el-button
          ></template
        >
      </BusinessTable>
      <p class="funds-note">
        维护每月固定支出，登记入账时单独选择实际付款月份。同一费用同一月份不会重复记账。
      </p>
    </div>

    <el-dialog
      v-model="importDialog"
      title="导入资金流水"
      width="520px"
      destroy-on-close
      ><el-form label-width="100px"
        ><OrganizationField v-model="cashImport.org_id" /><el-form-item
          label="CSV文件"
          ><input
            type="file"
            accept=".csv,text/csv"
            :disabled="!cashImport.org_id"
            @change="importFile" /></el-form-item></el-form
      ><el-alert
        title="文件中的账户按所选组织匹配，不会导入到其他组织。"
        type="info"
        :closable="false"
    /></el-dialog>
    <el-dialog
      :model-value="!!formDialog"
      :title="formTitles[formDialog]"
      width="560px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      destroy-on-close
      @update:model-value="
        (value) => {
          if (!value && !saving) formDialog = '';
        }
      "
    >
      <div v-if="formDialog === 'account'">
        <el-form label-width="115px" :disabled="saving"
          ><OrganizationField v-model="account.org_id" /><el-form-item
            label="账户名称"
            ><el-input v-model="account.account_name" placeholder="账户名称"
          /></el-form-item>
          <el-form-item label="账户类型"
            ><el-select v-model="account.account_type_code"
              ><el-option label="银行账户" value="bank" /><el-option
                label="公司金库"
                value="treasury" /></el-select
          ></el-form-item>
          <el-form-item label="期初余额（元）"
            ><el-input-number v-model="account.opening_balance" :precision="2"
          /></el-form-item>
          <el-form-item label="期初日期"
            ><el-date-picker
              v-model="account.opening_on"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
        </el-form>
      </div>
      <div v-if="formDialog === 'entry'">
        <el-form label-width="115px" :disabled="saving"
          ><OrganizationField v-model="entry.org_id" /><el-form-item
            label="资金账户"
            ><el-select v-model="entry.account_id" placeholder="账户"
              ><el-option
                v-for="item in accounts.filter(
                  (item) => !entry.org_id || item.org_id === entry.org_id,
                )"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="发生日期"
            ><el-date-picker
              v-model="entry.occurred_on"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="收支方向"
            ><el-select
              v-model="entry.direction_code"
              @change="
                entry.category_code =
                  entry.direction_code === 'income'
                    ? 'other_income'
                    : 'other_expense'
              "
              ><el-option label="收入" value="income" /><el-option
                label="支出"
                value="expense" /></el-select
          ></el-form-item>
          <el-form-item label="费用分类"
            ><el-select v-model="entry.category_code"
              ><el-option
                v-for="[value, label] in entry.direction_code === 'income'
                  ? incomeCategories
                  : expenseCategories"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
          <el-form-item label="金额（元）"
            ><el-input-number v-model="entry.amount" :min="0" :precision="2"
          /></el-form-item>
          <el-form-item label="摘要"
            ><el-input v-model="entry.summary" placeholder="摘要"
          /></el-form-item>
        </el-form>
      </div>
      <div v-if="formDialog === 'checkpoint'">
        <el-form label-width="115px" :disabled="saving"
          ><OrganizationField v-model="checkpoint.org_id" /><el-form-item
            label="资金账户"
            ><el-select v-model="checkpoint.account_id" placeholder="账户"
              ><el-option
                v-for="item in accounts.filter(
                  (item) =>
                    !checkpoint.org_id || item.org_id === checkpoint.org_id,
                )"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="余额时点"
            ><el-select v-model="checkpoint.balance_kind_code"
              ><el-option label="月末" value="month_end" /><el-option
                label="月中"
                value="mid_month" /></el-select
          ></el-form-item>
          <el-form-item label="核对日期"
            ><el-date-picker
              v-model="checkpoint.balance_on"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="金额（元）"
            ><el-input-number v-model="checkpoint.amount" :precision="2"
          /></el-form-item>
        </el-form>
      </div>
      <div v-if="formDialog === 'claim'">
        <el-form label-width="115px" :disabled="saving"
          ><OrganizationField v-model="claim.org_id" /><el-form-item
            label="报销人"
            ><el-select
              v-model="claim.employee_id"
              filterable
              placeholder="选择报销人，可跨任职公司"
              ><el-option
                v-for="item in employees"
                :key="item.id"
                :label="
                  item.full_name + ' · ' + (item.org_name || '未标注任职公司')
                "
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="报销事由"
            ><el-input
              v-model="claim.subject"
              maxlength="128"
              placeholder="事由"
          /></el-form-item>
          <el-form-item label="金额（元）"
            ><el-input-number v-model="claim.amount" :min="0" :precision="2"
          /></el-form-item>
          <el-form-item label="发生日期"
            ><el-date-picker
              v-model="claim.occurred_on"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="发票附件">
            <el-upload
              v-model:file-list="invoiceFiles"
              :auto-upload="false"
              :limit="50"
              accept=".pdf,.jpg,.jpeg,.png,.webp"
            >
              <el-button>选择发票</el-button>
              <template #tip
                ><div>
                  PDF、JPG、PNG、WebP；单份20MB，最多50份。提交前须有附件。
                </div></template
              >
            </el-upload>
          </el-form-item>
        </el-form>
      </div>
      <div v-if="formDialog === 'fixed'">
        <el-form label-width="115px" :disabled="saving"
          ><OrganizationField v-model="fixed.org_id" /><el-form-item
            label="费用名称"
            ><el-input v-model="fixed.cost_name" placeholder="费用名称"
          /></el-form-item>
          <el-form-item label="费用分类"
            ><el-select v-model="fixed.category_code"
              ><el-option
                v-for="[value, label] in fixedCategories"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
          <el-form-item label="资金账户"
            ><el-select v-model="fixed.account_id" placeholder="付款账户"
              ><el-option
                v-for="item in accounts.filter(
                  (item) => !fixed.org_id || item.org_id === fixed.org_id,
                )"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select
          ></el-form-item>
          <el-form-item label="月金额（元）"
            ><el-input-number
              v-model="fixed.monthly_amount"
              :min="0"
              :precision="2"
          /></el-form-item>
        </el-form>
      </div>

      <template v-if="formDialog === 'post' && selectedClaim"
        ><p class="mb-4">所属组织：{{ selectedClaim.org_name }}</p>
        <el-descriptions :column="1" border class="mb-4"
          ><el-descriptions-item label="员工">{{
            selectedClaim.full_name
          }}</el-descriptions-item
          ><el-descriptions-item label="报销事由">{{
            selectedClaim.subject
          }}</el-descriptions-item
          ><el-descriptions-item label="付款金额"
            >{{ money(selectedClaim.amount) }} 元</el-descriptions-item
          ></el-descriptions
        >
        <el-form label-width="115px" :disabled="saving"
          ><el-form-item label="付款账户" required
            ><el-select v-model="postAccount" placeholder="选择实际付款账户"
              ><el-option
                v-for="item in accounts.filter(
                  (item) => item.org_id === selectedClaim?.org_id,
                )"
                :key="item.id"
                :label="item.account_name"
                :value="item.id" /></el-select></el-form-item
        ></el-form>
        <el-alert
          title="确认实际付款后入账，系统将自动生成一笔报销支出。"
          type="info"
          :closable="false"
        />
      </template>
      <template v-if="formDialog === 'charge' && selectedCost">
        <el-descriptions :column="1" border
          ><el-descriptions-item label="所属组织">{{
            selectedCost.org_name
          }}</el-descriptions-item
          ><el-descriptions-item label="费用">{{
            selectedCost.cost_name
          }}</el-descriptions-item
          ><el-descriptions-item label="入账月份"
            ><el-date-picker
              v-model="postingMonth"
              type="month"
              value-format="YYYY-MM"
              :clearable="false"
              :disabled="saving" /></el-descriptions-item
          ><el-descriptions-item label="付款账户">{{
            accounts.find((item) => item.id === selectedCost!.account_id)
              ?.account_name || "—"
          }}</el-descriptions-item
          ><el-descriptions-item label="付款金额"
            >{{ money(selectedCost.monthly_amount) }} 元</el-descriptions-item
          ></el-descriptions
        >
        <el-alert
          class="mt-4"
          title="确认该月费用已实际支付后入账，系统将生成一笔固定成本支出。"
          type="info"
          :closable="false"
        />
      </template>
      <template #footer
        ><el-button :disabled="saving" @click="formDialog = ''">取消</el-button
        ><el-button type="primary" :loading="saving" @click="submitForm">{{
          ["post", "charge"].includes(formDialog) ? "确认付款入账" : "确认保存"
        }}</el-button></template
      >
    </el-dialog>
    <el-dialog
      v-model="attachmentDialog"
      title="报销发票"
      width="600px"
      :close-on-click-modal="false"
      :show-close="!saving"
    >
      <p class="mb-4">{{ attachmentClaim?.subject }}</p>
      <div v-for="file in attachmentClaim?.attachments || []" :key="file.id">
        <el-button link type="primary" @click="openInvoice(file)">{{
          file.file_name
        }}</el-button>
      </div>
      <el-upload
        v-if="
          attachmentClaim &&
          ['draft', 'rejected'].includes(attachmentClaim.status_code) &&
          (attachmentClaim.attachments?.length || 0) < 50
        "
        v-model:file-list="invoiceFiles"
        :auto-upload="false"
        :limit="50 - (attachmentClaim.attachments?.length || 0)"
        accept=".pdf,.jpg,.jpeg,.png,.webp"
        :disabled="saving"
      >
        <el-button :disabled="saving">补充发票（单份不超过20MB）</el-button>
      </el-upload>
      <template #footer
        ><el-button :disabled="saving" @click="attachmentDialog = false"
          >关闭</el-button
        ><el-button
          v-if="invoiceFiles.length"
          type="primary"
          :loading="saving"
          @click="appendInvoices"
          >保存附件</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>
<style scoped>
.funds-note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.funds-note {
  margin: 12px 0 0;
}
</style>
