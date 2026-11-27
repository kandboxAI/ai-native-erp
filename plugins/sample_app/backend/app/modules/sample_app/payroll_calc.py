"""薪酬口径。比例、起征点和税率档只从已保存的配置读取。"""
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def percent_amount(base, rate) -> Decimal:
    return money(Decimal(str(base or 0)) * Decimal(str(rate or 0)) / HUNDRED)


def overtime_pay(overtime_days, base_amount, expected_days, standard_days, mode_code, multiplier) -> Decimal:
    divisor = Decimal(str(expected_days or 0)) if mode_code == "attendance_days" else Decimal(str(standard_days or 0))
    if divisor <= 0:
        return money(0)
    daily = Decimal(str(base_amount or 0)) / divisor
    return money(Decimal(str(overtime_days or 0)) * daily * Decimal(str(multiplier or 0)))


def gross_pay(*, base_amount, performance_amount, bonus_amount, overtime_amount, software_amount, travel_amount, other_amount, adjust_amount) -> Decimal:
    total = (
        Decimal(str(base_amount or 0))
        + Decimal(str(performance_amount or 0))
        + Decimal(str(bonus_amount or 0))
        + Decimal(str(overtime_amount or 0))
        + Decimal(str(software_amount or 0))
        + Decimal(str(travel_amount or 0))
        + Decimal(str(other_amount or 0))
        - Decimal(str(adjust_amount or 0))
    )
    return money(total)


def social_amounts(base, plan: dict) -> dict[str, Decimal]:
    keys = (
        "pension_employer_rate",
        "pension_employee_rate",
        "unemployment_employer_rate",
        "unemployment_employee_rate",
        "injury_employer_rate",
        "medical_employer_rate",
        "medical_employee_rate",
        "housing_employer_rate",
        "housing_employee_rate",
    )
    return {key.removesuffix("_rate") + "_amount": percent_amount(base, plan.get(key)) for key in keys}


def tax_months(period_month: int, hire_year: int, hire_month: int, payroll_year: int) -> int:
    if hire_year < payroll_year:
        return period_month
    if hire_year > payroll_year:
        return 1
    return max(1, period_month - hire_month + 1)


def bracket_tax(taxable, brackets: list[dict]) -> Decimal:
    amount = Decimal(str(taxable or 0))
    if amount <= 0 or not brackets:
        return money(0)
    chosen = None
    for row in brackets:
        lower = Decimal(str(row["min_amount"]))
        upper = row.get("max_amount")
        if amount > lower and (upper is None or amount <= Decimal(str(upper))):
            chosen = row
    if chosen is None:
        return money(0)
    tax = amount * Decimal(str(chosen["rate"])) / HUNDRED - Decimal(str(chosen["quick_deduction"]))
    return money(tax if tax > 0 else 0)


def net_pay(*, gross, tax, pension_employee, unemployment_employee, medical_employee, housing_employee, other_deduction) -> Decimal:
    value = (
        Decimal(str(gross))
        - Decimal(str(tax))
        - Decimal(str(pension_employee))
        - Decimal(str(unemployment_employee))
        - Decimal(str(medical_employee))
        - Decimal(str(housing_employee))
        - Decimal(str(other_deduction or 0))
    )
    return money(value)


def receivable(total, received) -> Decimal:
    return money(Decimal(str(total or 0)) - Decimal(str(received or 0)))


def book_balance(opening, income, expense) -> Decimal:
    value = Decimal(str(opening or 0)) + Decimal(str(income or 0)) - Decimal(str(expense or 0))
    return money(value)


def loan_outstanding(principal, repaid) -> Decimal:
    return money(Decimal(str(principal or 0)) - Decimal(str(repaid or 0)))


def project_profit(received_cny, labor_cost, direct_cost) -> Decimal:
    value = Decimal(str(received_cny or 0)) - Decimal(str(labor_cost or 0)) - Decimal(str(direct_cost or 0))
    return money(value)


def employer_cost(*, gross, pension_employer, unemployment_employer, injury_employer, medical_employer, housing_employer) -> Decimal:
    value = (
        Decimal(str(gross))
        + Decimal(str(pension_employer))
        + Decimal(str(unemployment_employer))
        + Decimal(str(injury_employer))
        + Decimal(str(medical_employer))
        + Decimal(str(housing_employer))
    )
    return money(value)
