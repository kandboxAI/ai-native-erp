from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, resolve_effective_data_scope
from app.core.exceptions import AppException
from app.core.response import success_response

from . import scoped_service as service
from . import import_service
from . import employee_mcp_service
from .employee_mcp_schemas import BindingBody

router = APIRouter(prefix="/api/sample_app", tags=["快盒"])
_guard = [Depends(require_permissions(["sample_app:access"]))]


async def business_user(
    user: AuthenticatedUser = Depends(get_current_user),
    org_id: UUID | None = Query(default=None),
):
    if resolve_effective_data_scope(user, "sample_app:access") not in {"all", "organization", "department"}:
        raise AppException(message="本插件组织核算尚不支持本人或关联关系范围，请配置组织范围", status_code=403)
    if org_id is not None:
        ensure_org_access(user, org_id, "sample_app:access")
    return service.BusinessScope(user, org_id)


def _org(user):
    return user


class OrganizationBody(BaseModel):
    org_id: UUID | None = None


class EmployeeTransferBody(BaseModel):
    target_org_id: UUID
    effective_on: date
    social_plan_id: UUID
    preview: bool = True
    preview_key: str | None = None


@router.post("/employees/{employee_id}/transfer", dependencies=_guard)
async def transfer_employee(employee_id: UUID, body: EmployeeTransferBody, user=Depends(business_user)):
    from .transfer_service import transfer
    return success_response(await transfer(user, employee_id, body.target_org_id,
                                           body.effective_on, body.social_plan_id, preview=body.preview,
                                           preview_key=body.preview_key))


@router.delete("/records/{resource}/{record_id}", dependencies=_guard)
async def delete_record(resource: str, record_id: UUID, user=Depends(business_user)):
    from .deletion_service import delete_record as delete_business_record
    return success_response(await delete_business_record(user, resource, record_id))


@router.get("/organizations", dependencies=_guard)
async def organizations(user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await import_service.organizations(user))


@router.get("/import-history", dependencies=[Depends(require_permissions(["sample_app:access", "sample_app:history"]))])
async def import_history(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.history(_org(user)))


class SettingBody(OrganizationBody):
    daily_wage_mode_code: str
    standard_days: float
    overtime_multiplier: float
    tax_threshold: float


class PlanBody(OrganizationBody):
    plan_name: str
    pension_employer_rate: float = 0
    pension_employee_rate: float = 0
    unemployment_employer_rate: float = 0
    unemployment_employee_rate: float = 0
    injury_employer_rate: float = 0
    medical_employer_rate: float = 0
    medical_employee_rate: float = 0
    housing_employer_rate: float = 0
    housing_employee_rate: float = 0


class AttendanceRow(BaseModel):
    employee_id: UUID | None = None
    employee_no: str | None = None
    expected_days: float = 0
    actual_days: float = 0
    overtime_days: float = 0


class AttendanceBody(OrganizationBody):
    period_month: str
    rows: list[AttendanceRow]


class SalaryBody(OrganizationBody):
    employee_id: UUID
    social_plan_id: UUID | None = None
    social_base: float = 0
    base_amount: float
    performance_amount: float = 0
    valid_from: str
    valid_to: str | None = None


class MonthBody(OrganizationBody):
    period_month: str


class PayslipBody(OrganizationBody):
    project_id: UUID | None = None
    task_name: str | None = None
    bonus_amount: float | None = None
    software_amount: float | None = None
    travel_amount: float | None = None
    other_amount: float | None = None
    adjust_amount: float | None = None
    tax_amount: float | None = Field(default=None, ge=0)
    other_deduction_amount: float | None = None


@router.get("/status", dependencies=_guard)
async def status(user: AuthenticatedUser = Depends(business_user)):
    return success_response({"plugin_key": "sample_app", "status": "ready", "scope": "authorized"})


class EmployeeBody(OrganizationBody):
    personnel_type_code: str = "internal"
    project_id: UUID | None = None
    employee_no: str
    full_name: str
    employment_status_code: str = "active"
    hire_date: str | None = None
    bank_name: str | None = None
    account_no_masked: str | None = None
    flex_form: dict | None = None


@router.get("/employees", dependencies=_guard)
async def employees(personnel_type_code: str = "internal", user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.employees(_org(user), personnel_type_code))


@router.post("/employees", dependencies=_guard)
async def create_employee(body: EmployeeBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_employee(_org(user), user.user_id, None, body.model_dump()))


@router.put("/employees/{employee_id}", dependencies=_guard)
async def update_employee(employee_id: UUID, body: EmployeeBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_employee(_org(user), user.user_id, employee_id, body.model_dump()))


@router.get("/pay-setting", dependencies=_guard)
async def read_setting(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.read_setting(_org(user), user.user_id))


@router.put("/pay-setting", dependencies=_guard)
async def write_setting(body: SettingBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.write_setting(_org(user), user.user_id, body.model_dump()))


@router.get("/social-plans", dependencies=_guard)
async def social_plans(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.social_plans(_org(user)))


@router.post("/social-plans", dependencies=_guard)
async def create_plan(body: PlanBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.write_plan(_org(user), user.user_id, None, body.model_dump()))


@router.put("/social-plans/{plan_id}", dependencies=_guard)
async def update_plan(plan_id: UUID, body: PlanBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.write_plan(_org(user), user.user_id, plan_id, body.model_dump()))


@router.get("/attendance", dependencies=_guard)
async def attendance(period_month: str, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.attendance(_org(user), period_month))


@router.put("/attendance", dependencies=_guard)
async def save_attendance(body: AttendanceBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_attendance(_org(user), user.user_id, body.period_month, [row.model_dump() for row in body.rows]))


@router.get("/salaries", dependencies=_guard)
async def salaries(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.salaries(_org(user)))


@router.post("/salaries", dependencies=_guard)
async def add_salary(body: SalaryBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_salary(_org(user), user.user_id, body.model_dump()))


@router.post("/payrolls/calculate", dependencies=_guard)
async def calculate(body: MonthBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.calculate(_org(user), user.user_id, body.period_month))


@router.get("/payrolls", dependencies=_guard)
async def payrolls(period_month: str, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.payroll_lines(_org(user), period_month))


@router.put("/payslips/{payslip_id}", dependencies=_guard)
async def update_payslip(payslip_id: UUID, body: PayslipBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.update_line(_org(user), user.user_id, payslip_id, body.model_dump()))


@router.get("/software-claims", dependencies=_guard)
async def software_claims(
    period_month: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: AuthenticatedUser = Depends(business_user),
):
    return success_response(await service.page_software_claims(
        _org(user), period_month, page=page, page_size=page_size))


@router.post("/payrolls/close", dependencies=_guard)
async def close_payroll(body: MonthBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.close_payroll(_org(user), user.user_id, body.period_month))


@router.get("/payrolls/export", dependencies=_guard)
async def export_payroll(period_month: str, user: AuthenticatedUser = Depends(business_user)):
    return success_response({"filename": f"payroll-{period_month}.csv", "content": await service.export_csv(_org(user), period_month)})


class ProjectBody(OrganizationBody):
    project_name: str
    customer_name: str | None = None
    status_code: str = "active"
    pipeline_amount: float = 0
    flex_form: dict | None = None


class FlexFieldBody(BaseModel):
    form_key: str
    field_key: str
    field_name: str
    value_type_code: str
    is_required: bool = False


class FlexFieldUpdate(BaseModel):
    field_name: str
    is_required: bool = False
    is_active: bool = True


@router.get("/flex-fields", dependencies=_guard)
async def flex_fields(form_key: str, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.flex_fields(user, form_key))


@router.post("/flex-fields", dependencies=_guard)
async def create_flex_field(body: FlexFieldBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.create_flex_field(user, body.model_dump()))


@router.put("/flex-fields/{field_id}", dependencies=_guard)
async def update_flex_field(field_id: UUID, body: FlexFieldUpdate, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.update_flex_field(user, field_id, body.model_dump()))


class ContractBody(OrganizationBody):
    contract_no: str
    currency_code: str = "CNY"
    total_amount: float


class ReceiptPlanBody(OrganizationBody):
    plan_month: str
    amount: float


class ReceiptBody(OrganizationBody):
    received_on: str
    amount: float
    remark: str | None = None


class ProjectCostBody(OrganizationBody):
    cost_name: str
    amount: float
    occurred_on: str


@router.get("/projects", dependencies=_guard)
async def project_list(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.projects(_org(user)))


@router.post("/projects", dependencies=_guard)
async def create_project(body: ProjectBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_project(_org(user), user.user_id, None, body.model_dump()))


@router.put("/projects/{project_id}", dependencies=_guard)
async def update_project(project_id: UUID, body: ProjectBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_project(_org(user), user.user_id, project_id, body.model_dump()))


@router.get("/projects/{project_id}", dependencies=_guard)
async def project_detail(project_id: UUID, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.project_detail(_org(user), project_id))


@router.post("/projects/{project_id}/contracts", dependencies=_guard)
async def create_contract(project_id: UUID, body: ContractBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_contract(_org(user), user.user_id, project_id, body.model_dump()))


@router.post("/contracts/{contract_id}/plans", dependencies=_guard)
async def create_receipt_plan(contract_id: UUID, body: ReceiptPlanBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_plan(_org(user), user.user_id, contract_id, body.model_dump()))


@router.post("/contracts/{contract_id}/receipts", dependencies=_guard)
async def create_receipt(contract_id: UUID, body: ReceiptBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_project_receipt(_org(user), user.user_id, contract_id, body.model_dump()))


@router.post("/projects/{project_id}/costs", dependencies=_guard)
async def create_project_cost(project_id: UUID, body: ProjectCostBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_project_cost(_org(user), user.user_id, project_id, body.model_dump()))


class AccountBody(OrganizationBody):
    account_name: str
    account_type_code: str
    opening_balance: float = 0
    opening_on: str


class CashEntryBody(OrganizationBody):
    account_id: UUID
    occurred_on: str
    direction_code: str
    category_code: str
    amount: float
    summary: str | None = None
    project_id: UUID | None = None


class CashImportRow(BaseModel):
    account_name: str
    occurred_on: str
    direction_code: str
    category_code: str
    amount: float
    summary: str | None = None


class CashImportRows(OrganizationBody):
    rows: list[CashImportRow]


class CheckpointBody(OrganizationBody):
    account_id: UUID
    balance_on: str
    balance_kind_code: str
    amount: float


class LoanBody(OrganizationBody):
    employee_id: UUID
    debt_type_code: str = "employee_loan"
    account_id: UUID | None = None
    amount: float
    borrowed_on: str
    remark: str | None = None


class RepaymentBody(OrganizationBody):
    account_id: UUID
    amount: float
    repaid_on: str
    request_key: str | None = Field(default=None, min_length=1, max_length=64)


class ReimbursementBody(OrganizationBody):
    employee_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    subject: str = Field(min_length=1, max_length=128)
    occurred_on: str
    file_ids: list[UUID] = Field(default_factory=list, max_length=50)


class ReimbursementActionBody(OrganizationBody):
    action: str
    account_id: UUID | None = None


class FixedCostBody(OrganizationBody):
    account_id: UUID
    cost_name: str
    category_code: str
    monthly_amount: float


@router.get("/cash-ledger", dependencies=_guard)
async def cash_ledger(period_month: str | None = None, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.cash_ledger(_org(user), period_month))


@router.post("/cash-accounts", dependencies=_guard)
async def create_cash_account(body: AccountBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_cash_account(_org(user), user.user_id, body.model_dump()))


@router.post("/cash-entries", dependencies=_guard)
async def create_cash_entry(body: CashEntryBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.add_cash_entry(_org(user), user.user_id, body.model_dump()))


@router.post("/cash-entries/import", dependencies=_guard)
async def import_cash_entries(body: CashImportRows, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.import_cash_entries(_org(user), user.user_id, [row.model_dump() for row in body.rows]))


@router.post("/cash-balances", dependencies=_guard)
async def create_cash_balance(body: CheckpointBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.save_cash_checkpoint(_org(user), user.user_id, body.model_dump()))


@router.get("/loans", dependencies=_guard)
async def loan_list(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.loans(_org(user)))


@router.post("/loans", dependencies=_guard)
async def create_loan(body: LoanBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.create_loan(_org(user), user.user_id, body.model_dump()))


@router.post("/loans/{loan_id}/repayments", dependencies=_guard)
async def create_repayment(loan_id: UUID, body: RepaymentBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.repay_loan(_org(user), user.user_id, loan_id, body.model_dump()))


@router.get("/loans/{loan_id}/repayments", dependencies=_guard)
async def repayment_list(loan_id: UUID, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.loan_repayments(_org(user), loan_id))


@router.get("/reimbursements", dependencies=_guard)
async def reimbursement_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status_code: str | None = Query(default=None),
    occurred_month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    user: AuthenticatedUser = Depends(business_user),
):
    return success_response(await service.page_reimbursements(
        _org(user), page=page, page_size=page_size, keyword=keyword,
        status_code=status_code, occurred_month=occurred_month))


@router.post("/reimbursements", dependencies=_guard)
async def create_reimbursement(body: ReimbursementBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.create_reimbursement(_org(user), user.user_id, body.model_dump()))


@router.post("/reimbursements/{reimbursement_id}/actions", dependencies=_guard)
async def act_reimbursement(reimbursement_id: UUID, body: ReimbursementActionBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.reimbursement_action(_org(user), user.user_id, reimbursement_id, body.action, body.account_id))


@router.get("/fixed-costs", dependencies=_guard)
async def fixed_cost_list(user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.fixed_costs(_org(user)))


@router.post("/fixed-costs", dependencies=_guard)
async def create_fixed_cost(body: FixedCostBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.create_fixed_cost(_org(user), user.user_id, body.model_dump()))


@router.post("/fixed-costs/{cost_id}/charges", dependencies=_guard)
async def charge_fixed_cost(cost_id: UUID, body: MonthBody, user: AuthenticatedUser = Depends(business_user)):
    return success_response(await service.charge_fixed_cost(_org(user), user.user_id, cost_id, body.period_month))


# 社保缴费与工资实付使用同一组织授权适配层。
class SocialBasisBody(OrganizationBody):
    employee_id: UUID
    social_plan_id: UUID
    social_base: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    housing_base: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    valid_from: str

class SocialLineBody(BaseModel):
    id: UUID
    pension_employer_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    pension_employee_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    unemployment_employer_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    unemployment_employee_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    injury_employer_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    medical_employer_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    medical_employee_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    housing_employer_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    housing_employee_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

class SocialBillBody(OrganizationBody):
    lines: list[SocialLineBody]

class PaymentBody(OrganizationBody):
    account_id: UUID
    paid_on: date
    cash_entry_id: UUID | None = None

class PayrollPaymentBody(PaymentBody):
    period_month: str

@router.get("/social-bases", dependencies=_guard)
async def social_bases(user=Depends(business_user)):
    return success_response(await service.social_bases(_org(user)))

@router.post("/social-bases", dependencies=_guard)
async def save_social_basis(body: SocialBasisBody, user=Depends(business_user)):
    return success_response(await service.save_social_basis(_org(user), user.user_id, body.model_dump()))

@router.get("/social-bills", dependencies=_guard)
async def social_bills(user=Depends(business_user)):
    return success_response(await service.social_bills(_org(user)))

@router.post("/social-bills", dependencies=_guard)
async def generate_social_bill(body: MonthBody, user=Depends(business_user)):
    return success_response(await service.generate_social_bill(_org(user), user.user_id, body.model_dump()))

@router.get("/social-bills/{bill_id}", dependencies=_guard)
async def social_bill_detail(bill_id: UUID, user=Depends(business_user)):
    return success_response(await service.social_bill_detail(_org(user), bill_id))

@router.put("/social-bills/{bill_id}", dependencies=_guard)
async def update_social_bill(bill_id: UUID, body: SocialBillBody, user=Depends(business_user)):
    return success_response(await service.update_social_bill(_org(user), user.user_id, bill_id, body.model_dump()))

@router.post("/social-bills/{bill_id}/confirm", dependencies=_guard)
async def confirm_social_bill(bill_id: UUID, body: OrganizationBody, user=Depends(business_user)):
    return success_response(await service.confirm_social_bill(_org(user), user.user_id, bill_id, body.model_dump()))

@router.post("/social-bills/{bill_id}/pay", dependencies=_guard)
async def pay_social_bill(bill_id: UUID, body: PaymentBody, user=Depends(business_user)):
    return success_response(await service.pay_social_bill(_org(user), user.user_id, bill_id, body.model_dump()))

@router.post("/payrolls/pay", dependencies=_guard)
async def pay_payroll(body: PayrollPaymentBody, user=Depends(business_user)):
    return success_response(await service.pay_payroll(_org(user), user.user_id, body.model_dump()))


class ReimbursementFilesBody(BaseModel):
    file_ids: list[UUID] = Field(min_length=1, max_length=50)


@router.post("/reimbursements/{reimbursement_id}/attachments", dependencies=_guard)
async def add_reimbursement_files(reimbursement_id: UUID, body: ReimbursementFilesBody,
                                  user=Depends(business_user)):
    return success_response(await service.add_reimbursement_files(user, user.user_id, reimbursement_id, body.model_dump()))


@router.get("/employee-account-bindings", dependencies=_guard)
async def employee_account_bindings(user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await employee_mcp_service.bindings(user))


@router.get("/employee-account-options", dependencies=_guard)
async def employee_account_options(keyword: str = Query(default="", max_length=128), user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await employee_mcp_service.binding_accounts(user, keyword))


@router.put("/employee-account-bindings", dependencies=_guard)
async def employee_account_bind(body: BindingBody, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await employee_mcp_service.bind_account(user, body.user_id, body.employee_id, body.previous_user_id))


@router.delete("/employee-account-bindings/{user_id}", dependencies=_guard)
async def employee_account_unbind(user_id: UUID, employee_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await employee_mcp_service.unbind_account(user, user_id, employee_id))
