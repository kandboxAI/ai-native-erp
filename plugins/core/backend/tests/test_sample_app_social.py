"""社保基数独立、跨月现金、工资扣回与幂等；全为离线测试。"""
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from app.modules.user_profile.models import SysUser
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.core.exceptions import AppException
from app.modules.sample_app import social_service as s, social_repository as r, repository as common, service
from app.modules.sample_app.social_models import SocialBasis, SocialBill, SocialBillLine, PayrollPayment
from app.modules.sample_app.models import SampleCashEntry

D=Decimal

def run(coro):
    try: coro.send(None)
    except StopIteration as done: return done.value
    finally: coro.close()
    raise AssertionError("不得执行真实I/O")

@pytest.fixture
def env(monkeypatch):
    org,employee,account=(uuid4() for _ in range(3))
    bill=SocialBill(org_id=org,period_month=date(2026,10,1),status_code="confirmed")
    line=SocialBillLine(org_id=org,bill_id=bill.id,employee_id=employee,pension_employer_amount=D("5000"),pension_employee_amount=D("2000"))
    slip=NS(employee_id=employee,gross_amount=D("20000"),net_amount=D("18000"),**{k:getattr(line,k) for k in s.AMOUNTS})
    payroll=NS(id=uuid4(),period_month=date(2026,10,1),status_code="closed")
    session=NS(commit=AsyncMock())
    @asynccontextmanager
    async def context(): yield session
    monkeypatch.setattr(s,"get_session_context",context)
    monkeypatch.setattr(service,"get_session_context",context)
    monkeypatch.setattr(r,"lock_org",AsyncMock())
    monkeypatch.setattr(r,"bill",AsyncMock(return_value=bill))
    monkeypatch.setattr(r,"bills",AsyncMock(return_value=[bill]))
    monkeypatch.setattr(r,"lines",AsyncMock(return_value=[line]))
    monkeypatch.setattr(r,"payrolls",AsyncMock(return_value=[payroll]))
    monkeypatch.setattr(r,"bases",AsyncMock(return_value=[]))
    monkeypatch.setattr(r,"payment",AsyncMock(return_value=None))
    monkeypatch.setattr(r,"entry_used",AsyncMock(return_value=False))
    monkeypatch.setattr(r,"entry",AsyncMock(return_value=None))
    monkeypatch.setattr(common,"get_payroll",AsyncMock(return_value=payroll))
    monkeypatch.setattr(common,"list_payslips",AsyncMock(return_value=[slip]))
    monkeypatch.setattr(common,"get_account",AsyncMock(return_value=NS(id=account,opening_on=date(2026,1,1))))
    async def add(_session,row): return row
    monkeypatch.setattr(r,"add",AsyncMock(side_effect=add))
    return NS(org=org,employee=employee,account=account,bill=bill,line=line,slip=slip,payroll=payroll,session=session)

def payload(env, day="2026-10-24"):
    return dict(account_id=env.account,paid_on=day,cash_entry_id=None)

def test_separate_social_and_housing_bases_do_not_depend_on_salary():
    plan={f"{k}_rate":D("10") for k in s.KINDS}
    result=s.estimate(D("5000"),D("3000"),plan)
    assert result["pension_employee_amount"]==500
    assert result["housing_employee_amount"]==300

@pytest.mark.parametrize("value",["-1","NaN","Infinity","0.001", "10000000000000000"])
def test_invalid_amount(value):
    with pytest.raises(AppException): s.amount(value)

def test_full_social_cash_not_just_employer_cost(env):
    run(s.pay_social_bill(env.org,None,env.bill.id,payload(env)))
    entry=next(c.args[1] for c in r.add.await_args_list if isinstance(c.args[1],SampleCashEntry))
    assert entry.amount==7000 and entry.occurred_on==date(2026,10,24)
    assert env.bill.period_month==date(2026,10,1)
    assert env.bill.cash_entry_id==entry.id

def test_existing_bank_flow_is_claimed_without_second_entry(env):
    entry=SampleCashEntry(org_id=env.org,account_id=env.account,occurred_on=date(2026,10,24),amount=D("7000"),direction_code="expense",category_code="payroll_social")
    r.entry.return_value=entry
    p={**payload(env),"cash_entry_id":entry.id}
    run(s.pay_social_bill(env.org,None,env.bill.id,p))
    written=[c.args[1] for c in r.add.await_args_list if isinstance(c.args[1],SampleCashEntry)]
    assert written==[entry] and entry.source_id==env.bill.id
    assert entry.source_type_code=="social_bill"

@pytest.mark.parametrize("failure",["used","wrong_amount","wrong_org","income"])
def test_bank_flow_cannot_be_reused_or_mismatched(env,failure):
    entry=SampleCashEntry(org_id=env.org,account_id=env.account,occurred_on=date(2026,10,24),amount=D("7000"),direction_code="expense",category_code="payroll_social")
    r.entry.return_value=entry
    if failure=="used": r.entry_used.return_value=True
    if failure=="wrong_amount":entry.amount=D("6999")
    if failure=="wrong_org":r.entry.return_value=None
    if failure=="income":entry.direction_code="income"
    with pytest.raises(AppException):run(s.pay_social_bill(env.org,None,env.bill.id,{**payload(env),"cash_entry_id":entry.id}))
    env.session.commit.assert_not_called()

def test_repeated_social_payment_is_idempotent(env):
    entry=NS(id=uuid4(),account_id=env.account,occurred_on=date(2026,10,24))
    env.bill.cash_entry_id=entry.id;r.entry.return_value=entry
    run(s.pay_social_bill(env.org,None,env.bill.id,payload(env)))
    r.add.assert_not_called()
    with pytest.raises(AppException):run(s.pay_social_bill(env.org,None,env.bill.id,payload(env,"2026-10-25")))

def test_november_salary_payment_settles_october_not_new_cost(env):
    run(s.pay_payroll(env.org,None,{**payload(env,"2026-11-10"),"period_month":"2026-10"}))
    entry=next(c.args[1] for c in r.add.await_args_list if isinstance(c.args[1],SampleCashEntry))
    assert entry.amount==18000 and entry.occurred_on==date(2026,11,10)
    assert entry.source_id==env.payroll.id
    assert any(isinstance(c.args[1],PayrollPayment) for c in r.add.await_args_list)

def test_draft_payroll_not_treated_as_payment(env):
    env.payroll.status_code="draft"
    with pytest.raises(AppException):run(s.pay_payroll(env.org,None,{**payload(env),"period_month":"2026-10"}))
    r.add.assert_not_called()

def test_pending_personal_recovery_only_cleared_on_actual_wage_payment(env):
    env.bill.cash_entry_id=uuid4()
    report=run(s.social_bills(env.org))[0]
    assert D(report["labor_cost_amount"])==25000
    assert D(report["paid_amount"])==7000
    assert D(report["pending_recovery_amount"])==2000
    r.payment.return_value=NS(cash_entry_id=uuid4())
    report=run(s.social_bills(env.org))[0]
    assert D(report["labor_cost_amount"])==25000
    assert D(report["pending_recovery_amount"])==0
    assert D(report["recovered_amount"])==2000

def test_personal_recovery_matches_each_employee_not_just_aggregate(env):
    env.bill.cash_entry_id=uuid4()
    env.slip.employee_id=uuid4()
    r.payment.return_value=NS(cash_entry_id=uuid4())
    report=run(s.social_bills(env.org))[0]
    assert D(report["pending_recovery_amount"])==2000

def test_mismatched_payroll_blocked_before_close_or_payment(env):
    env.slip.pension_employee_amount=D("1999")
    with pytest.raises(AppException,match="不一致"):run(s.assert_payroll_matches(env.session,env.org,env.payroll))

def test_confirmed_bill_cannot_be_overwritten(env):
    with pytest.raises(AppException):run(s.update_social_bill(env.org,None,env.bill.id,{"lines":[]}))
    r.add.assert_not_called()

def test_basis_changes_close_previous_period_without_rewriting_bill(env,monkeypatch):
    old=SocialBasis(org_id=env.org,employee_id=env.employee,social_plan_id=uuid4(),social_base=D("5000"),housing_base=D("3000"),valid_from=date(2026,1,1))
    r.bases.return_value=[old]
    monkeypatch.setattr(common,"get_employee",AsyncMock(return_value=NS(personnel_type_code="internal")))
    monkeypatch.setattr(common,"get_social_plan",AsyncMock(return_value=NS()))
    run(s.save_social_basis(env.org,None,dict(employee_id=env.employee,social_plan_id=old.social_plan_id,social_base=5500,housing_base=3200,valid_from="2027-01")))
    assert old.valid_to==date(2027,1,1) and old.social_base==5000
    assert env.line.pension_employer_amount==5000
    assert any(isinstance(c.args[1],SocialBasis) and c.args[1].social_base==5500 for c in r.add.await_args_list)

def test_models_have_comments_tenant_local_fks_and_decimal_amounts():
    for model in [SocialBasis,SocialBill,SocialBillLine,PayrollPayment]:
        table=model.__table__
        assert table.schema is None and table.comment
        for column in table.c:
            assert column.comment, column.name
            if column.name.endswith("_amount") or "base" in column.name:
                assert str(column.type)=="NUMERIC(18, 2)"
        for fk in table.foreign_key_constraints:
            assert fk.ondelete in {"RESTRICT","SET NULL"}
            assert fk.name.startswith("fk_")
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_payroll_calculation_uses_confirmed_bill_instead_of_salary_base(env,monkeypatch):
    env.payroll.status_code="draft"
    env.session.add=lambda row:None
    setting=NS(standard_days=D("21.75"),daily_wage_mode_code="fixed_days",overtime_multiplier=D("2"),tax_threshold=D("5000"))
    salary=NS(base_amount=D("20000"),performance_amount=D("0"),social_base=D("99000"),social_plan_id=uuid4())
    values={"ensure_defaults":None,"get_setting":setting,"list_brackets":[],"list_plans":[],"draft_extras":{},"list_attendance":[],"list_employees":[dict(id=str(env.employee),full_name="test",employment_status_code="active",hire_date="2026-01-01")],"current_salary":salary,"prior_tax":(D("0"),D("0"),D("0")),"lock_payroll":env.payroll,"replace_payslips":None}
    for key,value in values.items():monkeypatch.setattr(common,key,AsyncMock(return_value=value))
    from app.modules.sample_app import software_claim_service
    monkeypatch.setattr(software_claim_service, "applied_amounts_for_period", AsyncMock(return_value={}))
    monkeypatch.setattr(common, "list_payslips", AsyncMock(return_value=[]))
    monkeypatch.setattr(software_claim_service, "mark_applied_after_payroll", AsyncMock())
    run(service.calculate(env.org,None,"2026-10"))
    line=common.replace_payslips.await_args.args[2][0]
    assert line["pension_employee_amount"]==2000
    assert line["employer_cost_amount"]==25000
    assert line["net_amount"]==18000

def test_salary_raise_inherits_old_legacy_base_without_changing_independent_basis(env,monkeypatch):
    from app.modules.sample_app.models import SampleSalary
    old=SampleSalary(org_id=env.org,employee_id=env.employee,social_plan_id=uuid4(),social_base=D("5000"),base_amount=D("10000"),performance_amount=D("0"),valid_from=date(2026,1,1))
    monkeypatch.setattr(common,"get_employee",AsyncMock(return_value=NS(id=env.employee,personnel_type_code="internal")))
    monkeypatch.setattr(common,"latest_salary",AsyncMock(return_value=old))
    monkeypatch.setattr(common,"save_salary",AsyncMock(return_value=old))
    run(service.add_salary(env.org,None,dict(employee_id=env.employee,base_amount=15000,performance_amount=0,social_base=15000,valid_from="2026-11-01")))
    stored=common.save_salary.await_args.args[2]
    assert stored["base_amount"]==15000 and stored["social_base"]==5000
    r.add.assert_not_called()
