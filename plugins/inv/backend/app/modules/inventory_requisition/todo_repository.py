"""申领待办的范围与来源状态，办理仍使用原申领服务。"""
from sqlalchemy import false, or_
from sqlmodel import select

from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.modules.todo.lifecycle_service import pending_source_ids
from .catalog import PERM_APPROVE, PERM_CREATE
from .models import InvMaterialRequisition as Request

APPROVAL = "inventory_requisition.approval"
RECEIPT = "inventory_requisition.receipt"
TYPES = (APPROVAL, RECEIPT)


def visible_query(type_key, user):
    stmt = select(Request)
    permission = PERM_APPROVE if type_key == APPROVAL else PERM_CREATE
    if permission not in user.permissions:
        return stmt.where(false())
    if type_key == RECEIPT:
        # 与收货接口一致：原申请人按本人关系签收，共享仓库所属组织不替代本人关系。
        return stmt.where(Request.status_code == "pending_receipt", Request.applicant_user_id == user.user_id)
    try:
        return stmt.where(Request.status_code == "submitted", *scoped_conditions(Request, user, permission))
    except AppException as error:
        if error.status_code != 403:
            raise
        return stmt.where(false())


def source_ids(type_key, user):
    return visible_query(type_key, user).with_only_columns(Request.id)


async def visible(session, type_key, user, source_id, org_id):
    return (await session.exec(visible_query(type_key, user).where(Request.id == source_id, Request.org_id == org_id))).first()


async def sync_page(session, cursor, size=100):
    stmt = select(Request).where(or_(
        Request.status_code.in_(("submitted", "pending_receipt")), Request.id.in_(pending_source_ids(TYPES)),
    ))
    if cursor is not None:
        stmt = stmt.where(Request.id > cursor)
    return (await session.exec(stmt.order_by(Request.id).limit(size).with_for_update(skip_locked=True))).all()
