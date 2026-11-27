"""删除范围、核算保护和事务回归；不连接真实数据库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import pytest
from sqlalchemy.dialects.postgresql import dialect
from app.core.exceptions import AppException
from app.modules.sample_app import deletion_service as service, deletion_repository as repo


@pytest.fixture
def env(monkeypatch):
    row = SimpleNamespace(id=uuid4(), org_id=uuid4(), status_code="draft", cash_entry_id=None,
                          valid_from=date(2026, 10, 1), valid_to=None, period_month=date(2026, 10, 1))
    scope = SimpleNamespace(user=object(), user_id=uuid4(), selected_org_id=None)
    session = SimpleNamespace(commit=AsyncMock(), add=Mock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(service, "get_session_context", context)
    monkeypatch.setattr(service.access_repository, "record_org", AsyncMock(return_value=row.org_id))
    monkeypatch.setattr(service, "lock_org", AsyncMock())
    monkeypatch.setattr(repo, "owned_row", AsyncMock(return_value=row))
    monkeypatch.setattr(repo, "has_references", AsyncMock(return_value=False))
    monkeypatch.setattr(repo, "has_payroll_since", AsyncMock(return_value=False))
    monkeypatch.setattr(repo, "other_versions", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "bill_lines", AsyncMock(return_value=[]))
    monkeypatch.setattr(service.repository, "list_payslips", AsyncMock(return_value=[]))
    return SimpleNamespace(row=row, scope=scope, session=session)


@pytest.mark.parametrize("resource", list(service.RESOURCES))
def test_unused_record_soft_delete_has_actor_and_commits(env, resource):
    asyncio.run(service.delete_record(env.scope, resource, env.row.id))
    assert env.row.deleted_by == env.scope.user_id and env.row.deleted_at == env.row.updated_at
    env.session.commit.assert_awaited_once()


@pytest.mark.parametrize("resource", ["cash-entries", "loans", "import-history", "unknown"])
def test_financial_history_is_not_a_deletion_resource(env, resource):
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, resource, env.row.id))
    env.session.commit.assert_not_awaited()


def test_payroll_draft_removes_details_but_closed_payroll_is_protected(env):
    slip = SimpleNamespace(id=uuid4())
    service.repository.list_payslips.return_value = [slip]
    env.row.status_code = "closed"
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, "payrolls", env.row.id))
    env.session.commit.assert_not_awaited()
    service.repository.list_payslips.assert_not_awaited()
    env.row.status_code = "draft"
    asyncio.run(service.delete_record(env.scope, "payrolls", env.row.id))
    assert slip.deleted_at == env.row.deleted_at and slip.deleted_by == env.scope.user_id
    env.session.commit.assert_awaited_once()


@pytest.mark.parametrize("status", ["submitted", "posted"])
def test_finalized_reimbursement_not_deleted(env, status):
    env.row.status_code = status
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, "reimbursements", env.row.id))
    env.session.add.assert_not_called()
    env.session.commit.assert_not_awaited()


def test_references_and_unauthorized_scope_are_rejected(env):
    repo.has_references.return_value = True
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, "employees", env.row.id))
    service.access_repository.record_org.return_value = None
    repo.owned_row.reset_mock()
    with pytest.raises(AppException) as exc:
        asyncio.run(service.delete_record(env.scope, "employees", env.row.id))
    assert exc.value.status_code == 404
    repo.owned_row.assert_not_awaited()
    env.session.commit.assert_not_awaited()


@pytest.mark.parametrize("resource", ["salaries", "social-bases", "attendance"])
def test_calculated_period_preserves_inputs(env, resource):
    repo.has_payroll_since.return_value = True
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, resource, env.row.id))
    env.session.add.assert_not_called()


def test_social_bill_children_share_soft_delete_transaction(env):
    child = SimpleNamespace(id=uuid4())
    service.bill_lines.return_value = [child]
    asyncio.run(service.delete_record(env.scope, "social-bills", env.row.id))
    assert child.deleted_at == env.row.deleted_at and child.deleted_by == env.scope.user_id
    env.session.commit.assert_awaited_once()


@pytest.mark.parametrize("status,paid", [("confirmed", None), ("draft", uuid4())])
def test_confirmed_or_paid_bill_preserved(env, status, paid):
    env.row.status_code, env.row.cash_entry_id = status, paid
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, "social-bills", env.row.id))
    env.session.commit.assert_not_awaited()


def test_repository_reference_checks_include_employee_business():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(first=lambda: None)))
    asyncio.run(repo.has_references(session, service.models.SampleEmployee, uuid4()))
    queries = [str(call.args[0].compile(dialect=dialect())) for call in session.exec.await_args_list]
    assert any("sample_app_reimbursement" in sql and "employee_id =" in sql for sql in queries)
    assert all("deleted_at IS NULL" in sql for sql in queries)


def test_removing_latest_version_restores_previous_validity(env):
    previous = SimpleNamespace(valid_from=date(2026, 9, 1), valid_to=env.row.valid_from)
    repo.other_versions.return_value = [previous]
    asyncio.run(service.delete_record(env.scope, "social-bases", env.row.id))
    assert previous.valid_to is None and previous.updated_by == env.scope.user_id
    repo.other_versions.return_value = [SimpleNamespace(valid_from=date(2026, 11, 1))]
    env.session.commit.reset_mock()
    with pytest.raises(AppException):
        asyncio.run(service.delete_record(env.scope, "salaries", env.row.id))
    env.session.commit.assert_not_awaited()
