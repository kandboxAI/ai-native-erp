"""正式方案事务编排：源资料固定后计算，重新校验并原子应用，不以预测代替执行事实。"""
import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from .archive_repository import archive_repository
from .models import MesExecutionEvent, MesWorkOrderEvent
from .repository import repository as task_repository
from .schedule_models import (MesOperationScheduleSetting, MesWorkOrderReadiness, MesWorkOrderInspectionSetting,
    MesSchedulePlan, MesSchedulePlanOperation, MesSchedulePlanSegment, MesOperationProductionPhase, MesWorkOrderFirstArticle)
from .schedule_plan_repository import repository
from .schedule_trial_repository import repository as sources
from .schedule_trial_planning import build_problem, snapshot_key, base_issues,resource_fingerprint,frozen_first
from .schedule_trial_schemas import TrialSolve
from .schedule_trial_service import authorize, run_solver, format_result

LIST, MANAGE, APPLY = "mes:schedule:list", "mes:schedule:manage", "mes:schedule:apply"


def require(user, permission):
    if "mes" not in user.enabled_plugin_keys or permission not in user.permissions:
        raise AppException("缺少排程方案权限或MES未启用",403)


def item(plan):
    return plan.model_dump(exclude={"input_snapshot","result_snapshot","flex_form","deleted_at","deleted_by","description"})


def touch(row,user):
    row.version_no+=1
    row.updated_at,row.updated_by=utc_now(),user.user_id


class PlanService:
    async def page(self,query,user):
        require(user,LIST)
        async with get_session_context() as session:
            rows,total=await repository.page(session,query,user)
            return dict(items=[item(r) for r in rows],total=total,page=query.page,page_size=query.page_size)

    async def get(self,session,identifier,user,permission,lock=False):
        require(user,permission)
        row=await repository.get(session,identifier,user,permission,lock)
        if row is None: raise AppException("排程方案不存在或无权访问",404)
        return row

    async def detail(self,identifier,user):
        async with get_session_context() as session:
            plan=await self.get(session,identifier,user,LIST)
            pairs=await repository.operations(session,plan,user,LIST)
            if len(pairs)!=await repository.operation_count(session,plan):
                raise AppException("方案包含当前无权查看的工单或工序，不能读取部分结果",403)
            segments=await repository.segments(session,[r.id for r,_,_ in pairs])
            people = await task_repository.production_person_names(session, {
                s.production_person_id for s in segments if s.production_person_id
            })
            person_names = {identifier: row.full_name for identifier, row in people.items() if row.org_id == plan.org_id}
            equipment_names = await repository.equipment_names(session, plan.org_id, {
                s.equipment_id for s in segments if s.equipment_id
            })
            mapping={r.id:(task,order) for r,task,order in pairs}
            risks=[]
            if MANAGE in user.permissions and plan.status_code in {"ready","applied"}:
                request=TrialSolve.model_validate(plan.input_snapshot["request"])
                current=await sources.snapshot(session,request,user,readonly=False)
                if plan.status_code=="ready" and snapshot_key(current)!=plan.input_hash:
                    risks.append("计算后工单或资源资料已变化，请重新计算后再应用")
                elif plan.status_code=="applied" and resource_fingerprint(current)!=plan.input_snapshot.get("applied_resource_hash"):
                    risks.append("人员资格、设备、日历或范围外占用已变化，请核对影响并人工发起重排")
                for row,task,order in pairs:
                    if order.status_code in {"paused","cancelled"}:risks.append(f"{order.work_order_no} 当前暂停或取消，不能继续按原计划执行")
            return dict(**item(plan),result=plan.result_snapshot,risk_issues=list(dict.fromkeys(risks)),
                readiness=[r.model_dump(exclude={"flex_form","description"}) for r in await repository.readiness(session,list({o.id for _,_,o in pairs}),user,LIST)],
                operations=[dict(**r.model_dump(exclude={"flex_form","description"}),operation_name=r.operation_name_snapshot,
                    work_order_no=r.work_order_no_snapshot) for r,t,o in pairs],
                segments=[dict(**s.model_dump(exclude={"flex_form","description"}),
                    production_person_name=person_names.get(s.production_person_id),
                    equipment_name=equipment_names.get(s.equipment_id) or (s.equipment_name_snapshot or "").partition(" · ")[2] or None,
                    operation_name=mapping[s.plan_operation_id][0].operation_name_snapshot,
                    work_order_no=mapping[s.plan_operation_id][1].work_order_no) for s in segments])

    async def save_inputs(self,session,body,request,snapshot,user):
        tasks={t.id:t for t in snapshot["tasks"]}
        processes={p.id:p for p in snapshot["processes"]}
        changed_orders=set()
        settings={r.operation_id:r for r in snapshot.get("settings",[])}
        for op in request.operation_rules:
            task=tasks.get(op.operation_id)
            process=processes.get(task.process_id) if task else None
            required=op.kind_key in {"machine","machine_inspection"}
            if not process or process.execution_kind_code!=op.kind_key or process.is_equipment_required is not required:
                raise AppException("请先在工艺档案确认执行类别和本厂机器需求，不能通过工单任意更改工艺类别",409)
            if task.is_equipment_required_snapshot is not None and task.is_equipment_required_snapshot is not required:
                raise AppException("工单机器需求快照与工艺定义不一致，请工程修订工序后再排程",409)
            if task.is_equipment_required_snapshot is None:
                task.is_equipment_required_snapshot=required;touch(task,user);op.version_no=task.version_no;changed_orders.add(task.work_order_id)
            row=settings.get(op.operation_id)
            if row is None:
                row=MesOperationScheduleSetting(org_id=body.org_id,operation_id=op.operation_id,
                    execution_kind_code=op.kind_key,setup_minutes=op.setup_minutes,load_minutes=op.load_minutes,
                    unload_minutes=op.unload_minutes,source_version_no_snapshot=op.version_no,
                    created_by=user.user_id,updated_by=user.user_id)
                repository.add(session,row)
            else: touch(row,user)
            row.execution_kind_code,row.setup_minutes,row.load_minutes,row.unload_minutes=op.kind_key,op.setup_minutes,op.load_minutes,op.unload_minutes
            row.can_supervise_two_machines=op.supervision_key=="two_machines"
            row.can_run_during_lunch,row.is_timing_confirmed=op.is_lunch_auto_allowed,op.is_timing_confirmed
            row.source_version_no_snapshot=op.version_no
            row.external_first_return_at,row.external_remaining_return_at=op.external_first_return_at,op.external_remaining_return_at
            row.inspection_process_id=op.inspection.process_id if op.inspection else None
            row.inspection_minutes_per_piece=op.inspection.minutes_per_piece if op.inspection else None
            row.is_inspection_equipment_required=op.inspection.is_equipment_required if op.inspection else False
        for order in snapshot["orders"]:
            if order.id in changed_orders:
                touch(order,user)
                next(r for r in request.order_rules if r.work_order_id==order.id).version_no=order.version_no
        readiness={(r.work_order_id,r.readiness_kind_code):r for r in snapshot.get("readiness",[])}
        for supplied in body.readiness:
            row=readiness.get((supplied.work_order_id,supplied.readiness_kind_code))
            if row is None:
                row=MesWorkOrderReadiness(org_id=body.org_id,work_order_id=supplied.work_order_id,
                    readiness_kind_code=supplied.readiness_kind_code,expected_at=supplied.expected_at,
                    created_by=user.user_id,updated_by=user.user_id)
                repository.add(session,row)
            else: touch(row,user)
            row.expected_at=supplied.expected_at
            if row.confirmed_at and not supplied.is_confirmed and any(t.id in snapshot["facts"] for t in snapshot["tasks"] if t.work_order_id==row.work_order_id):
                raise AppException("已实际生产的工单不能在重排时撤回就绪；请先暂停并登记制造异常",409)
            if supplied.is_confirmed:
                if not row.confirmed_at: row.confirmed_at,row.confirmed_by=utc_now(),user.user_id
            else: row.confirmed_at=row.confirmed_by=None
            readiness[(supplied.work_order_id,supplied.readiness_kind_code)]=row
        for order in request.order_rules:
            conditions=[readiness[(order.work_order_id,kind)] for kind in ("material","drawing","program","tool")]
            order.ready_at=max(r.confirmed_at or r.expected_at for r in conditions)
        inspections={r.work_order_id:r for r in snapshot.get("inspection_settings",[])}
        for order_id in body.work_order_ids:
            row=inspections.get(order_id)
            if row is None:
                row=MesWorkOrderInspectionSetting(org_id=body.org_id,work_order_id=order_id,
                    inspection_mode_code=request.inspection.mode_key,created_by=user.user_id,updated_by=user.user_id)
                repository.add(session,row)
            else: touch(row,user)
            row.inspection_mode_code,row.process_id=request.inspection.mode_key,request.inspection.process_id
            row.is_equipment_required,row.minutes_per_piece=request.inspection.is_equipment_required,request.inspection.minutes_per_piece
        await session.flush()

    async def create(self,body,user):
        authorize(body,user)
        request=TrialSolve.model_validate(body.model_dump(exclude={"plan_name","readiness"}))
        async with get_session_context() as session:
            orders=await repository.lock_orders(session,body.work_order_ids,user,MANAGE)
            if len(orders)!=len(body.work_order_ids):raise AppException("部分工单不存在或无权排程",404)
            await archive_repository.lock_organization(session,body.org_id)
            snapshot=await sources.snapshot(session,request,user,readonly=False)
            if body.snapshot_key!=snapshot_key(snapshot):raise AppException("工单或资源已变化，请重新读取排程资料",409)
            # 核心路线/事实不满足时不改工程配置，避免将错误输入作为正式参数保存。
            errors=base_issues(snapshot,request)
            if errors:raise AppException("；".join(errors[:8]),409)
            await self.save_inputs(session,body,request,snapshot,user)
            snapshot=await sources.snapshot(session,request,user,readonly=False)
            request.snapshot_key=snapshot_key(snapshot)
            problem,issues,labels=build_problem(snapshot,request)
            plan=MesSchedulePlan(org_id=body.org_id,plan_no=f"SP-{uuid7().hex[:24]}",plan_name=body.plan_name,
                window_start_at=body.start_at,window_end_at=body.end_at,status_code="calculating",input_hash=request.snapshot_key,
                input_snapshot={"protocol_version":1,"request":request.model_dump(mode="json"),"problem":jsonable_encoder(problem),
                    "source_facts":[dict(operation_id=str(t.id),process_id=str(t.process_id),sequence_no=t.sequence_no,
                        standard_minutes_per_unit=str(t.standard_minutes_per_unit),planned_quantity=str(t.planned_quantity)) for t in snapshot["tasks"]]},solver_version="ortools-9.15.6755/mes-aps-v2",
                time_limit_seconds=request.time_limit_seconds,created_by=user.user_id,updated_by=user.user_id)
            repository.add(session,plan)
            await session.flush()
            plan_id=plan.id
            # 工序FK即使无解仍记录完整参与范围；不把ID数组作为业务关联。
            for task in snapshot["tasks"]:
                repository.add(session,MesSchedulePlanOperation(org_id=body.org_id,plan_id=plan.id,operation_id=task.id,
                    work_order_id=task.work_order_id,source_version_no_snapshot=task.version_no,
                    operation_name_snapshot=task.operation_name_snapshot,
                    work_order_no_snapshot=next(o.work_order_no for o in snapshot["orders"] if o.id==task.work_order_id),
                    planned_quantity_snapshot=task.planned_quantity,
                    created_by=user.user_id,updated_by=user.user_id))
            await session.commit()
        try:
            raw=dict(status_code="PRECHECK_FAILED",issues=issues,segments=[],completions=[]) if issues else await run_solver(problem)
            result=raw if issues else format_result(raw,request,labels,utc_now())
            result["warnings"]=["结果以预计就绪及检验合格为条件；应用后仍检查实际就绪与首件放行。",
                "方案待人工确认，未应用前不占用正式生产资源。"]
            if any(not r.get("shipping_complete") for r in result.get("completions",[])):
                result["warnings"].append("部分货品未补齐整单齐套范围、出货准备或发货窗口，仅预测检验放行，不能当作出货承诺。")
            async with get_session_context() as session:
                plan=await self.get(session,plan_id,user,MANAGE,True)
                if plan.status_code!="calculating":raise AppException("方案计算已被取消",409)
                pairs=await repository.operations(session,plan,user,MANAGE)
                if len(pairs)!=await repository.operation_count(session,plan):raise AppException("计算期间工序权限发生变化",403)
                if result["status_code"] in {"OPTIMAL","FEASIBLE"}:
                    await self.save_result(session,plan,pairs,result,user)
                    plan.status_code="ready"
                else:plan.status_code="failed"
                plan.solver_result_code=result["status_code"]
                plan.result_snapshot=jsonable_encoder({k:v for k,v in result.items() if k!="segments"})
                touch(plan,user)
                await session.commit()
            return dict(**result,plan_id=str(plan_id),plan_no=plan.plan_no,plan_version_no=plan.version_no)
        except BaseException:
            # 计算取消/失败也有可审计的终态，不永久挂在“计算中”。
            async def failed():
                async with get_session_context() as session:
                    plan=await repository.get(session,plan_id,user,MANAGE,True)
                    if plan and plan.status_code=="calculating":
                        plan.status_code="failed";plan.result_snapshot={"issues":["计算中断，请重新生成方案"]};touch(plan,user)
                        await session.commit()
            await asyncio.shield(failed())
            raise

    async def save_result(self,session,plan,pairs,result,user):
        by_task={str(task.id):r for r,task,_ in pairs}
        last={}
        for r,task,order in pairs:
            if str(order.id) not in last or task.sequence_no>last[str(order.id)][0]:last[str(order.id)]=(task.sequence_no,r)
        people,equipment=await repository.resource_mapping(session,plan.org_id,
            [UUID(s["person_id"]) for s in result["segments"] if s["person_id"]],
            [UUID(s["equipment_id"]) for s in result["segments"] if s["equipment_id"]])
        grouped=defaultdict(list)
        for segment in result["segments"]:
            independent=segment["operation_id"] in {"first_inspection","final_inspection"} or segment["operation_id"].endswith(":inspection")
            row=by_task[segment["operation_id"].split(":")[0]] if segment["operation_id"].endswith(":inspection") else last[segment["order_id"]][1] if independent else by_task[segment["operation_id"]]
            grouped[row.id].append(segment)
            p=people.get(segment["person_id"]); e=equipment.get(segment["equipment_id"])
            if (segment["person_id"] and not p) or (segment["equipment_id"] and not e):raise AppException("计算期间资源已停用，请重新计算",409)
            repository.add(session,MesSchedulePlanSegment(org_id=plan.org_id,plan_operation_id=row.id,sequence_no=len(grouped[row.id]),
                production_phase_code=segment["batch_key"],piece_no=segment["piece_no"],quantity_snapshot=Decimal(1) if segment["piece_no"] else None,
                segment_type_code=segment["kind_key"],process_id=UUID(segment["process_id"]),
                production_person_id=p.id if p else None,equipment_id=e.id if e else None,
                person_no_snapshot=p.person_no if p else None,equipment_name_snapshot=f"{e.equipment_no} · {e.equipment_name}" if e else None,
                planned_start_at=segment["start_at"],planned_end_at=segment["end_at"],
                duration_minutes_snapshot=int((segment["end_at"]-segment["start_at"]).total_seconds()/60),
                person_capacity_units_snapshot=segment["person_capacity_units"],is_equipment_occupied=e is not None,
                is_independent_inspection=independent,created_by=user.user_id,updated_by=user.user_id))
            if not independent and segment["kind_key"]!="waiting_unload":
                row.production_person_id=p.id if p else row.production_person_id
                row.equipment_id=e.id if e else row.equipment_id
        for row,task,_ in pairs:
            segments=grouped[row.id]
            if not segments:raise AppException("求解结果遗漏工序，方案不能确认",409)
            row.planned_start_at=min(s["start_at"] for s in segments)
            row.planned_end_at=max(s["end_at"] for s in segments)
            row.duration_minutes_snapshot=sum(int((s["end_at"]-s["start_at"]).total_seconds()/60) for s in segments if s["kind_key"]!="waiting_unload")
            row.is_scheduled=True
        await session.flush()

    async def apply(self,identifier,body,user):
        require(user,APPLY);require(user,MANAGE)
        async with get_session_context() as session:
            plan=await self.get(session,identifier,user,APPLY,True)
            if plan.status_code=="applied" and plan.confirmed_by==user.user_id:return item(plan)
            if plan.version_no!=body.version_no or plan.status_code!="ready":raise AppException("只能确认最新的待确认方案",409)
            pairs=await repository.operations(session,plan,user,MANAGE)
            if len(pairs)!=await repository.operation_count(session,plan) or not pairs or any(not r.is_scheduled for r,_,_ in pairs):
                raise AppException("方案工序不完整或无权应用",409)
            order_ids=list({o.id for _,_,o in pairs})
            orders=await repository.lock_orders(session,order_ids,user,MANAGE)
            tasks=await repository.lock_tasks(session,order_ids,user,MANAGE)
            await archive_repository.lock_organization(session,plan.org_id)
            stage_rows=await repository.segments(session,[r.id for r,_,_ in pairs])
            # 资源主键先经真实方案FK定位，再投影自然人身份用于跨组织并发锁；不按客户端传入资源放行。
            from .schedule_execution_repository import repository as execution_repo
            parties=[]
            for identifier in sorted({s.production_person_id for s in stage_rows if s.production_person_id},key=str):
                person=await execution_repo.person(session,identifier,plan.org_id)
                if not person:raise AppException("方案人员身份已失效，请重新计算",409)
                parties.append(person[0].party_id)
            await repository.lock_resources(session,parties,[s.equipment_id for s in stage_rows if s.equipment_id])
            request=TrialSolve.model_validate(plan.input_snapshot["request"])
            if request.start_at<utc_now():raise AppException("方案开始时间已过，请重新计算，不应用过去的安排",409)
            snapshot=await sources.snapshot(session,request,user,readonly=False)
            if snapshot_key(snapshot)!=plan.input_hash or base_issues(snapshot,request):
                plan.status_code="invalid";touch(plan,user);await session.commit()
                raise AppException("工单、资源、日历或占用已变化，方案已失效，请重新计算",409)
            remaining_orders={o.id for o in orders if frozen_first(snapshot,o)}
            if any(o.status_code!="released" and o.id not in remaining_orders for o in orders):raise AppException("请先完成工单下单，再确认排程方案",409)
            phases=await repository.phases(session,[t.id for t in tasks])
            if any((p.status_code!="pending" or p.is_rework) and not (p.work_order_id in remaining_orders and p.production_phase_code=="first" and p.status_code=="completed") for p in phases):raise AppException("存在已执行批次，不能整体覆盖生产计划",409)
            active=await repository.active_source_plans(session,[t.id for t in tasks])
            for old,_ in active:old.is_active=False;touch(old,user)
            await session.flush()
            for old_plan in {p.id:p for _,p in active}.values():
                if not await repository.active_plan_operation_count(session,old_plan.id):
                    old_plan.status_code="superseded";old_plan.is_active=False;touch(old_plan,user)
            by_task={t.id:t for t in tasks}
            by_order={o.id:o for o in orders}
            by_equipment={e.id:e for e in snapshot["equipment"]}
            existing={(p.operation_id,p.production_phase_code):p for p in phases}
            for row,_,_ in pairs:
                task=by_task[row.operation_id]
                task.planned_start_at,task.planned_end_at=row.planned_start_at,row.planned_end_at
                task.equipment_id=row.equipment_id
                if row.equipment_id:
                    device=by_equipment[row.equipment_id]
                    task.workstation_name_snapshot=device.equipment_no
                    task.work_center_name_snapshot=device.work_center_name
                task.version_no+=1;task.updated_at=utc_now();task.updated_by=user.user_id
                row.applied_version_no_snapshot=task.version_no
                # 源工序只是计划元数据改变，工程参数口径未改变，可延续确认。
                for setting in snapshot.get("settings",[]):
                    if setting.operation_id==task.id:setting.source_version_no_snapshot=task.version_no;touch(setting,user)
                for code,quantity in (("first",Decimal(1)),("remaining",by_order[task.work_order_id].planned_quantity-1)):
                    if quantity<=0:continue
                    if code=="first" and task.work_order_id in remaining_orders:continue
                    phase=existing.get((task.id,code))
                    if phase is None:
                        phase=MesOperationProductionPhase(org_id=task.org_id,work_order_id=task.work_order_id,operation_id=task.id,
                            plan_operation_id=row.id,production_phase_code=code,planned_quantity=quantity,
                            created_by=user.user_id,updated_by=user.user_id)
                        repository.add(session,phase)
                    else:phase.plan_operation_id=row.id;phase.planned_quantity=quantity;touch(phase,user)
                repository.add(session,MesExecutionEvent(org_id=task.org_id,operation_id=task.id,event_type_code="scheduled",
                    note=f"应用自动排程方案 {plan.plan_no}；{body.note}",created_by=user.user_id,actor_user_id=user.user_id))
            gates={g.work_order_id:g for g in await repository.first_articles(session,order_ids)}
            for order in orders:
                if order.id not in gates:
                    repository.add(session,MesWorkOrderFirstArticle(org_id=order.org_id,work_order_id=order.id,
                        created_by=user.user_id,updated_by=user.user_id))
                touch(order,user)
            plan.status_code="applied";plan.confirmed_at=utc_now();plan.confirmed_by=user.user_id;touch(plan,user)
            plan.input_snapshot={**plan.input_snapshot,"applied_resource_hash":resource_fingerprint(snapshot)}
            await session.commit()
            return item(plan)

    async def update_readiness(self,identifier,body,user):
        require(user,MANAGE)
        async with get_session_context() as session:
            plan=await self.get(session,identifier,user,MANAGE)
            pairs=await repository.operations(session,plan,user,MANAGE)
            if len(pairs)!=await repository.operation_count(session,plan):raise AppException("无权维护完整方案开工条件",403)
            ids=list({o.id for _,_,o in pairs})
            orders=await repository.lock_orders(session,ids,user,MANAGE)
            await archive_repository.lock_organization(session,plan.org_id)
            wanted={(identifier,kind) for identifier in ids for kind in ("material","drawing","program","tool")}
            if {(r.work_order_id,r.readiness_kind_code) for r in body.readiness}!=wanted or len(body.readiness)!=len(wanted):raise AppException("请提交方案中每张工单的四项完整就绪条件",422)
            if any(o.status_code not in {"released","in_progress","draft"} for o in orders):raise AppException("已结束或暂停工单不能修改开工确认",409)
            rows={(r.work_order_id,r.readiness_kind_code):r for r in await repository.readiness(session,ids,user,MANAGE)}
            for supplied in body.readiness:
                row=rows.get((supplied.work_order_id,supplied.readiness_kind_code))
                if not row or supplied.version_no!=row.version_no:raise AppException("开工条件已变化，请刷新方案后维护",409)
                if row.confirmed_at and not supplied.is_confirmed:
                    from .schedule_execution_repository import repository as execution_repo
                    if any(p.status_code!="pending" for p,_ in await execution_repo.order_phases(session,row.work_order_id)):
                        raise AppException("工单已有实际生产，不能直接撤回就绪；请先暂停并登记制造异常",409)
                row.expected_at=supplied.expected_at
                if supplied.is_confirmed:
                    if not row.confirmed_at:row.confirmed_at,row.confirmed_by=utc_now(),user.user_id
                else:row.confirmed_at=row.confirmed_by=None
                touch(row,user)
            await session.commit()
            return {"updated":len(body.readiness)}

    async def cancel(self,identifier,body,user):
        require(user,MANAGE)
        async with get_session_context() as session:
            plan=await self.get(session,identifier,user,MANAGE,True)
            if plan.status_code=="cancelled":return item(plan)
            if plan.version_no!=body.version_no or plan.status_code in {"applied","superseded"}:
                raise AppException("已应用方案不能直接取消；未开工时请生成新方案替代",409)
            plan.status_code="cancelled";plan.description=body.note;touch(plan,user)
            await session.commit()
            return item(plan)


service=PlanService()
