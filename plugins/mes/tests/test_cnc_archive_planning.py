"""真实规划函数的工艺目录契约；替换HTTP，不连接外部模型或业务库。"""
import json
import time
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from pydantic import SecretStr
from app.modules.mes.cnc import ai
from app.modules.mes.cnc.drafts import apply_draft
from app.modules.mes.cnc.schemas import Specs


def fixture(monkeypatch,selected="GY006",mode="hourly",used=True):
    records=[dict(id=uuid4(),process_no=no,process_name=name,processing_type_code=kind,is_quality_required=False,description="PRIVATE-ARCHIVE-TEXT")
        for no,name,kind in (("GY005","CNC2","in_house"),("GY006","CNC4","in_house"),("OUT01","委外CNC","outsourced"))]
    decision=dict(rule_no="PRICE-CNC",used=used,process_no=selected,unit_hours="0.1" if used and mode=="hourly" else None,
        reason="按型腔和装夹要求估算",work_content="加工型腔",evidence_refs=["geometry:bounds"] if used else [])
    response=NS(raise_for_status=lambda:None,json=lambda:{"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"assessments":[decision],"warnings":[]},ensure_ascii=False)}}]})
    requests=[]
    def request(*args,**kwargs):requests.append(kwargs["json"]);return response
    monkeypatch.setattr(ai,"cloud_request",request)
    config=NS(ai_base_url="https://model.invalid/v1",ai_model="offline-test",ai_api_key=SecretStr("offline-fake-key"),ai_request_timeout=10)
    result=dict(facts=[],operations=[],warnings=[],total_pages=0)
    analysis=dict(documents=[],geometry={"bounds":[10,20,30]})
    rules=[dict(id="PRICE-CNC",name="加工中心加工",process_id=str(records[1]["id"]),process_type_code="cnc",pricing_mode_code=mode,hourly_rate=999,is_active=True)]
    def run():return ai.plan_operations(None,result,analysis,config,time.monotonic()+30,10,rules,{},records)
    return records,requests,run


def test_ai_sees_safe_authorized_archive_definitions_and_persists_exact_selected_process(monkeypatch):
    records,requests,run=fixture(monkeypatch)
    result=run();row=result["operations"][0]
    assert row["name"]=="CNC4" and row["process_id"]==str(records[1]["id"])
    assert row["process_no_snapshot"]=="GY006" and row["quote_rule_no"]=="PRICE-CNC"
    assert row["unit_hours"]=="0.1"
    prompt=requests[0]["messages"][0]["content"]
    context=json.loads(prompt.split("。整件上下文：",1)[1])
    assert context["manufacturing_processes"][1]==dict(process_no="GY006",process_name="CNC4",processing_type_code="in_house")
    assert "PRIVATE-ARCHIVE-TEXT" not in prompt and str(records[1]["id"]) not in prompt
    assert "hourly_rate" not in str(context["factory_processes"])
    schema = json.loads(prompt.split("严格符合 Schema：", 1)[1].split("。整件上下文：", 1)[0])
    choices = schema["$defs"]["AIProcessDecision"]["properties"]["process_no"]["anyOf"]
    assert next(item["enum"] for item in choices if item.get("type") == "string") == ["GY005", "GY006", "OUT01"]
    _,draft,_=apply_draft(Specs().model_dump(mode="json"),[],{"ai":result},str(uuid4()),10)
    assert draft[0]["process_id"]==row["process_id"] and draft[0]["process_no_snapshot"]=="GY006"


@pytest.mark.parametrize("selected",["INVENTED","OUT01"])
def test_unknown_or_outsource_in_hourly_archive_choice_is_rejected(monkeypatch,selected):
    _,_,run=fixture(monkeypatch,selected=selected)
    with pytest.raises(ValueError,match="专属规则绑定不一致"):run()


def test_dedicated_rule_uses_its_exact_archive_when_model_omits_number(monkeypatch):
    records,_,run=fixture(monkeypatch,selected=None)
    assert run()["operations"][0]["process_id"] == str(records[1]["id"])


def test_canonical_archive_name_does_not_break_existing_pricing_rule_rate(monkeypatch):
    from app.modules.mes.cnc.rules import RuleConfig,ProcessRule,apply_rules
    records,_,run=fixture(monkeypatch)
    operation=run()["operations"][0]
    config=RuleConfig(processes=[ProcessRule(id="PRICE-CNC",name="加工中心加工",process_id=records[1]["id"],process_type_code="cnc",hourly_rate=125)])
    _,rows,_=apply_rules(Specs().model_dump(mode="json"),[operation],{},config,1)
    assert rows[0]["name"]=="CNC4" and rows[0]["hourly_rate"]=="125"
    assert rows[0]["quote_rule_no"]=="PRICE-CNC" and rows[0]["unit_hours"]=="0.1"


def test_failed_full_plan_does_not_fall_back_to_free_text_candidates(monkeypatch, tmp_path):
    extraction = dict(facts=[], operations=[dict(name="钻攻M5螺纹孔", evidence_refs=["geometry:bounds"])], warnings=[])
    response = NS(raise_for_status=lambda: None, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(extraction)}}]})
    monkeypatch.setattr(ai, "cloud_request", lambda *a, **k: response)
    def fail(*a, **k):
        raise ValueError("没有选择有效正式工艺")
    monkeypatch.setattr(ai, "plan_operations", fail)
    cfg = NS(ai_base_url="https://model.invalid/v1", ai_model="offline", ai_api_key=SecretStr("offline"), ai_request_timeout=10, ai_total_timeout=30)
    monkeypatch.setattr(ai, "settings", lambda: cfg)
    result = ai.extract_requirements(dict(documents=[], geometry={"bounds": [10, 20, 30]}), tmp_path, quantity=1, process_rules=[])
    assert result["planning_status"] == "failed"
    assert result["operations"] == [] and result["suggested_operations"] == []
    assert result["operation_candidates"][0]["name"] == "钻攻M5螺纹孔"
    _, operations, _ = apply_draft({}, [], {"ai": result}, str(uuid4()), 1)
    assert operations == []


def test_legacy_unbound_ai_draft_cannot_be_applied():
    with pytest.raises(ValueError, match="未绑定正式工艺"):
        apply_draft({}, [], {"ai": {"planning_status": "completed", "operations": [dict(name="钻孔")] }}, str(uuid4()), 1)


def test_formal_route_validation_never_guesses_from_name_or_unique_category():
    from app.core.exceptions import AppException
    from app.modules.mes.process_matching import canonical_operations
    candidate = dict(id=uuid4(), process_no="GY005", process_name="CNC2", processing_type_code="in_house")
    with pytest.raises(AppException, match="必须从现有正式工艺"):
        canonical_operations([dict(name="CNC2")], [candidate], require_selected=True)
    row = canonical_operations([dict(name="钻攻M5螺纹孔", process_id=candidate["id"], note="钻攻M5螺纹孔")], [candidate], require_selected=True)[0]
    assert row["name"] == "CNC2" and row["note"] == "钻攻M5螺纹孔"


@pytest.mark.parametrize("bound", [False, True])
def test_quote_rejects_unselected_or_no_longer_visible_process_before_pricing(monkeypatch, bound):
    import asyncio
    from unittest.mock import AsyncMock
    from app.modules.mes.cnc import service as module
    from app.modules.mes.cnc.models import CncPart, CncOperation
    from app.modules.mes.cnc.pricing import IncompleteQuote
    from app.core.exceptions import AppException
    part = CncPart(name="测试", quantity=1, org_id=uuid4())
    operation = CncOperation(part_id=part.id, org_id=part.org_id, name="钻孔", process_id=uuid4() if bound else None)
    repo = NS(operations=AsyncMock(return_value=[operation]), add=lambda *a: pytest.fail("不能保存报价"))
    monkeypatch.setattr(module, "repo", repo)
    catalogue = AsyncMock(return_value=[])
    monkeypatch.setattr(module, "matching_catalog", catalogue)
    with pytest.raises(AppException if bound else IncompleteQuote):
        asyncio.run(module.service.make_quote(NS(), part, NS()))
    if not bound:
        catalogue.assert_not_awaited()


def test_uncovered_work_preserves_valid_operations_through_extraction_and_draft(monkeypatch, tmp_path):
    records, requests, run = fixture(monkeypatch)
    plan = dict(assessments=[dict(rule_no="PRICE-CNC", used=True, process_no="GY006", unit_hours="0.1",
        reason="加工型腔，按现有加工中心能力估算", work_content="铣削与钻孔", evidence_refs=["geometry:bounds"])],
        warnings=[], uncovered_requirements=["缺少可执行内孔珩磨的正式工艺"])
    def request(*args, **kwargs):
        requests.append(kwargs["json"])
        data = plan if kwargs.get("stage") == "ai.plan" else dict(facts=[], operations=[], warnings=[])
        return NS(raise_for_status=lambda: None, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]})
    monkeypatch.setattr(ai, "cloud_request", request)
    result = run()
    assert len(result["operations"]) == 1 and result["operations"][0]["process_id"] == str(records[1]["id"])
    assert result["uncovered_requirements"] == plan["uncovered_requirements"]
    assert any("内孔珩磨" in warning for warning in result["warnings"])
    prompt = requests[0]["messages"][0]["content"]
    assert "不要求档案名称与图纸加工内容逐字相同" in prompt and "不因一项缺失放弃其余路线" in prompt
    cfg = NS(ai_base_url="https://model.invalid/v1", ai_model="offline", ai_api_key=SecretStr("offline"), ai_request_timeout=10, ai_total_timeout=30)
    monkeypatch.setattr(ai, "settings", lambda: cfg)
    extracted = ai.extract_requirements(dict(documents=[], geometry={"bounds": [10,20,30]}), tmp_path,
        process_rules=[dict(id="PRICE-CNC", name="CNC4", process_id=str(records[1]["id"]), pricing_mode_code="hourly")], manufacturing_processes=records)
    assert extracted["planning_status"] == "partial" and extracted["status"] == "partial"
    assert len(extracted["operations"]) == 1 and extracted["suggested_operations"] == ["CNC4"]
    _, operations, summary = apply_draft({}, [], {"ai": extracted}, str(uuid4()), 1)
    assert len(operations) == 1 and summary["added_operations"] == 1
    assert operations[0]["process_id"] == str(records[1]["id"]) and operations[0]["unit_hours"] == "0.1"
    manual = [dict(name="人工工序", process_id=str(records[0]["id"]))]
    _, retained, _ = apply_draft({}, manual, {"ai": extracted}, str(uuid4()), 1)
    assert retained == manual


@pytest.mark.parametrize("uncovered", [[], ["内孔珩磨缺少工艺"]])
def test_quote_is_generated_with_uncovered_work_as_reference_warnings(monkeypatch, uncovered):
    import asyncio
    from decimal import Decimal
    from unittest.mock import AsyncMock
    from app.modules.mes.cnc import service as module
    from app.modules.mes.cnc.models import CncPart, CncOperation
    from app.modules.mes.cnc.exports import export_rows
    part = CncPart(name="测试", quantity=2, org_id=uuid4(), material="AL6061",
        stock_length=Decimal("10"), stock_width=Decimal("20"), stock_height=Decimal("30"),
        density=Decimal("2.7"), material_price=Decimal("30"),
        analysis={"ai": {"uncovered_requirements": uncovered},
                  "geometry": {"units": "mm", "volume_mm3": 1000, "bounds": [10, 20, 5]}})
    process_id = uuid4()
    operation = CncOperation(part_id=part.id, org_id=part.org_id, name="CNC4", process_id=process_id,
        unit_hours=Decimal("0.1"), hourly_rate=Decimal("100"), estimate_basis="按加工内容预估")
    written = []
    repo = NS(operations=AsyncMock(return_value=[operation]), files=AsyncMock(return_value=[]), add=lambda session,row: written.append(row))
    catalogue = AsyncMock(return_value=[dict(id=process_id, process_no="GY006", process_name="CNC4", processing_type_code="in_house")])
    monkeypatch.setattr(module, "repo", repo)
    monkeypatch.setattr(module, "matching_catalog", catalogue)
    monkeypatch.setattr(module, "files", NS(list_for_business=AsyncMock(return_value=[])))
    quote = asyncio.run(module.service.make_quote(NS(), part, NS(user_id=uuid4())))
    assert written == [quote]
    assert quote.unit_price == "10.49" and quote.total_price == "20.98"
    assert quote.inputs_snapshot["uncovered_requirements"] == uncovered
    assert quote.result_snapshot["weight_estimate"]["net_weight_kg"] == "0.002700"
    assert quote.result_snapshot["weight_estimate"]["net_total_weight_kg"] == "0.005400"
    assert quote.result_snapshot["weight_estimate"]["stock_weight_kg"] == quote.result_snapshot["stock_weight_kg"]
    if uncovered:
        assert quote.result_snapshot["is_reference"] is True
        assert quote.result_snapshot["uncovered_requirements"] == uncovered
        assert any("内孔珩磨" in text for text in quote.result_snapshot["warnings"])
    else:
        assert not quote.result_snapshot.get("is_reference")
    rows = export_rows(NS(id=str(quote.id), version_no=quote.version_no, inputs=quote.inputs_snapshot,
                          result=quote.result_snapshot, approved_by=None))
    assert any(row[0] == "报价提示" for row in rows) == bool(uncovered)
    assert ["单件预计净重 kg", "0.002700"] in rows
    assert ["整批预计净重 kg", "0.005400"] in rows
    # 报价人员可以补入未覆盖要求的费用，再直接更新价格。
    part.external_unit_cost = Decimal("2")
    revised = asyncio.run(module.service.make_quote(NS(), part, NS(user_id=uuid4())))
    assert revised.unit_price == "12.49" and revised.total_price == "24.98"
    part.density = Decimal("7.85")
    changed = asyncio.run(module.service.make_quote(NS(), part, NS(user_id=uuid4())))
    assert changed.result_snapshot["weight_estimate"]["net_weight_kg"] == "0.007850"
    assert quote.result_snapshot["weight_estimate"]["net_weight_kg"] == "0.002700"  # 历史快照不回写。


def test_quotation_cannot_adopt_legacy_quote_with_unbound_process(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from app.core.exceptions import AppException
    from app.modules.mes import quotation_service as module
    org_id = uuid4()
    line = NS(id=uuid4(), quantity=1, surface_treatment=None)
    part = NS(id=uuid4(), quantity=1, org_id=org_id, version_no=1)
    snapshot = NS(id=uuid4(), version_no=1, inputs_snapshot={"operations": [dict(name="钻攻M5")]})
    monkeypatch.setattr(module, "source_hash", lambda *a: "same")
    monkeypatch.setattr(module, "repo", NS(cnc_links=AsyncMock(return_value=[NS(part_id=part.id, source_hash="same")]), files=AsyncMock(return_value=[])))
    monkeypatch.setattr(module, "cnc_repo", NS(part=AsyncMock(return_value=part), quotes=AsyncMock(return_value=[snapshot]), active=AsyncMock(return_value=False), jobs=AsyncMock(return_value=NS(status_code="completed"))))
    with pytest.raises(AppException, match="未全部选择正式工艺"):
        asyncio.run(module.service.adoption_basis(NS(), NS(org_id=org_id), line, NS()))


@pytest.mark.parametrize("planning_status", ["failed", "partial"])
def test_worker_keeps_partial_operations_and_only_fails_invalid_plans(monkeypatch, tmp_path, planning_status):
    import asyncio
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from app.modules.mes.cnc import worker
    from app.modules.mes.cnc.models import CncPart, CncAnalysisJob
    from app.modules.mes.cnc.rules import RuleConfig
    from app.framework.db.tenant import use_tenant_schema
    part = CncPart(name="测试", quantity=1, org_id=uuid4(), version_no=1)
    job = CncAnalysisJob(part_id=part.id, org_id=part.org_id, auth_user_id=uuid4(), is_use_ai=True, is_use_ocr=False)
    session = NS(commit=AsyncMock(), flush=AsyncMock())
    @asynccontextmanager
    async def context(): yield session
    repo = NS(is_ready=AsyncMock(return_value=True), claim=AsyncMock(return_value=job), part=AsyncMock(return_value=part),
        rules=AsyncMock(return_value=(NS(version_no=1), RuleConfig(processes=[], is_auto_apply=False))),
        operations=AsyncMock(return_value=[]), files=AsyncMock(return_value=[]), job=AsyncMock(return_value=job), save_inputs=AsyncMock())
    monkeypatch.setattr(worker, "repo", repo)
    monkeypatch.setattr(worker, "get_session_context", context)
    monkeypatch.setattr(worker, "is_plugin_enabled_for_schema", AsyncMock(return_value=True))
    monkeypatch.setattr(worker, "current_actor", AsyncMock(return_value=NS(user_id=uuid4())))
    candidate = dict(id=uuid4(), process_no="GY006", process_name="CNC4", processing_type_code="in_house")
    monkeypatch.setattr(worker, "matching_catalog", AsyncMock(return_value=[candidate]))
    monkeypatch.setattr(worker, "files", NS(list_for_business=AsyncMock(return_value=[])))
    monkeypatch.setattr(worker, "settings", lambda: NS(storage=tmp_path, analysis_timeout_seconds=10, paddleocr_poll_timeout=10, ai_total_timeout=10))
    monkeypatch.setattr(worker, "mark", AsyncMock())
    monkeypatch.setattr(worker, "parse_local", lambda *a: dict(warnings=[], documents=[], geometry={}))
    valid_operation = dict(name="CNC4", process_id=str(candidate["id"]), process_no_snapshot="GY006", unit_hours="0.1")
    monkeypatch.setattr(worker, "extract_requirements", lambda *a, **k: dict(planning_status=planning_status, status="partial",
        operations=[valid_operation] if planning_status == "partial" else [],
        uncovered_requirements=["内孔珩磨缺少工艺"] if planning_status == "partial" else [], warnings=[]))
    from app.modules.mes.cnc.pricing import IncompleteQuote
    quote = AsyncMock(side_effect=IncompleteQuote(["未覆盖加工要求：内孔珩磨缺少工艺"]))
    monkeypatch.setattr(worker.service, "make_quote", quote)
    with use_tenant_schema("t_test"):
        asyncio.run(worker.run_pending())
    assert part.analysis["pricing"]["status"] == "incomplete"
    if planning_status == "partial":
        assert job.status_code == "completed" and "部分加工要求待补充" in job.stage
        assert len(part.analysis["ai"]["operations"]) == 1
        saved = repo.save_inputs.await_args.args[3]
        assert len(saved) == 1 and saved[0]["process_id"] == str(candidate["id"])
        assert saved[0]["unit_hours"] == "0.1"
        assert part.analysis["pricing"]["missing"] == ["未覆盖加工要求：内孔珩磨缺少工艺"]
        quote.assert_awaited_once()
    else:
        assert job.status_code == "failed" and "工艺规划未完成" in job.stage
        assert part.analysis["ai"]["operations"] == []
        quote.assert_not_awaited()
        assert repo.save_inputs.await_args.args[3] == []


@pytest.mark.parametrize("valid",[True,False])
def test_edit_validates_selected_process_before_saving_canonical_binding(monkeypatch,valid):
    import asyncio
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from app.core.exceptions import AppException
    from app.modules.mes.cnc import service as module
    from app.modules.mes.cnc.models import CncPart
    from app.modules.mes.cnc.schemas import Operation,PartEdit
    from app.modules.mes.cnc.repository import MANAGE
    identifier=uuid4();part=CncPart(name="测试零件",quantity=1,org_id=uuid4(),version_no=1)
    row=dict(id=identifier,process_no="GY006",process_name="CNC4",processing_type_code="in_house",is_quality_required=False)
    repo=NS(part=AsyncMock(return_value=part),operations=AsyncMock(return_value=[]),save_inputs=AsyncMock())
    @asynccontextmanager
    async def session():yield NS(commit=AsyncMock())
    monkeypatch.setattr(module,"repo",repo);monkeypatch.setattr(module,"get_session_context",session)
    monkeypatch.setattr(module,"matching_catalog",AsyncMock(return_value=[row] if valid else []))
    monkeypatch.setattr(module.service,"part_data",AsyncMock(return_value={"id":str(part.id)}))
    body=PartEdit(name="测试零件",quantity=1,version_no=1,specs=Specs(),operations=[Operation(name="加工中心加工",process_id=identifier,process_no_snapshot="伪造编号",quote_rule_no="PRICE-CNC",unit_hours="0.1",hourly_rate=100)])
    if valid:
        asyncio.run(module.service.edit(part.id,body,NS(user_id=uuid4(),permissions=[MANAGE])))
        saved=repo.save_inputs.call_args.args[3][0]
        assert saved["name"]=="CNC4" and saved["process_id"]==str(identifier) and saved["process_no_snapshot"]=="GY006"
        assert saved["quote_rule_no"]=="PRICE-CNC" and saved["hourly_rate"]=="100"
    else:
        with pytest.raises(AppException):asyncio.run(module.service.edit(part.id,body,NS(user_id=uuid4(),permissions=[MANAGE])))
        repo.save_inputs.assert_not_called()
