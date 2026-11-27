import type { FileItem } from "@/api/systemFile";
import { http } from "@/utils/http";
import { useBusinessContext } from "./sample_appContext";
export type OrganizationRow = { org_id?: string; org_name?: string };
export type PayrollBatch = {
  id: string;
  org_id: string;
  org_name: string;
  status_code: string;
};
type Envelope<T> = { code: number; message: string; data: T };
export type PagedResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type FlexValueType = "string" | "number" | "date" | "boolean";
export type FlexField = {
  id: string;
  form_key: string;
  field_key: string;
  field_name: string;
  value_type_code: FlexValueType;
  is_required: boolean;
  sort_no: number;
  is_active: boolean;
};
export type FlexValues = Record<string, string | number | boolean | null>;

export function flexDisplay(value: unknown, valueType: FlexValueType) {
  if (value === null || value === undefined || value === "") return "—";
  if (valueType === "boolean") return value ? "是" : "否";
  return String(value);
}

export type EmployeeOption = {
  employment_end_on?: string | null;
  personnel_type_code: "internal" | "outsourced";
  project_id: string | null;
  id: string;
  employee_no: string;
  full_name: string;
  employment_status_code: string;
  hire_date: string | null;
  bank_name?: string;
  account_no_masked?: string;
  flex_form?: FlexValues;
} & OrganizationRow;

export type EmployeeAccountBinding = {
  employee_id: string;
  employee_name: string;
  user_id: string;
  account_name: string;
  is_active: boolean;
  org_id: string;
};

export type EmployeeAccountOption = {
  id: string;
  name: string;
  org_name: string;
};

export type PaySetting = {
  daily_wage_mode_code: string;
  standard_days: number;
  overtime_multiplier: number;
  tax_threshold: number;
} & OrganizationRow;

export type SocialPlan = {
  id: string;
  plan_name: string;
  pension_employer_rate: number;
  pension_employee_rate: number;
  unemployment_employer_rate: number;
  unemployment_employee_rate: number;
  injury_employer_rate: number;
  medical_employer_rate: number;
  medical_employee_rate: number;
  housing_employer_rate: number;
  housing_employee_rate: number;
} & OrganizationRow;

export type TaxBracket = {
  sort_no: number;
  min_amount: number;
  max_amount: number | null;
  rate: number;
  quick_deduction: number;
} & OrganizationRow;

export type AttendanceRow = {
  id?: string | null;
  employee_id: string;
  employee_no: string;
  full_name: string;
  expected_days: number;
  actual_days: number;
  overtime_days: number;
  warning: boolean;
} & OrganizationRow;

export type SalaryRow = {
  id: string;
  employee_id: string;
  employee_no?: string;
  full_name?: string;
  social_plan_id: string | null;
  social_base: number;
  base_amount: number;
  performance_amount: number;
  valid_from: string;
  valid_to: string | null;
} & OrganizationRow;

export type PayslipRow = {
  payroll_status_code?: string;
  id: string;
  project_id?: string | null;
  employee_no: string;
  full_name: string;
  task_name: string | null;
  base_amount: number;
  performance_amount: number;
  bonus_amount: number;
  overtime_amount: number;
  software_amount: number;
  travel_amount: number;
  other_amount: number;
  adjust_amount: number;
  gross_amount: number;
  tax_amount: number;
  pension_employee_amount: number;
  unemployment_employee_amount: number;
  medical_employee_amount: number;
  housing_employee_amount: number;
  pension_employer_amount: number;
  unemployment_employer_amount: number;
  injury_employer_amount: number;
  medical_employer_amount: number;
  housing_employer_amount: number;
  other_deduction_amount: number;
  net_amount: number;
  employer_cost_amount: number;
  bank_name: string;
  account_no_masked: string;
} & OrganizationRow;

export type ImportSourceRow = {
  id: string;
  source_name: string;
  sheet_name: string;
  row_no: number;
  source_cells: Record<string, string | number | null>;
  handling_key: string;
  handling_note: string;
} & OrganizationRow;

export type ProjectRow = {
  id: string;
  project_name: string;
  remark?: string | null;
  flex_form?: FlexValues;
  customer_name: string | null;
  status_code: string;
  pipeline_amount: number;
  labor_cost: number;
  direct_cost: number;
  received_cny: number;
  receivable_cny: number;
  receivable_usd: number;
  gross_profit_cny: number;
} & OrganizationRow;

export type ProjectContract = {
  id: string;
  contract_no: string;
  currency_code: string;
  total_amount: number;
  received_amount: number;
  receivable_amount: number;
  plans: Array<{ id: string; plan_month: string; amount: number }>;
  receipts: Array<{
    id: string;
    received_on: string | null;
    amount: number;
    remark: string | null;
  }>;
} & OrganizationRow;

export type CashAccount = {
  id: string;
  account_name: string;
  account_type_code: string;
  opening_balance: number;
  opening_on: string;
  month_income: number;
  month_expense: number;
  book_balance: number;
} & OrganizationRow;

export type CashEntry = {
  source_type_code?: string | null;
  source_id?: string | null;
  account_id: string;
  id: string;
  account_name: string;
  occurred_on: string;
  direction_code: string;
  category_code: string;
  amount: number;
  summary: string | null;
} & OrganizationRow;

export type CashCheckpoint = {
  id: string;
  account_name: string;
  balance_on: string;
  balance_kind_code: string;
  amount: number;
  calculated_balance: number;
  difference: number;
} & OrganizationRow;

export type LoanRow = {
  id: string;
  employee_id: string;
  employee_no?: string;
  full_name?: string;
  account_id: string | null;
  debt_type_code: "employee_loan" | "company_payable";
  repayment_status_code: "unpaid" | "partial" | "settled";
  amount: number;
  borrowed_on: string;
  repaid_amount: number;
  outstanding_amount: number;
  remark: string | null;
} & OrganizationRow;

export type SoftwareClaimItem = {
  occurred_on: string | null;
  billing_month: string;
  amount: number | string;
  merchant_name: string;
  source_code: "wechat" | "alipay" | "bank_card" | "invoice" | string;
  note?: string | null;
};

export type SoftwareClaimRow = {
  id: string;
  employee_id: string;
  employee_no: string;
  full_name: string;
  org_id: string;
  org_name?: string;
  period_month: string;
  status_code: "preparing" | "ready" | "approved" | "applied" | string;
  claimed_amount: number;
  applied_amount: number;
  item_count: number;
  items: SoftwareClaimItem[];
  declared_file_count: number;
  attachments: FileItem[];
  approved: boolean;
  payslip_id: string | null;
};

export type ReimbursementRow = {
  attachments: FileItem[];
  id: string;
  employee_no?: string;
  full_name?: string;
  subject: string;
  amount: number;
  status_code: string;
  occurred_on: string;
} & OrganizationRow;

export type FixedCostRow = {
  id: string;
  cost_name: string;
  category_code: string;
  monthly_amount: number;
  account_id: string;
  is_active: boolean;
} & OrganizationRow;

export type LoanRepayment = {
  id: string;
  account_id: string;
  account_name: string;
  amount: number;
  repaid_on: string;
} & OrganizationRow;

export const socialAmountLabels = {
  pension_employer_amount: "单位养老",
  pension_employee_amount: "个人养老",
  unemployment_employer_amount: "单位失业",
  unemployment_employee_amount: "个人失业",
  injury_employer_amount: "单位工伤",
  medical_employer_amount: "单位医疗",
  medical_employee_amount: "个人医疗",
  housing_employer_amount: "单位公积金",
  housing_employee_amount: "个人公积金",
} as const;
export type SocialAmountKey = keyof typeof socialAmountLabels;
export type SocialBasis = OrganizationRow & {
  id: string;
  employee_id: string;
  employee_no?: string;
  full_name?: string;
  social_plan_id: string;
  social_base: number;
  housing_base: number;
  valid_from: string;
  valid_to: string | null;
};
export type SocialLine = Record<SocialAmountKey, number> & {
  id: string;
  employee_id: string;
  full_name: string;
  employee_no: string;
  social_base_snapshot: number;
  housing_base_snapshot: number;
};
export type SocialBill = OrganizationRow & {
  id: string;
  bill_id: string | null;
  period_month: string;
  status_code: string;
  employer_amount: number;
  employee_amount: number;
  total_amount: number;
  paid_amount: number;
  recovered_amount: number;
  pending_recovery_amount: number;
  gross_amount: number;
  labor_cost_amount: number;
  payroll_net_amount: number;
  has_payroll: boolean;
  payroll_status_code: string;
  payroll_paid: boolean;
  is_paid: boolean;
};
export type SocialDetail = OrganizationRow & {
  id: string;
  status_code: string;
  period_month: string;
  lines: SocialLine[];
};
export type PaymentInput = OrganizationRow & {
  account_id: string;
  paid_on: string;
  cash_entry_id?: string | null;
};

export function createSampleApi(filterOrganization: () => string = () => "") {
  const get = <T>(url: string, params?: object) =>
    http.request<Envelope<T>>("get", url, {
      params: {
        ...params,
        ...((url === "/api/sample_app/pay-setting" ||
          url.endsWith("/export")) &&
        filterOrganization()
          ? { org_id: filterOrganization() }
          : {}),
      },
    });
  const send = <T>(method: "post" | "put", url: string, data?: object) => {
    const organizationAction = [
      "/api/sample_app/attendance",
      "/api/sample_app/pay-setting",
      "/api/sample_app/payrolls/calculate",
      "/api/sample_app/payrolls/close",
    ].includes(url);
    const selected =
      (data as OrganizationRow)?.org_id ||
      (organizationAction ? filterOrganization() : "");
    const clean = data ? ({ ...data } as Record<string, unknown>) : undefined;
    if (clean && !clean.org_id) delete clean.org_id;
    return http.request<Envelope<T>>(method, url, {
      data: clean,
      params: selected ? { org_id: selected } : {},
    });
  };
  const listOrganizations = () =>
    http.request<Envelope<Array<{ id: string; org_name: string }>>>(
      "get",
      "/api/sample_app/organizations",
    );

  const listImportHistory = () =>
    get<ImportSourceRow[]>("/api/sample_app/import-history");

  const getPluginStatus = () =>
    get<{ plugin_key: string; status: string }>("/api/sample_app/status");

  const listFlexFields = (form_key: string) =>
    get<FlexField[]>("/api/sample_app/flex-fields", { form_key });
  const createFlexField = (data: {
    form_key: string;
    field_key: string;
    field_name: string;
    value_type_code: FlexValueType;
    is_required: boolean;
  }) => send<FlexField>("post", "/api/sample_app/flex-fields", data);
  const updateFlexField = (
    id: string,
    data: { field_name: string; is_required: boolean; is_active: boolean },
  ) => send<FlexField>("put", `/api/sample_app/flex-fields/${id}`, data);

  const listEmployees = (
    personnel_type_code: "internal" | "outsourced" = "internal",
  ) =>
    get<EmployeeOption[]>("/api/sample_app/employees", { personnel_type_code });

  const listEmployeeAccountBindings = () =>
    get<EmployeeAccountBinding[]>("/api/sample_app/employee-account-bindings");
  const listEmployeeAccountOptions = (keyword = "") =>
    get<EmployeeAccountOption[]>("/api/sample_app/employee-account-options", {
      keyword,
    });
  const bindEmployeeAccount = (data: {
    user_id: string;
    employee_id: string;
    previous_user_id?: string;
  }) => send("put", "/api/sample_app/employee-account-bindings", data);
  const unbindEmployeeAccount = (user_id: string, employee_id: string) =>
    http.request<Envelope<{ unbound: boolean }>>(
      "delete",
      `/api/sample_app/employee-account-bindings/${user_id}`,
      { params: { employee_id } },
    );

  const saveEmployee = (data: {
    personnel_type_code?: "internal" | "outsourced";
    project_id?: string | null;
    id?: string;
    employee_no: string;
    full_name: string;
    employment_status_code: string;
    hire_date: string | null;
    bank_name?: string | null;
    account_no_masked?: string | null;
    flex_form?: FlexValues;
  }) =>
    data.id
      ? send<EmployeeOption>(
          "put",
          `/api/sample_app/employees/${data.id}`,
          data,
        )
      : send<EmployeeOption>("post", "/api/sample_app/employees", data);

  const listSocialPlans = () =>
    get<SocialPlan[]>("/api/sample_app/social-plans");
  const getPaySetting = () =>
    get<{ setting: PaySetting; plans: SocialPlan[]; brackets: TaxBracket[] }>(
      "/api/sample_app/pay-setting",
    );

  const savePaySetting = (data: PaySetting) =>
    send<PaySetting>("put", "/api/sample_app/pay-setting", data);

  const saveSocialPlan = (data: Omit<SocialPlan, "id"> & { id?: string }) =>
    data.id
      ? send<SocialPlan>("put", `/api/sample_app/social-plans/${data.id}`, data)
      : send<SocialPlan>("post", "/api/sample_app/social-plans", data);

  const listAttendance = (period_month: string) =>
    get<AttendanceRow[]>("/api/sample_app/attendance", { period_month });

  const saveAttendance = (
    period_month: string,
    rows: Array<
      Pick<
        AttendanceRow,
        | "employee_id"
        | "employee_no"
        | "expected_days"
        | "actual_days"
        | "overtime_days"
      >
    >,
  ) =>
    send<{ saved: number; warnings: string[] }>(
      "put",
      "/api/sample_app/attendance",
      { period_month, rows },
    );

  const listSalaries = () => get<SalaryRow[]>("/api/sample_app/salaries");

  const createSalary = (
    data: Omit<SalaryRow, "id" | "employee_no" | "full_name">,
  ) => send<SalaryRow>("post", "/api/sample_app/salaries", data);

  const calculatePayroll = (period_month: string) =>
    send<{ count: number; warnings: string[] }>(
      "post",
      "/api/sample_app/payrolls/calculate",
      { period_month },
    );

  const getPayroll = (period_month: string) =>
    get<{ status_code: string; lines: PayslipRow[]; batches: PayrollBatch[] }>(
      "/api/sample_app/payrolls",
      { period_month },
    );

  const updatePayslip = (
    id: string,
    data: Partial<
      Pick<
        PayslipRow,
        | "project_id"
        | "task_name"
        | "bonus_amount"
        | "software_amount"
        | "travel_amount"
        | "other_amount"
        | "adjust_amount"
        | "tax_amount"
        | "other_deduction_amount"
      >
    >,
  ) => send<PayslipRow>("put", `/api/sample_app/payslips/${id}`, data);

  const closePayroll = (period_month: string) =>
    send<{ status_code: string }>("post", "/api/sample_app/payrolls/close", {
      period_month,
    });

  const exportPayroll = (period_month: string) =>
    get<{ filename: string; content: string }>(
      "/api/sample_app/payrolls/export",
      { period_month },
    );

  const listProjects = () => get<ProjectRow[]>("/api/sample_app/projects");

  const saveProject = (data: {
    id?: string;
    project_name: string;
    customer_name?: string | null;
    status_code: string;
    pipeline_amount: number;
    flex_form?: FlexValues;
  }) =>
    data.id
      ? send<ProjectRow>("put", `/api/sample_app/projects/${data.id}`, data)
      : send<ProjectRow>("post", "/api/sample_app/projects", data);

  const getProject = (id: string) =>
    get<
      ProjectRow & {
        contracts: ProjectContract[];
        costs: Array<{
          id: string;
          cost_name: string;
          amount: number;
          occurred_on: string;
        }>;
      }
    >(`/api/sample_app/projects/${id}`);

  const createContract = (
    projectId: string,
    data: { contract_no: string; currency_code: string; total_amount: number },
  ) =>
    send<ProjectContract>(
      "post",
      `/api/sample_app/projects/${projectId}/contracts`,
      data,
    );

  const createReceiptPlan = (
    contractId: string,
    data: { plan_month: string; amount: number },
  ) => send("post", `/api/sample_app/contracts/${contractId}/plans`, data);

  const createReceipt = (
    contractId: string,
    data: { received_on: string; amount: number; remark?: string },
  ) => send("post", `/api/sample_app/contracts/${contractId}/receipts`, data);

  const createProjectCost = (
    projectId: string,
    data: { cost_name: string; amount: number; occurred_on: string },
  ) => send("post", `/api/sample_app/projects/${projectId}/costs`, data);

  const getCashLedger = (period_month?: string | null) =>
    get<{
      month_income: number;
      month_expense: number;
      month_net: number;
      accounts: CashAccount[];
      entries: CashEntry[];
      checkpoints: CashCheckpoint[];
    }>("/api/sample_app/cash-ledger", period_month ? { period_month } : {});

  const createCashAccount = (data: {
    account_name: string;
    account_type_code: string;
    opening_balance: number;
    opening_on: string;
  }) => send("post", "/api/sample_app/cash-accounts", data);

  const createCashEntry = (data: {
    account_id: string;
    occurred_on: string;
    direction_code: string;
    category_code: string;
    amount: number;
    summary?: string;
  }) => send("post", "/api/sample_app/cash-entries", data);

  const importCashEntries = (
    rows: Array<{
      account_name: string;
      occurred_on: string;
      direction_code: string;
      category_code: string;
      amount: number;
      summary?: string;
    }>,
    org_id?: string,
  ) =>
    send<{ saved: number }>("post", "/api/sample_app/cash-entries/import", {
      rows,
      org_id,
    });

  const createCashBalance = (data: {
    account_id: string;
    balance_on: string;
    balance_kind_code: string;
    amount: number;
  }) => send("post", "/api/sample_app/cash-balances", data);

  const listLoans = () => get<LoanRow[]>("/api/sample_app/loans");

  const createLoan = (data: {
    employee_id: string;
    account_id?: string | null;
    debt_type_code: "employee_loan" | "company_payable";
    amount: number;
    borrowed_on: string;
    remark?: string;
  }) => send("post", "/api/sample_app/loans", data);

  const repayLoan = (
    id: string,
    data: {
      account_id: string;
      amount: number;
      repaid_on: string;
      request_key?: string;
    },
  ) => send("post", `/api/sample_app/loans/${id}/repayments`, data);

  const listLoanRepayments = (id: string) =>
    get<LoanRepayment[]>(`/api/sample_app/loans/${id}/repayments`);

  const listSoftwareClaims = (
    period_month: string,
    params: { page?: number; page_size?: number; org_id?: string } = {},
  ) =>
    get<PagedResult<SoftwareClaimRow>>("/api/sample_app/software-claims", {
      period_month,
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      ...(params.org_id ? { org_id: params.org_id } : {}),
    });

  const listReimbursements = (
    params: {
      page?: number;
      page_size?: number;
      keyword?: string;
      status_code?: string;
      occurred_month?: string;
      org_id?: string;
    } = {},
  ) =>
    get<PagedResult<ReimbursementRow>>("/api/sample_app/reimbursements", {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      ...(params.keyword ? { keyword: params.keyword } : {}),
      ...(params.status_code ? { status_code: params.status_code } : {}),
      ...(params.occurred_month ? { occurred_month: params.occurred_month } : {}),
      ...(params.org_id ? { org_id: params.org_id } : {}),
    });

  const createReimbursement = (data: {
    file_ids?: string[];
    employee_id: string;
    amount: number;
    subject: string;
    occurred_on: string;
  }) => send("post", "/api/sample_app/reimbursements", data);

  const addReimbursementFiles = (id: string, file_ids: string[]) =>
    send("post", `/api/sample_app/reimbursements/${id}/attachments`, {
      file_ids,
    });

  const actReimbursement = (
    id: string,
    data: { action: string; account_id?: string },
  ) => send("post", `/api/sample_app/reimbursements/${id}/actions`, data);

  const listFixedCosts = () =>
    get<FixedCostRow[]>("/api/sample_app/fixed-costs");

  const createFixedCost = (data: {
    account_id: string;
    cost_name: string;
    category_code: string;
    monthly_amount: number;
  }) => send("post", "/api/sample_app/fixed-costs", data);

  const chargeFixedCost = (id: string, period_month: string) =>
    send("post", `/api/sample_app/fixed-costs/${id}/charges`, { period_month });
  const listSocialBases = () =>
    get<SocialBasis[]>("/api/sample_app/social-bases");
  const saveSocialBasis = (data: Omit<SocialBasis, "id" | "valid_to">) =>
    send<SocialBasis>("post", "/api/sample_app/social-bases", data);
  const listSocialBills = () =>
    get<SocialBill[]>("/api/sample_app/social-bills");
  const generateSocialBill = (
    data: OrganizationRow & { period_month: string },
  ) =>
    send<{ id: string; warnings?: string[] }>(
      "post",
      "/api/sample_app/social-bills",
      data,
    );
  const getSocialBill = (id: string) =>
    get<SocialDetail>(`/api/sample_app/social-bills/${id}`);
  const updateSocialBill = (id: string, lines: SocialLine[]) =>
    send("put", `/api/sample_app/social-bills/${id}`, { lines });
  const confirmSocialBill = (id: string) =>
    send("post", `/api/sample_app/social-bills/${id}/confirm`, {});
  const paySocialBill = (id: string, data: PaymentInput) =>
    send("post", `/api/sample_app/social-bills/${id}/pay`, data);
  const payPayroll = (data: PaymentInput & { period_month: string }) =>
    send("post", "/api/sample_app/payrolls/pay", data);
  return {
    listEmployeeAccountBindings,
    listEmployeeAccountOptions,
    bindEmployeeAccount,
    unbindEmployeeAccount,
    listSocialBases,
    saveSocialBasis,
    listSocialBills,
    generateSocialBill,
    getSocialBill,
    updateSocialBill,
    confirmSocialBill,
    paySocialBill,
    payPayroll,
    listSocialPlans,
    listOrganizations,
    listImportHistory,
    getPluginStatus,
    listEmployees,
    saveEmployee,
    listFlexFields,
    createFlexField,
    updateFlexField,
    getPaySetting,
    savePaySetting,
    saveSocialPlan,
    listAttendance,
    saveAttendance,
    listSalaries,
    createSalary,
    calculatePayroll,
    getPayroll,
    updatePayslip,
    closePayroll,
    exportPayroll,
    listProjects,
    saveProject,
    getProject,
    createContract,
    createReceiptPlan,
    createReceipt,
    createProjectCost,
    getCashLedger,
    createCashAccount,
    createCashEntry,
    importCashEntries,
    createCashBalance,
    listLoans,
    createLoan,
    repayLoan,
    listLoanRepayments,
    listReimbursements,
    listSoftwareClaims,
    createReimbursement,
    addReimbursementFiles,
    actReimbursement,
    listFixedCosts,
    createFixedCost,
    chargeFixedCost,
  };
}
export function useSampleApi() {
  const context = useBusinessContext();
  return createSampleApi(() => context?.operationOrg.value || "");
}

export function transferSampleEmployee(
  id: string,
  data: {
    target_org_id: string;
    effective_on: string;
    social_plan_id: string;
    preview: boolean;
    preview_key?: string;
  },
) {
  return http.request<
    Envelope<{
      effective_on: string;
      plan_name: string;
      preview_key: string;
      base_amount: string;
      performance_amount: string;
      social_base: string;
      housing_base: string;
    }>
  >("post", `/api/sample_app/employees/${id}/transfer`, { data });
}

export const deleteSampleRecord = (resource: string, id: string) =>
  http.request<Envelope<{ id: string }>>(
    "delete",
    `/api/sample_app/records/${resource}/${id}`,
  );
