"""快盒业务查询与持久化；发薪员工保存在本插件名册中。"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from app.framework.db.models import utc_now

from .models import (
    SampleAccount,
    SampleAccountBalance,
    SampleAttendance,
    SampleCashEntry,
    SampleContract,
    SampleEmployee,
    SampleFixedCost,
    SampleFlexField,
    SampleFixedCostCharge,
    SampleLoan,
    SampleLoanRepayment,
    SampleReimbursement,
    SamplePaySetting,
    SamplePayroll,
    SamplePayslip,
    SampleProject,
    SampleProjectCost,
    SampleReceipt,
    SampleReceiptPlan,
    SampleSalary,
    SampleSocialPlan,
    SampleTaxBracket,
)

DEFAULT_BRACKETS = (
    (1, Decimal("0"), Decimal("36000"), Decimal("3"), Decimal("0")),
    (2, Decimal("36000"), Decimal("144000"), Decimal("10"), Decimal("2520")),
    (3, Decimal("144000"), Decimal("300000"), Decimal("20"), Decimal("16920")),
    (4, Decimal("300000"), Decimal("420000"), Decimal("25"), Decimal("31920")),
    (5, Decimal("420000"), Decimal("660000"), Decimal("30"), Decimal("52920")),
    (6, Decimal("660000"), Decimal("960000"), Decimal("35"), Decimal("85920")),
    (7, Decimal("960000"), None, Decimal("45"), Decimal("181920")),
)

DEFAULT_SOCIAL = {
    "plan_name": "默认口径",
    "pension_employer_rate": Decimal("16"),
    "pension_employee_rate": Decimal("8"),
    "unemployment_employer_rate": Decimal("0.7"),
    "unemployment_employee_rate": Decimal("0.3"),
    "injury_employer_rate": Decimal("0.16"),
    "medical_employer_rate": Decimal("8"),
    "medical_employee_rate": Decimal("2"),
    "housing_employer_rate": Decimal("5"),
    "housing_employee_rate": Decimal("5"),
}


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _num(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return value


def dump_model(row) -> dict:
    data = row.model_dump(mode="json")
    return {key: _num(value) if isinstance(value, Decimal) else value for key, value in data.items()}


async def ensure_defaults(session, org_id: UUID, user_id: UUID | None) -> None:
    setting = (await session.exec(select(SamplePaySetting).where(SamplePaySetting.org_id == org_id, SamplePaySetting.deleted_at.is_(None)))).first()
    if setting is None:
        session.add(SamplePaySetting(org_id=org_id, daily_wage_mode_code="fixed_days", created_by=user_id, updated_by=user_id))
    brackets = (await session.exec(select(SampleTaxBracket).where(SampleTaxBracket.org_id == org_id, SampleTaxBracket.deleted_at.is_(None)))).first()
    if brackets is None:
        for sort_no, lower, upper, rate, quick in DEFAULT_BRACKETS:
            session.add(SampleTaxBracket(
                org_id=org_id, sort_no=sort_no, min_amount=lower, max_amount=upper, rate=rate, quick_deduction=quick,
                created_by=user_id, updated_by=user_id,
            ))
    plan = (await session.exec(select(SampleSocialPlan).where(SampleSocialPlan.org_id == org_id, SampleSocialPlan.deleted_at.is_(None)))).first()
    if plan is None:
        session.add(SampleSocialPlan(org_id=org_id, created_by=user_id, updated_by=user_id, **DEFAULT_SOCIAL))
    await session.flush()


def _employee_row(employee: SampleEmployee) -> dict:
    return {
        "id": str(employee.id),
        "employee_no": employee.employee_no,
        "full_name": employee.full_name,
        "employment_status_code": employee.employment_status_code,
        "personnel_type_code": employee.personnel_type_code,
        "project_id": str(employee.project_id) if employee.project_id else None,
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "employment_end_on": employee.employment_end_on.isoformat() if getattr(employee, "employment_end_on", None) else None,
        "bank_name": employee.bank_name or "",
        "account_no_masked": employee.account_no_masked or "",
        "flex_form": dict(employee.flex_form or {}),
    }


async def list_employee_rows(session, org_id: UUID, personnel_type_code: str = "internal") -> list[SampleEmployee]:
    return list((await session.exec(select(SampleEmployee).where(SampleEmployee.org_id == org_id, SampleEmployee.personnel_type_code == personnel_type_code, SampleEmployee.deleted_at.is_(None)).order_by(SampleEmployee.employee_no))).all())


async def list_employees(session, org_id: UUID, personnel_type_code: str = "internal") -> list[dict]:
    return [_employee_row(row) for row in await list_employee_rows(session, org_id, personnel_type_code)]


async def get_employee(session, org_id: UUID, employee_id: UUID) -> SampleEmployee | None:
    return (await session.exec(select(SampleEmployee).where(SampleEmployee.id == employee_id, SampleEmployee.org_id == org_id, SampleEmployee.deleted_at.is_(None)))).first()


async def save_employee(session, org_id: UUID, employee_id: UUID | None, payload: dict, user_id: UUID | None) -> SampleEmployee:
    row = await get_employee(session, org_id, employee_id) if employee_id else None
    if row is None:
        row = SampleEmployee(org_id=org_id, created_by=user_id, **payload)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    row.updated_by, row.updated_at = user_id, utc_now()
    session.add(row)
    await session.flush()
    return row


async def get_setting(session, org_id: UUID) -> SamplePaySetting:
    return (await session.exec(select(SamplePaySetting).where(SamplePaySetting.org_id == org_id, SamplePaySetting.deleted_at.is_(None)))).one()


async def save_setting(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SamplePaySetting:
    row = await get_setting(session, org_id)
    for key, value in payload.items():
        setattr(row, key, value)
    row.updated_by, row.updated_at = user_id, utc_now()
    session.add(row)
    await session.flush()
    return row


async def list_plans(session, org_id: UUID) -> list[SampleSocialPlan]:
    return list((await session.exec(select(SampleSocialPlan).where(SampleSocialPlan.org_id == org_id, SampleSocialPlan.deleted_at.is_(None)).order_by(SampleSocialPlan.plan_name))).all())


async def save_plan(session, org_id: UUID, plan_id: UUID | None, payload: dict, user_id: UUID | None) -> SampleSocialPlan:
    row = None
    if plan_id is not None:
        row = (await session.exec(select(SampleSocialPlan).where(SampleSocialPlan.id == plan_id, SampleSocialPlan.org_id == org_id, SampleSocialPlan.deleted_at.is_(None)))).first()
    if row is None:
        row = SampleSocialPlan(org_id=org_id, created_by=user_id, **payload)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    row.updated_by, row.updated_at = user_id, utc_now()
    session.add(row)
    await session.flush()
    return row


async def list_brackets(session, org_id: UUID) -> list[SampleTaxBracket]:
    return list((await session.exec(select(SampleTaxBracket).where(SampleTaxBracket.org_id == org_id, SampleTaxBracket.deleted_at.is_(None)).order_by(SampleTaxBracket.sort_no))).all())


async def list_attendance(session, org_id: UUID, period: date) -> list[SampleAttendance]:
    return list((await session.exec(select(SampleAttendance).where(
        SampleAttendance.org_id == org_id, SampleAttendance.period_month == period, SampleAttendance.deleted_at.is_(None),
    ))).all())


async def upsert_attendance(session, org_id: UUID, employee_id: UUID, period: date, payload: dict, user_id: UUID | None) -> SampleAttendance:
    row = (await session.exec(select(SampleAttendance).where(
        SampleAttendance.org_id == org_id, SampleAttendance.employee_id == employee_id, SampleAttendance.period_month == period, SampleAttendance.deleted_at.is_(None),
    ))).first()
    if row is None:
        row = SampleAttendance(org_id=org_id, employee_id=employee_id, period_month=period, created_by=user_id, **payload)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    row.updated_by, row.updated_at = user_id, utc_now()
    session.add(row)
    await session.flush()
    return row


async def find_employee_by_no(session, org_id: UUID, employee_no: str) -> SampleEmployee | None:
    return (await session.exec(select(SampleEmployee).where(
        SampleEmployee.org_id == org_id, SampleEmployee.employee_no == employee_no, SampleEmployee.deleted_at.is_(None),
    ))).first()


async def list_salaries(session, org_id: UUID) -> list[SampleSalary]:
    return list((await session.exec(select(SampleSalary).join(SampleEmployee, SampleEmployee.id == SampleSalary.employee_id).where(SampleSalary.org_id == org_id, SampleEmployee.org_id == org_id, SampleEmployee.personnel_type_code == "internal", SampleEmployee.deleted_at.is_(None), SampleSalary.deleted_at.is_(None)).order_by(SampleSalary.valid_from.desc()))).all())


async def current_salary(session, org_id: UUID, employee_id: UUID, period: date) -> SampleSalary | None:
    end = date(period.year + (period.month == 12), 1 if period.month == 12 else period.month + 1, 1)
    rows = (await session.exec(select(SampleSalary).where(
        SampleSalary.org_id == org_id,
        SampleSalary.employee_id == employee_id,
        SampleSalary.deleted_at.is_(None),
        SampleSalary.valid_from < end,
    ))).all()
    chosen = [row for row in rows if row.valid_to is None or row.valid_to > period]
    if not chosen:
        return None
    return sorted(chosen, key=lambda row: row.valid_from)[-1]


async def save_salary(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleSalary:
    open_rows = (await session.exec(select(SampleSalary).where(
        SampleSalary.org_id == org_id,
        SampleSalary.employee_id == payload["employee_id"],
        SampleSalary.deleted_at.is_(None),
        SampleSalary.valid_to.is_(None),
        SampleSalary.valid_from < payload["valid_from"],
    ))).all()
    for row in open_rows:
        row.valid_to = payload["valid_from"]
        row.updated_by, row.updated_at = user_id, utc_now()
        session.add(row)
    created = SampleSalary(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(created)
    await session.flush()
    return created


async def get_payroll(session, org_id: UUID, period: date) -> SamplePayroll | None:
    return (await session.exec(select(SamplePayroll).where(
        SamplePayroll.org_id == org_id, SamplePayroll.period_month == period, SamplePayroll.deleted_at.is_(None),
    ))).first()


async def lock_payroll(session, payroll: SamplePayroll) -> SamplePayroll:
    return (await session.exec(select(SamplePayroll).where(SamplePayroll.id == payroll.id).with_for_update())).one()


async def prior_tax(session, org_id: UUID, employee_id: UUID, year: int, before: date) -> tuple[Decimal, Decimal, Decimal]:
    rows = (await session.exec(
        select(SamplePayslip, SamplePayroll.period_month)
        .join(SamplePayroll, SamplePayroll.id == SamplePayslip.payroll_id)
        .where(
            SamplePayslip.org_id == org_id,
            SamplePayslip.employee_id == employee_id,
            SamplePayslip.deleted_at.is_(None),
            SamplePayroll.deleted_at.is_(None),
            SamplePayroll.period_month >= date(year, 1, 1),
            SamplePayroll.period_month < before,
        )
    )).all()
    gross = tax = special = Decimal("0")
    for slip, _period in rows:
        gross += slip.gross_amount
        tax += slip.tax_amount
        special += slip.pension_employee_amount + slip.unemployment_employee_amount + slip.medical_employee_amount + slip.housing_employee_amount
    return gross, tax, special


async def replace_payslips(session, payroll: SamplePayroll, lines: list[dict], user_id: UUID | None) -> None:
    existing = (await session.exec(select(SamplePayslip).where(SamplePayslip.payroll_id == payroll.id))).all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    for line in lines:
        session.add(SamplePayslip(org_id=payroll.org_id, payroll_id=payroll.id, created_by=user_id, updated_by=user_id, **line))
    await session.flush()


async def list_payslips(session, payroll_id: UUID) -> list[SamplePayslip]:
    return list((await session.exec(select(SamplePayslip).where(SamplePayslip.payroll_id == payroll_id, SamplePayslip.deleted_at.is_(None)))).all())


async def draft_extras(session, payroll_id: UUID) -> dict[UUID, SamplePayslip]:
    rows = await list_payslips(session, payroll_id)
    return {row.employee_id: row for row in rows}


async def bank_masks(session, employee_ids: list[UUID]) -> dict[UUID, dict]:
    if not employee_ids:
        return {}
    rows = (await session.exec(select(SampleEmployee).where(SampleEmployee.id.in_(employee_ids), SampleEmployee.deleted_at.is_(None)))).all()
    return {row.id: {"bank_name": row.bank_name or "", "account_no_masked": row.account_no_masked or ""} for row in rows}


async def names_by_employee(session, employee_ids: list[UUID]) -> dict[UUID, dict]:
    if not employee_ids:
        return {}
    rows = (await session.exec(select(SampleEmployee).where(SampleEmployee.id.in_(employee_ids)))).all()
    return {
        row.id: {"employee_no": row.employee_no, "full_name": row.full_name, "hire_date": row.hire_date.isoformat() if row.hire_date else None}
        for row in rows
    }


def _alive(model, org_id: UUID):
    return (model.org_id == org_id, model.deleted_at.is_(None))


async def list_projects(session, org_id: UUID) -> list[SampleProject]:
    return list((await session.exec(select(SampleProject).where(*_alive(SampleProject, org_id)).order_by(SampleProject.project_name))).all())


async def get_project(session, org_id: UUID, project_id: UUID) -> SampleProject | None:
    return (await session.exec(select(SampleProject).where(SampleProject.id == project_id, *_alive(SampleProject, org_id)))).first()


async def save_project(session, org_id: UUID, project_id: UUID | None, payload: dict, user_id: UUID | None) -> SampleProject:
    row = await get_project(session, org_id, project_id) if project_id else None
    if row is None:
        row = SampleProject(org_id=org_id, created_by=user_id, **payload)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    row.updated_by, row.updated_at = user_id, utc_now()
    session.add(row)
    await session.flush()
    return row


async def list_contracts(session, org_id: UUID, project_id: UUID | None = None) -> list[SampleContract]:
    query = select(SampleContract).where(*_alive(SampleContract, org_id))
    if project_id is not None:
        query = query.where(SampleContract.project_id == project_id)
    return list((await session.exec(query.order_by(SampleContract.contract_no))).all())


async def get_contract(session, org_id: UUID, contract_id: UUID) -> SampleContract | None:
    return (await session.exec(select(SampleContract).where(SampleContract.id == contract_id, *_alive(SampleContract, org_id)))).first()


async def save_contract(session, org_id: UUID, project_id: UUID, payload: dict, user_id: UUID | None) -> SampleContract:
    row = SampleContract(org_id=org_id, project_id=project_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_plans_for(session, contract_ids: list[UUID]) -> list[SampleReceiptPlan]:
    if not contract_ids:
        return []
    return list((await session.exec(select(SampleReceiptPlan).where(SampleReceiptPlan.contract_id.in_(contract_ids), SampleReceiptPlan.deleted_at.is_(None)))).all())


async def list_receipts_for(session, contract_ids: list[UUID]) -> list[SampleReceipt]:
    if not contract_ids:
        return []
    return list((await session.exec(select(SampleReceipt).where(SampleReceipt.contract_id.in_(contract_ids), SampleReceipt.deleted_at.is_(None)))).all())


async def add_receipt_plan(session, org_id: UUID, contract_id: UUID, payload: dict, user_id: UUID | None) -> SampleReceiptPlan:
    row = SampleReceiptPlan(org_id=org_id, contract_id=contract_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def add_receipt(session, org_id: UUID, contract_id: UUID, payload: dict, user_id: UUID | None) -> SampleReceipt:
    row = SampleReceipt(org_id=org_id, contract_id=contract_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_costs(session, org_id: UUID, project_id: UUID | None = None) -> list[SampleProjectCost]:
    query = select(SampleProjectCost).where(*_alive(SampleProjectCost, org_id))
    if project_id is not None:
        query = query.where(SampleProjectCost.project_id == project_id)
    return list((await session.exec(query)).all())


async def add_cost(session, org_id: UUID, project_id: UUID, payload: dict, user_id: UUID | None) -> SampleProjectCost:
    row = SampleProjectCost(org_id=org_id, project_id=project_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def labor_cost_by_project(session, org_id: UUID) -> dict[UUID, Decimal]:
    projects = await list_projects(session, org_id)
    by_name = {row.project_name: row.id for row in projects}
    slips = (await session.exec(select(SamplePayslip).where(*_alive(SamplePayslip, org_id)))).all()
    totals = {row.id: Decimal("0") for row in projects}
    for slip in slips:
        target = slip.project_id if slip.project_id in totals else by_name.get(slip.task_name or "")
        if target in totals:
            totals[target] += slip.employer_cost_amount
    return totals


async def get_org_employee(session, org_id: UUID, employee_id: UUID) -> SampleEmployee | None:
    return await get_employee(session, org_id, employee_id)


async def list_accounts(session, org_id: UUID) -> list[SampleAccount]:
    return list((await session.exec(select(SampleAccount).where(*_alive(SampleAccount, org_id)).order_by(SampleAccount.account_name))).all())


async def get_account(session, org_id: UUID, account_id: UUID) -> SampleAccount | None:
    return (await session.exec(select(SampleAccount).where(SampleAccount.id == account_id, *_alive(SampleAccount, org_id)))).first()


async def save_account(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleAccount:
    row = SampleAccount(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_entries(session, org_id: UUID) -> list[SampleCashEntry]:
    return list((await session.exec(select(SampleCashEntry).where(*_alive(SampleCashEntry, org_id)).order_by(SampleCashEntry.occurred_on))).all())


async def add_entry(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleCashEntry:
    row = SampleCashEntry(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_checkpoints(session, org_id: UUID) -> list[SampleAccountBalance]:
    return list((await session.exec(select(SampleAccountBalance).where(*_alive(SampleAccountBalance, org_id)))).all())


async def save_checkpoint(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleAccountBalance:
    row = SampleAccountBalance(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_loans(session, org_id: UUID) -> list[SampleLoan]:
    return list((await session.exec(select(SampleLoan).where(*_alive(SampleLoan, org_id)).order_by(SampleLoan.borrowed_on.desc()))).all())


async def get_loan(session, org_id: UUID, loan_id: UUID) -> SampleLoan | None:
    return (await session.exec(select(SampleLoan).where(SampleLoan.id == loan_id, *_alive(SampleLoan, org_id)))).first()


async def lock_loan(session, org_id: UUID, loan_id: UUID) -> SampleLoan | None:
    return (await session.exec(select(SampleLoan).where(SampleLoan.id == loan_id, *_alive(SampleLoan, org_id)).with_for_update())).first()


async def repayment_by_request(session, org_id: UUID, request_key: str):
    return (await session.exec(select(SampleLoanRepayment).where(*_alive(SampleLoanRepayment, org_id), SampleLoanRepayment.request_key == request_key))).first()


async def add_loan(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleLoan:
    row = SampleLoan(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_repayments(session, org_id: UUID, loan_ids: list[UUID]) -> list[SampleLoanRepayment]:
    if not loan_ids:
        return []
    return list((await session.exec(select(SampleLoanRepayment).where(SampleLoanRepayment.loan_id.in_(loan_ids), *_alive(SampleLoanRepayment, org_id)).order_by(SampleLoanRepayment.repaid_on, SampleLoanRepayment.created_at))).all())


async def add_repayment(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleLoanRepayment:
    row = SampleLoanRepayment(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_reimbursements(session, org_id: UUID) -> list[SampleReimbursement]:
    return list((await session.exec(select(SampleReimbursement).where(*_alive(SampleReimbursement, org_id)).order_by(SampleReimbursement.occurred_on.desc()))).all())


async def page_reimbursements(
    session,
    org_ids: list[UUID],
    *,
    page: int,
    page_size: int,
    keyword: str | None = None,
    status_code: str | None = None,
    occurred_month: date | None = None,
):
    """按授权组织分页查询费用报销；keyword 匹配事由。"""
    if not org_ids:
        return 0, []
    conditions = [SampleReimbursement.deleted_at.is_(None), SampleReimbursement.org_id.in_(org_ids)]
    if keyword and keyword.strip():
        conditions.append(SampleReimbursement.subject.ilike(f"%{keyword.strip()}%"))
    if status_code:
        conditions.append(SampleReimbursement.status_code == status_code)
    if occurred_month is not None:
        start = occurred_month.replace(day=1)
        end = date(start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1)
        conditions.append(SampleReimbursement.occurred_on >= start)
        conditions.append(SampleReimbursement.occurred_on < end)
    total = (await session.exec(select(func.count()).select_from(SampleReimbursement).where(*conditions))).one()
    rows = list((await session.exec(
        select(SampleReimbursement).where(*conditions)
        .order_by(SampleReimbursement.occurred_on.desc(), SampleReimbursement.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    return int(total or 0), rows


async def get_reimbursement(session, org_id: UUID, reimbursement_id: UUID) -> SampleReimbursement | None:
    return (await session.exec(select(SampleReimbursement).where(SampleReimbursement.id == reimbursement_id, *_alive(SampleReimbursement, org_id)).with_for_update())).first()


async def add_reimbursement(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleReimbursement:
    row = SampleReimbursement(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def list_fixed_costs(session, org_id: UUID) -> list[SampleFixedCost]:
    return list((await session.exec(select(SampleFixedCost).where(*_alive(SampleFixedCost, org_id)).order_by(SampleFixedCost.cost_name))).all())


async def add_fixed_cost(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleFixedCost:
    row = SampleFixedCost(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def get_fixed_cost(session, org_id: UUID, cost_id: UUID) -> SampleFixedCost | None:
    return (await session.exec(select(SampleFixedCost).where(SampleFixedCost.id == cost_id, *_alive(SampleFixedCost, org_id)))).first()


async def find_charge(session, cost_id: UUID, period: date) -> SampleFixedCostCharge | None:
    return (await session.exec(select(SampleFixedCostCharge).where(
        SampleFixedCostCharge.fixed_cost_id == cost_id,
        SampleFixedCostCharge.period_month == period,
        SampleFixedCostCharge.deleted_at.is_(None),
    ))).first()


async def add_charge(session, org_id: UUID, payload: dict, user_id: UUID | None) -> SampleFixedCostCharge:
    row = SampleFixedCostCharge(org_id=org_id, created_by=user_id, updated_by=user_id, **payload)
    session.add(row)
    await session.flush()
    return row


async def get_social_plan(session, org_id: UUID, plan_id: UUID):
    return (await session.exec(select(SampleSocialPlan).where(SampleSocialPlan.id == plan_id, SampleSocialPlan.org_id == org_id, SampleSocialPlan.deleted_at.is_(None)))).first()


async def financial_person_names(session, employee_ids: list[UUID]) -> dict[UUID, dict]:
    """已授权往来账、报销单的人员显示契约；仅姓名与编号，不读取工资、银行卡或入职信息。"""
    if not employee_ids:
        return {}
    rows = (await session.exec(select(SampleEmployee.id, SampleEmployee.full_name, SampleEmployee.employee_no).where(SampleEmployee.id.in_(employee_ids)))).all()
    return {identity: {"full_name": name, "employee_no": number} for identity, name, number in rows}


async def latest_salary(session, org_id, employee_id):
    return (await session.exec(select(SampleSalary).where(SampleSalary.org_id == org_id, SampleSalary.employee_id == employee_id, SampleSalary.deleted_at.is_(None)).order_by(SampleSalary.valid_from.desc()))).first()


async def get_payslip(session, org_id, identity):
    return (await session.exec(select(SamplePayslip).where(SamplePayslip.id == identity, SamplePayslip.org_id == org_id, SamplePayslip.deleted_at.is_(None)))).first()

async def payroll_by_id(session, org_id, identity):
    return (await session.exec(select(SamplePayroll).where(SamplePayroll.id == identity, SamplePayroll.org_id == org_id, SamplePayroll.deleted_at.is_(None)))).one()


def flex_field_payload(row: SampleFlexField) -> dict:
    return {
        "id": str(row.id), "form_key": row.form_key, "field_key": row.field_key, "field_name": row.field_name,
        "value_type_code": row.value_type_code, "is_required": row.is_required, "sort_no": row.sort_no, "is_active": row.is_active,
    }


async def list_flex_fields(session, form_key: str) -> list[SampleFlexField]:
    return list((await session.exec(select(SampleFlexField).where(
        SampleFlexField.form_key == form_key, SampleFlexField.deleted_at.is_(None),
    ).order_by(SampleFlexField.sort_no, SampleFlexField.field_key))).all())


async def get_flex_field(session, field_id: UUID) -> SampleFlexField | None:
    return (await session.exec(select(SampleFlexField).where(SampleFlexField.id == field_id, SampleFlexField.deleted_at.is_(None)))).first()
