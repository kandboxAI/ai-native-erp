"""明显无解的产能诊断；不扩大资源能力，不访问数据库。"""
from app.modules.mes.schedule_capacity import available_minutes, capacity_issues
from test_schedule_solver import op, order, inspection


def issues(value):
    return capacity_issues([value], {"order": {"order": "TEST-100"}, "operation": {"op": "CNC4"}})


def test_calendar_capacity_uses_union_not_duplicate_qualification_intervals():
    assert available_minutes([[0, 60], [10, 50], [30, 90], [120, 150], [160, 160]]) == 120


def test_one_hundred_pieces_cannot_sum_capacity_across_candidate_machines():
    task = op(run=73, load=1, unload=1, setup=10,
        people=[dict(id="person", work=[[0, 2550]], auto=[[0, 3000]])],
        machines=[dict(id=f"m{i}", work=[[0, 3000]]) for i in range(14)], lunch=False)
    value = order(quantity=100, operations=[task]);value["inspection"] = None
    result = issues(value)
    assert len(result) == 1
    assert "TEST-100 / 第1道 CNC4" in result[0]
    assert "7510分钟" in result[0] and "人员最多可用2550分钟" in result[0]
    assert "单台候选设备最多可用3000分钟" in result[0]
    assert task["run"] == 73 and value["quantity"] == 100 and len(task["machines"]) == 14


def test_longer_capable_candidate_avoids_false_rejection_and_lunch_is_explicit():
    task = op(kind="manual", machines=[], run=100, lunch=False, two=False,
        people=[dict(id="short", work=[[0, 90]], auto=[[0, 150]]), dict(id="long", work=[[0, 100]], auto=[[0, 150]])])
    value = order(operations=[task]);value["inspection"] = None
    assert not issues(value)
    task["people"] = task["people"][:1]
    assert issues(value)
    task["lunch"] = True
    assert not issues(value)


def test_independent_first_and_final_inspection_do_not_require_same_person():
    value = order(quantity=2, operations=[op(run=1)])
    value["inspection"] = inspection()
    value["inspection"]["run"] = 100
    value["inspection"]["people"] = [dict(id="a", work=[[0, 100]], auto=[[0, 100]]),dict(id="b", work=[[0, 100]], auto=[[0, 100]])]
    assert not issues(value)  # Each inspection can choose a different qualified person.


def test_remaining_batch_excludes_the_already_released_first_piece():
    value = order(quantity=2, operations=[op(run=100, people=[dict(id="a",work=[[0,100]],auto=[[0,100]])])])
    value.update(remaining_only=True, first_actual_release=-100, inspection=None)
    assert not issues(value)
    value["remaining_only"] = False
    assert issues(value)


def test_external_work_only_checks_its_independent_inspection_not_factory_processing():
    external = dict(id="op",kind="external",run=1440,setup=0,load=0,unload=0,people=[],machines=[],after_inspection=inspection())
    external["after_inspection"]["run"] = 600
    value = order(quantity=2,operations=[external]);value["inspection"] = None
    result = issues(value)
    assert len(result) == 1 and "独立检验" in result[0] and "1200分钟" in result[0]
