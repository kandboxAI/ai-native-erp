"""多组织列表、主体不变、关联写入与越权；不连接真实数据库。"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy.dialects import postgresql
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.sample_app import scoped_service as scoped, access_repository as repo
from app.modules.sample_app.api import business_user
from app.modules.sample_app.models import SampleEmployee


def complete(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coroutine.close()
    raise AssertionError("不允许真实异步I/O")

@pytest.fixture
def env(monkeypatch):
    own, other = uuid4(), uuid4()
    user = AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test", user_id=uuid4(), org_id=own, org_ids=[own,other], permission_scopes={"sample_app:access":"organization","sample_app:history":"organization"})
    choices=[{"id":own,"org_name":"A"},{"id":other,"org_name":"B"}]
    @asynccontextmanager
    async def context(): yield SimpleNamespace()
    monkeypatch.setattr(scoped,"get_session_context",context)
    async def options(_session,_user,selected=None,permission=None):
        return [row for row in choices if selected is None or row["id"]==selected]
    monkeypatch.setattr(repo,"organizations",options)
    return SimpleNamespace(user=user,own=own,other=other,scope=scoped.BusinessScope(user))


def test_default_scope_preserves_identity_and_queries_all_authorized_orgs(env,monkeypatch):
    context=complete(business_user(user=env.user,org_id=None))
    assert context.user is env.user
    assert context.selected_org_id is None
    query=AsyncMock(side_effect=lambda org,*args:[{"id":str(org)}])
    monkeypatch.setattr(scoped.business,"employees",query)
    rows=complete(scoped.invoke("employees",context,"internal"))
    assert {row["org_id"] for row in rows}=={str(env.own),str(env.other)}
    assert env.user.org_id==env.own
    filtered=complete(business_user(user=env.user,org_id=env.other))
    assert len(complete(scoped.invoke("employees",filtered,"internal")))==1
    with pytest.raises(AppException): complete(business_user(user=env.user,org_id=uuid4()))


def test_new_records_require_explicit_org_for_multi_org_access(env,monkeypatch):
    create=AsyncMock(return_value={"id":"new"})
    monkeypatch.setattr(scoped.business,"save_cash_account",create)
    with pytest.raises(AppException): complete(scoped.invoke("save_cash_account",env.scope,env.user.user_id,{"account_name":"test"}))
    create.assert_not_called()
    complete(scoped.invoke("save_cash_account",env.scope,env.user.user_id,{"org_id":env.other,"account_name":"test"}))
    assert create.call_args.args[0]==env.other
    assert "org_id" not in create.call_args.args[2]


def test_record_actions_resolve_owner_and_reject_cross_org_payload(env,monkeypatch):
    monkeypatch.setattr(repo,"record_org",AsyncMock(return_value=env.other))
    repay=AsyncMock(return_value={"id":"payment"})
    monkeypatch.setattr(scoped.business,"repay_loan",repay)
    loan_id=uuid4()
    complete(scoped.invoke("repay_loan",env.scope,env.user.user_id,loan_id,{"amount":10}))
    assert repay.call_args.args[0]==env.other
    with pytest.raises(AppException): complete(scoped.invoke("repay_loan",env.scope,env.user.user_id,loan_id,{"org_id":env.own,"amount":10}))
    monkeypatch.setattr(repo,"record_org",AsyncMock(return_value=None))
    with pytest.raises(AppException): complete(scoped.invoke("repay_loan",env.scope,env.user.user_id,loan_id,{"amount":10}))


def test_financial_aggregates_keep_account_org_labels(env,monkeypatch):
    async def ledger(org,*args):
        value=10 if org==env.own else 20
        return {"accounts":[{"id":str(org),"book_balance":value}],"entries":[],"checkpoints":[],"month_income":value,"month_expense":0,"month_net":value}
    monkeypatch.setattr(scoped.business,"cash_ledger",ledger)
    result=complete(scoped.invoke("cash_ledger",env.scope,None))
    assert result["month_income"]==30
    assert {row["org_name"] for row in result["accounts"]}=={"A","B"}


def test_detail_rows_keep_parent_organization_for_display():
    org = {"id": uuid4(), "org_name": "费用组织"}
    result = scoped.tagged({"contracts": [{"plans": [{}], "receipts": [{}]}],
                            "costs": [{}], "lines": [{}]}, org)
    rows = [result, result["contracts"][0], result["contracts"][0]["plans"][0],
            result["contracts"][0]["receipts"][0], result["costs"][0], result["lines"][0]]
    assert all(row["org_id"] == str(org["id"]) and row["org_name"] == org["org_name"] for row in rows)


def test_repository_owner_query_contains_framework_scope_and_soft_delete(env):
    session=SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(first=lambda:None)))
    complete(repo.record_org(session,env.user,SampleEmployee,uuid4()))
    sql=str(session.exec.call_args.args[0].compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}))
    assert "deleted_at IS NULL" in sql
    assert "org_id IN" in sql
    assert str(env.own) in sql and str(env.other) in sql


def test_cross_company_debt_uses_explicit_ledger_and_separately_authorizes_person(env,monkeypatch):
    selected=scoped.BusinessScope(env.user,env.own)
    person=uuid4()
    async def person_org(_session,user,model,identity,filter_org=None):
        assert user is env.user
        assert identity == person
        assert filter_org is None
        return env.other
    monkeypatch.setattr(repo,"record_org",person_org)
    create=AsyncMock(return_value={"id":"debt"})
    monkeypatch.setattr(scoped.business,"create_loan",create)
    result=complete(scoped.invoke("create_loan",selected,env.user.user_id,{"org_id":env.own,"employee_id":person,"amount":100}))
    assert create.call_args.args[0] == env.own
    assert create.call_args.kwargs["counterparty_org_id"] == env.other
    assert result["org_id"] == str(env.own)
    assert selected.selected_org_id == env.own
    monkeypatch.setattr(repo,"record_org",AsyncMock(return_value=None))
    with pytest.raises(AppException):
        complete(scoped.invoke("create_loan",selected,env.user.user_id,{"org_id":env.own,"employee_id":person,"amount":100}))
    assert create.await_count == 1


def test_reimbursement_uses_expense_company_not_employer(env, monkeypatch):
    selected=scoped.BusinessScope(env.user,env.own)
    person=uuid4()
    lookup=AsyncMock(return_value=env.other)
    monkeypatch.setattr(repo,"record_org",lookup)
    create=AsyncMock(return_value={"id":"claim"})
    monkeypatch.setattr(scoped.business,"create_reimbursement",create)
    result=complete(scoped.invoke("create_reimbursement",selected,env.user.user_id,{"org_id":env.own,"employee_id":person,"amount":100,"subject":"expense"}))
    assert lookup.call_args.args[-1] is None
    assert create.call_args.args[0] == env.own
    assert create.call_args.kwargs["claimant_org_id"] == env.other
    assert result["org_id"] == str(env.own)
    monkeypatch.setattr(repo,"record_org",AsyncMock(return_value=None))
    with pytest.raises(AppException):
        complete(scoped.invoke("create_reimbursement",selected,env.user.user_id,{"org_id":env.own,"employee_id":person,"amount":100}))
    assert create.await_count == 1


def test_transfer_preserves_old_employee_and_requires_fresh_preview(env, monkeypatch):
    from datetime import date
    from decimal import Decimal
    from unittest.mock import Mock
    from app.modules.sample_app import transfer_service as transfer

    period = date(2026, 11, 1)
    employee = SampleEmployee(org_id=env.own, employee_no="E01", full_name="员工",
                              personnel_type_code="internal", employment_status_code="active",
                              hire_date=date(2026, 5, 1))
    plan = SimpleNamespace(id=uuid4(), plan_name="目标缴费方案")
    salary = SimpleNamespace(employee_id=employee.id, valid_from=employee.hire_date, valid_to=None,
                             base_amount=Decimal("10000"), performance_amount=Decimal("500"),
                             social_base=Decimal("6000"), social_plan_id=uuid4())
    session = SimpleNamespace(add=Mock(), commit=AsyncMock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(transfer, "get_session_context", context)
    monkeypatch.setattr(repo, "record_org", AsyncMock(return_value=env.own))
    monkeypatch.setattr(transfer.transfer_repository, "lock_employee", AsyncMock(return_value=employee))
    monkeypatch.setattr(transfer.transfer_repository, "has_period_conflict", AsyncMock(return_value=False))
    for name, value in {"find_employee_by_no": None, "get_social_plan": plan,
                        "current_salary": salary, "list_salaries": [salary]}.items():
        monkeypatch.setattr(transfer.repository, name, AsyncMock(return_value=value))
    added = []
    async def add(_session, row):
        added.append(row)
        return row
    for name, value in {"lock_org": AsyncMock(), "current_basis": AsyncMock(return_value=None),
                        "bases": AsyncMock(return_value=[]), "add": add}.items():
        monkeypatch.setattr(transfer.social_repository, name, value)
    args = (env.scope, employee.id, env.other, period, plan.id)
    preview = complete(transfer.transfer(*args, preview=True))
    session.add.assert_not_called()
    salary.base_amount = Decimal("11000")
    with pytest.raises(AppException):
        complete(transfer.transfer(*args, preview=False, preview_key=preview["preview_key"]))
    session.commit.assert_not_awaited()
    preview = complete(transfer.transfer(*args, preview=True))
    complete(transfer.transfer(*args, preview=False, preview_key=preview["preview_key"]))
    assert employee.org_id == env.own and employee.employment_end_on == salary.valid_to == period
    assert added[0].id != employee.id and added[0].org_id == env.other
    assert added[1].employee_id == added[2].employee_id == added[0].id
    assert added[1].social_plan_id == added[2].social_plan_id == plan.id
    session.commit.assert_awaited_once()
