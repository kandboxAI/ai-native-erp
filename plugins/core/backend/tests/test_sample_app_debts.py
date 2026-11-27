"""员工往来款的方向、状态、超额偿还和幂等校验；不连接真实数据库。"""
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import AppException
from app.modules.sample_app import service


def complete(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coroutine.close()
    raise AssertionError("测试不能执行真实异步I/O")


@pytest.fixture
def environment(monkeypatch):
    org_id, loan_id, account_id, employee_id = (uuid4() for _ in range(4))
    loan = SimpleNamespace(id=loan_id, org_id=org_id, employee_id=employee_id, debt_type_code="company_payable", amount=Decimal("100"), borrowed_on=date(2026, 10, 1), account_id=None)
    repayment = SimpleNamespace(id=uuid4(), loan_id=loan_id, org_id=org_id, account_id=account_id, amount=Decimal("40"), repaid_on=date(2026, 10, 23))
    session = SimpleNamespace(commit=AsyncMock())
    @asynccontextmanager
    async def session_context():
        yield session
    monkeypatch.setattr(service, "get_session_context", session_context)
    monkeypatch.setattr(service, "_employee", AsyncMock())
    monkeypatch.setattr(service, "_account", AsyncMock())
    write = AsyncMock()
    monkeypatch.setattr(service, "_write_entry", write)
    monkeypatch.setattr(service.repository, "dump_model", lambda row: {"id": str(row.id)})
    for name, value in [("lock_loan", loan), ("get_loan", loan), ("list_repayments", []), ("repayment_by_request", None), ("add_loan", loan), ("add_repayment", repayment)]:
        monkeypatch.setattr(service.repository, name, AsyncMock(return_value=value))
    return SimpleNamespace(org=org_id, loan=loan, repayment=repayment, account=account_id, employee=employee_id, write=write, session=session)


def repayment_payload(env, amount=40):
    return {"account_id": str(env.account), "amount": amount, "repaid_on": "2026-10-23", "request_key": "same-confirmation"}


def test_company_payable_registration_does_not_create_cash_flow(environment):
    env = environment
    complete(service.create_loan(env.org, None, {"employee_id": str(env.employee), "debt_type_code": "company_payable", "amount": 100, "borrowed_on": "2026-10-01", "account_id": None}))
    env.write.assert_not_called()
    service.repository.add_loan.assert_awaited_once()
    assert service.repository.add_loan.await_args.args[2]["account_id"] is None


def test_existing_employee_loan_still_records_expense(environment):
    env = environment
    env.loan.debt_type_code, env.loan.account_id = "employee_loan", env.account
    complete(service.create_loan(env.org, None, {"employee_id": str(env.employee), "debt_type_code": "employee_loan", "amount": 100, "borrowed_on": "2026-10-01", "account_id": str(env.account)}))
    assert env.write.await_args.args[3]["direction_code"] == "expense"


@pytest.mark.parametrize("debt_type,direction,category", [("company_payable", "expense", "employee_payable_settlement"), ("employee_loan", "income", "loan_repayment")])
def test_repayment_generates_correct_direction(environment, debt_type, direction, category):
    env = environment
    env.loan.debt_type_code = debt_type
    complete(service.repay_loan(env.org, None, env.loan.id, repayment_payload(env)))
    data = env.write.await_args.args[3]
    assert (data["direction_code"], data["category_code"]) == (direction, category)
    assert data["source_id"] == env.repayment.id
    service.repository.lock_loan.assert_awaited_once_with(env.session, env.org, env.loan.id)
    env.session.commit.assert_awaited_once()


def test_status_is_derived_from_actual_repayments():
    assert service.repayment_status(Decimal("100"), Decimal("0")) == "unpaid"
    assert service.repayment_status(Decimal("100"), Decimal("40")) == "partial"
    assert service.repayment_status(Decimal("100"), Decimal("100")) == "settled"


def test_repayment_cannot_exceed_outstanding(environment):
    env = environment
    service.repository.list_repayments.return_value = [SimpleNamespace(amount=Decimal("70"))]
    with pytest.raises(AppException, match="超过未还"):
        complete(service.repay_loan(env.org, None, env.loan.id, repayment_payload(env)))
    service.repository.add_repayment.assert_not_called()
    env.write.assert_not_called()
    env.session.commit.assert_not_called()


def test_same_request_does_not_write_twice(environment):
    env = environment
    service.repository.repayment_by_request.return_value = env.repayment
    complete(service.repay_loan(env.org, None, env.loan.id, repayment_payload(env)))
    service.repository.add_repayment.assert_not_called()
    env.write.assert_not_called()


def test_reused_request_with_different_amount_is_rejected(environment):
    env = environment
    service.repository.repayment_by_request.return_value = env.repayment
    with pytest.raises(AppException, match="已使用"):
        complete(service.repay_loan(env.org, None, env.loan.id, repayment_payload(env, 41)))
    env.write.assert_not_called()


def test_cross_organization_debt_is_not_accessible(environment):
    env = environment
    service.repository.lock_loan.return_value = None
    with pytest.raises(AppException, match="不存在"):
        complete(service.repay_loan(uuid4(), None, env.loan.id, repayment_payload(env)))
    env.write.assert_not_called()


def test_date_and_amount_are_validated(environment):
    env = environment
    payload = {**repayment_payload(env), "repaid_on": "2026-09-30"}
    with pytest.raises(AppException, match="早于"):
        complete(service.repay_loan(env.org, None, env.loan.id, payload))
    for amount in [0, -1, "NaN", "1.001"]:
        with pytest.raises(AppException):
            service._debt_amount(amount)


def test_payable_cannot_fake_a_cash_account_at_registration(environment):
    env = environment
    with pytest.raises(AppException, match="不指定资金账户"):
        complete(service.create_loan(env.org, None, {"employee_id": str(env.employee), "account_id": str(env.account), "debt_type_code": "company_payable", "amount": 100, "borrowed_on": "2026-10-01"}))
    env.write.assert_not_called()

def test_cash_ledger_optional_period_preserves_all_history(environment, monkeypatch):
    env = environment
    account = SimpleNamespace(id=env.account, opening_on=date(2026, 1, 1), opening_balance=Decimal("10"), account_name="测试账户")
    entries = [SimpleNamespace(id=uuid4(), account_id=env.account, occurred_on=date(2026, 8, 1), direction_code="income", amount=Decimal("100")), SimpleNamespace(id=uuid4(), account_id=env.account, occurred_on=date(2026, 9, 1), direction_code="expense", amount=Decimal("30"))]
    checkpoint = SimpleNamespace(id=uuid4(), account_id=env.account, balance_on=date(2026, 8, 31), amount=Decimal("110"))
    monkeypatch.setattr(service.repository, "list_accounts", AsyncMock(return_value=[account]))
    monkeypatch.setattr(service.repository, "list_entries", AsyncMock(return_value=entries))
    monkeypatch.setattr(service.repository, "list_checkpoints", AsyncMock(return_value=[checkpoint]))
    all_rows = complete(service.cash_ledger(env.org))
    assert len(all_rows["entries"]) == 2
    assert len(all_rows["checkpoints"]) == 1
    assert all_rows["accounts"][0]["book_balance"] == 80
    assert all_rows["month_net"] == 70
    august = complete(service.cash_ledger(env.org, "2026-08"))
    assert len(august["entries"]) == 1
    assert august["accounts"][0]["book_balance"] == 110
    september = complete(service.cash_ledger(env.org, "2026-09"))
    assert len(september["entries"]) == 1
    assert september["checkpoints"] == []
    assert september["month_net"] == -30

def test_funds_navigation_resolves_independent_pages_and_preserves_old_link():
    from pathlib import Path
    import tomllib
    from app.modules.sample_app.catalog import MENUS
    from app.modules.system.tenant_template import relocate_catalog_menu, resort_catalog_menu
    root = Path(__file__).resolve().parents[4]
    plugin = root / "plugins" / "sample_app"
    manifest = tomllib.loads((plugin / "plugin.toml").read_text(encoding="utf-8"))
    by_key = {menu.key: menu for menu in MENUS}
    directory = by_key["SampleAppFunds"]
    assert directory.menu_type_code == "directory"
    children = [menu for menu in MENUS if menu.parent_key == directory.key]
    assert len(children) == 6
    assert len({menu.path for menu in children}) == 6
    for menu in children:
        assert menu.key in manifest["menu_keys"]
        assert menu.permission_key == "sample_app:access"
        assert (plugin / "web" / "src" / "views" / (menu.component + ".vue")).is_file()
    social = by_key["SampleAppSocial"]
    wages = by_key["SampleAppWages"]
    assert [social.sort_no, wages.sort_no, directory.sort_no] == [5, 6, 7]
    for parent, keys in [(social, ["SampleAppSocialBasis", "SampleAppSetting", "SampleAppSocialBills"]), (wages, ["SampleAppSalary", "SampleAppAttendance", "SampleAppPayroll"])]:
        assert parent.menu_type_code == "directory" and parent.key in manifest["menu_keys"]
        assert [by_key[key].sort_no for key in keys] == [1, 2, 3]
        for key in keys:
            assert by_key[key].parent_key == parent.key
            assert by_key[key].previous_parent_keys
    old = by_key["SampleAppCash"]
    assert old.path == "/sample-app/cash"
    parent = SimpleNamespace(id=uuid4(), menu_key="SampleAppRoot")
    funds = SimpleNamespace(id=uuid4(), menu_key="SampleAppFunds", deleted_at=None)
    row = SimpleNamespace(parent_id=parent.id, sort_no=7)
    menus = {"SampleAppRoot": parent, "SampleAppFunds": funds}
    assert relocate_catalog_menu(row, old, menus, {parent.id: parent, funds.id: funds})
    assert row.parent_id == funds.id
    assert row.sort_no == old.sort_no


def test_cross_company_counterparty_keeps_debt_and_cash_in_ledger_org(environment):
    env = environment
    salary_org = uuid4()
    complete(service.create_loan(env.org, None, {"employee_id": str(env.employee), "debt_type_code": "employee_loan", "amount": 100, "borrowed_on": "2026-10-01", "account_id": str(env.account)}, counterparty_org_id=salary_org))
    service._employee.assert_awaited_once_with(env.session, salary_org, env.employee)
    service._account.assert_awaited_once_with(env.session, env.org, env.account)
    assert service.repository.add_loan.call_args.args[1] == env.org
    assert service._write_entry.call_args.args[1] == env.org


def test_cross_company_reimbursement_keeps_payment_in_expense_company(environment, monkeypatch):
    env=environment
    employer=uuid4()
    row=SimpleNamespace(id=uuid4(),subject="test expense",amount=Decimal("100"),status_code="submitted",employee_id=env.employee)
    monkeypatch.setattr(service.repository,"add_reimbursement",AsyncMock(return_value=row))
    monkeypatch.setattr(service.repository,"get_reimbursement",AsyncMock(return_value=row))
    env.session.add=lambda entity:None
    complete(service.create_reimbursement(env.org,None,{"employee_id":env.employee,"amount":100,"subject":"test expense","occurred_on":"2026-10-23"},claimant_org_id=employer))
    service._employee.assert_awaited_once_with(env.session,employer,env.employee)
    assert service.repository.add_reimbursement.call_args.args[1] == env.org
    service._write_entry.assert_not_called()
    complete(service.reimbursement_action(env.org,None,row.id,"post",env.account))
    service._account.assert_awaited_once_with(env.session,env.org,env.account)
    assert service._write_entry.call_args.args[1] == env.org
    assert row.status_code == "posted"
