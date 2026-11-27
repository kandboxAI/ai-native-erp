"""员工 MCP 的协议、本人鉴权、确认与幂等；禁止连接实际数据库/OSS。"""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import dialect
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.sample_app import employee_mcp_service as service, employee_mcp_protocol as protocol
from app.modules.sample_app import employee_mcp_repository as repo, employee_mcp_auth as auth
from app.modules.sample_app.employee_mcp_schemas import PrepareBody, InvoiceDescription
from app.modules.sample_app.employee_mcp_models import EmployeeUser, EmployeeExpenseRequest, EmployeeExpenseFile, EmployeeExpenseInvoice
from app.modules.sample_app.employee_mcp_manifest import manifest_hash


def test_employee_portal_confirmation_and_interrupted_upload_retry():
    from app.modules.sample_app.employee_mcp_portal import JAVASCRIPT
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node 执行页面脚本")
    result = subprocess.run([node, str(Path(__file__).with_name("employee_portal_ui.mjs"))],
                            input=json.dumps(JAVASCRIPT), text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_portal_connection_remains_available_when_token_is_denied():
    from app.modules.sample_app.employee_mcp_portal import JAVASCRIPT
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node 执行页面脚本")
    harness = r'''
const vm = require("node:vm"), assert = require("node:assert/strict");
const elements = new Map(), copied = [];
const element = id => {
 if (!elements.has(id)) elements.set(id, {value:"",hidden:true,disabled:false,textContent:"",classList:{toggle(){}}});
 return elements.get(id);
};
const context = vm.createContext({URLSearchParams, location:{search:""},
 document:{getElementById:element,querySelectorAll:()=>[]},
 navigator:{clipboard:{writeText:async text=>copied.push(text)}},
 fetch:async path=>({ok:path!=="/employee/token",json:async()=>
 path==="/employee/connection"?{mcp_url:"https://employee.example.com/mcp/sample-app/employee"}:
 path==="/employee/token"?{message:"尚未绑定"}:{captcha_id:"test",image:"test"}})
});
vm.runInContext(SOURCE,context);
(async()=>{
 await vm.runInContext("loadConnection()",context);
 await element("copyUrl").onclick();
 assert.equal(copied[0],"https://employee.example.com/mcp/sample-app/employee");
 await element("copyConfig").onclick();
 const config=JSON.parse(copied[1]).mcpServers.kuaihe_employee;
 assert.equal(config.headers.Authorization,"Bearer <短期凭证>");
 assert.equal(config.url,copied[0]);
 await element("issue").onclick();
 assert.equal(element("message").textContent,"尚未绑定");
 assert.equal(element("mcpUrl").value,copied[0]);
 assert.equal(element("credential").hidden,true);
 assert.equal(element("copyUrl").disabled,false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace("SOURCE", json.dumps(JAVASCRIPT))
    result = subprocess.run([node, "-"], input=harness, text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(monkeypatch):
    user = SimpleNamespace(user_id=uuid4(), auth_user_id=uuid4(), tenant_id=uuid4(), tenant_schema="t_unit",
        permissions=[service.SELF_PERMISSION], enabled_plugin_keys=["sample_app"], org_ids=[], org_id=None)
    person = SimpleNamespace(id=uuid4(), org_id=uuid4(), personnel_type_code="internal", full_name="本人")
    binding = SimpleNamespace(employee_id=person.id, org_id=person.org_id)
    invoice = {"file_name": "invoice.pdf", "file_size": 100, "content_type": "application/pdf", "content_md5": "a"*24}
    expected = SimpleNamespace(**invoice, file_id=uuid4())
    row = SimpleNamespace(id=uuid4(), user_id=user.user_id, employee_id=person.id, org_id=person.org_id,
        request_key="stable-key", subject="出差", amount=Decimal("10.00"), occurred_on=utc_now().date(),
        expires_at=utc_now()+timedelta(hours=1), approved_at=None, reimbursement_id=None,
        invoice_manifest_hash=manifest_hash([invoice]), status_code="ready", source_code="mcp", previous_request_id=None)
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), add=Mock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(service, "get_session_context", context)
    monkeypatch.setattr(service, "ensure_org_access", Mock())
    monkeypatch.setattr(repo, "current_binding", AsyncMock(return_value=[binding]))
    monkeypatch.setattr(repo, "active_employee", AsyncMock(return_value=person))
    monkeypatch.setattr(repo, "own_org_name", AsyncMock(return_value="本人企业"))
    monkeypatch.setattr(repo, "active_org_names", AsyncMock(return_value=[SimpleNamespace(id=person.org_id, org_name="本人企业")]))
    monkeypatch.setattr(repo, "own_request", AsyncMock(return_value=row))
    monkeypatch.setattr(repo, "request_by_key", AsyncMock(return_value=row))
    monkeypatch.setattr(repo, "request_files", AsyncMock(return_value=[SimpleNamespace(file_id=expected.file_id)]))
    monkeypatch.setattr(repo, "invoice_manifest", AsyncMock(return_value=[expected]))
    monkeypatch.setattr(repo, "next_request", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "own_result", AsyncMock(return_value=None))
    monkeypatch.setattr(service.files, "pending_items", AsyncMock(return_value=[{**invoice, "id": str(expected.file_id)}]))
    monkeypatch.setattr(service.files, "bind", AsyncMock())
    monkeypatch.setattr(service.repository, "add_reimbursement", AsyncMock(return_value=SimpleNamespace(id=uuid4(), amount=row.amount, status_code="submitted")))
    return SimpleNamespace(user=user, person=person, row=row, session=session, invoice=invoice, expected=expected)


def test_missing_subject_asks_without_db_write(env):
    result = run(service.prepare(env.user, PrepareBody(request_key="stable-key", subject="  ")))
    assert result["status"] == "needs_input" and result["missing_fields"] == ["subject"]
    repo.current_binding.assert_not_awaited()
    service.repository.add_reimbursement.assert_not_awaited()


@pytest.mark.parametrize("existing,adding,allowed", [(0, 50, True), (49, 1, True), (50, 1, False), (49, 2, False)])
def test_invoice_tickets_count_existing_attachments(env, monkeypatch, existing, adding, allowed):
    from app.modules.sample_app.employee_mcp_schemas import InvoiceDescription
    env.row.status_code = "preparing"
    declared = [SimpleNamespace(file_name=f"invoice-{i}.pdf", file_size=100, content_type="application/pdf",
                 content_md5=str(i).zfill(24), file_id=uuid4() if i < existing else None) for i in range(50)]
    repo.invoice_manifest.return_value = declared
    repo.request_files.return_value = [SimpleNamespace(file_id=item.file_id) for item in declared[:existing]]
    issue = AsyncMock(side_effect=lambda **_: {"id": str(uuid4())})
    monkeypatch.setattr(service.files, "create_upload_ticket", issue)
    invoices = [InvoiceDescription(**service.invoice_data(declared[(existing+i)%50])) for i in range(adding)]
    if allowed:
        assert len(run(service.upload_tickets(env.user, env.row.id, invoices))) == adding
        assert issue.await_count == adding
    else:
        with pytest.raises(AppException) as error:
            run(service.upload_tickets(env.user, env.row.id, invoices))
        assert error.value.status_code == 422
        issue.assert_not_awaited()


@pytest.mark.parametrize("bindings", [[], [object(), object()]])
def test_admin_has_no_self_identity_bypass(env, bindings):
    env.user.permissions += ["sample_app:access"]
    repo.current_binding.return_value = bindings
    with pytest.raises(AppException):
        run(service.identity(env.session, env.user))


def test_selected_user_and_org_are_never_input():
    from pydantic import ValidationError
    for field in ("user_id", "employee_id", "org_id", "tenant_schema", "confirmed", "source", "source_code", "status_code"):
        with pytest.raises(ValidationError):
            PrepareBody.model_validate({"request_key": "stable-key", field: str(uuid4())})


def test_unapproved_request_never_creates_reimbursement(env):
    assert run(service.submit(env.user, env.row.id))["status"] == "needs_confirmation"
    service.repository.add_reimbursement.assert_not_awaited()
    env.session.commit.assert_not_awaited()


def test_missing_and_other_user_requests_are_404(env):
    repo.own_request.return_value = None
    with pytest.raises(AppException) as error:
        run(service.detail(env.user, uuid4()))
    assert error.value.status_code == 404
    assert repo.own_request.await_args.args[1] == env.user.user_id


def test_changed_binding_invalidates_previous_confirmation(env):
    env.row.employee_id = uuid4()
    with pytest.raises(AppException):
        run(service.submit(env.user, env.row.id))
    service.repository.add_reimbursement.assert_not_awaited()


def test_expired_request_is_not_submitted(env):
    env.row.expires_at = utc_now()-timedelta(seconds=1)
    with pytest.raises(AppException) as error:
        run(service.submit(env.user, env.row.id))
    assert error.value.status_code == 410


def test_submit_locks_request_and_replays_exact_result(env):
    env.row.approved_at = utc_now()
    env.row.status_code = "approved"
    first = run(service.submit(env.user, env.row.id))
    assert first["replayed"] is False
    created = service.repository.add_reimbursement.return_value
    assert env.row.reimbursement_id == created.id
    repo.own_result.return_value = created
    env.row.expires_at = utc_now()-timedelta(days=1)
    second = run(service.submit(env.user, env.row.id))
    assert second["replayed"] is True and second["reimbursement_id"] == first["reimbursement_id"]
    service.repository.add_reimbursement.assert_awaited_once()
    service.files.bind.assert_awaited_once()
    env.session.commit.assert_awaited_once()


def test_attachment_binding_failure_prevents_commit(env):
    env.row.approved_at = utc_now()
    env.row.status_code = "approved"
    service.files.bind.side_effect = AppException("发票属于他人", status_code=422)
    with pytest.raises(AppException):
        run(service.submit(env.user, env.row.id))
    assert env.row.reimbursement_id is None
    env.session.commit.assert_not_awaited()


def test_invoice_manifest_is_checked_before_human_approval(env):
    repo.request_files.return_value = [SimpleNamespace(file_id=uuid4())]
    env.row.invoice_manifest_hash = manifest_hash([{"file_name": "a.pdf", "file_size": 1, "content_md5": "original"}])
    service.files.pending_items.return_value = [{"file_name": "b.pdf", "file_size": 1, "content_md5": "changed"}]
    with pytest.raises(AppException):
        run(service.approve(env.user, env.row.id))
    assert env.row.approved_at is None
    env.session.commit.assert_not_awaited()


def test_prepare_idempotency_rejects_different_amount(env):
    with pytest.raises(AppException):
        run(service.prepare(env.user, PrepareBody(request_key=env.row.request_key, subject=env.row.subject,
            amount="11", occurred_on=env.row.occurred_on, invoice_title="本人企业", files=[env.invoice])))
    env.session.commit.assert_not_awaited()


def test_invoice_title_selects_payer_org_not_roster_org(env):
    payer = uuid4()
    repo.active_org_names.return_value = [
        SimpleNamespace(id=env.person.org_id, org_name="示例任职公司"),
        SimpleNamespace(id=payer, org_name="示例费用(青岛)科技有限公司"),
    ]
    repo.request_by_key.return_value = None
    result = run(service.prepare(env.user, PrepareBody(
        request_key="payer-key", subject="加油", amount="10.00", occurred_on=env.row.occurred_on,
        invoice_title=" 示例费用（青岛）科技有限公司 ", files=[env.invoice])))
    created = next(call.args[0] for call in env.session.add.call_args_list if isinstance(call.args[0], EmployeeExpenseRequest))
    assert created.org_id == payer and created.employee_id == env.person.id
    assert result["org_id"] == str(payer) and result["status"] == "preparing"
    env.session.commit.assert_awaited_once()


def test_unknown_invoice_title_does_not_create_request(env):
    result = run(service.prepare(env.user, PrepareBody(
        request_key="missing-org", subject="加油", amount="10.00", occurred_on=env.row.occurred_on,
        invoice_title="没有这家公司", files=[env.invoice])))
    assert result["status"] == "needs_input" and result["missing_fields"] == ["invoice_title"]
    env.session.add.assert_not_called()
    env.session.commit.assert_not_awaited()


def test_manual_prepare_keeps_roster_org_without_invoice_title(env):
    repo.request_by_key.return_value = None
    result = run(service.prepare(env.user, PrepareBody(
        request_key="manual-key", subject="出差", amount="10.00", occurred_on=env.row.occurred_on,
        files=[env.invoice]), source="manual"))
    created = next(call.args[0] for call in env.session.add.call_args_list if isinstance(call.args[0], EmployeeExpenseRequest))
    assert created.org_id == env.person.org_id and result["status"] == "preparing"
    repo.active_org_names.assert_not_awaited()


def test_identical_prepare_retry_does_not_modify_frozen_request(env):
    result = run(service.prepare(env.user, PrepareBody(request_key=env.row.request_key, subject=env.row.subject,
                 amount=env.row.amount, occurred_on=env.row.occurred_on, invoice_title="本人企业", files=[env.invoice])))
    assert result["request_id"] == str(env.row.id) and result["request_status"] == "ready"
    env.session.add.assert_not_called()
    env.session.commit.assert_not_awaited()


def test_missing_invoice_manifest_cannot_create_mutable_request(env):
    result = run(service.prepare(env.user, PrepareBody(request_key="new-request", subject="出差",
                 amount="10.00", occurred_on="2026-10-26")))
    assert result["missing_fields"] == ["files"]
    repo.current_binding.assert_not_awaited()
    env.session.commit.assert_not_awaited()


@pytest.mark.parametrize("changed,value", [("file_name", "other.pdf"), ("file_size", 101),
    ("content_type", "image/png"), ("content_md5", "b"*24)])
def test_upload_ticket_rejects_any_change_to_declared_original(env, monkeypatch, changed, value):
    env.row.status_code = "preparing"
    issue = AsyncMock()
    monkeypatch.setattr(service.files, "create_upload_ticket", issue)
    invoice = InvoiceDescription(**{**env.invoice, changed: value})
    with pytest.raises(AppException) as error:
        run(service.upload_tickets(env.user, env.row.id, [invoice]))
    assert error.value.status_code == 409
    issue.assert_not_awaited()
    env.session.commit.assert_not_awaited()


@pytest.mark.parametrize("state", ["ready", "approved", "superseded", "legacy", "submitted"])
def test_frozen_or_obsolete_requests_reject_upload_endpoints(env, monkeypatch, state):
    env.row.status_code = state
    issue, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service.files, "create_upload_ticket", issue)
    monkeypatch.setattr(service.files, "complete_upload", complete)
    with pytest.raises(AppException):
        run(service.upload_tickets(env.user, env.row.id, [InvoiceDescription(**env.invoice)]))
    with pytest.raises(AppException):
        run(service.complete_upload(env.user, env.row.id, uuid4()))
    issue.assert_not_awaited()
    complete.assert_not_awaited()
    env.session.commit.assert_not_awaited()


def test_last_declared_upload_freezes_request_and_completion_retry_is_read_only(env, monkeypatch):
    env.row.status_code = "preparing"
    link = SimpleNamespace(file_id=env.expected.file_id)
    repo.request_files.side_effect = [[], [link]]
    complete = AsyncMock()
    monkeypatch.setattr(service.files, "complete_upload", complete)
    result = run(service.complete_upload(env.user, env.row.id, env.expected.file_id))
    assert result["attached"] and env.row.status_code == "ready"
    env.session.commit.assert_awaited_once()
    repo.request_files.side_effect = None
    repo.request_files.return_value = [link]
    result = run(service.complete_upload(env.user, env.row.id, env.expected.file_id))
    assert result["reused"]
    complete.assert_awaited_once()
    env.session.commit.assert_awaited_once()


def test_unrelated_upload_ticket_cannot_be_completed_into_request(env, monkeypatch):
    env.row.status_code = "preparing"
    complete = AsyncMock()
    monkeypatch.setattr(service.files, "complete_upload", complete)
    with pytest.raises(AppException):
        run(service.complete_upload(env.user, env.row.id, uuid4()))
    complete.assert_not_awaited()


def test_uploaded_metadata_must_match_declaration_before_linking(env, monkeypatch):
    env.row.status_code = "preparing"
    repo.request_files.return_value = []
    monkeypatch.setattr(service.files, "complete_upload", AsyncMock())
    service.files.pending_items.return_value = [{**env.invoice, "file_size": 101}]
    with pytest.raises(AppException):
        run(service.complete_upload(env.user, env.row.id, env.expected.file_id))
    env.session.add.assert_not_called()
    env.session.commit.assert_not_awaited()


def test_prepare_new_version_invalidates_old_version_atomically(env):
    repo.request_by_key.return_value = None
    old_id = env.row.id
    result = run(service.prepare(env.user, PrepareBody(request_key="new-version-key", subject="新的事由",
        amount="20.00", occurred_on=env.row.occurred_on, invoice_title="本人企业", files=[env.invoice], previous_request_id=old_id)))
    assert env.row.status_code == "superseded"
    assert result["previous_request_id"] == str(old_id) and result["request_status"] == "preparing"
    created = next(call.args[0] for call in env.session.add.call_args_list if isinstance(call.args[0], EmployeeExpenseRequest))
    assert created.invoice_manifest_hash == manifest_hash([env.invoice]) and created.source_code == "mcp"
    assert any(isinstance(call.args[0], EmployeeExpenseInvoice) for call in env.session.add.call_args_list)
    env.session.commit.assert_awaited_once()
    for operation in (service.approve, service.submit):
        with pytest.raises(AppException):
            run(operation(env.user, old_id))
    service.repository.add_reimbursement.assert_not_awaited()


def test_cannot_replace_submitted_or_different_source_request(env):
    repo.request_by_key.return_value = None
    body = PrepareBody(request_key="new-version-key", subject="事由", amount="20.00",
        occurred_on=env.row.occurred_on, invoice_title="本人企业", files=[env.invoice], previous_request_id=env.row.id)
    with pytest.raises(AppException):
        run(service.prepare(env.user, body, source="manual"))
    env.row.reimbursement_id = uuid4()
    with pytest.raises(AppException):
        run(service.prepare(env.user, body))
    assert env.row.status_code == "ready"
    env.session.commit.assert_not_awaited()


def test_revision_rejects_branching_from_an_already_replaced_request(env):
    repo.request_by_key.return_value = None
    repo.next_request.return_value = SimpleNamespace(id=uuid4())
    with pytest.raises(AppException):
        run(service.prepare(env.user, PrepareBody(request_key="new-version-key", subject="事由", amount="20.00",
            occurred_on=env.row.occurred_on, invoice_title="本人企业", files=[env.invoice], previous_request_id=env.row.id)))
    env.session.commit.assert_not_awaited()


def test_manual_return_to_edit_invalidates_old_confirmation(env):
    env.row.source_code = "manual"
    result = run(service.revise_manual(env.user, env.row.id))
    assert result["request_status"] == "superseded"
    with pytest.raises(AppException):
        run(service.approve(env.user, env.row.id))
    with pytest.raises(AppException):
        run(service.submit(env.user, env.row.id))
    service.files.bind.assert_not_awaited()


def test_mcp_request_cannot_use_manual_edit_endpoint(env):
    with pytest.raises(AppException):
        run(service.revise_manual(env.user, env.row.id))
    env.session.commit.assert_not_awaited()


def test_submit_rechecks_original_manifest_after_human_approval(env):
    env.row.status_code, env.row.approved_at = "approved", utc_now()
    service.files.pending_items.return_value = [{**env.invoice, "file_name": "replacement.pdf"}]
    with pytest.raises(AppException):
        run(service.submit(env.user, env.row.id))
    service.repository.add_reimbursement.assert_not_awaited()
    env.session.commit.assert_not_awaited()


def test_review_markup_has_no_file_picker_or_upload_button():
    from app.modules.sample_app.employee_mcp_portal import HTML
    review = HTML.split('<section id="expense"', 1)[1].split('<section id="pairing"', 1)[0]
    assert 'type="file"' not in review and 'id="upload"' not in review and 'id="invoices"' not in review
    assert 'id="editManual"' in review and 'id="copyAiRevision"' in review


def test_protocol_unknown_and_malformed_tools_never_dispatch(env):
    assert run(protocol.dispatch({"id":1,"method":"tools/call","params":{"name":"sql"}}, env.user, "http://localhost"))["error"]["code"] == -32602
    result = run(protocol.dispatch({"id":1,"method":"tools/call","params":{"name":"submit_reimbursement","arguments":{"request_id":str(env.row.id),"employee_id":str(uuid4())}}}, env.user,"http://localhost"))
    assert result["error"]["code"] == -32602
    service.repository.add_reimbursement.assert_not_awaited()


def test_protocol_hides_person_name_and_download_capability():
    result = protocol.tool_data({"status":"awaiting_confirmation", "employee_name":"private-name",
                                "attachments":[{"id":"one","file_name":"invoice.pdf","url":"signed-download-secret","content_md5":"digest"}]})
    assert "employee_name" not in result
    assert "url" not in result["attachments"][0]


def test_models_have_comments_fks_and_bounded_names():
    for model in (EmployeeUser, EmployeeExpenseRequest, EmployeeExpenseFile, EmployeeExpenseInvoice):
        table = model.__table__
        assert table.comment and table.schema is None
        for column in table.columns:
            assert column.comment, column.name
            if column.name.endswith("_id"):
                assert column.foreign_keys
        for item in list(table.constraints)+list(table.indexes):
            assert item.name and len(item.name.encode()) <= 63
    assert next(iter(EmployeeExpenseFile.__table__.c.file_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(EmployeeExpenseInvoice.__table__.c.file_id.foreign_keys)).ondelete == "SET NULL"
    for name in ("source_code", "status_code"):
        assert str(EmployeeExpenseRequest.__table__.c[name].server_default.arg) == "'legacy'"


def test_repository_uses_explicit_self_filter_and_row_lock():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(first=lambda: None)))
    user_id, request_id = uuid4(), uuid4()
    run(repo.own_request(session, user_id, request_id))
    statement = session.exec.await_args.args[0]
    sql = str(statement.compile(dialect=dialect()))
    assert "user_id =" in sql and "deleted_at IS NULL" in sql and "FOR UPDATE" in sql
    assert user_id in statement.compile().params.values()


def test_portal_history_lists_employee_requests_across_expense_orgs():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    user_id, employee_id, org_id = uuid4(), uuid4(), uuid4()
    assert run(repo.own_recent_requests(session, user_id, employee_id, org_id)) == []
    statement = session.exec.await_args.args[0]
    compiled = statement.compile(dialect=dialect())
    sql = str(compiled)
    assert "user_id =" in sql and "employee_id =" in sql
    assert "deleted_at IS NULL" in sql and "reimbursement_id IS NULL" in sql and "LIMIT" in sql
    assert "expires_at >" in sql and "status_code IN" in sql
    assert compiled.params[next(key for key in compiled.params if key.startswith("status_code"))] == ["preparing", "ready", "approved"]
    assert all(value in compiled.params.values() for value in (user_id, employee_id, 50))
    assert org_id not in compiled.params.values()


def test_portal_history_uses_live_status_and_hides_unavailable_receipts(env, monkeypatch):
    active = SimpleNamespace(**vars(env.row))
    receipt = SimpleNamespace(**{**vars(env.row), "id": uuid4(), "status_code": "posted",
                                "amount": Decimal("99.00"), "subject": "正式报销内容"})
    query = AsyncMock(return_value=[active])
    monkeypatch.setattr(repo, "own_recent_requests", query)
    formal_query = AsyncMock(return_value=(1, [receipt]))
    monkeypatch.setattr(repo, "page_own_reimbursements", formal_query)
    data = run(service.recent_requests(env.user, page=1, page_size=20))
    assert {item["status"] for item in data["items"]} == {"awaiting_confirmation", "posted"}
    formal = next(item for item in data["items"] if item["reimbursement_id"])
    assert formal["request_id"] is None and formal["subject"] == "正式报销内容" and formal["amount"] == "99.00"
    formal_query.assert_awaited_once_with(env.session, env.person.id, page=1, page_size=20)
    assert data["total"] == 1 and data["page"] == 1 and data["page_size"] == 20
    assert data["employee_name"] == env.person.full_name
    assert query.await_args.args[1:] == (env.user.user_id, env.person.id, env.person.org_id)
    assert all("user_id" not in item and "attachments" not in item for item in data["items"])


def test_portal_history_keeps_drafts_only_on_first_page(env, monkeypatch):
    active = SimpleNamespace(**vars(env.row))
    receipt = SimpleNamespace(**{**vars(env.row), "id": uuid4(), "status_code": "posted",
                                "amount": Decimal("12.00"), "subject": "第二页正式单"})
    monkeypatch.setattr(repo, "own_recent_requests", AsyncMock(return_value=[active]))
    monkeypatch.setattr(repo, "page_own_reimbursements", AsyncMock(return_value=(25, [receipt])))
    page2 = run(service.recent_requests(env.user, page=2, page_size=20))
    assert all(item.get("reimbursement_id") for item in page2["items"])
    assert page2["total"] == 25 and page2["page"] == 2
    assert len(page2["drafts"]) == 1


def test_submitted_portal_detail_keeps_owned_invoice_metadata(env, monkeypatch):
    env.row.reimbursement_id = uuid4()
    repo.own_result.return_value = SimpleNamespace(**{**vars(env.row), "id": env.row.reimbursement_id,
        "status_code": "submitted", "subject": "正式单据的事由", "amount": Decimal("20.00")})
    file_id = uuid4()
    listing = AsyncMock(return_value=[SimpleNamespace(id=file_id, original_file_name="invoice.pdf",
                       file_size=1234, content_type="application/pdf")])
    monkeypatch.setattr(service.files, "list_for_business", listing)
    data = run(service.detail(env.user, env.row.id))
    assert data["employee_name"] == env.person.full_name
    assert data["attachments"] == [{"id": str(file_id), "file_name": "invoice.pdf",
                                    "file_size": 1234, "content_type": "application/pdf"}]
    assert listing.await_args.args[2] == [env.row.reimbursement_id]
    assert data["status"] == "submitted"
    assert data["subject"] == "正式单据的事由" and data["amount"] == "20.00"
    service.files.pending_items.assert_not_awaited()


def test_formal_history_and_detail_use_employee_not_creator():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda: [], first=lambda: None)))
    employee_id, reimbursement_id = uuid4(), uuid4()
    run(repo.own_reimbursements(session, employee_id))
    sql = str(session.exec.await_args.args[0].compile(dialect=dialect()))
    assert "employee_id =" in sql and "deleted_at IS NULL" in sql and "LIMIT" in sql
    assert "created_by =" not in sql and "employee_expense_request" not in sql and "org_id =" not in sql
    run(repo.own_reimbursement(session, employee_id, reimbursement_id))
    statement = session.exec.await_args.args[0]
    assert employee_id in statement.compile().params.values() and reimbursement_id in statement.compile().params.values()
    assert "deleted_at IS NULL" in str(statement.compile(dialect=dialect()))


def test_formal_detail_and_files_allow_owned_admin_entry_and_deny_other_employee(env, monkeypatch):
    receipt = SimpleNamespace(**{**vars(env.row), "id": uuid4(), "status_code": "posted"})
    lookup = AsyncMock(return_value=receipt)
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(repo, "own_reimbursement", lookup)
    monkeypatch.setattr(service.files, "list_for_business", listing)
    data = run(service.reimbursement_detail(env.user, receipt.id))
    assert data["reimbursement_id"] == str(receipt.id) and data["status"] == "posted"
    lookup.assert_awaited_with(env.session, env.person.id, receipt.id)
    assert run(service.can_read_own_reimbursement(env.session, env.user, receipt.id)) is True
    lookup.return_value = None
    listing.reset_mock()
    with pytest.raises(AppException) as exc:
        run(service.reimbursement_detail(env.user, uuid4()))
    assert exc.value.status_code == 404
    listing.assert_not_awaited()
    assert run(service.can_read_own_reimbursement(env.session, env.user, uuid4())) is False
    repo.current_binding.return_value = []
    lookup.reset_mock()
    assert run(service.can_read_own_reimbursement(env.session, env.user, receipt.id)) is False
    lookup.assert_not_awaited()


def test_mcp_token_is_not_a_normal_access_token(env, monkeypatch):
    from app.auth import token as tokens
    settings = SimpleNamespace(jwt_secret="unit-secret-for-mcp-tests-only-123456", access_token_audience="authenticated")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(tokens, "get_settings", lambda: settings)
    now = int(__import__('time').time())
    parent = jwt.encode({"sub":str(env.user.auth_user_id),"tenant_id":str(env.user.tenant_id),"aud":"authenticated","type":"access","iat":now,"exp":now+120}, settings.jwt_secret, algorithm="HS256")
    issued = auth.issue_token(env.user, parent)
    assert issued["expires_in"] == 30 * 24 * 60 * 60
    assert issued["expires_at"] == now + issued["expires_in"]
    claims = jwt.decode(issued["access_token"], settings.jwt_secret, algorithms=["HS256"], audience=auth.AUDIENCE)
    assert claims["scope"] == "reimbursement:self"
    with pytest.raises(HTTPException):
        tokens.verify_access_token(issued["access_token"])


def test_http_transport_and_confirmation_surface(env, monkeypatch):
    from app.modules.sample_app import employee_mcp as server
    monkeypatch.setattr(server, "enforce_fixed_window_rate_limit", AsyncMock())
    monkeypatch.setattr(protocol, "dispatch", AsyncMock(return_value={"jsonrpc":"2.0","id":1,"result":{}}))
    server.app.dependency_overrides[auth.mcp_user] = lambda: env.user
    client = TestClient(server.app, base_url=server.config.public_url)
    headers = {"Accept":"application/json, text/event-stream","MCP-Protocol-Version":protocol.VERSION}
    try:
        assert client.post("/mcp/sample-app/employee", json={"jsonrpc":"2.0","id":1,"method":"ping"},headers=headers).status_code == 200
        assert client.post("/mcp/sample-app/employee", json={"jsonrpc":"2.0","method":"notifications/initialized"},headers=headers).status_code == 202
        assert client.post("/mcp/sample-app/employee", json={"jsonrpc":"2.0","method":"tools/call"},headers=headers).status_code == 400
        assert client.post("/mcp/sample-app/employee", json=[],headers=headers).status_code == 400
        assert client.get("/mcp/sample-app/employee").status_code == 405
        assert client.get("/",headers={"Origin":"https://evil.invalid"}).status_code == 403
        assert client.get("/",headers={"Host":"evil.invalid"}).status_code == 403
        assert client.post("/employee/approve",json={"request_id":str(env.row.id)}).status_code == 401
        assert client.get("/employee/requests").status_code == 401
        assert client.get("/employee/reimbursements/"+str(env.row.id)).status_code == 401
        assert client.post("/employee/prepare",json={}).status_code == 401
        assert client.post("/employee/submit",json={"request_id":str(env.row.id)}).status_code == 401
        assert client.post("/employee/revise",json={"request_id":str(env.row.id)}).status_code == 401
        assert client.get("/").status_code == 200
        assert client.get("/portal.js").status_code == 200
        assert client.get("/portal.css").status_code == 200
        connection = client.get("/employee/connection")
        assert connection.status_code == 200
        assert connection.json() == {
            "name": "快盒员工报销", "transport": "Streamable HTTP",
            "mcp_url": server.config.public_url + "/mcp/sample-app/employee",
            "auth_type": "Bearer", "header_name": "Authorization",
        }
        assert connection.headers["cache-control"] == "no-store"
    finally:
        server.app.dependency_overrides.clear()


def test_manual_prepare_source_is_server_assigned(env, monkeypatch):
    from app.modules.sample_app import employee_mcp as server
    prepare = AsyncMock(return_value={"request_id": str(env.row.id)})
    monkeypatch.setattr(service, "prepare", prepare)
    server.app.dependency_overrides[auth.normal_employee] = lambda: env.user
    try:
        client = TestClient(server.app, base_url=server.config.public_url)
        body = {"request_key": "manual-prepare", "subject": "事由", "amount": "10.00",
                "occurred_on": "2026-10-26", "files": [env.invoice]}
        assert client.post("/employee/prepare", json=body).status_code == 200
        assert prepare.await_args.kwargs == {"source": "manual"}
        assert client.post("/employee/prepare", json={**body, "source_code": "mcp"}).status_code == 422
        assert prepare.await_count == 1
    finally:
        server.app.dependency_overrides.clear()


def test_browser_session_cookie_rotates_and_logs_out(monkeypatch):
    from time import time
    from app.modules.sample_app import employee_mcp as server

    expires = int(time()) + 600
    login = AsyncMock(return_value={"code": 0, "data": {"user": {"display_name": "本人"},
        "session": {"access_token": "first-access", "refresh_token": "first-refresh", "session_expires_at": expires}}})
    renew = AsyncMock(return_value={"code": 0, "data": {"access_token": "second-access",
        "refresh_token": "second-refresh", "session_expires_at": expires}})
    user_id = uuid4()
    revoke = AsyncMock()
    monkeypatch.setattr(server, "auth_login", login)
    monkeypatch.setattr(server, "auth_refresh", renew)
    monkeypatch.setattr(server, "verify_refresh_token", AsyncMock(return_value=SimpleNamespace(user_id=user_id)))
    monkeypatch.setattr(server, "revoke_refresh_token", revoke)
    client = TestClient(server.app, base_url=server.config.public_url)
    assert client.post("/employee/session/refresh", json={}).status_code == 401
    result = client.post("/employee/session/login", json={"login_name": "tester", "password": "test-password",
        "captcha_id": "captcha", "captcha_code": "abcd"})
    assert result.status_code == 200 and "refresh_token" not in result.json()["data"]["session"]
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Path=/employee/session" in cookie and "SameSite=strict" in cookie
    result = client.post("/employee/session/refresh", json={})
    assert result.status_code == 200 and "refresh_token" not in result.json()["data"]
    assert renew.await_args.args[0].refresh_token == "first-refresh"
    assert client.cookies[server.SESSION_COOKIE] == "second-refresh"
    assert client.post("/employee/session/logout", json={}).status_code == 200
    revoke.assert_awaited_once_with("second-refresh", user_id)
    assert client.post("/employee/session/refresh", json={}).status_code == 401


def test_portal_lists_own_software_claims():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda: [], one=lambda: 0)))
    user_id, employee_id = uuid4(), uuid4()
    total, rows = run(repo.page_own_software_claims(session, user_id, employee_id, page=2, page_size=10))
    assert total == 0 and rows == []
    compiled = session.exec.await_args.args[0].compile(dialect=dialect())
    sql = str(compiled)
    assert "user_id =" in sql and "employee_id =" in sql and "LIMIT" in sql and "OFFSET" in sql
    assert "status_code IN" in sql and "deleted_at IS NULL" in sql
    assert all(value in compiled.params.values() for value in (user_id, employee_id, 10, 10))


def test_portal_pages_own_reimbursements():
    session = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda: [], one=lambda: 0)))
    employee_id = uuid4()
    total, rows = run(repo.page_own_reimbursements(session, employee_id, page=1, page_size=20))
    assert total == 0 and rows == []
    compiled = session.exec.await_args.args[0].compile(dialect=dialect())
    sql = str(compiled)
    assert "employee_id =" in sql and "deleted_at IS NULL" in sql and "LIMIT" in sql
    assert "created_by =" not in sql and "org_id =" not in sql
    assert 20 in compiled.params.values()


def test_change_password_rejects_mismatched_confirmation(env, monkeypatch):
    from app.modules.sample_app.employee_mcp_schemas import ChangePasswordBody
    body = ChangePasswordBody(current_password="old-pass-1", new_password="new-pass-12", confirm_password="other")
    with pytest.raises(AppException, match="两次输入"):
        run(service.change_password(env.user, body))


def test_portal_markup_includes_software_history_and_password_form():
    from app.modules.sample_app.employee_mcp_portal import HTML, JAVASCRIPT
    assert 'id="softwareHistory"' in HTML
    assert 'id="passwordForm"' in HTML
    assert 'id="expensePager"' in HTML and 'id="softwarePager"' in HTML
    assert "/employee/software-claims" in JAVASCRIPT
    assert "page_size=" in JAVASCRIPT
    assert "/employee/session/change-password" in JAVASCRIPT
