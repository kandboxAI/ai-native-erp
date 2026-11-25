"""将授权快照和明确的工程确认输入转换为纯计算资料；缺项阻断，不自动补零。"""
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from math import ceil, floor

from .calendar_windows import effective_windows
from .schedule_limits import MAX_STAGES, MAX_RESOURCE_WINDOW_COMBINATIONS
from .schedule_capacity import capacity_issues


def snapshot_key(snapshot):
    def canonical(value):
        if isinstance(value, datetime): return value.astimezone(UTC).isoformat()
        if isinstance(value, Decimal): return str(value.normalize())
        return str(value)
    rows = [("incomplete_project",str(identifier)) for identifier in snapshot.get("incomplete_projects",[])]
    for key in ("orders", "tasks", "processes", "equipment", "links", "qualifications", "calendars", "periods", "dependencies", "exceptions", "settings", "readiness", "inspection_settings", "phases", "gates"):
        for row in snapshot.get(key, []):
            # 仅计算摘要，不把自由文本、联系方式或原始导入数据交给求解器/客户端。
            values = {name: canonical(getattr(row, name)) for name in (
                "id", "version_no", "updated_at", "status_code", "is_active", "process_id", "equipment_id",
                "production_person_id", "valid_from", "valid_to", "start_minute_of_day", "end_minute_of_day",
                "timezone_name", "weekday_no", "period_type_code", "sequence_no", "planned_quantity", "due_at",
                "standard_minutes_per_unit", "is_quality_required", "processing_type_code", "unit_code", "previous_process_id",
                "start_at", "end_at", "exception_type_code", "expected_at", "confirmed_at", "readiness_kind_code",
                "execution_kind_code", "is_equipment_required", "is_equipment_required_snapshot", "setup_minutes", "load_minutes", "unload_minutes", "can_supervise_two_machines",
                "inspection_process_id", "inspection_minutes_per_piece", "is_inspection_equipment_required", "external_first_return_at", "external_remaining_return_at",
                "can_run_during_lunch", "source_version_no_snapshot", "inspection_mode_code", "minutes_per_piece", "is_equipment_required") if hasattr(row, name)}
            rows.append((key, values))
    rows.extend(("person", (str(p.id), str(p.party_id), str(u), p.version_no)) for p, u in snapshot["people"])
    rows.extend(("reservation", [str(v) for v in (row[:7] if len(row) > 7 and row[7] is None else row)])
        for row in snapshot["reservations"])
    rows.extend(("fact", str(v)) for v in snapshot["facts"])
    rows.extend(("absence", [str(v) for v in row]) for row in snapshot.get("absences", []))
    rows.extend(("phase_reservation", [str(v) for v in row]) for row in snapshot.get("phase_reservations", []))
    rows.extend(("execution_fact",[str(v) for v in row]) for row in snapshot.get("execution_facts",[]))
    rows.extend(("fixed_person",[str(k),str(v)]) for k,v in snapshot.get("fixed_people",{}).items())
    rows.extend(("actual_resource",[str(v) for v in row]) for row in snapshot.get("unknown_actual_resources",[]))
    return sha256(json.dumps(sorted(rows, key=str), sort_keys=True).encode()).hexdigest()


def frozen_first(snapshot,order):
    gate=next((g for g in snapshot.get("gates",[]) if g.work_order_id==order.id and g.status_code=="released" and g.released_at),None)
    tasks=[t for t in snapshot["tasks"] if t.work_order_id==order.id]
    phases=[p for p in snapshot.get("phases",[]) if p.work_order_id==order.id]
    first={p.operation_id:p for p in phases if p.production_phase_code=="first" and p.status_code=="completed"}
    if not gate or order.planned_quantity<=1 or set(first)!={t.id for t in tasks}:return None
    if any(p.status_code!="pending" or p.is_rework for p in phases if p.production_phase_code=="remaining"):return None
    if any(task_id in first and (phase_id!=first[task_id].id or not ended) for task_id,phase_id,ended in snapshot.get("execution_facts",[])):return None
    return gate.released_at


def prepare(snapshot, scope):
    processes={p.id:p for p in snapshot["processes"]}
    tasks = defaultdict(list)
    for task in snapshot["tasks"]:
        tasks[task.work_order_id].append(task)
    return dict(snapshot_key=snapshot_key(snapshot),
        settings=[r.model_dump(mode="json", exclude={"flex_form", "description"}) for r in snapshot.get("settings", [])],
        readiness=[r.model_dump(mode="json", exclude={"flex_form", "description"}) for r in snapshot.get("readiness", [])],
        inspection_settings=[r.model_dump(mode="json", exclude={"flex_form", "description"}) for r in snapshot.get("inspection_settings", [])],
        orders=[dict(id=str(o.id), work_order_no=o.work_order_no,schedule_mode_code="remaining" if frozen_first(snapshot,o) else "full",
        production_order_id=str(o.production_order_id) if getattr(o,"production_order_id",None) else None,
        is_project_complete=getattr(o,"production_order_id",None) not in snapshot.get("incomplete_projects",set()),
        version_no=o.version_no, quantity=str(o.planned_quantity), unit_code=o.unit_code, due_at=o.due_at,
        operations=[dict(id=str(t.id), version_no=t.version_no, operation_name=t.operation_name_snapshot,
            is_equipment_required_snapshot=getattr(t,"is_equipment_required_snapshot",None),
            execution_kind_code=getattr(processes.get(t.process_id),"execution_kind_code",None),
            process_id=str(t.process_id) if t.process_id else None, standard_minutes_per_unit=t.standard_minutes_per_unit,
            is_quality_required=t.is_quality_required, status_code=t.status_code) for t in tasks[o.id]]) for o in snapshot["orders"]],
        processes=[dict(id=str(p.id), process_name=p.process_name, execution_kind_code=getattr(p,"execution_kind_code",None),
            is_equipment_required=getattr(p,"is_equipment_required",None)) for p in snapshot["processes"]],
        issues=base_issues(snapshot, scope))


def resource_fingerprint(snapshot):
    # 排程应用与实际报工会正常改变工单版本；风险复核单独比较资源条件，避免误报为资料失效。
    content=dict(snapshot)
    for key in ("orders","tasks","settings","readiness","inspection_settings","phases","gates"):content[key]=[]
    content["facts"]=set()
    content["execution_facts"]=[];content["fixed_people"]={}
    return snapshot_key(content)


def base_issues(snapshot, scope):
    issues = []
    if set(scope.work_order_ids) != {o.id for o in snapshot["orders"]} or snapshot["hidden_route"]:
        issues.append("工单或完整工序路线不在当前排程管理范围内，请重新选择")
    for order in snapshot["orders"]:
        label = order.work_order_no
        remaining=bool(frozen_first(snapshot,order))
        if order.status_code not in ({"in_progress","released"} if remaining else {"draft", "released"}) or any(getattr(order, k) for k in ("good_quantity", "scrap_quantity", "rework_quantity")):
            issues.append(f"{label}：只安排尚未开工的完整工单，或首件已实际放行且剩余批量尚未开工的工单")
        if order.processing_type_code not in {"in_house", "outsourced"}:
            issues.append(f"{label}：采购货品不属于生产工艺排程范围")
        if order.due_at is None:
            issues.append(f"{label}：缺少明确交期，请先补齐出货承诺时间")
        if order.planned_quantity < 1 or order.planned_quantity != int(order.planned_quantity):
            issues.append(f"{label}：首件试排只支持按整件计数的数量")
        if order.unit_code != "piece":
            issues.append(f"{label}：首轮仅支持标准单位“件”，其他计量单位不能按首件直接换算")
        tasks = [t for t in snapshot["tasks"] if t.work_order_id == order.id]
        if not tasks:
            issues.append(f"{label}：尚未配置完整工序路线")
        if len({t.sequence_no for t in tasks}) != len(tasks):
            issues.append(f"{label}：工序顺序重复，请先核对路线")
        seen = set()
        for task in tasks:
            title = f"{label} / {task.operation_name_snapshot}"
            required = {edge.previous_process_id for edge in snapshot.get("dependencies", []) if edge.process_id == task.process_id}
            if not required <= seen:
                issues.append(f"{title}：路线缺少前置工艺或顺序不正确，请先核对完整路线")
            seen.add(task.process_id)
            if task.status_code not in {"draft", "pending", "dispatched"} or (not remaining and (task.id in snapshot["facts"] or any(
                    getattr(task, k) for k in ("good_quantity", "scrap_quantity", "rework_quantity")))):
                issues.append(f"{title}：存在执行或报工事实，不重新安排首件")
            if task.planned_quantity != order.planned_quantity:
                issues.append(f"{title}：工序数量与交付数量不同，请先核对，不自动换算")
            process = next((p for p in snapshot["processes"] if p.id == task.process_id), None)
            execution_kind = getattr(process, "execution_kind_code", None)
            if not execution_kind and getattr(process, "processing_type_code", None) == "outsourced":
                issues.append(f"{title}：请在工艺档案中确认排程执行类别为“委外（不占本厂机器）”")
            elif execution_kind != "external" and (not task.standard_minutes_per_unit or task.standard_minutes_per_unit <= 0):
                issues.append(f"{title}：缺少单件标准工时")
            if not task.equipment_id and (getattr(task, "workstation_name_snapshot", None) or "").strip():
                issues.append(f"{title}：已指定工作站但尚未关联正式设备，请先核对设备限制")
    return issues


def build_problem(snapshot, request):
    issues = base_issues(snapshot, request)
    origin, end = request.start_at, request.end_at
    horizon = floor((end - origin).total_seconds() / 60)
    if not request.is_regular_calendar_confirmed:
        issues.append("请确认本次窗口内常规日历适用，暂无未登记的请假、维修、节假日等例外")
    rules = {r.operation_id: r for r in request.operation_rules}
    order_rules = {r.work_order_id: r for r in request.order_rules}
    if set(rules) != {t.id for t in snapshot["tasks"]} or set(order_rules) != {o.id for o in snapshot["orders"]}:
        issues.append("确认资料必须覆盖本次完整工单及全部工序，不能漏排或额外添加")
    processes = {p.id: p for p in snapshot["processes"]}
    qualified = defaultdict(list)
    for q in snapshot["qualifications"]:
        qualified[(q.production_person_id, q.process_id)].append((q.valid_from, q.valid_to or end))
    labels = {"person": {}, "equipment": {}, "operation": {}, "order": {}}

    def minutes(value, up):
        return (ceil if up else floor)((value - origin).total_seconds() / 60)

    def windows(resource, field):
        result = {"work": [], "auto": []}
        first = origin.date() - timedelta(days=1)
        for offset in range((end.date() - first).days + 2):
            day = first + timedelta(days=offset)
            active = [c for c in snapshot["calendars"] if getattr(c, field) == resource.id and c.is_active
                and not c.deleted_at and c.valid_from <= day and (not c.valid_to or day < c.valid_to)]
            if len(active) > 1:
                raise ValueError("资源日历有效期重叠，请先核对")
            if not active:
                continue
            blocked = [(a, b) for party, a, b in snapshot.get("absences", []) if getattr(resource, "party_id", None) == party]
            daily = effective_windows(active[0], snapshot["periods"], snapshot.get("exceptions", []), day, blocked)
            work = sorted(daily["work"])
            result["work"].extend((max(0, minutes(a, True)), min(horizon, minutes(b, False))) for a, b in work)
            # 只合并夹在两个工作时段中的显式午休；不把夜晚/请假当成可无人加工。
            merged = daily["auto"]
            result["auto"].extend((max(0, minutes(a, True)), min(horizon, minutes(b, False))) for a, b in merged)
        return {key: [w for w in value if w[0] < w[1]] for key, value in result.items()}

    people_windows, equipment_windows = {}, {}
    try:
        people_windows = {p.id: windows(p, "production_person_id") for p, _ in snapshot["people"]}
        equipment_windows = {e.id: windows(e, "equipment_id") for e in snapshot["equipment"]}
    except ValueError as exc:
        issues.append(str(exc))
    capabilities = defaultdict(set)
    for link in snapshot["links"]:
        capabilities[link.equipment_id].add(link.process_id)
    for e in snapshot["equipment"]:
        labels["equipment"][str(e.id)] = f"{e.equipment_no} · {e.equipment_name}"
    for p, _ in snapshot["people"]:
        labels["person"][str(p.party_id)] = p.person_no

    unknown_people, unknown_machines = set(), set()
    for party,equipment in snapshot.get("unknown_actual_resources",[]):
        if party:unknown_people.add(str(party))
        if equipment:unknown_machines.add(str(equipment))
    reservations = {"person": defaultdict(list), "machine": defaultdict(list)}
    users = {u: str(p.party_id) for p, u in snapshot["people"] if u}
    equipment_by_no = {e.equipment_no: str(e.id) for e in snapshot["equipment"]}
    for equipment_id, user_id, status, start, finish, station, live, *assigned_party in snapshot["reservations"]:
        machine = str(equipment_id) if equipment_id else equipment_by_no.get(station)
        person = str(assigned_party[0]) if assigned_party and assigned_party[0] else users.get(user_id)
        if live or status not in {"draft", "pending", "dispatched"} or not start or not finish or finish <= start:
            if not machine and not person:
                issues.append("存在无法确定人员/设备及释放时刻的在制任务，请先核对当前占用")
            if machine:
                unknown_machines.add(machine)
            if person:
                unknown_people.add(person)
            continue
        a, b = max(0, minutes(start, False)), min(horizon, minutes(finish, True))
        if a < b:
            if not machine and not person:
                issues.append("存在尚未关联正式人员或设备的范围外计划，请先核对资源归属")
            if machine:
                reservations["machine"][machine].append((a, b))
            if person:
                reservations["person"][person].append((a, b))
    for party_id, equipment_id, start, finish, demand in snapshot.get("phase_reservations", []):
        a, b = max(0, minutes(start, False)), min(horizon, minutes(finish, True))
        if a >= b: continue
        if party_id and demand: reservations["person"][str(party_id)].append((a, b, demand))
        if equipment_id: reservations["machine"][str(equipment_id)].append((a, b))

    def candidates(process_id, fixed_machine=None, fixed_user=None, machine_required=False, fixed_party=None, *, label=None, fixed_person=None):
        if process_id not in processes:
            return [], []
        label = label or processes[process_id].process_name
        people = []
        has_person = has_qualification = has_work_window = has_qualified_window = False
        for p, user_id in snapshot["people"]:
            if (fixed_user and fixed_user != user_id) or (fixed_party and fixed_party != p.party_id) or (fixed_person and fixed_person != p.id):
                continue
            has_person = True
            bounds = qualified[(p.id, process_id)]
            if not bounds:
                continue
            has_qualification = True
            daily = people_windows.get(p.id, {})
            has_work_window = has_work_window or bool(daily.get("work"))
            actual = {key: sorted(set((max(lo, minutes(a, True)), min(hi, minutes(b, False)))
                for lo, hi in daily.get(key, []) for a, b in bounds
                if max(lo, minutes(a, True)) < min(hi, minutes(b, False)))) for key in ("work", "auto")}
            if actual["work"]:
                has_qualified_window = True
                if str(p.party_id) not in unknown_people:
                    people.append(dict(id=str(p.party_id), **actual))
        machines = [dict(id=str(e.id), work=equipment_windows.get(e.id, {}).get("work", [])) for e in snapshot["equipment"]
            if str(e.id) not in unknown_machines and process_id in capabilities[e.id]
            and (not fixed_machine or e.id == fixed_machine) and equipment_windows.get(e.id, {}).get("work")]
        if not people:
            if not has_person:
                if fixed_person:
                    reason = "指定的生产人员不可排程，或与原方案固定人员不一致，请核对本工序派工"
                elif fixed_user:
                    reason = "已派工账号未匹配到本组织可排程的生产人员，请核对账号关联、启用状态和原方案人员"
                elif fixed_party:
                    reason = "原方案指定的生产人员在本组织不可排程，请核对人员状态"
                else:
                    reason = "本组织没有可排程的生产人员，请核对人员档案"
            elif not has_qualification:
                reason = "人员在排程窗口内没有该工艺的有效资格，请核对技能及有效期"
            elif not has_qualified_window:
                reason = ("工作时段与该工艺的资格有效期不重合" if has_work_window
                    else "有该工艺资格的人员在本次排程窗口内没有可用工作时段，请核对工作日历和请假例外")
            else:
                reason = "可用人员仍有未结束或释放时间不明确的任务，请核对实际占用"
            constraint = "（仅检查已派工或原方案指定人员）" if fixed_person or fixed_user or fixed_party else ""
            issues.append(f"{label}：{reason}{constraint}")
        if machine_required and not machines:
            issues.append(f"{label}：缺少匹配工艺、日历和可信可用时段的设备")
        return people, machines

    def inspection_operation(config, identifier):
        process=processes.get(config.process_id)
        if not process or process.processing_type_code!="in_house" or getattr(process,"execution_kind_code",None) not in {"inspection","machine_inspection"}:
            issues.append("检验必须选择工艺档案中已明确的有效检验工艺，不能以加工资格代替")
        if process and getattr(process,"is_equipment_required",None) is not config.is_equipment_required:
            issues.append("检验设备要求须与正式工艺定义一致")
        people,machines=candidates(config.process_id,machine_required=config.is_equipment_required)
        return dict(id=identifier,process_id=str(config.process_id),kind="machine" if config.is_equipment_required else "inspection",
            is_inspection=True,run=int(config.minutes_per_piece.to_integral_value(rounding=ROUND_CEILING)),
            setup=0,load=0,unload=0,two=False,lunch=False,people=people,machines=machines)

    orders = []
    segment_count = 0
    for order in snapshot["orders"]:
        released=frozen_first(snapshot,order)
        labels["order"][str(order.id)] = order.work_order_no
        rule = order_rules.get(order.id)
        if not rule:
            continue
        if rule.version_no != order.version_no or not rule.is_readiness_confirmed:
            issues.append(f"{order.work_order_no}：请核对最新版本，并确认材料、图纸、程序及刀具的最早就绪时间")
        operations = []
        for task in [t for t in snapshot["tasks"] if t.work_order_id == order.id]:
            labels["operation"][str(task.id)] = task.operation_name_snapshot
            op = rules.get(task.id)
            if not op:
                continue
            if op.version_no != task.version_no or not op.is_timing_confirmed:
                issues.append(f"{task.operation_name_snapshot}：请核对最新版本，并确认单件工时为净加工/人工耗时，准备与装卸另计且不重复")
            process = processes.get(task.process_id)
            if not process or process.processing_type_code not in {"in_house","outsourced"}:
                issues.append(f"{task.operation_name_snapshot}：未匹配有效生产工艺")
                continue
            declared=getattr(process,"execution_kind_code",None)
            if (process.processing_type_code=="outsourced") != (op.kind_key=="external"):
                issues.append(f"{task.operation_name_snapshot}：委外/自制属性与执行类别不一致，请先维护工艺档案")
            if not declared or declared!=op.kind_key:
                issues.append(f"{task.operation_name_snapshot}：请先在工艺档案明确排程执行类别，工单不能自行把加工资格当检验资格或改为人工绕开设备")
            required=op.kind_key in {"machine","machine_inspection"}
            source_required=getattr(task,"is_equipment_required_snapshot",None)
            if getattr(process,"is_equipment_required",None) is not required or (source_required is not None and source_required is not required):
                issues.append(f"{task.operation_name_snapshot}：机器需求快照与当前工艺不一致，请工程确认配置后重新排程")
            if (task.is_quality_required or op.kind_key=="external") and op.kind_key not in {"inspection", "machine_inspection"} and not op.inspection:
                issues.append(f"{task.operation_name_snapshot}：请补齐工序放行/回厂检验的独立工艺、人员设备及耗时")
            if op.kind_key not in {"machine", "machine_inspection"} and task.equipment_id:
                issues.append(f"{task.operation_name_snapshot}：已指定设备，不能改为无设备任务来绕过资源约束")
            machine_required = op.kind_key in {"machine", "machine_inspection"}
            assigned_person = getattr(task, "assigned_production_person_id", None)
            applied_party = snapshot.get("fixed_people", {}).get(task.id)
            # 与执行派工一致，旧系统账号仅在没有手动生产人员和已应用方案人员时使用。
            fixed_user = None if assigned_person or applied_party else task.assigned_user_id
            people, machines = ([],[]) if op.kind_key=="external" else candidates(
                task.process_id, task.equipment_id, fixed_user, machine_required,
                applied_party if released else None,
                label=f"{order.work_order_no} / {task.operation_name_snapshot}", fixed_person=assigned_person)
            operation=dict(id=str(task.id), process_id=str(task.process_id), kind="machine" if machine_required else op.kind_key,
                is_inspection=op.kind_key in {"inspection", "machine_inspection"}, run=int(Decimal(str(task.standard_minutes_per_unit or 1)).to_integral_value(rounding=ROUND_CEILING)),
                setup=op.setup_minutes, load=op.load_minutes, unload=op.unload_minutes, two=op.supervision_key == "two_machines",
                lunch=op.is_lunch_auto_allowed, people=people, machines=machines)
            if op.kind_key=="external":
                if int(order.planned_quantity)>1 and not op.external_remaining_return_at:
                    issues.append(f"{task.operation_name_snapshot}：缺少剩余批量预计回厂时间")
                operation["external_returns"]={"first":minutes(op.external_first_return_at,True),
                    "remaining":minutes(op.external_remaining_return_at,True) if op.external_remaining_return_at else horizon}
                if any(not 0<=v<=horizon for v in operation["external_returns"].values()):issues.append("委外预计回厂须在本次窗口内")
            if op.inspection:
                qa_id=f"{task.id}:inspection"
                operation["after_inspection"]=inspection_operation(op.inspection,qa_id)
                labels["operation"][qa_id]=f"{task.operation_name_snapshot} · 回厂检验" if op.kind_key=="external" else f"{task.operation_name_snapshot} · 工序放行"
                segment_count+=max(1,int(order.planned_quantity))*4
            operations.append(operation)
            if released:operation["setup"]=0
            segment_count += max(1, int(order.planned_quantity)) * (4 if machine_required else 1) + 1
        inspection = None
        if request.inspection.mode_key == "last_operation":
            if not operations or not (operations[-1].get("is_inspection") or operations[-1].get("after_inspection")):
                issues.append(f"{order.work_order_no}：复用末道检验时，完整路线最后一道必须明确为人工检验或设备检验")
        else:
            inspector = processes.get(request.inspection.process_id)
            if operations and (operations[-1].get("is_inspection") or operations[-1].get("after_inspection")):
                issues.append(f"{order.work_order_no}：末道已包含检验，请选择复用末道检验，避免重复检验及放行口径不一致")
            if not inspector or inspector.processing_type_code != "in_house" or getattr(inspector,"execution_kind_code",None) not in {"inspection","machine_inspection"}:
                issues.append("首件/最终检验必须选用有效自制检验工艺，并具有真实资格及日历")
            if inspector and getattr(inspector,"is_equipment_required",None) is not request.inspection.is_equipment_required:
                issues.append("检验机器需求须与工艺档案一致，不能省略三坐标等已确认的检验设备")
            inspection = inspection_operation(request.inspection,"first_inspection")
        group_key=str(order.production_order_id) if rule.delivery_mode_key=="whole_project" and getattr(order,"production_order_id",None) else str(order.id)
        shipping_complete=rule.shipping_preparation_minutes is not None and bool(rule.shipping_windows) and (rule.delivery_mode_key=="individual" or getattr(order,"production_order_id",None) not in snapshot.get("incomplete_projects",set()))
        if any(w.start_at<origin or w.end_at>end for w in rule.shipping_windows):issues.append("出货时段须在本次排程窗口内")
        orders.append(dict(id=str(order.id), quantity=max(1, int(order.planned_quantity)),delivery_group=group_key,
            remaining_only=bool(released),first_actual_release=minutes(released,False) if released else None,
            shipping_complete=shipping_complete,shipping_preparation=rule.shipping_preparation_minutes,
            shipping_windows=[(minutes(w.start_at,True),minutes(w.end_at,False)) for w in rule.shipping_windows],
            ready=max(0, minutes(rule.ready_at, True)), due=minutes(order.due_at, False) if order.due_at else 0,
            operations=operations, inspection=inspection))
        if inspection:
            segment_count += max(1, int(order.planned_quantity)) * 4
    if segment_count > MAX_STAGES or len(snapshot["tasks"]) > 100:
        issues.append(f"本次预计建模{segment_count}段、{len(snapshot['tasks'])}道工序，超过试排上限（{MAX_STAGES}段/100道工序）；请缩小工单范围，不会截断数量或漏排工序")
    complexity = sum(o["quantity"] * sum(
        (3 if op["kind"] == "machine" else 1) * sum(len(p["work"]) + len(p["auto"]) for p in op["people"])
        + sum(len(e["work"]) for e in op["machines"]) for op in o["operations"] + [op["after_inspection"] for op in o["operations"] if op.get("after_inspection")] + ([o["inspection"]] if o["inspection"] else [])) for o in orders)
    if complexity > MAX_RESOURCE_WINDOW_COMBINATIONS:
        issues.append(f"本次候选资源与日历组合估算为{complexity}，超过单次试排上限{MAX_RESOURCE_WINDOW_COMBINATIONS}；请缩小工单范围或窗口，不会静默删减候选资源")
    issues.extend(capacity_issues(orders, labels))
    labels["operation"].update(first_inspection="首件全路线检验", final_inspection="剩余批量最终检验")
    previous={str(t.id):max(0,minutes(t.planned_start_at,True)) for t in snapshot["tasks"] if getattr(t,"planned_start_at",None)}
    return dict(horizon=horizon, orders=orders, reservations=reservations,previous_starts=previous,
        time_limit_seconds=request.time_limit_seconds), list(dict.fromkeys(issues)), labels
