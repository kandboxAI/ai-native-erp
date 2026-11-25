"""核价到制造档案匹配；不访问真实数据库或外部模型。"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.mes.archive_models import MesProcess, MesProjectStage
from app.modules.mes.models import MesWorkOrderOperation
from app.modules.mes.process_matching import match_process, analysis_matches, bind_production_operations, canonical_operations
from app.modules.mes.quotation_production import production_operations
from app.modules.mes.archive_repository import archive_repository
from test_quotations import store, run
from test_sales_orders import sales, approved, adopted_route, approve_order, body, release_body, service


def process(no, name, **values):
    return dict(id=uuid4(), process_no=no, process_name=name, processing_type_code="in_house", is_quality_required=False) | values


def test_exact_code_and_normalized_name_beat_broad_category():
    cnc2, cnc4 = process("GY005", "CNC2"), process("GY006", "CNC4")
    rows = [cnc2, cnc4]
    assert match_process("ＧＹ００５", rows)["process"] == cnc2
    assert match_process(" cnc 4 ", rows)["process"] == cnc4
    assert match_process("CNC 粗加工", rows, process_type_code="cnc")["status_code"] == "ambiguous"


def test_unique_category_duplicate_names_and_outsource_constraint():
    nc = process("GY002", "NC车")
    assert match_process("普通数控加工", [nc])["process"] == nc
    assert match_process("NC车", [nc, process("OTHER", "NC车")])["status_code"] == "ambiguous"
    assert match_process("NC车", [nc], pricing_mode_code="external")["status_code"] == "unmatched"
    assert match_process("未知工序", [nc])["status_code"] == "unmatched"
    assert match_process("", [nc])["status_code"] == "unmatched"


def test_explicit_archive_binding_distinguishes_same_names_and_does_not_fall_back():
    first,second=process("GY005","CNC"),process("GY006","CNC")
    original=dict(name="加工中心加工",quote_rule_no="PRICE-CNC",unit_hours="0.2",hourly_rate="100",process_no="GY006")
    row=canonical_operations([original],[first,second])[0]
    assert row["process_id"]==str(second["id"]) and row["name"]=="CNC" and row["process_no_snapshot"]=="GY006"
    assert row["quote_rule_no"]=="PRICE-CNC" and row["hourly_rate"]=="100" and row["unit_hours"]=="0.2"
    assert "process_id" not in original
    with pytest.raises(AppException):canonical_operations([row],[first],strict=True)
    assert match_process("CNC",[first],process_id=second["id"])["process"] is None
    assert match_process("CNC",[process("OUT","CNC",processing_type_code="outsourced")])["process"] is None


def test_selected_archive_is_kept_in_production_even_if_name_was_renamed():
    selected=process("GY006","四轴精加工")
    raw=[dict(name="旧工艺名称",process_id=str(selected["id"]),process_no_snapshot="GY006",unit_hours="0.1")]
    op=bind_production_operations(production_operations(raw,"DRAWING"),raw,[selected])[0]
    assert op.process_id==selected["id"] and op.operation_name=="四轴精加工"
    assert op.standard_minutes_per_unit==Decimal(6)


def test_quality_gate_does_not_turn_machining_into_inspection():
    cnc = process("CNC", "CNC2", is_quality_required=True)
    assert match_process("终检", [cnc], process_type_code="inspection")["status_code"] == "unmatched"
    assert match_process("终检", [process("QA", "QA"), process("QC", "QC")],
        process_type_code="inspection")["status_code"] == "ambiguous"
    assert match_process("CNC",[process("QA","QA")],process_no="QA",process_type_code="cnc")["process"] is None


def test_analysis_report_is_not_a_new_relation_and_does_not_change_pricing():
    rows = [dict(name="普通数控加工", unit_hours="0.1", quote_rule_no="PRICE-NC")]
    report = analysis_matches(rows, [process("GY002", "NC车")])
    assert report["matched_count"] == 1 and report["pending_count"] == 0
    assert report["items"][0]["process_no"] == "GY002"
    assert "id" not in report["items"][0] and "process_id" not in report["items"][0]
    assert rows[0]["name"] == "普通数控加工" and rows[0]["quote_rule_no"] == "PRICE-NC"


def test_preserves_order_duplicates_times_and_inspection():
    rows = [dict(name="普通数控加工", unit_hours="0.1"), dict(name="普通数控加工", unit_hours="0.2"),
        dict(name="QA", unit_hours="0.01"), dict(name="CNC 粗加工", unit_hours="1")]
    candidates = [process("GY002", "NC车"), process("GY034", "QA", is_quality_required=True),
        process("GY005", "CNC2"), process("GY006", "CNC4")]
    ops = bind_production_operations(production_operations(rows, "DRAWING"), rows, candidates)
    assert [op.operation_name for op in ops] == ["NC车", "NC车", "QA", "CNC 粗加工"]
    assert [op.standard_minutes_per_unit for op in ops] == [Decimal("6"), Decimal("12"), Decimal("0.6"), Decimal("60")]
    assert ops[0].process_id == ops[1].process_id == candidates[0]["id"]
    assert ops[2].is_quality_required and ops[3].process_id is None
    assert "报价工序原名" in ops[0].operation_description and "多个可选工艺" in ops[3].operation_description


def add_processes(sales):
    org_id = sales.actor.org_id
    with Session(sales.engine) as session:
        stage = MesProjectStage(org_id=org_id, stage_no="MACHINE", stage_name="机加")
        session.add(stage); session.flush()
        archive = MesProcess(org_id=org_id, process_no="GY002", process_name="NC车", project_stage_id=stage.id)
        inactive = MesProcess(org_id=org_id, process_no="OFF", process_name="CNC2", is_active=False)
        other = MesProcess(org_id=sales.foreign_org, process_no="OTHER", process_name="CNC4")
        deleted = MesProcess(org_id=org_id, process_no="DELETED", process_name="CNC5", deleted_at=utc_now())
        session.add_all([archive, inactive, other, deleted]); session.commit()
        return archive.id


def test_release_real_archive_binding_and_scope(sales):
    identifier = add_processes(sales)
    quote = approved(sales)
    adopted_route(sales, quote, [dict(name="普通数控加工", unit_hours="0.1"), dict(name="CNC 粗加工", unit_hours="0.2")])
    order = run(service.create(body(quote), sales.actor))
    order = approve_order(order, sales)
    result = run(service.release(order["id"], release_body(order, sales), sales.actor))
    with Session(sales.engine) as session:
        ops = session.scalars(select(MesWorkOrderOperation).order_by(MesWorkOrderOperation.sequence_no)).all()
        assert ops[0].process_id == identifier and ops[0].operation_name_snapshot == "NC车"
        assert ops[0].stage_name_snapshot == "机加" and ops[0].standard_minutes_per_unit == Decimal("6")
        assert ops[1].process_id is None and "工艺档案待匹配" in ops[1].operation_description
    assert result["id"] == order["id"]


def test_release_prefers_adopted_real_process_id_over_duplicate_names(sales):
    add_processes(sales)
    with Session(sales.engine) as session:
        second=MesProcess(org_id=sales.actor.org_id,process_no="GY999",process_name="NC车")
        session.add(second);session.commit();identifier=second.id
    quote=approved(sales)
    adopted_route(sales,quote,[dict(name="NC车",process_id=str(identifier),process_no_snapshot="GY999",unit_hours="0.1")])
    order=run(service.create(body(quote),sales.actor))
    order=approve_order(order,sales)
    run(service.release(order["id"],release_body(order,sales),sales.actor))
    with Session(sales.engine) as session:
        operations=session.scalars(select(MesWorkOrderOperation)).all()
        assert len(operations)==1 and operations[0].process_id==identifier


def test_repository_checks_action_scope_and_reads_only_matching_fields(sales):
    add_processes(sales)
    async def query():
        async with sales.sessions() as session:
            return await archive_repository.matching_processes(session, sales.actor.org_id, sales.actor, "mes:work_order:create")
    rows = run(query())
    assert [row["process_no"] for row in rows] == ["GY002"]
    assert set(rows[0]) == {"id", "process_no", "process_name", "processing_type_code", "is_quality_required"}
    sales.actor.permission_scopes["mes:work_order:create"] = "self"
    assert run(query()) == []
    sales.actor.permissions.remove("mes:work_order:create")
    with pytest.raises(AppException): run(query())
