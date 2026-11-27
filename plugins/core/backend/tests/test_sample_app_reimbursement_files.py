"""报销附件事务与状态校验，不连接真实数据库或 OSS。"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import pytest
from app.core.exceptions import AppException
from app.modules.sample_app import service, reimbursement_files
from app.modules.file.service import scene


def run(coro):
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coro.close()
    raise AssertionError("不允许真实 I/O")


@pytest.fixture
def env(monkeypatch):
    row = SimpleNamespace(id=uuid4(), status_code="draft")
    actor = SimpleNamespace(user_id=uuid4())
    session = SimpleNamespace(commit=AsyncMock(), add=Mock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(service, "get_session_context", context)
    monkeypatch.setattr(service.repository, "get_reimbursement", AsyncMock(return_value=row))
    monkeypatch.setattr(service.repository, "add_reimbursement", AsyncMock(return_value=row))
    monkeypatch.setattr(service.repository, "dump_model", lambda r: {"id": str(r.id)})
    monkeypatch.setattr(service, "_employee", AsyncMock())
    monkeypatch.setattr(service.file_service, "bind", AsyncMock())
    monkeypatch.setattr(service.file_service, "count_for_business", AsyncMock(return_value={row.id: 0}))
    return SimpleNamespace(row=row, actor=actor, session=session, org=uuid4(), employee=uuid4())


def test_invoice_scene_rejects_office_and_limits_size():
    spec = scene(reimbursement_files.SCENE)
    assert set(spec.content_types()) == {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    assert spec.max_count == 50 and spec.max_bytes == 20 * 1024 * 1024


def test_reimbursement_requests_accept_50_invoices_and_reject_51():
    from pydantic import ValidationError
    from app.modules.sample_app.api import ReimbursementBody, ReimbursementFilesBody
    from app.modules.sample_app.employee_mcp_schemas import TicketBody
    from app.modules.sample_app.employee_mcp_local import ReimbursementInput

    ids = [uuid4() for _ in range(51)]
    invoice = {"file_name": "invoice.pdf", "content_type": "application/pdf",
               "file_size": 100, "content_md5": "a" * 24}
    validators = [
        lambda count: ReimbursementBody(employee_id=uuid4(), subject="出差", amount="10.00",
            occurred_on="2026-10-26", file_ids=ids[:count]),
        lambda count: ReimbursementFilesBody(file_ids=ids[:count]),
        lambda count: TicketBody(request_id=uuid4(), files=[invoice] * count),
        lambda count: ReimbursementInput(file_paths=[f"C:/invoices/{i}.pdf" for i in range(count)]),
    ]
    for validate in validators:
        validate(50)
        with pytest.raises(ValidationError):
            validate(51)


def test_submit_without_attachment_does_not_commit(env):
    with pytest.raises(AppException):
        run(service.reimbursement_action(env.org, env.actor.user_id, env.row.id, "submit", None))
    env.session.commit.assert_not_awaited()
    assert env.row.status_code == "draft"


def test_binding_failure_prevents_reimbursement_commit(env):
    service.file_service.bind.side_effect = AppException(message="文件不属于当前用户", status_code=422)
    with pytest.raises(AppException):
        run(service.create_reimbursement(env.org, env.actor.user_id, {
            "employee_id": env.employee, "amount": "12.34", "subject": "出差", "occurred_on": "2026-10-24",
            "file_ids": [uuid4()],
        }, actor=env.actor))
    env.session.commit.assert_not_awaited()


@pytest.mark.parametrize("status", ["submitted", "posted"])
def test_finalized_attachment_cannot_be_changed(env, status):
    env.row.status_code = status
    with pytest.raises(AppException):
        run(service.add_reimbursement_files(env.org, env.actor.user_id, env.row.id, {"file_ids": [uuid4()]}, actor=env.actor))
    service.file_service.bind.assert_not_awaited()


def test_rejected_claim_can_add_then_resubmit(env):
    env.row.status_code = "rejected"
    run(service.add_reimbursement_files(env.org, env.actor.user_id, env.row.id, {"file_ids": [uuid4()]}, actor=env.actor))
    service.file_service.count_for_business.return_value = {env.row.id: 1}
    run(service.reimbursement_action(env.org, env.actor.user_id, env.row.id, "submit", None))
    assert env.row.status_code == "submitted"


def test_missing_subject_rejected_before_persistence(env):
    with pytest.raises(AppException):
        run(service.create_reimbursement(env.org, env.actor.user_id, {"subject": "   ", "amount": "1"}, actor=env.actor))
    service.repository.add_reimbursement.assert_not_awaited()


def test_file_checker_requires_plugin_and_business_permission(monkeypatch):
    query = AsyncMock(return_value=uuid4())
    monkeypatch.setattr(reimbursement_files.access_repository, "record_org", query)
    user = SimpleNamespace(enabled_plugin_keys=[], permissions=["sample_app:access"])
    assert run(reimbursement_files.can_read(None, user, uuid4())) is False
    query.assert_not_awaited()
    user.enabled_plugin_keys = ["sample_app"]
    assert run(reimbursement_files.can_read(None, user, uuid4())) is True


@pytest.mark.parametrize("change", ["other_user", "expired", "other_scene", "bound"])
def test_pending_invoice_recheck_denies_invalid_files(monkeypatch, change):
    from datetime import timedelta
    from app.modules.file import service as file_module
    from app.framework.datetime_local import local_now
    user=SimpleNamespace(user_id=uuid4())
    row=SimpleNamespace(uploader_user_id=user.user_id,status_code="pending",scene_code=reimbursement_files.SCENE,
                        expires_at=local_now()+timedelta(hours=1))
    if change=="other_user": row.uploader_user_id=uuid4()
    if change=="expired": row.expires_at=local_now()-timedelta(seconds=1)
    if change=="other_scene": row.scene_code="not_invoice"
    if change=="bound": row.status_code="bound"
    monkeypatch.setattr(file_module.repository,"upload_for_ingest",AsyncMock(return_value=row))
    with pytest.raises(AppException):
        run(file_module.service.pending_items(None,[uuid4()],user=user,scene_code=reimbursement_files.SCENE))
