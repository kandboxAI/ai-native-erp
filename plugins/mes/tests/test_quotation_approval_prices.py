"""审核定价：价格、交期与审计原子保存；真实库和外部模型不参与。"""
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import UUID, uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlmodel import Session
from app.core.exceptions import AppException
from app.modules.mes.quotation_models import MesQuotationEvent
from app.modules.mes.quotation_schemas import QuotationApprovalBody, QuotationCommand, EngineeringBody
from app.modules.mes.quotation_service import service
from test_quotations import store, run, attach


def ready(store):
    body = store.body.model_copy(deep=True)
    body.lines[0].quantity_tiers = [Decimal(20), Decimal(30)]
    quote = run(service.save(None, body, store.user))
    attach(store, quote)
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), store.user))
    row = quote["lines"][0]
    return run(service.engineering(quote["id"], EngineeringBody(version_no=quote["version_no"], lines=[dict(
        id=row["id"], quoted_material="AL6082", weight_kg="0.5", unit_price="12.80", engineering_note="工程核算说明",
        quantity_tiers=[dict(id=tier["id"], unit_price=value, calculation_note="原核算依据") for tier,value in zip(row["quantity_tiers"], ("12", "11"))])]), store.user, submit=True))


def body(quote):
    row = quote["lines"][0]
    return QuotationApprovalBody(version_no=quote["version_no"], price_adjustment_reason="结合客户要求调整最终售价", lines=[dict(
        id=row["id"], lead_days=18, unit_price="15.00", quantity_tiers=[dict(id=t["id"], unit_price="13.00") for t in row["quantity_tiers"]])])


def test_reviewer_changes_primary_and_tier_prices_without_engineering_permission(store):
    quote = ready(store)
    reviewer = NS(**{**vars(store.reviewer), "permissions": ["mes:quotation:list", "mes:quotation:approve"]})
    approved = run(service.approve(quote["id"], body(quote), reviewer))
    row = approved["lines"][0]
    assert approved["status_code"] == "final_review" and approved["version_no"] == quote["version_no"] + 1
    assert row["unit_price"] == "15.00" and row["lead_days"] == 18
    assert [t["unit_price"] for t in row["quantity_tiers"]] == ["13.00", "13.00"]
    full = run(service.detail(quote["id"], store.user))["lines"][0]
    assert full["engineering_note"] == "工程核算说明" and full["quoted_material"] == "AL6082"
    assert all(t["calculation_note"] == "原核算依据" for t in full["quantity_tiers"])
    logs = [e for e in approved["events"] if e["action_key"] == "approval_price"]
    assert len(logs) == 3
    assert "工程报价12.80 EUR → 审核定价15.00 EUR" in logs[0]["note"]
    assert all("P1" in e["note"] and "结合客户要求" in e["note"] for e in logs)
    with Session(store.engine) as session:
        records = session.execute(select(MesQuotationEvent).where(MesQuotationEvent.quotation_id == UUID(quote["id"]), MesQuotationEvent.action_key == "approval_price")).scalars().all()
        assert all(e.created_by == reviewer.user_id and e.version_no_snapshot == approved["version_no"] for e in records)
    with pytest.raises(AppException):
        run(service.approve(quote["id"], body(approved), reviewer))


@pytest.mark.parametrize("invalid", ["reason", "null", "missing_tier", "duplicate_tier", "foreign_tier", "stale", "self_review", "permission", "scope"])
def test_invalid_price_approval_rolls_back_prices_delivery_and_audit(store, invalid):
    quote = ready(store); supplied = body(quote); reviewer = store.reviewer
    before = run(service.detail(quote["id"], store.user))
    if invalid == "reason": supplied.price_adjustment_reason = ""
    if invalid == "null": supplied.lines[0].unit_price = None
    if invalid == "missing_tier": supplied.lines[0].quantity_tiers.pop()
    if invalid == "duplicate_tier": supplied.lines[0].quantity_tiers[1].id = supplied.lines[0].quantity_tiers[0].id
    if invalid == "foreign_tier": supplied.lines[0].quantity_tiers[1].id = uuid4()
    if invalid == "stale": supplied.version_no -= 1
    if invalid == "self_review": reviewer = store.user
    if invalid == "permission": reviewer = NS(**{**vars(reviewer), "permissions": ["mes:quotation:list", "mes:quotation:price"]})
    if invalid == "scope": reviewer = NS(**{**vars(reviewer), "org_id": store.foreign_org})
    with pytest.raises(AppException): run(service.approve(quote["id"], supplied, reviewer))
    loaded = run(service.detail(quote["id"], store.user))
    assert loaded == before


def test_unchanged_prices_need_no_reason_and_backward_compatible_delivery_only_approval(store):
    quote = ready(store)
    approved = run(service.approve(quote["id"], QuotationApprovalBody(version_no=quote["version_no"],lines=[dict(id=quote["lines"][0]["id"],lead_days=14)]), store.reviewer))
    assert approved["lines"][0]["unit_price"] == "12.80"
    assert not any(e["action_key"] == "approval_price" for e in approved["events"])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "100000001", "1.001"])
def test_approval_price_has_same_money_constraints_as_engineering(value):
    with pytest.raises(ValidationError):
        QuotationApprovalBody(version_no=1, lines=[dict(id=uuid4(),lead_days=10,unit_price=value)])
    with pytest.raises(ValidationError):
        QuotationApprovalBody(version_no=1, lines=[dict(id=uuid4(),lead_days=10,quantity_tiers=[dict(id=uuid4(),unit_price=value)])])
