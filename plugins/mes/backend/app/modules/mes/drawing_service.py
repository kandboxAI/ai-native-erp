"""货品图纸版本：父工单锁内保存完整修订，旧文件永久保留绑定。"""
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.file.service import file_item, service as files
from app.modules.user_profile.public import user_display_names

from .drawing_files import DRAWING_SCENE, DRAWING_TYPE, append_revision, validate_product_files
from .drawing_repository import drawing_repository as revisions
from .repository import repository


async def current_files(session, order):
    latest = await revisions.latest(session, order)
    rows = await files.list_for_business(session, DRAWING_TYPE, [order.id], scene_code=DRAWING_SCENE)
    if latest is None:
        return None, rows
    links = await revisions.links(session, order, [latest.id])
    by_id = {row.id: row for row in rows}
    return latest, [by_id[link.attachment_id] for link in links if link.attachment_id in by_id]


class DrawingService:
    async def drawings(self, order_id, user):
        async with get_session_context() as session:
            order = await repository.get_work_order(session, order_id, user)
            if order is None:
                raise AppException("工单不存在或无权查看", 404)
            latest, rows = await current_files(session, order)
            return dict(version_no=order.version_no, revision_label=order.drawing_revision_label,
                revision_no=latest.revision_no if latest else 0, is_legacy=latest is None and bool(rows),
                editable=order.status_code in {"draft", "released"} and not await repository.history_exists(session, order.id),
                items=[file_item(row) for row in rows])

    async def save(self, order_id, body, user):
        from .order_service import touch
        async with get_session_context() as session:
            order = await repository.get_work_order(session, order_id, user, permission="mes:work_order:manage", for_update=True)
            if order is None:
                raise AppException("工单不存在或无权修改", 404)
            if order.version_no != body.version_no:
                raise AppException("工单已更新，请刷新后重试", 409)
            if order.status_code not in {"draft", "released"} or await repository.history_exists(session, order.id):
                raise AppException("工单已执行或已结束，图纸已冻结", 409)
            latest, current = await current_files(session, order)
            current_ids = {row.id for row in current}
            label = (order.drawing_revision_label or "").strip() or None
            if set(body.attachment_ids) == current_ids and body.revision_label == label:
                raise AppException("文件和图纸版次没有变化，无需保存新版本", 422)
            by_id = {row.id: row for row in current}
            new_ids = [identifier for identifier in body.attachment_ids if identifier not in current_ids]
            new_files = await files.bind(session, new_ids, user=user, org_id=order.org_id,
                scene_code=DRAWING_SCENE, business_type_code=DRAWING_TYPE, business_id=order.id)
            by_id.update({row.id: row for row in new_files})
            desired = [by_id[identifier] for identifier in body.attachment_ids]
            validate_product_files(desired)
            number = latest.revision_no if latest else 0
            if latest is None and current:
                # Preserve all existing attachments before enforcing the two-slot contract.
                await append_revision(session, order, [row.id for row in current], 1, label,
                    "启用版本管理时归档原有附件；记录时间及人员为归档信息", user)
                number = 1
            number += 1
            await append_revision(session, order, body.attachment_ids, number, body.revision_label, body.change_note, user)
            order.drawing_revision_label = body.revision_label
            repository.add(session, touch(order, user, "drawing_updated", previous=order.status_code,
                note=f"图纸修订V{number}；{body.change_note}"))
            await session.commit()
            return dict(id=str(order.id), version_no=order.version_no, revision_no=number)

    async def history(self, order_id, query, user):
        async with get_session_context() as session:
            order = await repository.get_work_order(session, order_id, user)
            if order is None:
                raise AppException("工单不存在或无权查看", 404)
            rows, total = await revisions.history(session, order, query)
            links = await revisions.links(session, order, [row.id for row in rows])
            attached = await files.list_for_business(session, DRAWING_TYPE, [order.id], scene_code=DRAWING_SCENE) if rows else []
            by_id = {row.id: row for row in attached}
            names = await user_display_names(session, {row.created_by for row in rows if row.created_by}) if rows else {}
            items = [dict(id=str(row.id), revision_no=row.revision_no, revision_label=row.revision_label,
                change_note=row.change_note, created_at=row.created_at.isoformat(), created_by_name=names.get(row.created_by, "系统"),
                items=[file_item(by_id[link.attachment_id]) for link in links
                    if link.revision_id == row.id and link.attachment_id in by_id]) for row in rows]
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)


drawing_service = DrawingService()
