"""软件报销：工资月归属、询问规则与协议注册；不连接真实库/OSS。"""
import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.exceptions import AppException
from app.modules.sample_app import software_claim_service as claims
from app.modules.sample_app.employee_mcp_protocol import TOOLS, with_link
from app.modules.sample_app.employee_mcp_schemas import SoftwareClaimItemBody, SoftwareClaimPrepareBody
from app.modules.sample_app.software_claim_period import (
    allowed_period_months, billing_problem, resolved_billing_month, suggest_period_month,
)


def test_upload_window_suggests_previous_month_until_the_fifth():
    assert suggest_period_month(date(2026, 11, 1)) == "2026-10"
    assert suggest_period_month(date(2026, 11, 5)) == "2026-10"
    assert suggest_period_month(date(2026, 11, 6)) == "2026-11"
    assert suggest_period_month(date(2026, 1, 3)) == "2025-12"


def test_allowed_payroll_months_are_previous_current_and_next():
    assert allowed_period_months(date(2026, 11, 16)) == {"2026-10", "2026-11", "2026-12"}
    assert allowed_period_months(date(2026, 12, 31)) == {"2026-11", "2026-12", "2027-01"}


def test_unidentified_billing_month_asks_with_suggestion_and_never_infers():
    result = billing_problem("2026-10", [None, "2026-10"], date(2026, 11, 3))
    assert result["status"] == "needs_input"
    assert result["missing_items"] == [1]
    assert result["suggested_period_month"] == "2026-10"
    assert "不得推断" in result["question"]


def test_billing_month_mismatch_requires_split_not_silent_move():
    result = billing_problem("2026-10", ["2026-10", "2026-11"], date(2026, 11, 3))
    assert result["status"] == "needs_split"
    assert result["conflicting_months"] == ["2026-11"]


def test_all_items_identified_for_payroll_month_pass():
    assert billing_problem("2026-11", ["2026-11", "2026-11"], date(2026, 11, 20)) is None


def test_transaction_date_decides_month_when_no_billing_period_is_printed():
    # 10-29 交易、11 月才上传：所属工资月为 10 月；入账日期不参与归属。
    item = SoftwareClaimItemBody(occurred_on=date(2026, 10, 29), amount="20", merchant_name="Cursor", source_code="alipay")
    assert resolved_billing_month(item.occurred_on, item.billing_month) == "2026-10"
    assert billing_problem("2026-10", [resolved_billing_month(item.occurred_on, None)], date(2026, 11, 3)) is None


def test_billing_period_overrides_transaction_date():
    item = SoftwareClaimItemBody(occurred_on=date(2026, 11, 2), billing_month="2026-10", amount="20", merchant_name="Cursor", source_code="invoice")
    assert resolved_billing_month(item.occurred_on, item.billing_month) == "2026-10"


def test_no_date_and_no_period_asks_instead_of_guessing():
    item = SoftwareClaimItemBody(amount="20", merchant_name="Cursor", source_code="alipay")
    assert item.occurred_on is None
    result = billing_problem("2026-10", [resolved_billing_month(item.occurred_on, item.billing_month)], date(2026, 11, 3))
    assert result["status"] == "needs_input"
    assert result["suggested_period_month"] == "2026-10"


def test_claim_amount_sums_items_without_cap():
    total, rows = claims.validate_items(
        [
            SoftwareClaimItemBody(occurred_on=date(2026, 10, 29), amount="120.50", merchant_name="Cursor", source_code="invoice"),
            SoftwareClaimItemBody(occurred_on=date(2026, 10, 2), amount="200.00", merchant_name="OpenAI", source_code="alipay"),
        ],
        ["2026-10", "2026-10"],
    )
    assert total == Decimal("320.50")
    assert [row["billing_month"] for row in rows] == ["2026-10", "2026-10"]


def test_prepare_schema_accepts_billing_month_and_bank_card_source():
    body = SoftwareClaimPrepareBody(
        request_key="software-key-01",
        period_month="2026-10",
        items=[
            {"occurred_on": "2026-10-24", "amount": "133.74", "merchant_name": "APPLE.COM/US", "source_code": "bank_card"},
            {"occurred_on": "2026-10-29", "billing_month": "2026-10", "amount": "20", "merchant_name": "Codex", "source_code": "invoice"},
        ],
        files=[{"file_name": "a.png", "content_type": "image/png", "file_size": 12, "content_md5": "AAAAAAAAAAAAAAAAAAAAAA=="}],
    )
    assert body.items[0].source_code == "bank_card"
    assert body.items[0].billing_month is None
    assert body.items[1].billing_month == "2026-10"
    assert "prepare_software_claim" in TOOLS
    assert "get_my_software_claim" in TOOLS
    linked = with_link({"request_id": "claim-1", "status": "ready"}, "https://kk.example", software=True)
    assert linked["confirmation_url"] == "https://kk.example/?software_claim_id=claim-1"


def test_admin_list_rejects_bad_period_before_database():
    with pytest.raises(AppException, match="工资月份格式"):
        asyncio.run(claims.admin_list(uuid4(), "2026-13"))


def test_admin_software_claims_is_registered_for_scoped_reads():
    from app.modules.sample_app import scoped_service
    from app.modules.sample_app.api import router
    assert "software_claims" in scoped_service._ALLOWED
    assert hasattr(scoped_service, "page_software_claims")
    assert hasattr(scoped_service, "page_reimbursements")
    assert "/api/sample_app/software-claims" in {route.path for route in router.routes}
    assert "/api/sample_app/reimbursements" in {route.path for route in router.routes}


def test_admin_page_repo_returns_empty_without_orgs():
    from app.modules.sample_app import employee_mcp_repository as employee_repo
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    session = SimpleNamespace(exec=AsyncMock())
    total, rows = asyncio.run(
        employee_repo.page_software_claims_for_orgs(session, [], "2026-11", page=1, page_size=20)
    )
    assert total == 0 and rows == []
    session.exec.assert_not_awaited()


def test_software_claim_list_route_is_registered_before_detail():
    from app.modules.sample_app import employee_mcp
    paths = [(getattr(route, "path", None), sorted(getattr(route, "methods", []) or []))
             for route in employee_mcp.app.routes]
    assert ("/employee/software-claims", ["GET"]) in paths
    assert ("/employee/session/change-password", ["POST"]) in paths
