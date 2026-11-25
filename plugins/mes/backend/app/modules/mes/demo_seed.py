"""MES 最小演示数据：只复用已有物料，不直接创建库存事实。"""

from __future__ import annotations

from decimal import Decimal

from sqlmodel import select

from app.modules.inventory.public import first_active_item

from .models import MesWorkOrder, MesWorkOrderOperation

DEMO_ORDER = 80
DEMO_REMARK = "MES-DEMO"

EXCEPTION_DEMO_MARKER = "MES-EXCEPTION-DEMO-v1"
EXCEPTION_DEMO_SCENARIOS = (
    ("MATERIAL", "【演示】铝合金毛坯待补料", "material_shortage", "pending", 8, False),
    ("EQUIPMENT", "【演示】CNC 主轴报警处理中", "equipment_failure", "in_progress", 4, True),
    ("QUALITY", "【演示】首件尺寸复测待确认", "quality_abnormal", "waiting_confirmation", 2, True),
    ("OVERDUE-MATERIAL", "【演示】关键材料补料已超时", "material_shortage", "pending", -2, True),
    ("OVERDUE-QUALITY", "【演示】表面毛刺整改已超时", "quality_abnormal", "in_progress", -1, True),
    ("CLOSED", "【演示】夹具定位异常已复核关闭", "other", "closed", -1, True),
)


async def seed_exception_demo(session, *, org_id=None, work_order_no=None, apply=False, now=None):
    """独立显式演示入口；整批提交由调用方负责，不通过通知服务或生产状态机造数。"""
    from datetime import timedelta
    from hashlib import sha256
    from app.framework.db.models import utc_now
    from .exception_models import MesExceptionCase, MesExceptionEvent
    from .exception_demo_repository import exception_demo_repository as demo_repo
    now=now or utc_now()
    orders=await demo_repo.orders(session,org_id,work_order_no)
    if not orders: raise RuntimeError("没有可关联的 MES 演示工单；可显式用 --work-order-no 指定已确认的工单")
    organizations={row.org_id for row in orders}
    if len(organizations)!=1: raise RuntimeError("来源工单涉及多个组织，请用 --org-id 明确选择")
    org_id=orders[0].org_id
    users=await demo_repo.users(session,org_id)
    if not users: raise RuntimeError("来源组织没有活动租户用户，未写入")
    actor=next((row.created_by for row in orders if row.created_by in users),users[0])
    reviewer=next((identifier for identifier in users if identifier!=actor),None)
    numbers=[f"EX-DEMO-{entry[0]}" for entry in EXCEPTION_DEMO_SCENARIOS]
    existing=await demo_repo.existing(session,org_id,numbers)
    for row in existing.values():
        if not row.flex_form.get("demo") or row.flex_form.get("seed_key")!=EXCEPTION_DEMO_MARKER:
            raise RuntimeError(f"演示编号 {row.case_no} 已被其他记录占用；未覆盖")
    operations=await demo_repo.operations(session,org_id,[row.id for row in orders])
    result=dict(org_id=str(org_id),created=0,preserved=len(existing),skipped=[],items=[])
    for index,(key,title,kind,status,hours,assigned) in enumerate(EXCEPTION_DEMO_SCENARIOS):
        number=numbers[index]
        if number in existing: continue
        if status=="closed" and reviewer is None:
            result["skipped"].append("缺少第二名活动用户，跳过已关闭演示，不伪造本人复核")
            continue
        order=orders[index%len(orders)]
        row=MesExceptionCase(org_id=org_id,case_no=number,work_order_id=order.id,operation_id=operations.get(order.id),title=title,
            description=f"【演示】{EXCEPTION_DEMO_MARKER}；用于验证异常列表、责任处理及驾驶舱展示，不代表实际生产事故。",
            exception_type_code=kind,status_code=status,assigned_user_id=actor if assigned else None,due_at=now+timedelta(hours=hours),
            created_at=now-timedelta(hours=6),created_by=actor,updated_by=reviewer if status=="closed" else actor,
            idempotency_key=f"{EXCEPTION_DEMO_MARKER}:{org_id}:{key}",request_hash=sha256(f"{EXCEPTION_DEMO_MARKER}:{org_id}:{key}".encode()).hexdigest(),
            flex_form={"demo":True,"seed_key":EXCEPTION_DEMO_MARKER})
        records=[]
        def record(action,before,after,note,happened,by):
            records.append(MesExceptionEvent(org_id=org_id,case_id=row.id,action_code=action,from_status_code=before,to_status_code=after,
                note=f"【演示】{note}",assigned_user_id=row.assigned_user_id,due_at_snapshot=row.due_at,created_at=happened,created_by=by))
        record("created",None,"pending","登记制造异常",row.created_at,actor)
        if status in {"in_progress","waiting_confirmation","closed"}:
            record("start","pending","in_progress","已接手，检查影响范围与处理方案",now-timedelta(hours=5),actor)
            record("progress","in_progress","in_progress","已核对物料、设备或检验条件，保留处理进展",now-timedelta(hours=3),actor)
        if status in {"waiting_confirmation","closed"}:
            row.resolved_by=actor;row.resolved_at=now-timedelta(minutes=30)
            record("resolve","in_progress","waiting_confirmation","处理完成，复测结果符合要求，提交复核",row.resolved_at,actor)
        if status=="closed":
            row.closed_by=reviewer;row.closed_at=now-timedelta(minutes=15)
            record("approve","waiting_confirmation","closed","由另一名用户核对演示处理结果后关闭",row.closed_at,reviewer)
        row.version_no=len(records)
        row.updated_at=records[-1].created_at
        if apply:
            demo_repo.add(session,row);await session.flush()
            for entry in records: demo_repo.add(session,entry)
        result["created"]+=1
        result["items"].append(dict(case_no=number,title=title,status_code=status,work_order_no=order.work_order_no,events=len(records)))
    if apply: await session.flush()
    return result


async def seed_demo(session, ctx) -> None:
    # JSONB 下标表达式需要显式转换为布尔值；直接与 True 比较会生成
    # ``jsonb = boolean``，PostgreSQL 无法执行。
    existing = (
        await session.exec(
            select(MesWorkOrder.id)
            .where(MesWorkOrder.flex_form["demo"].as_boolean() == True)  # noqa: E712
            .limit(1)
        )
    ).first()
    if existing is not None:
        return
    item = await first_active_item(session)
    if item is None:
        return
    work_order = MesWorkOrder(
        org_id=ctx.root_org_id,
        work_order_no="MO-DEMO-0001",
        product_item_id=item.id,
        product_item_no_snapshot=item.item_no,
        product_item_name_snapshot=item.item_name,
        unit_code=item.unit_code,
        planned_quantity=Decimal("10"),
        priority_code="normal",
        status_code="released",
        created_by=ctx.admin_user_id,
        updated_by=ctx.admin_user_id,
        flex_form={"demo": True, "remark": DEMO_REMARK},
    )
    session.add(work_order)
    await session.flush()
    session.add(
        MesWorkOrderOperation(
            org_id=ctx.root_org_id,
            work_order_id=work_order.id,
            operation_no="OP-010",
            operation_name_snapshot="装配报工演示",
            operation_description="手机端 Track-in、现场报工和 Track-out 演示任务",
            sequence_no=10,
            work_center_name_snapshot="演示装配车间",
            workstation_name_snapshot="演示工位 A",
            assigned_user_id=ctx.admin_user_id,
            planned_quantity=Decimal("10"),
            status_code="dispatched",
            priority_code="normal",
            created_by=ctx.admin_user_id,
            updated_by=ctx.admin_user_id,
        )
    )
