from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.sample_app import service
from app.modules.sample_app.payroll_calc import (
    bracket_tax,
    employer_cost,
    gross_pay,
    net_pay,
    overtime_pay,
    book_balance,
    loan_outstanding,
    project_profit,
    receivable,
    social_amounts,
    tax_months,
)

PLAN = {
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
BRACKETS = [
    {"min_amount": 0, "max_amount": 36000, "rate": 3, "quick_deduction": 0},
    {"min_amount": 36000, "max_amount": 144000, "rate": 10, "quick_deduction": 2520},
]


def test_overtime_uses_selected_day_divisor():
    assert overtime_pay(2, 21750, 20, Decimal("21.75"), "fixed_days", 2) == Decimal("4000.00")
    assert overtime_pay(2, 20000, 20, Decimal("21.75"), "attendance_days", 2) == Decimal("4000.00")


def test_gross_net_and_employer_cost():
    social = social_amounts(10000, PLAN)
    assert social["pension_employee_amount"] == Decimal("800.00")
    assert social["housing_employer_amount"] == Decimal("500.00")
    gross = gross_pay(base_amount=10000, performance_amount=2000, bonus_amount=500, overtime_amount=400, software_amount=100, travel_amount=200, other_amount=50, adjust_amount=80)
    assert gross == Decimal("13170.00")
    assert net_pay(gross=gross, tax=100, pension_employee=800, unemployment_employee=30, medical_employee=200, housing_employee=500, other_deduction=40) == Decimal("11500.00")
    assert employer_cost(gross=gross, pension_employer=1600, unemployment_employer=70, injury_employer=16, medical_employer=800, housing_employer=500) == Decimal("16156.00")


def test_cumulative_tax_and_hire_month():
    assert bracket_tax(Decimal("10000"), BRACKETS) == Decimal("300.00")
    assert bracket_tax(Decimal("40000"), BRACKETS) == Decimal("1480.00")
    assert bracket_tax(Decimal("0"), BRACKETS) == Decimal("0.00")
    assert tax_months(3, 2026, 3, 2026) == 1
    assert tax_months(3, 2025, 11, 2026) == 3


def test_project_receivable_and_profit_keep_currencies_apart():
    assert receivable(305500, 100000) == Decimal("205500.00")
    assert project_profit(100000, 40000, 5000) == Decimal("55000.00")
    assert project_profit(0, 40000, 0) == Decimal("-40000.00")


def test_cash_balance_and_loan_outstanding():
    assert book_balance(1000, 300, 80) == Decimal("1220.00")
    assert loan_outstanding(150000, 20000) == Decimal("130000.00")


def test_payslip_update_keeps_manual_tax_amount(monkeypatch):
    org_id, payslip_id, payroll_id, employee_id = (uuid4() for _ in range(4))
    slip = SimpleNamespace(
        id=payslip_id, payroll_id=payroll_id, employee_id=employee_id, project_id=None,
        base_amount=Decimal("10000"), performance_amount=Decimal("0"), bonus_amount=Decimal("0"),
        overtime_amount=Decimal("0"), software_amount=Decimal("0"), travel_amount=Decimal("0"),
        other_amount=Decimal("0"), adjust_amount=Decimal("0"),
        pension_employee_amount=Decimal("800"), unemployment_employee_amount=Decimal("30"),
        medical_employee_amount=Decimal("200"), housing_employee_amount=Decimal("500"),
        other_deduction_amount=Decimal("0"),
        pension_employer_amount=Decimal("1600"), unemployment_employer_amount=Decimal("70"),
        injury_employer_amount=Decimal("16"), medical_employer_amount=Decimal("800"),
        housing_employer_amount=Decimal("500"),
        tax_amount=Decimal("99"), gross_amount=Decimal("0"), net_amount=Decimal("0"),
        employer_cost_amount=Decimal("0"), updated_by=None, updated_at=None,
    )
    payroll = SimpleNamespace(id=payroll_id, status_code="draft", period_month=date(2026, 10, 1))
    session = SimpleNamespace(commit=AsyncMock(), add=lambda _row: None)

    @asynccontextmanager
    async def session_context():
        yield session

    async def lock_org(_session, _org):
        return None

    monkeypatch.setattr(service, "get_session_context", session_context)
    monkeypatch.setattr(service.repository, "get_payslip", AsyncMock(return_value=slip))
    monkeypatch.setattr(service.repository, "payroll_by_id", AsyncMock(return_value=payroll))
    monkeypatch.setattr(service.repository, "dump_model", lambda row: {"tax_amount": float(row.tax_amount), "net_amount": float(row.net_amount)})
    monkeypatch.setattr("app.modules.sample_app.social_repository.lock_org", lock_org)

    async def run():
        return await service.update_line(org_id, None, payslip_id, {
            "bonus_amount": 500,
            "tax_amount": 123.45,
            "software_amount": 0,
            "travel_amount": 0,
            "other_amount": 0,
            "adjust_amount": 0,
            "other_deduction_amount": 0,
        })

    result = __import__("asyncio").run(run())
    assert slip.tax_amount == Decimal("123.45")
    assert slip.gross_amount == Decimal("10500.00")
    assert slip.net_amount == Decimal("8846.55")
    assert result["tax_amount"] == 123.45
    session.commit.assert_awaited_once()
