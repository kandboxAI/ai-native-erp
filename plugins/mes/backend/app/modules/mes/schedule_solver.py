"""纯计算CP-SAT内核：整数分钟、无数据库/网络/姓名；只输出条件试排。

每件装料/加工/卸料独立建模；整批转序及完整首件路线是独立的先后约束。
资源选择不拆成互不相干的阶段：同一工序在首件与剩余批量使用同一人、机。
"""
from collections import defaultdict
from time import monotonic

from ortools.sat.python import cp_model


def solve_trial(data):
    model = cp_model.CpModel()
    horizon = data["horizon"]
    machine_intervals = defaultdict(list)
    person_intervals = defaultdict(list)
    person_demands = defaultdict(list)
    segments = []
    counter = 0

    def variable(label):
        nonlocal counter
        counter += 1
        return model.new_int_var(0, horizon, f"{label}_{counter}")

    def fit(start, end, windows, present, duration=None):
        if duration is not None:
            # 固定耗时直接约束合法开始区间，避免逐件×候选人员×每日时段
            # 生成海量选择布尔变量；不合并午休、停机等不可用间隔。
            starts = [[max(0, lo), min(horizon, hi) - duration] for lo, hi in windows
                if max(0, lo) <= min(horizon, hi) - duration]
            if starts:
                model.add_linear_expression_in_domain(start, cp_model.Domain.from_intervals(starts)).only_enforce_if(present)
            else:
                model.add(present == 0)
            return
        choices = []
        for lo, hi in windows:
            lo, hi = max(0, lo), min(horizon, hi)
            if lo >= hi:
                continue
            choice = model.new_bool_var(f"window_{counter}_{len(choices)}")
            model.add(start >= lo).only_enforce_if(choice)
            model.add(end <= hi).only_enforce_if(choice)
            choices.append(choice)
        model.add(sum(choices) == present)

    def choices(resources):
        values = [(r, model.new_bool_var(f"resource_{counter}_{r['id']}")) for r in resources]
        model.add(sum(b for _, b in values) == 1)
        return values

    for kind, groups in data.get("reservations", {}).items():
        for identifier, periods in groups.items():
            for period in periods:
                start, end = period[:2]
                interval = model.new_fixed_size_interval_var(start, end - start, "reserved")
                if kind == "machine":
                    machine_intervals[identifier].append(interval)
                else:
                    person_intervals[identifier].append(interval)
                    person_demands[identifier].append(period[2] if len(period) > 2 else 2)

    def operation(order, op):
        if op["kind"]=="external":
            qa=operation(order,op["after_inspection"])
            def external_batch(batch_key,count,predecessor):
                start,end=variable("external_start"),variable("external_return")
                model.add(start==predecessor)
                model.add(end==op["external_returns"][batch_key])
                model.add(end>=start)
                segments.append(dict(order_id=order["id"],operation_id=op["id"],batch_key=batch_key,piece_no=0,
                    kind_key="external_wait",start=start,end=end,process_id=op["process_id"],person_capacity_units=0,people=[],machines=[]))
                return qa(batch_key,count,end)
            return external_batch
        people = choices(op["people"])
        machines = choices(op["machines"]) if op["kind"] == "machine" else []

        def stage(batch, piece, kind, minutes, predecessor, automatic=False, machine=False):
            start, end = variable("start"), variable("end")
            model.add(end == start + minutes)
            model.add(start >= predecessor)
            for person, present in people if minutes else []:
                interval = model.new_optional_interval_var(start, minutes, end, present, "person")
                person_intervals[person["id"]].append(interval)
                person_demands[person["id"]].append(1 if automatic and op["two"] else 2)
                fit(start, end, person["auto"] if automatic and op["lunch"] else person["work"], present, minutes)
            if machine and minutes:
                for resource, present in machines:
                    interval = model.new_optional_interval_var(start, minutes, end, present, "machine_setup")
                    machine_intervals[resource["id"]].append(interval)
                    fit(start, end, resource["work"], present, minutes)
            if minutes:
                segments.append(dict(order_id=order["id"], operation_id=op["id"], batch_key=batch,
                    piece_no=piece, kind_key=kind, start=start, end=end, people=people,
                    process_id=op.get("process_id"), person_capacity_units=1 if automatic and op["two"] else 2,
                    machines=machines if op["kind"] == "machine" else []))
            return start, end

        setup_end = None

        def batch(batch_key, count, predecessor):
            nonlocal setup_end
            if setup_end is None:
                if op["setup"]:
                    _, setup_end = stage("first", 0, "preparation", op["setup"], predecessor, machine=bool(machines))
                else:
                    setup_end = predecessor
            previous = variable("batch_ready")
            model.add(previous >= predecessor)
            model.add(previous >= setup_end)
            for piece in range(1, count + 1):
                if machines:
                    load_start, load_end = stage(batch_key, piece, "load", op["load"], previous)
                    run_start, run_end = stage(batch_key, piece, "inspection" if op.get("is_inspection") else "run", op["run"], load_end, automatic=True)
                    model.add(run_start == load_end)
                    unload_start, unload_end = stage(batch_key, piece, "unload", op["unload"], run_end)
                    # 没有卸料动作时无需等人；有卸料时整段设备占用包含等待。
                    if not op["unload"]:
                        model.add(unload_start == run_end)
                    for resource, present in machines:
                        hold_duration = variable("hold_duration")
                        model.add(hold_duration == unload_end - load_start)
                        hold = model.new_optional_interval_var(load_start, hold_duration, unload_end, present, "machine_hold")
                        machine_intervals[resource["id"]].append(hold)
                        fit(load_start, unload_end, resource["work"], present)
                    segments.append(dict(order_id=order["id"], operation_id=op["id"], batch_key=batch_key,
                        piece_no=piece, kind_key="waiting_unload", start=run_end, end=unload_start,
                        process_id=op.get("process_id"), person_capacity_units=0,
                        people=[], machines=machines))
                    previous = unload_end
                else:
                    _, previous = stage(batch_key, piece, "inspection" if op["kind"] == "inspection" else "manual",
                        op["run"], previous)
            return previous

        if op.get("after_inspection"):
            qa=operation(order,op["after_inspection"])
            return lambda batch_key,count,predecessor:qa(batch_key,count,batch(batch_key,count,predecessor))
        return batch

    completions = []
    for order in data["orders"]:
        operations = [(op, operation(order, op)) for op in order["operations"]]
        first_end = order["ready"]
        if not order.get("remaining_only"):
            for _, batch in operations:first_end = batch("first", 1, first_end)
        # 在完整首件路线末尾进行独立首件质检；通过是条件预测，不生成放行事实。
        if order["inspection"] and not order.get("remaining_only"):
            first_inspection = operation(order, order["inspection"])
            first_end = first_inspection("first", 1, first_end)
        end = first_end
        if order["quantity"] > 1:
            for _, batch in operations:
                end = batch("remaining", order["quantity"] - 1, end)
            if order["inspection"]:
                final_inspection = operation(order, {**order["inspection"], "id": "final_inspection"})
                end = final_inspection("remaining", order["quantity"] - 1, end)
        completions.append((order, order["first_actual_release"] if order.get("remaining_only") else first_end, end))

    if not completions:
        return dict(status_code="PRECHECK_FAILED", issues=["没有完整的可排工单"], segments=[])
    for intervals in machine_intervals.values():
        model.add_no_overlap(intervals)
    for identifier, intervals in person_intervals.items():
        model.add_cumulative(intervals, person_demands[identifier], 2)

    # 同项目整单交付以全部货品齐套为起点；出货条件不完整时只显示检验预测。
    delivery_groups=defaultdict(list)
    for order,first,end in completions:delivery_groups[order.get("delivery_group",order["id"])].append((order,end))
    delivery_ends={}
    objective_deliveries=[]
    for rows in delivery_groups.values():
        ready=variable("delivery_ready")
        model.add_max_equality(ready,[end for _,end in rows])
        rules=[(o.get("shipping_preparation"),o.get("shipping_windows")) for o,_ in rows]
        complete=all(o.get("shipping_complete",False) for o,_ in rows) and all(rule==rules[0] for rule in rules)
        dispatch=None
        if complete:
            start,dispatch=variable("shipping_start"),variable("shipping_end")
            model.add(start>=ready);model.add(dispatch==start+rules[0][0])
            fit(start,dispatch,rules[0][1],1,rules[0][0])
        for o,_ in rows:delivery_ends[o["id"]]=dispatch
        objective_deliveries.append((min(o["due"] for o,_ in rows),dispatch if dispatch is not None else ready))
    objectives = []
    for due in sorted({d for d,_ in objective_deliveries}):
        group = [(d,e) for d,e in objective_deliveries if d == due]
        delays = []
        for _, end in group:
            delay = model.new_int_var(0, horizon + abs(due), "delay")
            model.add_max_equality(delay, [0, end - due])
            delays.append(delay)
        objectives.extend([sum(delays), sum(e for _, e in group)])
    movements=[]
    for operation_id,previous in data.get("previous_starts",{}).items():
        starts=[s["start"] for s in segments if s["operation_id"]==operation_id]
        if not starts:continue
        start=variable("operation_start");model.add_min_equality(start,starts)
        delta=model.new_int_var(0,horizon+abs(previous),"plan_change")
        model.add_abs_equality(delta,start-previous);movements.append(delta)
    if movements:objectives.append(sum(movements))
    makespan = variable("makespan")
    model.add_max_equality(makespan, [end for _, _, end in completions])
    objectives.append(makespan)
    deadline = monotonic() + data["time_limit_seconds"]
    best = None
    all_optimal = True
    for objective in objectives:
        remaining = deadline - monotonic()
        if remaining <= 0:
            all_optimal = False
            break
        model.minimize(objective)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = 1
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if best is None:
                return dict(status_code=solver.status_name(status), segments=[], completions=[])
            all_optimal = False
            break
        best = solver
        if status != cp_model.OPTIMAL:
            all_optimal = False
            break
        model.add(objective == solver.value(objective))
    if best is None:
        return dict(status_code="UNKNOWN", segments=[], completions=[])
    output = []
    for segment in segments:
        start, end = best.value(segment["start"]), best.value(segment["end"])
        if start == end:
            continue
        output.append({k: v for k, v in segment.items() if k not in {"start", "end", "people", "machines"}} | dict(
            start=start, end=end,
            person_id=next((r["id"] for r, b in segment["people"] if best.boolean_value(b)), None),
            equipment_id=next((r["id"] for r, b in segment["machines"] if best.boolean_value(b)), None)))
    return dict(status_code="OPTIMAL" if all_optimal else "FEASIBLE", segments=sorted(output, key=lambda r: (r["start"], r["operation_id"])),
        completions=[dict(work_order_id=o["id"], first_article_release=best.value(first), inspection_release=best.value(end), due=o["due"],
            shipping_complete=delivery_ends[o["id"]] is not None,shipping_release=best.value(delivery_ends[o["id"]]) if delivery_ends[o["id"]] is not None else None)
            for o, first, end in completions])


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(solve_trial(json.load(sys.stdin)), ensure_ascii=True))
