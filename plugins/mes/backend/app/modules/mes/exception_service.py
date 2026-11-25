"""异常闭环事务：异常自身流转，不隐式开停生产、不代替质量放行。"""
from datetime import UTC, timedelta
from hashlib import sha256
import json

from app.core.exceptions import AppException
from app.framework.db.models import utc_now, uuid7
from app.framework.db.session import get_session_context
from app.modules.user_profile.public import list_assignee_options, user_display_names
from app.modules.notification_center.service import notify
from .exception_models import MesExceptionCase, MesExceptionEvent
from .exception_repository import exception_repository as repo
from .repository import repository as production_repo

ACTION_PERMISSION = {"assign":"manage", "start":"handle", "progress":"handle", "resolve":"handle", "approve":"review", "reject":"review", "reopen":"review"}
FIELDS = ("id", "org_id", "case_no", "work_order_id", "operation_id", "title", "description", "exception_type_code", "status_code",
          "assigned_user_id", "due_at", "resolved_at", "resolved_by", "closed_at", "closed_by", "version_no", "created_at", "created_by", "updated_at")


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def require(user, suffix):
    if f"mes:exception:{suffix}" not in user.permissions: raise AppException("缺少当前异常处理操作权限", 403)


def allowed_actions(row, user):
    result=[]
    if "mes:exception:manage" in user.permissions and row.status_code in {"pending", "in_progress"}: result.append("assign")
    if "mes:exception:handle" in user.permissions and row.assigned_user_id == user.user_id:
        if row.status_code == "pending": result.append("start")
        if row.status_code == "in_progress": result.extend(["progress", "resolve"])
    if "mes:exception:review" in user.permissions:
        if row.status_code == "waiting_confirmation":
            result.append("reject")
            if row.resolved_by != user.user_id: result.append("approve")
        if row.status_code == "closed": result.append("reopen")
    return result


def event(session, row, action, before, note, user_id):
    repo.add(session, MesExceptionEvent(org_id=row.org_id, case_id=row.id, action_code=action, from_status_code=before,
        to_status_code=row.status_code, note=note, assigned_user_id=row.assigned_user_id, due_at_snapshot=row.due_at, created_by=user_id))


async def send_notice(session, row, scene, actor_id, event_key):
    # 通知仅带单号和期限，不带异常标题、处理说明、客户或图纸内容。
    return await notify(session, scene_key=f"mes.exception.{scene}", org_id=row.org_id,
        actors={"owner":[row.assigned_user_id] if row.assigned_user_id else [], "reporter":[row.created_by] if row.created_by else []},
        payload={"case_no":row.case_no, "due_at":aware(row.due_at).isoformat()}, business_type_code="mes_exception",
        business_id=row.id, event_key=event_key, redirect_url=f"/mes/exceptions?case_id={row.id}", source_module_code="mes", created_by=actor_id)


class ExceptionService:
    async def items(self, session, pairs, user):
        names = await user_display_names(session, {identifier for row, _ in pairs for identifier in (row.assigned_user_id, row.created_by) if identifier})
        operations = await repo.operation_names(session, {row.operation_id for row,_ in pairs if row.operation_id})
        now=utc_now()
        return [dict(**{name:getattr(row,name) for name in FIELDS}, work_order_no=number,
            assigned_user_name=names.get(row.assigned_user_id), reporter_name=names.get(row.created_by), operation_name=operations.get(row.operation_id),
            is_overdue=row.status_code != "closed" and aware(row.due_at) < now, allowed_actions=allowed_actions(row,user)) for row,number in pairs]

    async def page(self, query, user):
        require(user,"list")
        async with get_session_context() as session:
            pairs,total=await repo.page(session,query,user,utc_now())
            return dict(items=await self.items(session,pairs,user),total=total,page=query.page,page_size=query.page_size)

    async def get(self, session, identifier, user, permission="list", *, lock=False):
        require(user,"list"); require(user,permission)
        pair=await repo.get(session,identifier,user,f"mes:exception:{permission}",lock=lock)
        if pair is None or (permission != "list" and await repo.get(session,identifier,user,"mes:exception:list") is None):
            raise AppException("异常单不存在或超出当前操作范围",404)
        return pair

    async def detail(self, identifier, user):
        async with get_session_context() as session:
            pair=await self.get(session,identifier,user)
            return (await self.items(session,[pair],user))[0]

    async def history(self, identifier, query, user):
        async with get_session_context() as session:
            await self.get(session,identifier,user)
            rows,total=await repo.history(session,identifier,query.page,query.page_size)
            names=await user_display_names(session,{identifier for row in rows for identifier in (row.created_by,row.assigned_user_id) if identifier})
            fields=("id","action_code","from_status_code","to_status_code","note","assigned_user_id","due_at_snapshot","created_at")
            return dict(items=[dict(**{key:getattr(row,key) for key in fields},actor_name=names.get(row.created_by) if row.created_by else "系统", assigned_user_name=names.get(row.assigned_user_id)) for row in rows],
                total=total,page=query.page,page_size=query.page_size)

    async def orders(self, query, user):
        require(user,"create")
        if "mes:work_order:list" not in user.permissions: raise AppException("登记异常需要生产工单查询权限",403)
        async with get_session_context() as session:
            return [dict(id=row.id, org_id=row.org_id, label=f"{row.work_order_no} · {row.product_item_name_snapshot}") for row in await repo.orders(session,query,user)]

    async def source_options(self, identifier, query, user):
        require(user,"create")
        if "mes:work_order:list" not in user.permissions: raise AppException("登记异常需要生产工单查询权限",403)
        async with get_session_context() as session:
            order=await repo.source(session,identifier,user)
            if order is None: raise AppException("工单不存在或无权登记异常",404)
            return dict(operations=[dict(id=row.id,label=row.operation_name_snapshot) for row in await repo.operations(session,order)],
                users=await list_assignee_options(session,user,order.org_id,"mes:exception:create",query.keyword))

    async def assignees(self, identifier, query, user):
        async with get_session_context() as session:
            row,_=await self.get(session,identifier,user,"manage")
            return await list_assignee_options(session,user,row.org_id,"mes:exception:manage",query.keyword)

    async def check_assignee(self, session, identifier, org_id):
        if identifier and not await production_repo.is_active_assignee(session,identifier,org_id):
            raise AppException("责任人不存在、已停用或不属于异常组织",409)

    async def create(self, body, user):
        require(user,"create"); require(user,"list")
        if "mes:work_order:list" not in user.permissions: raise AppException("登记异常需要生产工单查询权限",403)
        digest=sha256(json.dumps(body.model_dump(mode="json"),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        async with get_session_context() as session:
            existing=await repo.by_key(session,user.user_id,body.idempotency_key)
            if existing:
                if existing.request_hash != digest: raise AppException("登记标识已用于其他内容，请重新登记",409)
                pair=await self.get(session,existing.id,user)
                return (await self.items(session,[pair],user))[0]
            order=await repo.source(session,body.work_order_id,user)
            if order is None or order.status_code == "cancelled": raise AppException("来源工单不存在、已取消或无权登记",404)
            # 同工单登记串行；等待父工单锁期间，另一相同请求可能已提交。
            existing=await repo.by_key(session,user.user_id,body.idempotency_key)
            if existing:
                if existing.request_hash != digest: raise AppException("登记标识已用于其他内容，请重新登记",409)
                return (await self.items(session,[await self.get(session,existing.id,user)],user))[0]
            if body.operation_id and await repo.operation(session,body.operation_id,order) is None:
                raise AppException("来源工序不属于该工单或已删除",409)
            if body.due_at <= utc_now(): raise AppException("处理期限须晚于当前时间",422)
            await self.check_assignee(session,body.assigned_user_id,order.org_id)
            identifier=uuid7()
            row=MesExceptionCase(id=identifier,org_id=order.org_id,case_no=f"EX-{utc_now():%Y%m%d}-{identifier.hex[-12:].upper()}",
                **body.model_dump(exclude={"idempotency_key"}),idempotency_key=body.idempotency_key,request_hash=digest,
                created_by=user.user_id,updated_by=user.user_id)
            repo.add(session,row); await session.flush()
            event(session,row,"created",None,"登记异常",user.user_id)
            notice=await send_notice(session,row,"assigned",user.user_id,f"mes.exception.created:{row.id}")
            result=(await self.items(session,[(row,order.work_order_no)],user))[0]
            result["notification_warning"]=notice.skipped_reason if notice.skipped_reason not in {None,"duplicate_event"} else None
            await session.commit()
            return result

    async def command(self, identifier, action, body, user):
        if action not in ACTION_PERMISSION: raise AppException("不支持的异常处理动作",422)
        permission=ACTION_PERMISSION[action]
        async with get_session_context() as session:
            row,number=await self.get(session,identifier,user,permission,lock=True)
            if row.version_no != body.version_no: raise AppException("异常单已更新，请刷新后重试",409)
            if action not in allowed_actions(row,user): raise AppException("当前状态、责任人或复核身份不允许该操作",409)
            if action != "assign" and (body.assigned_user_id or body.due_at): raise AppException("此动作不能改派或修改期限",422)
            if action not in {"start","approve"} and not body.note: raise AppException("请填写处理说明或结果",422)
            before=row.status_code; now=utc_now(); scene=None
            if action == "assign":
                if body.assigned_user_id is None: raise AppException("请选择责任人",422)
                await self.check_assignee(session,body.assigned_user_id,row.org_id)
                if body.due_at and body.due_at <= now: raise AppException("新处理期限须晚于当前时间",422)
                if row.assigned_user_id != body.assigned_user_id: row.status_code="pending"
                row.assigned_user_id=body.assigned_user_id
                if body.due_at: row.due_at=body.due_at
                row.last_reminded_at=None; scene="assigned"
            elif action == "start": row.status_code="in_progress"
            elif action == "resolve":
                row.status_code="waiting_confirmation"; row.resolved_at=now; row.resolved_by=user.user_id; row.last_reminded_at=None; scene="review"
            elif action == "approve":
                row.status_code="closed"; row.closed_at=now; row.closed_by=user.user_id; scene="closed"
            elif action in {"reject","reopen"}:
                row.status_code="in_progress"; row.resolved_at=None; row.resolved_by=None; row.closed_at=None; row.closed_by=None; row.last_reminded_at=None; scene="assigned"
            row.version_no+=1; row.updated_at=now; row.updated_by=user.user_id
            event(session,row,action,before,body.note or ("开始处理" if action == "start" else "复核通过"),user.user_id)
            result=(await self.items(session,[(row,number)],user))[0]
            if scene:
                notice=await send_notice(session,row,scene,user.user_id,f"mes.exception.{action}:{row.id}:{row.version_no}")
                result["notification_warning"]=notice.skipped_reason if notice.skipped_reason not in {None,"duplicate_event"} else None
            await session.commit()
            return result

    async def remind_overdue(self):
        async with get_session_context() as session:
            if not await repo.is_ready(session): return 0
            now=utc_now(); rows=await repo.reminder_candidates(session,now,now-timedelta(hours=24)); sent=0
            for row in rows:
                notice=await send_notice(session,row,"overdue",None,f"mes.exception.overdue:{row.id}:{row.version_no}:{now.date()}")
                if notice.created or notice.skipped_reason == "duplicate_event":
                    row.last_reminded_at=now; row.updated_at=now; row.updated_by=None
                    event(session,row,"reminded",row.status_code,"期限已过，已发出处理提醒",None); sent+=1
            await session.commit()
            return sent


exception_service = ExceptionService()
