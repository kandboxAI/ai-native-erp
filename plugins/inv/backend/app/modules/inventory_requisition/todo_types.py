"""物资申领审批、本人签收接入账号待办。"""
from functools import partial

from app.core.exceptions import AppException
from app.modules.todo import lifecycle_service as lifecycle
from app.modules.todo.registry import TodoType
from app.modules.todo.targets import authorized_web_target
from . import todo_repository as repository
from .models import InvMaterialRequisition


async def sources(type_key, session, user):
    if not await lifecycle.tables_available(session, InvMaterialRequisition.__tablename__):
        return lifecycle.empty_sources()
    return repository.source_ids(type_key, user)


async def present(type_key, session, todo, user):
    if not await lifecycle.tables_available(session, InvMaterialRequisition.__tablename__):
        return None
    row = await repository.visible(session, type_key, user, todo.source_id, todo.org_id)
    if row is None:
        return None
    summary = f"申请单号：{row.request_no}；请{'审批物资申领' if type_key == repository.APPROVAL else '核对数量、规格和完好情况后签收，发现问题请反馈异常'}。"
    web = await authorized_web_target(session, user, type_key, row.id)
    targets = {"miniapp": f"/pages/material-detail/index?id={row.id}"}
    if web:
        targets["web"] = web
    return {"summary": f"申领人：{row.applicant_name_snapshot}。{summary}", "priority_summary": summary,
            "open_miniapp_directly": True, "targets": targets,
            "web_unavailable_reason": "" if web else "当前账号未获授权的管理端业务入口，请联系管理员核对菜单及权限，或从小程序办理。"}


async def execute(*_):
    raise AppException("请进入物资申领详情办理", 409)


TODO_TYPES = [TodoType(key, label, partial(present, key), execute, partial(sources, key)) for key, label in (
    (repository.APPROVAL, "物资申领待审批"), (repository.RECEIPT, "物资申领待签收"),
)]


async def sync_todos(session, row, user=None):
    """调用方持有申请行锁；创建新申请时持有尚未提交的新行。"""
    await session.flush()
    for type_key, label, states, completed in (
        (repository.APPROVAL, "物资申领待审批", {"submitted"}, {"approved", "rejected", "issued", "pending_receipt", "received", "receipt_exception"}),
        # 历史 issued 仅表示未记录签收，不能据此推断仍需申请人办理。
        (repository.RECEIPT, "物资申领待签收", {"pending_receipt"}, {"received", "receipt_exception"}),
    ):
        active = row.status_code in states
        recipients = set()
        if active:
            if type_key == repository.RECEIPT:
                # 签收只有单据申请人一个接收对象，审批/发放人不参与签收分配。
                owner = row.applicant_user_id
                candidates = await lifecycle.recipient_contexts(session, {owner})
                candidate = candidates.get(owner)
                if candidate and candidate.user_id == owner and await repository.visible(
                    session, type_key, candidate, row.id, row.org_id,
                ):
                    recipients.add(owner)
            else:
                for candidate in (await lifecycle.recipient_contexts(session)).values():
                    if await repository.visible(session, type_key, candidate, row.id, row.org_id):
                        recipients.add(candidate.user_id)
        await lifecycle.sync_source(session, type_key=type_key, row=row, active=active, user_ids=recipients,
            title=f"{label} · {row.request_no}", summary="请进入申领详情办理。",
            completion_status="completed" if row.status_code in completed else "cancelled",
            actor_id=user.user_id if user else None,
            arrived_at=row.updated_at if type_key == repository.RECEIPT else row.created_at)
