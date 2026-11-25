"""正式排程的实际准入与批次流转。被生产/质量公开服务在同一事务内调用。"""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from .archive_repository import archive_repository
from .calendar_windows import effective_windows
from .schedule_execution_repository import repository as repo


def touch(row,user):
    row.version_no+=1;row.updated_at=utc_now();row.updated_by=user.user_id


async def current_phase(session,task,order):
    rows=await repo.phases(session,task.id)
    if not rows:return None
    gate=await repo.gate(session,order.id)
    if gate is None:raise AppException("正式方案缺少首件准入资料，请联系排产员核对",409)
    code="remaining" if gate.status_code=="released" and any(p.production_phase_code=="remaining" for p,_,_ in rows) else "first"
    selected=next((row for row in rows if row[0].production_phase_code==code),None)
    return (*selected,gate) if selected else None


async def context(session,task,order):
    current=await current_phase(session,task,order)
    if not current:return None
    phase,op,plan,gate=current
    good,scrap,rework=await repo.totals(session,phase.id)
    reported = good + scrap + rework
    segments=await repo.phase_segments(session,phase)
    person=next((s.production_person_id for s in segments if not s.is_independent_inspection and s.production_person_id),None)
    assigned = getattr(task, "assigned_production_person_id", None)
    readiness=await repo.readiness(session,order.id)
    missing=[code for code in ("material","drawing","program","tool") if not any(r.readiness_kind_code==code and r.confirmed_at for r in readiness)]
    setting=await repo.setting(session,task.id)
    planned=[s for s in segments if not s.is_independent_inspection]
    planned_start=min((s.planned_start_at for s in planned),default=None)
    predecessors=await repo.order_phases(session,order.id)
    predecessor_ready=not any(p.production_phase_code==phase.production_phase_code and other.sequence_no<task.sequence_no and p.status_code!="completed" for p,other in predecessors)
    reason=""
    if missing:reason="开工条件尚未实际确认"
    elif phase.status_code=="completed" and gate.status_code!="released":reason="本工序首件已完成，等待后道首件流转及全路线检验放行"
    elif not predecessor_ready:reason="本批次前置工序尚未完成"
    elif assigned and person and assigned != person:reason="派工人员已变更，请重新排程并应用方案后开工"
    elif planned_start and planned_start>utc_now():reason="尚未到本批次计划开始时间"
    from .repository import repository as task_repo
    named = (await task_repo.production_person_names(session, {person})).get(person) if person else None
    return dict(plan_id=str(plan.id),plan_no=plan.plan_no,production_phase_id=str(phase.id),production_phase_code=phase.production_phase_code,
        phase_status_code=phase.status_code,first_article_status_code=gate.status_code,is_rework=phase.is_rework and reported > 0,
        planned_quantity=float(phase.planned_quantity),reported_quantity=float(reported),
        remaining_quantity=float(max(Decimal(0),phase.planned_quantity-reported)),
        production_person_id=str(person) if person else None,missing_readiness=missing,
        production_person_name=named.full_name if named and named.org_id == task.org_id else None,
        production_person_no=next((s.person_no_snapshot for s in planned if s.person_no_snapshot),None),
        execution_kind_code=setting.execution_kind_code if setting else None,load_minutes=setting.load_minutes if setting else 0,
        unload_minutes=setting.unload_minutes if setting else 0,planned_start_at=planned_start,
        can_start=phase.status_code=="pending" and not reason,reason=reason,
        phase_label="首件" if phase.production_phase_code=="first" else "剩余批量")


async def validate_resource(session,task,person_id,user,stage,setting,equipment_id,exclude=None,*,process_id=None):
    pair=await repo.person(session,person_id,task.org_id)
    if not pair:raise AppException("正式安排的生产人员已停用或身份无效，请重新排程",409)
    person,linked_user=pair
    from .schedule_plan_repository import repository as plan_repo
    await plan_repo.lock_resources(session,[person.party_id],[equipment_id] if equipment_id else [])
    if linked_user!=user.user_id and "mes:operation_task:manage" not in user.permissions:
        raise AppException("该批次安排给其他生产人员；代录须具有生产执行管理权限",403)
    now=utc_now();process_id=process_id or task.process_id
    definition=await repo.process(session,process_id,task.org_id)
    if not definition or (setting and definition.execution_kind_code!=setting.execution_kind_code) or definition.is_equipment_required is not bool(equipment_id):
        raise AppException("工艺类别或机器需求已改变，不能继续使用原安排，请工程确认后重新排程",409)
    if not await repo.qualified(session,person,process_id,now):raise AppException("生产人员当前没有该工艺的有效资格",409)
    if equipment_id and not await repo.equipment(session,equipment_id,task.org_id,process_id):
        raise AppException("实际设备已停用或不再适用于该工艺",409)
    calendars=await repo.calendars(session,person,equipment_id)
    periods,exceptions=await repo.calendar_rows(session,[c.id for c in calendars])
    absences=await repo.person_absences(session,person.party_id,now)
    for resource,identifier in (("production_person_id",person.id),("equipment_id",equipment_id)):
        if not identifier:continue
        active=[c for c in calendars if getattr(c,resource)==identifier and c.valid_from<=now.astimezone(ZoneInfo(c.timezone_name)).date()
            and (not c.valid_to or now.astimezone(ZoneInfo(c.timezone_name)).date()<c.valid_to)]
        if len(active)!=1:raise AppException("当前缺少唯一有效的人员或设备日历",409)
        c=active[0];windows=effective_windows(c,periods,exceptions,now.astimezone(ZoneInfo(c.timezone_name)).date(),absences if resource=="production_person_id" else [])
        # 开工、切换和恢复均为人工动作；午休内仅已进入自动段的机器可持续运行。
        if not any(a<=now<b for a,b in windows["work"]):raise AppException("当前处于休息、请假或设备不可用时段，不能开始人工操作",409)
    demand=1 if stage=="run" and setting and setting.can_supervise_two_machines else 2
    used=0
    for execution,other,other_setting,party_id in await repo.actual_occupancy(session,person,equipment_id,exclude):
        if equipment_id and (execution.equipment_id or other.equipment_id)==equipment_id:
            raise AppException("设备仍被其他实际执行占用，请先核对并结束对应执行",409)
        same_person=party_id==person.party_id or (execution.production_person_id is None and linked_user==execution.worker_user_id)
        if same_person and execution.status_code!="paused":
            used+=1 if execution.segment_type_code=="run" and other_setting and other_setting.can_supervise_two_machines else 2
    if used+demand>2:raise AppException("人员当前容量不足：自动照看最多两机，人工专注操作独占人员",409)
    return person


async def before_start(session,task,order,body,user):
    state=await current_phase(session,task,order)
    if not state:return None
    phase,op,plan,gate=state
    await archive_repository.lock_organization(session,task.org_id)
    if phase.status_code!="pending":
        raise AppException("当前首件已完成，须等待完整路线首件检验放行后再开始剩余批量" if phase.status_code=="completed" else "当前生产批次不允许开工",409)
    if body.production_phase_code and body.production_phase_code!=phase.production_phase_code:
        raise AppException("首件/剩余批量状态已变化，请刷新任务",409)
    readiness=await repo.readiness(session,order.id)
    if any(not any(r.readiness_kind_code==kind and r.confirmed_at and r.confirmed_at<=utc_now() for r in readiness) for kind in ("material","drawing","program","tool")):
        raise AppException("材料、图纸、程序或刀具尚未实际确认就绪；预计到时不能代替开工确认",409)
    phases=await repo.order_phases(session,order.id)
    if any(p.production_phase_code==phase.production_phase_code and other.sequence_no<task.sequence_no and p.status_code!="completed" for p,other in phases):
        raise AppException("本批次前置工序尚未完成或检验放行，不能越序开工",409)
    previous=[(p,other) for p,other in phases if p.production_phase_code==phase.production_phase_code and other.sequence_no<task.sequence_no]
    if previous:
        preceding=max(previous,key=lambda pair:pair[1].sequence_no)[0]
        good,_,_=await repo.totals(session,preceding.id)
        if good<phase.planned_quantity:raise AppException("前序合格数量不足本批次需要，请先通过异常、返修或工程调整处理，不能虚报后序产量",409)
    source=next((r for r in plan.input_snapshot.get("source_facts",[]) if r["operation_id"]==str(task.id)),None)
    same_time=bool(source) and ((source["standard_minutes_per_unit"]=="None" and task.standard_minutes_per_unit is None) or
        (source["standard_minutes_per_unit"]!="None" and task.standard_minutes_per_unit is not None and Decimal(source["standard_minutes_per_unit"])==task.standard_minutes_per_unit))
    if not source or source["process_id"]!=str(task.process_id) or source["sequence_no"]!=task.sequence_no or Decimal(source["planned_quantity"])!=task.planned_quantity or not same_time:
        raise AppException("工序配置与正式方案不一致，请重新排程",409)
    segments=await repo.phase_segments(session,phase)
    setting=await repo.setting(session,task.id)
    process=await repo.process(session,task.process_id,task.org_id)
    if not setting or not process or process.execution_kind_code!=setting.execution_kind_code or process.is_equipment_required is not task.is_equipment_required_snapshot:
        raise AppException("工艺执行类别或设备需求已改变，请工程核对后重新排程",409)
    planned=[s for s in segments if not s.is_independent_inspection]
    if not planned:raise AppException("正式阶段安排缺失，不能开工",409)
    if utc_now()<min(s.planned_start_at for s in planned):raise AppException("尚未到本批次计划开始时间，请按计划执行或重新排程",409)
    if setting.execution_kind_code=="external":
        if "mes:operation_task:manage" not in user.permissions:raise AppException("委外发出及回厂登记需要生产执行管理权限",403)
        phase.status_code="in_progress";touch(phase,user)
        return dict(production_phase_id=phase.id,production_person_id=None,equipment_id=None,segment_type_code="external_wait")
    person_id=planned[0].production_person_id
    assigned = getattr(task, "assigned_production_person_id", None)
    if assigned and assigned != person_id:
        raise AppException("派工人员已变更，请重新排程并应用方案后开工", 409)
    if body.production_person_id and body.production_person_id!=person_id:raise AppException("实际人员与正式安排不一致，请先改派并重新排程",409)
    setting=await repo.setting(session,task.id)
    if setting is None:raise AppException("缺少已确认的工序阶段参数",409)
    stage="load" if setting.execution_kind_code=="machine" and setting.load_minutes else "run" if setting.execution_kind_code=="machine" else "manual"
    await validate_resource(session,task,person_id,user,stage,setting,op.equipment_id)
    phase.status_code="in_progress";touch(phase,user)
    return dict(production_phase_id=phase.id,production_person_id=person_id,equipment_id=op.equipment_id,segment_type_code=stage)


async def manual_assignment(session, task, body, *, exclude_execution=None):
    identifier = getattr(task, "assigned_production_person_id", None)
    if not identifier:
        return {}
    if body.production_person_id and body.production_person_id != identifier:
        raise AppException("报工人员与当前派工不一致，请刷新任务", 409)
    await archive_repository.lock_organization(session, task.org_id)
    pair = await repo.person(session, identifier, task.org_id)
    if not pair or not await repo.qualified(session, pair[0], task.process_id, utc_now()):
        raise AppException("派工人员已停用或当前没有该工艺的有效资格，请重新派工", 409)
    person, _ = pair
    from .schedule_plan_repository import repository as plan_repo
    await plan_repo.lock_resources(session, [person.party_id], [])
    if any(execution.status_code != "paused" for execution, *_ in
           await repo.actual_occupancy(session, person, None, exclude_execution)):
        raise AppException("派工人员仍有未结束的实际作业，请先结束对应执行", 409)
    return {"production_person_id": identifier}


async def validate_report(session,execution,body,user):
    if not execution.production_phase_id:return
    if execution.segment_type_code=="external_wait":raise AppException("委外尚未确认回厂，不能记录回厂产量",409)
    # 通过已授权执行所在工序定位，不接受客户端传入批次主键。
    phases=await repo.phases(session,execution.operation_id)
    phase=next((p for p,_,_ in phases if p.id==execution.production_phase_id),None)
    if not phase:raise AppException("生产批次安排已失效，请刷新任务",409)
    quantity=body.good_quantity+body.scrap_quantity+body.rework_quantity
    reported = sum(await repo.totals(session, phase.id))
    if phase.is_rework and reported > 0:
        if quantity:raise AppException("返工复作保留原报工数量，不能重复增加产量；可记录工时后结束复作并检验",409)
    elif quantity<=0:raise AppException("普通生产报工必须填写产出数量",409)
    elif reported+quantity>phase.planned_quantity:
        raise AppException("本次报工超过当前首件或剩余批量的可报数量",409)
    elif phase.is_rework:
        # 历史版本会将零产量结束的首件标为返工，随首次有效产量提交恢复普通报工。
        phase.is_rework = False
        touch(phase, user)


async def after_track_out(session,task,order,execution,user):
    if not execution.production_phase_id:return False
    phases=await repo.order_phases(session,order.id)
    phase=next((p for p,_ in phases if p.id==execution.production_phase_id),None)
    if phase is None:raise AppException("实际批次记录缺失",409)
    good,scrap,rework=await repo.totals(session,phase.id)
    total=good+scrap+rework
    last=max(other.sequence_no for _,other in phases)
    if phase.production_phase_code=="first" and (good<1 or scrap or rework):
        phase.status_code = "pending"
        phase.is_rework = total > 0
    elif total<phase.planned_quantity:
        phase.status_code="pending"
    elif task.is_quality_required or task.sequence_no==last or (await repo.setting(session,task.id)).inspection_process_id:
        phase.status_code="waiting_quality"
        if phase.production_phase_code=="first" and task.sequence_no==last:
            gate=await repo.gate(session,order.id);gate.status_code="waiting_quality";touch(gate,user)
    else:phase.status_code="completed";phase.is_rework=False
    task.status_code="waiting_quality" if phase.status_code=="waiting_quality" else "completed" if all(p.status_code=="completed" for p,_ in phases if p.operation_id==task.id) else "pending"
    # 首件通过本身不结束整张工单；独立最终检验仍必须真实完成。
    order.status_code="in_progress";order.closed_at=order.closed_by=None
    order.good_quantity=order.scrap_quantity=order.rework_quantity=Decimal(0)
    touch(phase,user)
    return True


async def before_resume(session,task,order,execution,user):
    if not execution.production_phase_id:
        await manual_assignment(session, task, execution, exclude_execution=execution.id)
        return
    await archive_repository.lock_organization(session,task.org_id)
    if execution.segment_type_code not in {"external_wait","external_return"}:
        await validate_resource(session,task,execution.production_person_id,user,execution.segment_type_code,
            await repo.setting(session,task.id),execution.equipment_id,execution.id)
    await set_phase_status(session,execution,"in_progress",user)


async def set_phase_status(session,execution,status,user):
    if execution and execution.production_phase_id:
        pair=await repo.report_phase(session,execution.id)
        if pair:pair[0].status_code=status;touch(pair[0],user)


async def validate_finish(session,execution):
    if not execution.production_phase_id:return
    if execution.segment_type_code=="external_wait":raise AppException("委外尚未确认回厂，不能结束执行",409)
    setting=await repo.setting(session,execution.operation_id)
    if setting and setting.execution_kind_code=="machine" and setting.unload_minutes and execution.segment_type_code!="unload":
        raise AppException("本工序需要人工卸料，请先切换到“卸料”并完成卸料后再结束执行；午休自动结束不释放设备",409)


async def change_stage(session,task,order,execution,stage,user):
    if not execution.production_phase_id:raise AppException("该任务未采用自动排程批次，无需切换阶段",409)
    setting=await repo.setting(session,task.id)
    if setting and setting.execution_kind_code=="external":
        if stage!="external_return" or execution.segment_type_code!="external_wait":raise AppException("当前不是待回厂的委外任务",409)
        if "mes:operation_task:manage" not in user.permissions:raise AppException("缺少委外回厂登记权限",403)
        execution.segment_type_code=stage;execution.updated_at=utc_now();execution.updated_by=user.user_id
        return
    if not setting or setting.execution_kind_code!="machine":raise AppException("只有机器加工任务可切换装料、自动加工和卸料阶段",409)
    allowed={"load":{"run"},"run":{"unload"} if setting.unload_minutes else {"load"},"unload":{"load","run"} if not setting.load_minutes else {"load"}}
    if stage==execution.segment_type_code:return
    if stage not in allowed.get(execution.segment_type_code,set()):raise AppException("实际阶段顺序不正确，请按装料、加工、卸料操作",409)
    await archive_repository.lock_organization(session,task.org_id)
    await validate_resource(session,task,execution.production_person_id,user,stage,setting,execution.equipment_id,execution.id)
    execution.segment_type_code=stage;execution.updated_at=utc_now();execution.updated_by=user.user_id


async def inspection_context(session,task,order,body,user):
    state=await current_phase(session,task,order)
    if not state:return None
    phase,op,plan,gate=state
    if phase.status_code!="waiting_quality" or task.status_code!="waiting_quality":raise AppException("本生产批次尚未提交检验",409)
    if body.production_phase_code and body.production_phase_code!=phase.production_phase_code:raise AppException("检验批次已变化，请刷新",409)
    phases=await repo.order_phases(session,order.id)
    last=max(other.sequence_no for _,other in phases)
    is_last=task.sequence_no==last
    execution=await repo.last_execution(session,phase.id)
    if execution is None:raise AppException("缺少本批次已结束的实际执行，不能提交检验",409)
    if is_last and any(p.production_phase_code==phase.production_phase_code and other.id!=task.id and p.status_code!="completed" for p,other in phases):
        raise AppException("本批次尚未走完完整工艺路线，不能全路线放行",409)
    good,scrap,rework=await repo.totals(session,phase.id)
    if body.result_code=="pass":
        if good+scrap+rework<phase.planned_quantity:raise AppException("本批次数量尚未完成，不能检验放行",409)
        if phase.production_phase_code=="first" and (good<1 or scrap or rework):
            raise AppException("首件尚无完整合格产量，请核对返工或报工更正；不得凭检验新增首件数量",409)
    segments=await repo.phase_segments(session,phase)
    qa=[s for s in segments if s.is_independent_inspection and s.production_person_id]
    if not qa:qa=[s for s in segments if s.segment_type_code=="inspection" and s.production_person_id]
    if not qa:raise AppException("本检验缺少正式人员/工艺安排，请联系工程核对检验参数",409)
    planned=qa[0]
    process=await repo.process(session,planned.process_id,task.org_id)
    if not process or process.execution_kind_code not in {"inspection","machine_inspection"} or process.is_equipment_required is not bool(planned.equipment_id):
        raise AppException("检验工艺或设备要求已变化，请工程重新确认检验安排",409)
    if body.production_person_id and body.production_person_id!=planned.production_person_id:raise AppException("检验人员与安排不一致，请先核对改派",409)
    await archive_repository.lock_organization(session,task.org_id)
    await validate_resource(session,task,planned.production_person_id,user,"manual",None,planned.equipment_id,execution.id,process_id=planned.process_id)
    inspection_type="first_article" if is_last and phase.production_phase_code=="first" else "final" if is_last else "operation"
    return dict(phase=phase,gate=gate,phases=phases,execution=execution,good=good,scrap=scrap,rework=rework,
        inspection_type=inspection_type,person_id=planned.production_person_id,equipment_id=planned.equipment_id,is_last=is_last)


async def apply_inspection(session,task,order,body,user,state,inspection):
    phase,gate,phases=state["phase"],state["gate"],state["phases"]
    if body.result_code=="pass":
        phase.status_code="completed";phase.is_rework=False;touch(phase,user)
        if state["inspection_type"]=="first_article":
            gate.status_code="released";gate.last_inspection_id=inspection.id;gate.released_at=utc_now();gate.released_by=user.user_id;touch(gate,user)
    else:
        start=next((other for _,other in phases if other.id==body.rework_operation_id),None) if body.rework_operation_id else task
        if start is None:raise AppException("返工起始工序不属于当前工单",409)
        if start.sequence_no>task.sequence_no:raise AppException("返工不能从尚未执行的后续工序开始",409)
        affected=[other.id for p,other in phases if p.production_phase_code==phase.production_phase_code and other.sequence_no>=start.sequence_no]
        if not await repo.can_inspect_operations(session,affected,user):raise AppException("返工涉及当前无权处理的工序，请由覆盖完整路线的质量人员处理",403)
        for p,other in phases:
            if p.production_phase_code==phase.production_phase_code and other.sequence_no>=start.sequence_no:
                p.status_code="pending";p.is_rework=True;touch(p,user)
                other.status_code="pending";other.version_no+=1;other.updated_at=utc_now();other.updated_by=user.user_id
        if phase.production_phase_code=="first":
            gate.status_code="rework";gate.last_inspection_id=inspection.id;gate.released_at=gate.released_by=None;touch(gate,user)
    for p,other in phases:
        related=[entry for entry,_ in phases if entry.operation_id==other.id]
        if all(entry.status_code=="completed" for entry in related):other.status_code="completed"
        elif any(entry.status_code=="waiting_quality" for entry in related):other.status_code="waiting_quality"
        elif not any(entry.status_code in {"in_progress","paused"} for entry in related):other.status_code="pending"
    complete=gate.status_code=="released" and all(p.status_code=="completed" for p,_ in phases)
    order.status_code="completed" if complete else "in_progress"
    order.closed_at,order.closed_by=(utc_now(),user.user_id) if complete else (None,None)
    last=max((other for _,other in phases),key=lambda row:row.sequence_no)
    for key in ("good_quantity","scrap_quantity","rework_quantity"):setattr(order,key,getattr(last,key) if complete else Decimal(0))
    inspection.to_status_code=task.status_code


async def ensure_order_complete(session,order):
    phases=await repo.order_phases(session,order.id)
    if not phases:return
    gate=await repo.gate(session,order.id)
    if not gate or gate.status_code!="released" or any(p.status_code!="completed" for p,_ in phases):
        raise AppException("自动排程工单尚未完成全路线首件放行及剩余批量检验，不能手动完结",409)


async def before_report_change(session,report,task,order):
    pair=await repo.report_phase(session,report.execution_id)
    if not pair:return
    phase,_=pair
    gate=await repo.gate(session,order.id)
    if phase.production_phase_code=="first" and gate and gate.status_code=="released":
        raise AppException("首件已实际放行，不能直接更改首件原产量；请通过制造异常和返修流程处理",409)


async def guard_manual_schedule(session,pairs,changes):
    for org in sorted({task.org_id for task,_ in pairs},key=str):await archive_repository.lock_organization(session,org)
    from .schedule_plan_repository import repository as plan_repo
    people,devices=[],[]
    for task,_ in pairs:
        change=changes[task.id]
        parties,equipment=await repo.manual_resources(session,task,change)
        people.extend(parties);devices.extend(equipment)
    await plan_repo.lock_resources(session,people,devices)
    for task,_ in pairs:
        error=await repo.manual_plan_conflict(session,task,changes[task.id])
        if error:raise AppException(error,409)


async def after_report_change(session,report,task,order,user):
    pair=await repo.report_phase(session,report.execution_id)
    if not pair:return
    phase,execution=pair
    good,scrap,rework=await repo.totals(session,phase.id)
    if good+scrap+rework>phase.planned_quantity:raise AppException("更正后的数量超过本生产批次计划，请先核对",409)
    phases=await repo.order_phases(session,order.id)
    last=max(other.sequence_no for _,other in phases)
    if execution.tracked_out_at is None:
        phase.status_code="paused" if execution.status_code=="paused" else "in_progress"
    elif good+scrap+rework<phase.planned_quantity:phase.status_code="pending"
    elif task.is_quality_required or task.sequence_no==last:phase.status_code="waiting_quality"
    else:phase.status_code="completed"
    touch(phase,user)
    task.status_code=phase.status_code if phase.status_code in {"in_progress","paused","waiting_quality"} else "pending"
    order.status_code="in_progress";order.closed_at=order.closed_by=None
    order.good_quantity=order.scrap_quantity=order.rework_quantity=Decimal(0)
