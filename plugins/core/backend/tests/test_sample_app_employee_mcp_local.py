"""本地上传编排与授权目录，HTTP 均模拟，不测试真实 OSS。"""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
import pytest
from app.modules.sample_app.employee_mcp_local import LocalClient, ReimbursementInput, validate_base_url


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def local(tmp_path):
    root = tmp_path / "invoices"
    root.mkdir()
    file = root / "receipt.pdf"
    file.write_bytes(b"%PDF-1.4\nunit invoice")
    client = LocalClient(roots=[root], state_path=tmp_path/"state.bin", open_browser=lambda _: None)
    return client, file


def test_missing_reason_does_not_read_file_or_network(local, monkeypatch):
    client, file = local
    monkeypatch.setattr(client, "read_invoice", lambda _: pytest.fail("不应读取文件"))
    result = run(client.reimburse(ReimbursementInput(file_paths=[str(file)])))
    assert result["status"] == "needs_input" and result["missing_fields"] == ["subject"]


def test_file_roots_extension_and_magic_are_enforced(local, tmp_path):
    client, file = local
    content, description = client.read_invoice(str(file))
    assert description["content_md5"] == base64.b64encode(hashlib.md5(content).digest()).decode()
    outside = tmp_path/"outside.pdf"
    outside.write_bytes(content)
    with pytest.raises(ValueError):
        client.read_invoice(str(outside))
    file.write_bytes(b"not an invoice PDF")
    with pytest.raises(ValueError):
        client.read_invoice(str(file))
    with pytest.raises(ValueError):
        client.read_invoice("relative.pdf")
    secret = file.with_suffix(".env")
    secret.write_text("secret")
    with pytest.raises(ValueError):
        client.read_invoice(str(secret))


def test_symlink_cannot_escape_authorized_root(local, tmp_path):
    client, file = local
    outside = tmp_path/"outside.pdf"
    outside.write_bytes(b"%PDF-1.4\nnot allowed")
    link = file.parent/"link.pdf"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("此 Windows 用户没有创建符号链接权限")
    with pytest.raises(ValueError):
        client.read_invoice(str(link))


def test_upload_hosts_and_redirect_style_urls_are_restricted(local):
    client, _ = local
    assert client.upload_url("https://bucket.oss-cn-beijing.aliyuncs.com/key")
    for value in ("https://attacker.invalid/file", "http://169.254.169.254/secret", "https://aliyuncs.com.attacker.invalid/key", "https://user:pass@bucket.oss-cn-beijing.aliyuncs.com/key"):
        with pytest.raises(ValueError):
            client.upload_url(value)
    for value in ("http://remote.example", "https://a.example/path", "https://u:p@a.example"):
        with pytest.raises(ValueError):
            validate_base_url(value)


def test_credentials_stay_in_protected_state_not_results(local):
    client, _ = local
    client.state={"access_token":"not-for-model", "expires_at":9999999999}
    client.save_state()
    loaded=LocalClient(roots=client.roots,state_path=client.state_path)
    assert loaded.state["access_token"] == "not-for-model"
    if os.name == "nt":
        assert b"not-for-model" not in client.state_path.read_bytes()
    else:
        assert client.state_path.stat().st_mode & 0o077 == 0


def test_pairing_returns_browser_link_without_device_secret(local, monkeypatch):
    client, _ = local
    monkeypatch.delenv("KUAIHE_EMPLOYEE_MCP_TOKEN", raising=False)
    client.api=AsyncMock(return_value={"device_code":"device-secret","verification_url":client.base_url+"/?browser_code=public-code"})
    async def execute():
        async with httpx.AsyncClient() as http:
            return await client.authenticated(http)
    token, result = run(execute())
    assert token is None and result["status"] == "needs_login"
    assert "device-secret" not in json.dumps(result)
    assert client.load_state()["device_code"] == "device-secret"


def test_single_tool_uploads_once_and_retries_without_upload(local, monkeypatch):
    client, file = local
    uploaded_requests = []
    def transport(request):
        uploaded_requests.append(request)
        assert "authorization" not in request.headers
        assert request.content.startswith(b"%PDF-")
        return httpx.Response(200)
    client.transport=httpx.MockTransport(transport)
    client.authenticated=AsyncMock(return_value=("employee-only-token", None))
    state={"uploaded":False, "approved":False}
    calls=[]
    description=client.read_invoice(str(file))[1]
    async def rpc(_http,_token,name,arguments):
        calls.append((name,arguments))
        if name == "prepare_reimbursement": return {"request_id":"unit-request"}
        if name == "get_my_reimbursement_result":
            if state["approved"]:
                return {"reimbursement_id":"one-result","status":"submitted","attachments":[description]}
            return {"attachments":[description] if state["uploaded"] else []}
        if name == "create_invoice_upload_tickets":
            assert len(arguments["files"]) == 1
            return {"tickets":[{"id":"unit-file","upload":{"method":"PUT","url":"https://unit.oss-cn-beijing.aliyuncs.com/file", "headers":{"Content-Type":description["content_type"],"Content-MD5":description["content_md5"]}}}]}
        if name == "complete_invoice_upload": state["uploaded"]=True; return {"attached":True}
        raise AssertionError(name)
    monkeypatch.setattr(client,"rpc",rpc)
    body=ReimbursementInput(subject="出差",amount="10",occurred_on="2026-10-24",invoice_title="示例费用科技有限公司",file_paths=[str(file)])
    first=run(client.reimburse(body))
    assert first["status"] == "needs_confirmation" and len(uploaded_requests)==1
    assert "submit_reimbursement" not in [name for name, _ in calls]
    state["approved"]=True
    second=run(client.reimburse(body))
    assert second["reimbursement_id"] == "one-result" and len(uploaded_requests)==1
    keys=[arguments["request_key"] for name,arguments in calls if name=="prepare_reimbursement"]
    assert keys[0] == keys[1]
    preparation=next(arguments for name,arguments in calls if name=="prepare_reimbursement")
    assert preparation["files"] == [description] and preparation["invoice_manifest_hash"]
    assert preparation["invoice_title"] == "示例费用科技有限公司"


def test_duplicate_files_rejected_before_contacting_service(local):
    client,file=local
    client.authenticated=AsyncMock()
    body=ReimbursementInput(subject="出差",amount="10",occurred_on="2026-10-24",invoice_title="示例费用科技有限公司",file_paths=[str(file),str(file)])
    with pytest.raises(ValueError):
        run(client.reimburse(body))
    client.authenticated.assert_not_awaited()


def test_software_claim_asks_when_no_date_and_no_period_before_network(local):
    from datetime import date
    from app.modules.sample_app.employee_mcp_local import SoftwareClaimInput
    client, file = local
    client.authenticated = AsyncMock()
    current = f"{date.today():%Y-%m}"
    body = SoftwareClaimInput(period_month=current, file_paths=[str(file)],
                              items=[{"amount": "88", "merchant_name": "Cursor", "source_code": "alipay"}])
    result = run(client.software_claim(body))
    assert result["status"] == "needs_input"
    assert result["missing_items"] == [1]
    assert "suggested_period_month" in result
    client.authenticated.assert_not_awaited()


def test_software_claim_transaction_month_must_match_declared_payroll_month(local):
    from datetime import date
    from app.modules.sample_app.employee_mcp_local import SoftwareClaimInput
    client, file = local
    client.authenticated = AsyncMock()
    current = f"{date.today():%Y-%m}"
    body = SoftwareClaimInput(period_month=current, file_paths=[str(file)],
                              items=[{"occurred_on": f"{current}-01", "amount": "88", "merchant_name": "Cursor", "source_code": "alipay"},
                                     {"occurred_on": "2000-01-15", "amount": "10", "merchant_name": "ChatGPT", "source_code": "alipay"}])
    result = run(client.software_claim(body))
    assert result["status"] == "needs_split"
    assert "2000-01" in result["conflicting_months"]
    client.authenticated.assert_not_awaited()


def test_software_claim_uploads_once_and_retries_without_upload(local, monkeypatch):
    from datetime import date
    from app.modules.sample_app.employee_mcp_local import SoftwareClaimInput
    client, file = local
    uploaded_requests = []

    def transport(request):
        uploaded_requests.append(request)
        return httpx.Response(200)

    client.transport = httpx.MockTransport(transport)
    client.authenticated = AsyncMock(return_value=("employee-only-token", None))
    description = client.read_invoice(str(file))[1]
    state = {"uploaded": False}
    period = f"{date.today():%Y-%m}"
    calls = []

    async def rpc(_http, _token, name, arguments):
        calls.append((name, arguments))
        if name == "prepare_software_claim":
            assert arguments["period_month"] == period
            assert arguments["items"][0]["billing_month"] == period
            return {"request_id": "claim-unit", "claimed_amount": "88.00", "applied_amount": "88.00"}
        if name == "get_my_software_claim":
            return {"status": "ready" if state["uploaded"] else "preparing",
                    "attachments": [description] if state["uploaded"] else []}
        if name == "create_software_claim_upload_tickets":
            return {"tickets": [{"id": "claim-file", "upload": {
                "method": "PUT", "url": "https://unit.oss-cn-beijing.aliyuncs.com/file",
                "headers": {"Content-Type": description["content_type"], "Content-MD5": description["content_md5"]}}}]}
        if name == "complete_software_claim_upload":
            state["uploaded"] = True
            return {"attached": True}
        raise AssertionError(name)

    monkeypatch.setattr(client, "rpc", rpc)
    body = SoftwareClaimInput(period_month=period, file_paths=[str(file)],
                              items=[{"occurred_on": "2026-10-08", "billing_month": period, "amount": "88", "merchant_name": "Cursor", "source_code": "wechat"}])
    first = run(client.software_claim(body))
    assert first["status"] == "needs_confirmation"
    assert first["confirmation_url"].endswith("software_claim_id=claim-unit")
    assert len(uploaded_requests) == 1
    second = run(client.software_claim(body))
    assert second["status"] == "needs_confirmation"
    assert len(uploaded_requests) == 1
