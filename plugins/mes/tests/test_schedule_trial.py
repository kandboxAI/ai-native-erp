"""自动试排接入：预检缺项、快照保护、只读事务释放和子进程约束。"""
import asyncio
from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.modules.mes import schedule_trial_service as module
from app.modules.mes.schedule_trial_planning import build_problem, prepare, snapshot_key
from app.modules.mes.schedule_trial_schemas import TrialScope, TrialSolve
from app.modules.mes.schedule_trial_service import service, run_solver
from app.modules.mes import schedule_trial_planning as planning
from app.modules.mes.schedule_limits import MAX_STAGES
from test_schedule_solver import op, order

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2030, 11, 11, 8, tzinfo=TZ)  # 周一；不读取真实资源。


def fixture():
    org, process, qc, equipment, person, party = [uuid4() for _ in range(6)]
    work = NS(id=uuid4(), org_id=org, work_order_no="TEST-ONLY", status_code="released", processing_type_code="in_house",
        planned_quantity=Decimal(2), good_quantity=0, scrap_quantity=0, rework_quantity=0, due_at=START + timedelta(days=2),
        version_no=1, unit_code="piece")
    task = NS(id=uuid4(), org_id=org, work_order_id=work.id, operation_name_snapshot="CNC-TEST", sequence_no=1,
        process_id=process, equipment_id=None, assigned_user_id=None, planned_quantity=Decimal(2), good_quantity=0,
        scrap_quantity=0, rework_quantity=0, standard_minutes_per_unit=Decimal("10.2"), version_no=1, status_code="pending", is_quality_required=False)
    p = NS(id=person, party_id=party, person_no="TEST-P", version_no=1)
    e = NS(id=equipment, equipment_no="TEST-E", equipment_name="测试设备", process_id=None, version_no=1)
    qualification = [NS(id=uuid4(), production_person_id=person, process_id=proc, valid_from=START,
        valid_to=None, version_no=1) for proc in (process, qc)]
    calendars, periods = [], []
    for kind, resource in (("person", person), ("equipment", equipment)):
        c = NS(id=uuid4(), org_id=org, production_person_id=resource if kind == "person" else None,
            equipment_id=resource if kind == "equipment" else None, valid_from=date(2030, 11, 11), valid_to=None,
            is_active=True, deleted_at=None, timezone_name="Asia/Shanghai", version_no=1)
        calendars.append(c)
        times = [("work", 480, 1080)] if kind == "equipment" else [("work", 480, 720), ("lunch", 720, 810), ("work", 810, 1080)]
        for day in range(1, 6):
            periods.extend(NS(id=uuid4(), calendar_id=c.id, org_id=org, weekday_no=day, period_type_code=key,
                start_minute_of_day=a, end_minute_of_day=b, is_active=True, deleted_at=None, version_no=1) for key, a, b in times)
    snapshot = dict(orders=[work], tasks=[task], hidden_route=False, facts=set(),
        processes=[NS(id=key, process_name=name, processing_type_code="in_house", version_no=1,execution_kind_code="machine" if key==process else "inspection",is_equipment_required=key==process) for key, name in ((process, "CNC"), (qc, "QC"))],
        equipment=[e], people=[(p, None)], qualifications=qualification, calendars=calendars, periods=periods,
        links=[NS(id=uuid4(), equipment_id=equipment, process_id=process, version_no=1)], reservations=[])
    request = TrialSolve(org_id=org, work_order_ids=[work.id], start_at=START, end_at=START + timedelta(days=2),
        snapshot_key=snapshot_key(snapshot), is_regular_calendar_confirmed=True,
        order_rules=[dict(work_order_id=work.id, version_no=1, ready_at=START, is_readiness_confirmed=True)],
        operation_rules=[dict(operation_id=task.id, version_no=1, kind_key="machine", setup_minutes=0, load_minutes=2,
            unload_minutes=2, supervision_key="two_machines", is_lunch_auto_allowed=True, is_timing_confirmed=True)],
        inspection=dict(process_id=qc, is_equipment_required=False, minutes_per_piece=2), time_limit_seconds=1)
    actor = NS(enabled_plugin_keys=["mes"], permissions=["mes:schedule:manage"],
        permission_scopes={"mes:schedule:manage": "organization"}, org_access_mode_code="selected", org_id=org, org_ids=[])
    return snapshot, request, actor


def test_real_calendar_expansion_qualification_intersection_and_no_sensitive_solver_input():
    snapshot, request, _ = fixture()
    problem, issues, labels = build_problem(snapshot, request)
    assert not issues
    task = problem["orders"][0]["operations"][0]
    assert task["run"] == 11  # 时长向上取整，不能侵入不可用时段。
    assert task["people"][0]["work"][:2] == [(0, 240), (330, 600)]
    assert task["people"][0]["auto"][0] == (0, 600)
    assert task["machines"][0]["work"][0] == (0, 600)
    assert not any(word in str(problem) for word in ("TEST-P", "测试设备", "姓名", "TEST-ONLY"))


@pytest.mark.parametrize("missing", ["calendar", "qualification", "device", "route", "confirmed", "standard", "fact", "count", "unit", "quality", "outsourced", "hidden", "assigned"])
def test_missing_or_unsupported_facts_fail_closed(missing):
    snapshot, request, _ = fixture()
    task = snapshot["tasks"][0]
    if missing == "calendar": snapshot["calendars"] = []
    if missing == "qualification": snapshot["qualifications"] = []
    if missing == "device": snapshot["links"] = []
    if missing == "route": snapshot["tasks"] = []
    if missing == "confirmed": request.operation_rules[0].is_timing_confirmed = False
    if missing == "standard": task.standard_minutes_per_unit = None
    if missing == "fact": snapshot["facts"].add(task.id)
    if missing == "count": task.planned_quantity = Decimal(3)
    if missing == "unit": snapshot["orders"][0].unit_code = "kg"
    if missing == "quality": task.is_quality_required = True
    if missing == "outsourced": snapshot["processes"][0].processing_type_code = "outsourced"
    if missing == "hidden": snapshot["hidden_route"] = True
    if missing == "assigned": task.assigned_user_id = uuid4()
    _, issues, _ = build_problem(snapshot, request)
    assert issues


@pytest.mark.parametrize("first_released", [False, True])
def test_replan_uses_applied_assignment_before_legacy_account(first_released):
    snapshot, request, _ = fixture()
    task = snapshot["tasks"][0]
    work = snapshot["orders"][0]
    person = snapshot["people"][0][0]
    task.assigned_user_id = uuid4()  # 旧派工账号没有对应的生产人员。
    snapshot["fixed_people"] = {task.id: person.party_id}
    if first_released:
        snapshot["gates"] = [NS(work_order_id=work.id, status_code="released", released_at=START)]
        snapshot["phases"] = [
            NS(id=uuid4(), work_order_id=work.id, operation_id=task.id,
               production_phase_code="first", status_code="completed"),
            NS(id=uuid4(), work_order_id=work.id, operation_id=task.id,
               production_phase_code="remaining", status_code="pending", is_rework=False),
        ]
        snapshot["execution_facts"] = [(task.id, snapshot["phases"][0].id, START)]

    problem, issues, _ = build_problem(snapshot, request)

    assert not issues
    assert problem["orders"][0]["remaining_only"] is first_released
    assert [p["id"] for p in problem["orders"][0]["operations"][0]["people"]] == [str(person.party_id)]

    task.assigned_production_person_id = uuid4()
    _, issues, _ = build_problem(snapshot, request)
    assert any("指定的生产人员不可排程" in issue for issue in issues)


def test_expiring_qualification_limits_both_work_and_auto_windows():
    snapshot, request, _ = fixture()
    snapshot["qualifications"][0].valid_to = START + timedelta(hours=1)
    problem, issues, _ = build_problem(snapshot, request)
    assert not issues
    p = problem["orders"][0]["operations"][0]["people"][0]
    assert p["work"] == [(0, 60)] and p["auto"] == [(0, 60)]


def test_unknown_occupancy_excludes_resource_and_old_plan_is_reserved_conservatively():
    snapshot, request, _ = fixture()
    equipment = snapshot["equipment"][0]
    snapshot["reservations"] = [(equipment.id, None, "in_progress", None, None, None, True)]
    _, issues, _ = build_problem(snapshot, request)
    assert any("设备" in issue for issue in issues)
    snapshot["reservations"] = [(None, None, "pending", START, START + timedelta(hours=1), equipment.equipment_no, False)]
    problem, issues, _ = build_problem(snapshot, request)
    assert not issues
    assert problem["reservations"]["machine"][str(equipment.id)] == [(0, 60)]
    snapshot["reservations"] = [(None, None, "pending", START, START + timedelta(hours=1), "未知工作站", False)]
    _, issues, _ = build_problem(snapshot, request)
    assert any("资源归属" in issue for issue in issues)


def test_same_natural_person_uses_same_capacity_identity():
    snapshot, request, _ = fixture()
    problem, _, _ = build_problem(snapshot, request)
    assert problem["orders"][0]["operations"][0]["people"][0]["id"] == str(snapshot["people"][0][0].party_id)


def test_weekend_and_custom_calendar_gaps_are_not_merged_into_lunch():
    snapshot, request, _ = fixture()
    request.start_at = datetime(2030, 11, 16, 8, tzinfo=TZ)
    request.end_at = request.start_at + timedelta(days=1)
    _, issues, _ = build_problem(snapshot, request)
    assert issues
    snapshot, request, _ = fixture()
    for p in snapshot["periods"]:
        if p.period_type_code == "lunch": p.is_active = False
    problem, _, _ = build_problem(snapshot, request)
    assert problem["orders"][0]["operations"][0]["people"][0]["auto"][:2] == [(0, 240), (330, 600)]


@pytest.mark.parametrize("change", ["task", "calendar", "qualification", "occupancy"])
def test_snapshot_detects_source_changes(change):
    snapshot, request, _ = fixture()
    if change == "task": snapshot["tasks"][0].version_no += 1
    if change == "calendar": snapshot["periods"][0].start_minute_of_day += 1
    if change == "qualification": snapshot["qualifications"][0].valid_to = START + timedelta(hours=2)
    if change == "occupancy": snapshot["reservations"].append((uuid4(), None, "pending", START, START + timedelta(hours=1), None, False))
    assert snapshot_key(snapshot) != request.snapshot_key


def test_limits_and_timezone_are_required():
    _, request, _ = fixture()
    body = request.model_dump()
    body["start_at"] = "2030-11-11T08:00:00"
    with pytest.raises(ValidationError): TrialSolve(**body)
    body = request.model_dump()
    body["operation_rules"].append(body["operation_rules"][0])
    with pytest.raises(ValidationError): TrialSolve(**body)


def service_fixture(monkeypatch):
    snapshot, request, actor = fixture()
    opened = []
    @asynccontextmanager
    async def context():
        opened.append(True)
        try: yield object()
        finally: opened.pop()
    monkeypatch.setattr(module, "get_session_context", context)
    monkeypatch.setattr(module.repository, "snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(module, "utc_now", lambda: START)
    return snapshot, request, actor, opened


def test_service_closes_read_transaction_before_solver_and_never_writes(monkeypatch):
    _, request, actor, opened = service_fixture(monkeypatch)
    async def solver(problem):
        assert not opened
        return dict(status_code="UNKNOWN", segments=[], completions=[])
    monkeypatch.setattr(module, "run_solver", solver)
    result = asyncio.run(service.solve(request, actor))
    assert result["status_code"] == "UNKNOWN" and not opened


def test_precheck_and_stale_snapshot_do_not_start_solver(monkeypatch):
    snapshot, request, actor, _ = service_fixture(monkeypatch)
    solver = AsyncMock()
    monkeypatch.setattr(module, "run_solver", solver)
    request.is_regular_calendar_confirmed = False
    result = asyncio.run(service.solve(request, actor))
    assert result["status_code"] == "PRECHECK_FAILED"
    snapshot["tasks"][0].version_no += 1
    with pytest.raises(AppException): asyncio.run(service.solve(request, actor))
    solver.assert_not_awaited()


def test_permission_plugin_and_organization_are_server_enforced(monkeypatch):
    _, request, actor, _ = service_fixture(monkeypatch)
    actor.org_id = uuid4()
    with pytest.raises(AppException): asyncio.run(service.solve(request, actor))
    actor.permissions = []
    with pytest.raises(AppException): asyncio.run(service.prepare(request, actor))
    actor.permissions = ["mes:schedule:manage"]
    actor.enabled_plugin_keys = []
    with pytest.raises(AppException): asyncio.run(service.prepare(request, actor))


def test_isolated_subprocess_runs_without_database_or_model_settings():
    result = asyncio.run(run_solver(dict(horizon=600, time_limit_seconds=1, orders=[order(operations=[op()])], reservations={})))
    assert result["status_code"] == "OPTIMAL" and result["segments"]


def test_last_operation_reuse_requires_real_inspection_and_does_not_create_extra_step():
    snapshot, request, _ = fixture()
    request.inspection = type(request.inspection)(mode_key="last_operation")
    _, issues, _ = build_problem(snapshot, request)
    assert any("最后一道" in issue for issue in issues)
    request.operation_rules[0].kind_key = "machine_inspection"
    snapshot["processes"][0].execution_kind_code="machine_inspection"
    request.operation_rules[0].load_minutes = request.operation_rules[0].unload_minutes = 0
    request.operation_rules[0].supervision_key = "exclusive"
    request.operation_rules[0].is_lunch_auto_allowed = False
    snapshot["tasks"][0].is_quality_required = True
    problem, issues, _ = build_problem(snapshot, request)
    assert not issues and problem["orders"][0]["inspection"] is None
    assert problem["orders"][0]["operations"][0]["is_inspection"]


def test_route_dependency_missing_or_reversed_blocks_trial():
    snapshot, request, _ = fixture()
    snapshot["dependencies"] = [NS(id=uuid4(), process_id=snapshot["tasks"][0].process_id, previous_process_id=uuid4())]
    _, issues, _ = build_problem(snapshot, request)
    assert any("前置工艺" in issue for issue in issues)


def test_busy_solver_and_timeout_release_capacity(monkeypatch):
    import subprocess
    monkeypatch.setattr(module, "_active_solves", 2)
    with pytest.raises(AppException): asyncio.run(run_solver({}))
    monkeypatch.setattr(module, "_active_solves", 0)
    calls = []
    class Process:
        returncode = None
        def communicate(self, input=None, timeout=None):
            if timeout is not None: raise subprocess.TimeoutExpired("controlled", timeout)
            return b"", b""
        def poll(self): return self.returncode
        def kill(self): self.returncode = -1; calls.append("killed")
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: Process())
    result = asyncio.run(run_solver(dict(time_limit_seconds=1)))
    assert result["status_code"] == "UNKNOWN"
    assert calls == ["killed"] and module._active_solves == 0


def test_two_hundred_piece_orders_keep_all_32_operations_with_larger_budget():
    snapshot, request, _ = fixture()
    source_order, source_task = snapshot["orders"][0], snapshot["tasks"][0]
    source_rule, source_order_rule = request.operation_rules[0], request.order_rules[0]
    source_task.standard_minutes_per_unit = Decimal(1)
    snapshot["orders"], snapshot["tasks"] = [], []
    request.order_rules, request.operation_rules = [], []
    for _ in range(2):
        work = deepcopy(source_order)
        work.id, work.planned_quantity = uuid4(), Decimal(100)
        snapshot["orders"].append(work)
        request.work_order_ids = [w.id for w in snapshot["orders"]]
        request.order_rules.append(source_order_rule.model_copy(update={"work_order_id": work.id}))
        for index in range(16):
            task = deepcopy(source_task)
            task.id, task.work_order_id, task.sequence_no = uuid4(), work.id, index + 1
            task.planned_quantity = work.planned_quantity
            snapshot["tasks"].append(task)
            request.operation_rules.append(source_rule.model_copy(update={"operation_id": task.id}))
    problem, issues, _ = build_problem(snapshot, request)
    assert not issues
    assert [o["quantity"] for o in problem["orders"]] == [100, 100]
    assert [len(o["operations"]) for o in problem["orders"]] == [16, 16]
    for work in snapshot["orders"]:
        work.planned_quantity = Decimal(500)
    for task in snapshot["tasks"]:
        task.planned_quantity = Decimal(500)
    _, issues, _ = build_problem(snapshot, request)
    assert any(f"{MAX_STAGES}段" in issue and "预计建模" in issue for issue in issues)


def test_resource_combination_limit_still_rejects_without_removing_candidates(monkeypatch):
    snapshot, request, _ = fixture()
    monkeypatch.setattr(planning, "MAX_RESOURCE_WINDOW_COMBINATIONS", 1)
    problem, issues, _ = build_problem(snapshot, request)
    assert any("组合估算" in issue and "上限1" in issue for issue in issues)
    assert len(problem["orders"][0]["operations"][0]["people"]) == 1
    assert len(problem["orders"][0]["operations"][0]["machines"]) == 1


def test_solver_budget_defaults_to_60_seconds_and_rejects_unbounded_requests():
    _, request, _ = fixture()
    body = request.model_dump(exclude={"time_limit_seconds"})
    assert TrialSolve.model_validate(body).time_limit_seconds == 60
    with pytest.raises(ValidationError):
        TrialSolve.model_validate(body | {"time_limit_seconds": 61})
