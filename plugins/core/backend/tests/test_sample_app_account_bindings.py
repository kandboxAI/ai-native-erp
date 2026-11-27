"""管理员账号关联维护：本人权限不能代管，换绑原子保留历史，范围不能越权。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import dialect
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException, register_exception_handlers
from app.modules.sample_app import employee_mcp_service as service, employee_mcp_repository as repo


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(monkeypatch):
    org, employee_id = uuid4(), uuid4()
    admin = SimpleNamespace(user_id=uuid4(), permissions=["sample_app:access","user_profile:detail","user_profile:list"])
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), add=Mock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(service,"get_session_context",context)
    monkeypatch.setattr(service,"ensure_org_access",Mock())
    monkeypatch.setattr(service.users,"detail",AsyncMock(return_value=SimpleNamespace(is_active=True,account_is_active=True,full_name="账号甲",display_name="账号甲")))
    monkeypatch.setattr(repo,"active_employee",AsyncMock(return_value=SimpleNamespace(id=employee_id,org_id=org,personnel_type_code="internal")))
    monkeypatch.setattr(repo,"current_binding",AsyncMock(return_value=[]))
    monkeypatch.setattr(repo,"insert",AsyncMock())
    return SimpleNamespace(admin=admin,org=org,employee_id=employee_id,session=session)


def test_employee_permission_cannot_manage_bindings(env):
    employee=SimpleNamespace(permissions=[service.SELF_PERMISSION])
    with pytest.raises(AppException):
        run(service.bind_account(employee,uuid4(),env.employee_id))
    service.users.detail.assert_not_awaited()
    with pytest.raises(AppException):
        run(service.unbind_account(employee,uuid4(),env.employee_id))


def test_bind_new_account_uses_public_user_validation(env):
    user_id=uuid4()
    run(service.bind_account(env.admin,user_id,env.employee_id))
    service.users.detail.assert_awaited_once_with(str(user_id),env.admin)
    added=repo.insert.await_args.args[1]
    assert added.user_id==user_id and added.employee_id==env.employee_id and added.org_id==env.org
    assert added.created_by==env.admin.user_id
    env.session.commit.assert_awaited_once()


def test_switch_account_preserves_both_old_links_in_one_transaction(env):
    old_user,new_user=uuid4(),uuid4()
    old_owner=SimpleNamespace(employee_id=env.employee_id,org_id=env.org,valid_to=None)
    old_target=SimpleNamespace(employee_id=uuid4(),org_id=env.org,valid_to=None)
    repo.current_binding.side_effect=lambda session,user_id,lock: [old_owner] if user_id==old_user else [old_target]
    run(service.bind_account(env.admin,new_user,env.employee_id,old_user))
    assert old_owner.valid_to is not None and old_target.valid_to==old_owner.valid_to
    added=repo.insert.await_args.args[1]
    assert added.user_id==new_user and added.employee_id==env.employee_id
    assert old_owner.updated_by==env.admin.user_id
    env.session.commit.assert_awaited_once()


def test_retried_switch_returns_existing_binding(env):
    old_user,new_user=uuid4(),uuid4()
    target=SimpleNamespace(employee_id=env.employee_id,org_id=env.org,valid_to=None)
    repo.current_binding.side_effect=lambda session,user_id,lock: [] if user_id==old_user else [target]
    run(service.bind_account(env.admin,new_user,env.employee_id,old_user))
    repo.insert.assert_not_awaited()
    env.session.commit.assert_not_awaited()


def test_stale_previous_account_does_not_change_another_binding(env):
    old_user,new_user=uuid4(),uuid4()
    changed=SimpleNamespace(employee_id=uuid4(),org_id=env.org,valid_to=None)
    repo.current_binding.side_effect=lambda session,user_id,lock: [changed] if user_id==old_user else []
    with pytest.raises(AppException) as error:
        run(service.bind_account(env.admin,new_user,env.employee_id,old_user))
    assert error.value.status_code==409 and changed.valid_to is None
    env.session.commit.assert_not_awaited()


def test_switch_cannot_end_out_of_scope_old_assignment(env):
    old=SimpleNamespace(employee_id=uuid4(),org_id=uuid4(),valid_to=None)
    repo.current_binding.return_value=[old]
    def check(user,org,permission):
        if org!=env.org:raise AppException("越权",status_code=403)
    service.ensure_org_access.side_effect=check
    with pytest.raises(AppException):
        run(service.bind_account(env.admin,uuid4(),env.employee_id))
    assert old.valid_to is None
    env.session.commit.assert_not_awaited()


def test_unbind_keeps_history_and_rejects_stale_employee(env):
    row=SimpleNamespace(employee_id=env.employee_id,org_id=env.org,valid_to=None)
    repo.current_binding.return_value=[row]
    with pytest.raises(AppException):
        run(service.unbind_account(env.admin,uuid4(),uuid4()))
    assert row.valid_to is None
    assert run(service.unbind_account(env.admin,uuid4(),env.employee_id))["unbound"] is True
    assert row.valid_to is not None and row.updated_by==env.admin.user_id


def test_listing_uses_scoped_employee_query(monkeypatch):
    org=uuid4()
    user=AuthenticatedUser(auth_user_id=uuid4(),tenant_id=uuid4(),tenant_no="unit",tenant_schema="t_unit",user_id=uuid4(),
        org_id=org,org_ids=[org],permission_scopes={"sample_app:access":"organization"})
    session=SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda:[])))
    run(repo.visible_bindings(session,user))
    statement=session.exec.await_args.args[0]
    sql=str(statement.compile(dialect=dialect()))
    assert "sample_app_employee.org_id =" in sql and "deleted_at IS NULL" in sql
    assert org in statement.compile().params.values()


def test_main_admin_routes_do_not_accept_employee_only_user():
    from app.modules.sample_app.api import router
    app=FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(permissions=[service.SELF_PERMISSION])
    client=TestClient(app)
    assert client.get("/api/sample_app/employee-account-bindings").status_code==403
    assert client.put("/api/sample_app/employee-account-bindings",json={"user_id":str(uuid4()),"employee_id":str(uuid4())}).status_code==403
