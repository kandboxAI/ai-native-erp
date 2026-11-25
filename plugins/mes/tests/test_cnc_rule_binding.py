"""报价工艺专属规则：优先级、真实外键、数据范围与模型出口；无真实库或模型调用。"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core.exceptions import AppException
from app.modules.mes.cnc import ai
from app.modules.mes.cnc.models import CncRuleEntry, CncRuleSet
from app.modules.mes.cnc.repository import repository
from app.modules.mes.cnc.rules import ProcessRule, ExternalRule, RuleConfig, RulesEdit, apply_rules
from app.modules.mes.process_matching import validate_rule_bindings


def process(kind="in_house", name="CNC4", no="GY006"):
    return dict(id=uuid4(), process_no=no, process_name=name, processing_type_code=kind)


def config_for(p, *, active=True, rate=150):
    return RuleConfig(processes=[
        ProcessRule(id="exact", name="四轴价格", process_id=p["id"], process_type_code="cnc", hourly_rate=rate, is_active=active),
    ])


@pytest.mark.parametrize("active,expected", [(True, "150"), (False, None)])
def test_only_enabled_exact_process_can_supply_a_rate(active, expected):
    p = process()
    _, rows, _ = apply_rules({}, [dict(name="CNC4", process_id=p["id"], quote_rule_no="generic", unit_hours="0.2")], {}, config_for(p, active=active), 3)
    assert rows[0]["hourly_rate"] == expected
    if active:
        assert rows[0]["parameter_sources"]["hourly_rate"]["rule_no"] == "exact"
    assert rows[0]["unit_hours"] == "0.2"


def test_other_process_cannot_borrow_bound_rate_even_with_old_rule_number():
    p = process()
    _, rows, _ = apply_rules({}, [dict(name="CNC2", process_id=uuid4(), quote_rule_no="exact", process_type_code="cnc")], {}, config_for(p), 1)
    assert rows[0]["hourly_rate"] is None


def test_manual_values_and_previous_frozen_quote_are_preserved():
    p = process()
    original = dict(name="CNC4", process_id=str(p["id"]), hourly_rate="88", unit_hours="0.4")
    frozen = json.dumps(original, sort_keys=True)
    _, rows, _ = apply_rules({}, [original], {}, config_for(p), 2)
    assert rows[0]["hourly_rate"] == "88" and rows[0]["unit_hours"] == "0.4"
    assert json.dumps(original, sort_keys=True) == frozen


def test_missing_exact_price_does_not_silently_use_generic_price():
    p = process()
    _, rows, _ = apply_rules({}, [dict(name="CNC4", process_id=p["id"])], {}, config_for(p, rate=None), 1)
    assert rows[0]["hourly_rate"] is None


def test_external_binding_uses_exact_unit_rate():
    p = process("outsourced", "硬质氧化", "OUT01")
    config = RuleConfig(processes=[], external_processes=[
        ExternalRule(id="exact", name="专属氧化", process_id=p["id"], price_unit_code="m2", rate_per_m2=90, minimum_unit=3),
    ])
    _, rows, _ = apply_rules({}, [dict(name="硬质氧化", process_id=p["id"], pricing_mode_code="external", quote_rule_no="general")], {}, config, 2)
    assert rows[0]["external_rate"] == "90" and rows[0]["external_price_unit_code"] == "m2"
    assert rows[0]["external_minimum_unit"] == "3" and rows[0]["quote_rule_no"] == "exact"


def test_binding_contract_requires_real_uuid_and_one_active_rule_per_process():
    p = process()
    with pytest.raises(ValidationError):
        ProcessRule(id="bad", name="bad", process_id="CNC4")
    with pytest.raises(ValidationError):
        ProcessRule(id="bad", name="bad")
    with pytest.raises(ValidationError, match="只能启用一条"):
        RuleConfig(processes=[ProcessRule(id=str(i), name="专属", process_id=p["id"]) for i in range(2)])
    assert ProcessRule(id="ok", name="专属", process_id=p["id"]).keywords == []
    assert CncRuleEntry.__table__.c.process_id.nullable
    fk = next(iter(CncRuleEntry.__table__.c.process_id.foreign_keys))
    assert fk.target_fullname == "mes_process.id" and fk.ondelete == "RESTRICT"


@pytest.mark.parametrize("failure", ["not_visible", "outsourced", "category"])
def test_binding_rejects_foreign_scope_inactive_mode_and_category(failure):
    p = process("outsourced" if failure == "outsourced" else "in_house", "下料" if failure == "category" else "CNC4")
    with pytest.raises(AppException):
        validate_rule_bindings(config_for(p), [] if failure == "not_visible" else [p])


def test_rule_binding_round_trip_uses_real_column_and_not_json_association():
    p = process(); config = config_for(p); owner = CncRuleSet(org_id=uuid4())
    written = []
    session = NS(execute=AsyncMock(), add=written.append)
    asyncio.run(repository.save_rules(session, owner, config, NS(user_id=uuid4())))
    bound = next(row for row in written if row.rule_no == "exact")
    assert bound.process_id == p["id"] and "process_id" not in bound.definition
    session.execute = AsyncMock(side_effect=[NS(scalar_one_or_none=lambda: owner), NS(scalars=lambda: NS(all=lambda: written))])
    _, restored = asyncio.run(repository.rules(session, NS(permissions=["mes:quote:list"], org_id=owner.org_id, org_access_mode_code="all", permission_scopes={"mes:quote:list": "all"})))
    assert restored.processes[0].process_id == p["id"]


@pytest.mark.parametrize("mode,valid", [("hourly", True), ("external", True), ("hourly", False)])
def test_ai_bound_rule_uses_only_safe_exact_archive_and_cannot_switch_process(monkeypatch, mode, valid):
    p = process("outsourced" if mode == "external" else "in_house")
    decision = dict(rule_no="exact", used=True, process_no=None if valid else "OTHER", unit_hours="0.1" if mode == "hourly" else None,
        reason="依据几何估时", work_content="加工", evidence_refs=["geometry:bounds"])
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(dict(assessments=[decision], warnings=[]))}}]}
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs["json"])
        return NS(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(ai, "cloud_request", request)
    cfg = NS(ai_base_url="https://invalid.example/v1", ai_model="offline", ai_api_key=SecretStr("offline"), ai_request_timeout=10)
    def run():
        return ai.plan_operations(None, dict(facts=[], operations=[], warnings=[], total_pages=0), dict(documents=[], geometry={"bounds": [1, 2, 3]}),
            cfg, time.monotonic()+30, 2, [dict(id="exact", name="专属", process_id=str(p["id"]), pricing_mode_code=mode, hourly_rate=150)], {}, [p])
    if valid:
        result = run()
        assert result["operations"][0]["process_id"] == str(p["id"])
        prompt = calls[0]["messages"][0]["content"]
        context = json.loads(prompt.split("。整件上下文：", 1)[1])
        assert context["factory_processes"][0]["bound_process_no"] == p["process_no"]
        assert str(p["id"]) not in prompt and "hourly_rate" not in str(context["factory_processes"])
    else:
        with pytest.raises(ValueError, match="专属规则绑定不一致"):
            run()


def test_rule_save_validates_before_mutating_and_returns_scoped_options(monkeypatch):
    from app.modules.mes.cnc import service as module
    p = process(); owner = CncRuleSet(org_id=uuid4(), version_no=1)
    session = NS(commit=AsyncMock())
    @asynccontextmanager
    async def context(): yield session
    repo = NS(rules=AsyncMock(return_value=(owner, config_for(p))), save_rules=AsyncMock())
    monkeypatch.setattr(module, "get_session_context", context)
    monkeypatch.setattr(module, "repo", repo)
    catalogue = AsyncMock(return_value=[])
    monkeypatch.setattr(module, "matching_catalog", catalogue)
    body = RulesEdit(version_no=1, config=config_for(p))
    with pytest.raises(AppException):
        asyncio.run(module.service.rules(NS(), body))
    repo.save_rules.assert_not_awaited(); session.commit.assert_not_awaited()
    catalogue.return_value = [dict(**p, description="PRIVATE")]
    result = asyncio.run(module.service.rules(NS(), body))
    assert result["manufacturing_processes"] == [dict(id=str(p["id"]), process_no=p["process_no"], process_name="CNC4", processing_type_code="in_house", process_type_code="cnc")]
    assert catalogue.await_args.kwargs["lock"] is True
    repo.save_rules.assert_awaited_once(); session.commit.assert_awaited_once()
    saved_config = repo.save_rules.await_args.args[2]
    assert saved_config.processes[0].name == p["process_name"]
    assert saved_config.processes[0].process_type_code == "cnc"


def test_ai_keeps_different_cnc_archives_and_applies_each_dedicated_rate(monkeypatch):
    from app.modules.mes.cnc.drafts import apply_draft
    p2, p4 = process(name="CNC2", no="GY005"), process()
    cfg = RuleConfig(processes=[
        ProcessRule(id="two", name="三轴", process_id=p2["id"], hourly_rate=100),
        ProcessRule(id="four", name="四轴", process_id=p4["id"], hourly_rate=180),
    ])
    decisions = [dict(rule_no=rule.id, used=bool(rule.process_id), process_no=None,
        unit_hours="0.1" if rule.process_id else None, reason="按不同加工内容估时",
        work_content="加工", evidence_refs=["geometry:bounds"] if rule.process_id else []) for rule in cfg.processes if rule.process_id]
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(dict(assessments=decisions, warnings=[]))}}]}
    monkeypatch.setattr(ai, "cloud_request", lambda *a, **k: NS(raise_for_status=lambda: None, json=lambda: payload))
    settings = NS(ai_base_url="https://invalid.example/v1", ai_model="offline", ai_api_key=SecretStr("offline"), ai_request_timeout=10)
    result = ai.plan_operations(None, dict(facts=[], operations=[], warnings=[], total_pages=0), dict(documents=[], geometry={"bounds": [1, 2, 3]}),
        settings, time.monotonic()+30, 2, [{**r.model_dump(mode="json"), "pricing_mode_code": "hourly"} for r in cfg.processes], {}, [p2, p4])
    _, draft, _ = apply_draft({}, [], {"ai": result}, str(uuid4()), 2)
    _, rows, _ = apply_rules({}, draft, {}, cfg, 1)
    assert [(r["name"], r["hourly_rate"], r["quote_rule_no"]) for r in rows] == [("CNC2", "100", "two"), ("CNC4", "180", "four")]


@pytest.mark.parametrize("mode", ["hourly", "external"])
def test_ai_rejects_old_unbound_rules_before_calling_model(monkeypatch, mode):
    monkeypatch.setattr(ai, "cloud_request", lambda *a, **k: pytest.fail("旧通用规则不得发给模型"))
    with pytest.raises(ValueError, match="必须绑定现有正式工艺"):
        ai.plan_operations(None, dict(facts=[], operations=[], warnings=[], total_pages=0),
            dict(documents=[], geometry={}), NS(), time.monotonic()+30, 1,
            [dict(id="legacy", name="通用工序", keywords=["CNC"], pricing_mode_code=mode)], {}, [process()])


@pytest.mark.parametrize("cls", [ProcessRule, ExternalRule])
@pytest.mark.parametrize("active", [True, False])
def test_production_rules_cannot_use_keywords_instead_of_archive_binding(cls, active):
    with pytest.raises(ValidationError):
        cls(id="legacy", name="通用", keywords=["CNC"], is_active=active)
    with pytest.raises(ValidationError):
        cls(id="legacy", name="通用", process_id=None, keywords=["CNC"], is_active=active)


def test_initial_rules_are_only_extracted_from_archives_without_guessed_prices():
    from app.modules.mes.cnc.rules import archive_rules
    p = process()
    external = process("outsourced", "喷砂", "OUT01")
    assert RuleConfig().processes == [] and RuleConfig().external_processes == []
    assert archive_rules([]).processes == []
    config = archive_rules([p, external])
    assert [(r.name, r.process_id) for r in config.processes] == [(p["process_name"], p["id"])]
    assert config.processes[0].process_type_code == "cnc" and config.processes[0].hourly_rate is None
    assert [(r.name, r.process_id) for r in config.external_processes] == [(external["process_name"], external["id"])]
    assert config.external_processes[0].rate_per_kg is None


def test_same_name_or_category_without_process_binding_never_supplies_price():
    p = process()
    for value in (dict(name="CNC4", quote_rule_no="exact", process_type_code="cnc"),
                  dict(name="CNC4", process_id=uuid4(), quote_rule_no="exact")):
        _, rows, summary = apply_rules({}, [value], {}, config_for(p), 1)
        assert rows[0]["hourly_rate"] is None and summary["unmatched_operations"] == ["CNC4"]


def test_first_rule_read_seeds_only_scoped_archives_without_private_prices(monkeypatch):
    from app.modules.mes import process_matching
    p = process()
    external = process("outsourced", "喷砂", "OUT01")
    catalogue = AsyncMock(return_value=[p, external])
    monkeypatch.setattr(process_matching, "matching_catalog", catalogue)
    written = []
    session = NS(add=written.append, flush=AsyncMock(), execute=AsyncMock(side_effect=[
        NS(scalar_one_or_none=lambda: None),
        NS(first=lambda: None),
        None,  # 初始化 save_rules 的 DELETE，当前组织还没有任何规则。
        NS(scalars=lambda: NS(all=lambda: [r for r in written if isinstance(r, CncRuleEntry)])),
    ]))
    user = NS(user_id=uuid4(), org_id=uuid4(), org_access_mode_code="all",
              permissions=["mes:quote:list"], permission_scopes={"mes:quote:list": "all"})
    _, config = asyncio.run(repository.rules(session, user))
    assert config.materials == []
    assert [r.process_id for r in config.processes] == [p["id"]]
    assert [r.process_id for r in config.external_processes] == [external["id"]]
    assert config.processes[0].hourly_rate is None and config.external_processes[0].rate_per_kg is None
    catalogue.assert_awaited_once_with(session, user.org_id, user, "mes:quote:list", lock=True)
