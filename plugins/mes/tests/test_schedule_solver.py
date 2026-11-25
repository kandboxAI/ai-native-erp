"""自动试排约束回归：纯内存，不访问业务库或模型服务。"""
from copy import deepcopy

from app.modules.mes.schedule_solver import solve_trial


def op(identifier="op", machine="machine", person="person", run=60, **changes):
    windows = [[0, 240], [330, 600]]
    value = dict(id=identifier, kind="machine", run=run, setup=0, load=0, unload=0, two=True, lunch=True,
        people=[dict(id=person, work=windows, auto=[[0, 600]])], machines=[dict(id=machine, work=[[0, 600]])])
    return value | changes


def inspection(person="qc"):
    return op("first_inspection", person=person, run=1, kind="inspection", machines=[], two=False, lunch=False)


def order(identifier="order", quantity=1, operations=None, ready=0, due=600):
    return dict(id=identifier, quantity=quantity, ready=ready, due=due,
        operations=operations or [op()], inspection=inspection())


def solve(orders, **changes):
    return solve_trial(dict(horizon=600, time_limit_seconds=3, orders=orders, reservations={}) | changes)


def stages(result, kind=None, batch=None):
    return [s for s in result["segments"] if (kind is None or s["kind_key"] == kind) and (batch is None or s["batch_key"] == batch)]


def test_external_wait_uses_no_factory_resource_and_both_returns_require_qa():
    external=dict(id="external",process_id="outside",kind="external",people=[],machines=[],
        external_returns={"first":120,"remaining":360},after_inspection=inspection())
    value=order(quantity=2,operations=[external]);value["inspection"]=None
    result=solve([value])
    assert result["status_code"]=="OPTIMAL"
    waits=stages(result,"external_wait")
    assert len(waits)==2 and all(not s["person_id"] and not s["equipment_id"] for s in waits)
    checks=stages(result,"inspection")
    assert len(checks)==2 and {s["start"] for s in checks}=={120,360}


def test_fixed_duration_does_not_span_calendar_gap_and_accepts_exact_window():
    task=op(kind="manual",machines=[],two=False,lunch=False,run=60,
        people=[dict(id="person",work=[[0,30],[60,120]],auto=[[0,120]])])
    result=solve([order(operations=[task])])
    assert result["status_code"]=="OPTIMAL"
    assert [(s["start"],s["end"]) for s in stages(result,"manual")]==[(60,120)]
    task["people"][0]["work"]=[[0,30],[60,119]]
    assert solve([order(operations=[task])])["status_code"]=="INFEASIBLE"


def test_optional_candidate_with_short_windows_is_excluded_not_entire_problem():
    task=op(kind="manual",machines=[],two=False,lunch=False,run=60,
        people=[dict(id="short",work=[[0,59]],auto=[[0,600]]),dict(id="valid",work=[[0,60]],auto=[[0,60]])])
    result=solve([order(operations=[task])])
    assert result["status_code"]=="OPTIMAL"
    assert {s["person_id"] for s in stages(result,"manual")}=={"valid"}


def test_hundred_piece_orders_preserve_all_pieces_and_phases():
    values=[]
    for identifier in ("a","b"):
        tasks=[]
        for index in range(4):
            resource=f"{identifier}-{index}"
            windows=[[3*index,3*index+3],[100+300*index,100+300*index+297]]
            tasks.append(op(resource,machine=resource,person=resource,run=1,load=1,unload=1,
                people=[dict(id=resource,work=windows,auto=windows)],
                machines=[dict(id=resource,work=windows)]))
        value=order(identifier,quantity=100,operations=tasks,due=2000)
        value["inspection"]["people"][0].update(id=f"{identifier}-qc",work=[[0,2000]],auto=[[0,2000]])
        values.append(value)
    result=solve(values,horizon=2000,time_limit_seconds=10)
    assert result["status_code"] in {"FEASIBLE","OPTIMAL"}
    assert len(result["completions"])==2
    for value in values:
        for task in value["operations"]:
            runs=[s for s in stages(result,"run") if s["operation_id"]==task["id"]]
            assert len(runs)==100
            assert sum(s["batch_key"]=="first" for s in runs)==1
            assert {s["piece_no"] for s in runs if s["batch_key"]=="remaining"}==set(range(1,100))


def test_whole_project_shipping_waits_for_all_goods_and_next_dispatch_window():
    values=[order("a",operations=[op("a","m1",person="p1",run=60)]),order("b",operations=[op("b","m2",person="p2",run=120)])]
    for value in values:value.update(delivery_group="project",shipping_complete=True,shipping_preparation=30,shipping_windows=[[0,100],[330,600]])
    result=solve(values)
    assert result["status_code"]=="OPTIMAL"
    assert {r["shipping_release"] for r in result["completions"]}=={360}
    assert all(r["shipping_complete"] for r in result["completions"])


def test_remaining_only_does_not_repeat_actual_first_or_preparation():
    value=order(quantity=3,operations=[op(run=20)])
    value.update(remaining_only=True,first_actual_release=-60)
    result=solve([value])
    assert result["status_code"]=="OPTIMAL"
    assert all(s["batch_key"]=="remaining" for s in result["segments"])
    assert len(stages(result,"run"))==2
    assert result["completions"][0]["first_article_release"]==-60


def test_two_machine_supervision_shares_time_without_halving_runtime():
    result = solve([order("a", operations=[op("a", "m1", run=120)]), order("b", operations=[op("b", "m2", run=120)])])
    assert result["status_code"] == "OPTIMAL"
    runs = stages(result, "run")
    assert {s["start"] for s in runs} == {0}
    assert {s["end"] - s["start"] for s in runs} == {120}


def test_third_machine_cannot_share_one_person_and_focus_blocks_supervision():
    tasks = [order(str(i), operations=[op(str(i), f"m{i}", run=120)]) for i in range(3)]
    result = solve(tasks)
    assert max(s["end"] for s in stages(result, "run")) >= 240
    focus = order("focus", operations=[op("focus", run=120, kind="manual", machines=[], two=False, lunch=False)])
    result = solve([tasks[0], focus])
    run = stages(result, "run")[0]
    manual = stages(result, "manual")[0]
    assert run["end"] <= manual["start"] or manual["end"] <= run["start"]


def test_lunch_finishing_machine_is_held_until_person_returns_to_unload():
    first = order("a", operations=[op("a", run=100, load=10, unload=10)], ready=190)
    second = order("b", operations=[op("b", person="other", run=5)], ready=305)
    result = solve([first, second])
    assert result["status_code"] == "OPTIMAL"
    waiting = stages(result, "waiting_unload")[0]
    assert waiting["start"] == 300 and waiting["end"] == 330
    other = next(s for s in stages(result, "run") if s["order_id"] == "b")
    assert other["start"] >= 340


def test_first_article_traverses_full_route_then_remaining_batch_counts_q_minus_one():
    result = solve([order(quantity=3, operations=[op("a", "m1", run=10), op("b", "m2", run=20)])])
    assert result["status_code"] == "OPTIMAL"
    first = stages(result, "run", "first")
    remaining = stages(result, "run", "remaining")
    assert len(first) == 2 and len(remaining) == 4
    gate = next(s for s in stages(result, "inspection", "first"))
    assert min(s["start"] for s in remaining) >= gate["end"]
    assert max(s["end"] for s in remaining if s["operation_id"] == "a") <= min(s["start"] for s in remaining if s["operation_id"] == "b")
    assert sum(s["end"] - s["start"] for s in first + remaining) == (10 + 20) * 3


def test_one_piece_has_no_remaining_batch_and_no_quantity_increment():
    result = solve([order()])
    assert len(stages(result, "run")) == 1
    assert not stages(result, batch="remaining")


def test_per_piece_reload_cannot_be_hidden_inside_unattended_batch():
    result = solve([order(quantity=3, ready=210, operations=[op(run=40, load=5, unload=5)])])
    assert result["status_code"] == "OPTIMAL"
    assert len(stages(result, "load")) == 3
    assert all(s["end"] <= 240 or s["start"] >= 330 for s in stages(result, "load") + stages(result, "unload"))


def test_calendar_gap_is_not_overnight_permission_and_unknown_empty_candidate_is_infeasible():
    result = solve([order(operations=[op(run=610)])])
    assert result["status_code"] == "INFEASIBLE" and not result["segments"]
    result = solve([order(operations=[op(people=[])])])
    assert result["status_code"] == "INFEASIBLE"


def test_machine_and_person_fixed_occupancy_is_respected():
    result = solve([order()], reservations={"machine": {"machine": [[0, 60]]}, "person": {"person": [[60, 90]]}})
    assert stages(result, "run")[0]["start"] >= 90


def test_earlier_due_group_not_worsened_for_later_group():
    first = order("near", due=10, operations=[op("near", run=20)])
    later = order("late", due=30, operations=[op("late", run=1)])
    result = solve([later, first])
    assert next(s for s in stages(result, "run") if s["order_id"] == "near")["start"] == 0


def test_preparation_is_counted_once_not_multiplied_by_quantity():
    result = solve([order(quantity=3, operations=[op(run=10, setup=15)])])
    assert sum(s["end"] - s["start"] for s in stages(result, "preparation")) == 15
    assert sum(s["end"] - s["start"] for s in stages(result, "run")) == 30


def test_solver_does_not_mutate_input():
    data = dict(horizon=600, time_limit_seconds=1, orders=[order()], reservations={})
    before = deepcopy(data)
    solve_trial(data)
    assert before == data


def test_last_inspection_reused_as_gate_without_adding_duplicate_measurements():
    task = order(quantity=3, operations=[op("cut", run=10), inspection()])
    task["inspection"] = None
    result = solve([task])
    measurements = stages(result, "inspection")
    assert len(measurements) == 3  # 首件1次、剩余2次，不再额外加3次。
    gate = next(s for s in measurements if s["batch_key"] == "first")
    assert min(s["start"] for s in stages(result, "run", "remaining")) >= gate["end"]


def test_device_inspection_occupies_person_exclusively_and_never_uses_lunch():
    measuring = op("qc", "cmm", run=20, is_inspection=True, two=False, lunch=False)
    task = order(operations=[measuring], ready=230)
    task["inspection"] = None
    result = solve([task])
    measurement = stages(result, "inspection")[0]
    assert measurement["start"] >= 330
    assert measurement["equipment_id"] == "cmm"
