from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.inventory.common import qty
from app.modules.inventory.constants import (
    ORDER_CONFIRMED,
    STOCK_AVAILABLE,
)
from app.modules.inventory.item_policy import GENERAL_WAREHOUSE_SCOPE, restricted_item_ids
from app.modules.inventory.models import InvStockOrder, InvStockOrderLine
from app.modules.inventory.stock_order.posting import post_order
from app.modules.inventory.stock_order.tracking import register_tracking_source
from app.modules.inventory.stock_order.repository import repository as stock_order_repository
from app.modules.inventory.warning.notifier import notify_stock_alerts
from app.modules.inventory.warehouse.deletion import register_warehouse_delete_validator
from app.modules.inventory.warehouse.service import warehouse_service
from app.modules.inventory.warehouse.schemas import RequisitionApprovalContext
from app.modules.notification_center.service import notify
from app.modules.file.service import register_file_access, register_file_scene, service as file_service

from .models import InvMaterialRequisition, InvMaterialRequisitionEvent, InvMaterialRequisitionLine, InvMaterialRequisitionReceiptLine
from .repository import repository
from .schemas import (
    RequisitionCreate,
    RequisitionDecision,
    RequisitionEventItem,
    RequisitionItem,
    RequisitionListQuery,
    RequisitionReject,
    RequisitionVersion,
    RequisitionEvidence,
    RequisitionIssue,
    RequisitionReceipt,
)

PERM_CREATE = "inventory_requisition:create"
PERM_LIST = "inventory_requisition:list"
PERM_DETAIL = "inventory_requisition:detail"
PERM_APPROVE = "inventory_requisition:approve"
PERM_ISSUE = "inventory_requisition:issue"
PERM_APPLY_CANTEEN = "inventory_requisition:apply_canteen"

logger = logging.getLogger(__name__)
FILE_BUSINESS_TYPE = "inv_material_requisition_event"
for _scene in ("requisition_apply", "requisition_issue", "requisition_receive", "requisition_exception", "requisition_resolve"):
    register_file_scene(_scene, kinds={"image"}, max_bytes=2 * 1024 * 1024, max_count=6)


class RequisitionService:
    async def _sync_todos(self, session, row, user):
        from .todo_types import sync_todos
        await sync_todos(session, row, user)

    async def _bind_photos(self, session, event, file_ids, user, scene_code):
        if file_ids:
            await file_service.bind(session, file_ids, user=user, org_id=event.org_id,
                                    scene_code=scene_code, business_type_code=FILE_BUSINESS_TYPE, business_id=event.id)

    @staticmethod
    def _name(user: AuthenticatedUser) -> str:
        return (user.display_name or user.email or str(user.user_id)).strip()

    @staticmethod
    def _request_no() -> str:
        now = local_now()
        return f"LY{now:%Y%m%d%H%M%S}{uuid7().hex[-6:].upper()}"

    @staticmethod
    def _require_org(user: AuthenticatedUser) -> UUID:
        if user.org_id is None:
            raise AppException("当前账号未关联组织，不能办理物资领用", status_code=status.HTTP_400_BAD_REQUEST)
        return user.org_id

    @staticmethod
    def _check_version(row: InvMaterialRequisition, version_no: int) -> None:
        if row.version_no != version_no:
            raise AppException("申请已被其他人处理，请刷新后重试", status_code=status.HTTP_409_CONFLICT)

    @staticmethod
    def _warehouse_permission(user: AuthenticatedUser) -> str:
        for permission in (PERM_CREATE, PERM_LIST, PERM_APPROVE, PERM_ISSUE):
            if permission in user.permissions:
                return permission
        raise AppException("无权查询领用仓库", status_code=status.HTTP_403_FORBIDDEN)

    async def warehouse_options(self, user: AuthenticatedUser, *, mine: bool = True) -> list[dict]:
        self._require_org(user)
        if not mine and PERM_LIST not in user.permissions:
            raise AppException("无权查询领用审批仓库", status_code=403)
        async with get_session_context() as session:
            warehouses = await repository.accessible_warehouses(session, user, self._warehouse_permission(user) if mine else PERM_LIST)
            contexts = await warehouse_service.requisition_approval_contexts(session, warehouses.values())
        return [
            {"id": str(row.id), "warehouse_no": row.warehouse_no, "warehouse_name": row.warehouse_name, **contexts[row.id]}
            for row in warehouses.values()
        ]

    def _event(
        self,
        row: InvMaterialRequisition,
        user: AuthenticatedUser,
        event_type: str,
        from_status: str | None,
        to_status: str,
        note: str | None = None,
    ) -> InvMaterialRequisitionEvent:
        return InvMaterialRequisitionEvent(
            org_id=row.org_id,
            requisition_id=row.id,
            event_type_code=event_type,
            from_status_code=from_status,
            to_status_code=to_status,
            note=note,
            operator_user_id=user.user_id,
            operator_name_snapshot=self._name(user),
            created_by=user.user_id,
        )

    async def _notify_transition(
        self,
        session: AsyncSession,
        row: InvMaterialRequisition,
        user: AuthenticatedUser,
        *,
        scene_key: str,
        event_suffix: str,
        title: str,
        content: str,
        recipients: list[UUID] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """发送申领状态通知；通知失败不影响申领主事务。"""
        try:
            async with session.begin_nested():
                result = await notify(
                    session,
                    scene_key=scene_key,
                    recipients=recipients,
                    business_type_code="inventory_requisition",
                    business_id=row.id,
                    payload={
                        "title": title,
                        "content": content,
                        "request_no": row.request_no,
                        **(payload or {}),
                    },
                    org_id=row.org_id,
                    event_key=f"inventory_requisition:{row.id}:{row.version_no}:{event_suffix}",
                    redirect_url=f"/pages/material-detail/index?id={row.id}",
                    source_module_code="inventory",
                    created_by=user.user_id,
                )
            if result.skipped_reason:
                logger.info(
                    "inventory requisition notification skipped request_id=%s scene=%s reason=%s",
                    row.id,
                    scene_key,
                    result.skipped_reason,
                )
        except Exception:
            logger.warning(
                "inventory requisition notification failed request_id=%s scene=%s",
                row.id,
                scene_key,
                exc_info=True,
            )

    async def _serialize(self, session: AsyncSession, row: InvMaterialRequisition) -> dict:
        from app.modules.asset_management.stock_service import stock_service
        data = RequisitionItem.model_validate(row).model_dump(mode="json")
        data["personal_custody_assets"] = await stock_service.issued_personal_assets_in_session(session, row.stock_order_id, row.id)
        lines = await repository.lines(session, row.id)
        unit_names = await repository.unit_names(session, {line.unit_code_snapshot for line in lines})
        data["lines"] = [
            {
                "id": str(line.id),
                "item_id": str(line.item_id),
                "item_no_snapshot": line.item_no_snapshot,
                "item_name_snapshot": line.item_name_snapshot,
                "specification_snapshot": line.specification_snapshot,
                "unit_code_snapshot": line.unit_code_snapshot,
                "unit_name": unit_names.get(line.unit_code_snapshot, line.unit_code_snapshot),
                "quantity": str(line.quantity),
                "issued_quantity": str(line.issued_quantity) if line.issued_quantity is not None else None,
            }
            for line in lines
        ]
        data["events"] = [
            RequisitionEventItem.model_validate(event).model_dump(mode="json")
            for event in await repository.events(session, row.id)
        ]
        event_ids = [UUID(event["id"]) for event in data["events"]]
        if event_ids:
            photos = await file_service.items_for_business(session, FILE_BUSINESS_TYPE, event_ids)
            receipt_lines = await repository.receipt_lines(session, event_ids)
            for event in data["events"]:
                event_id = UUID(event["id"])
                event["photos"] = photos.get(event_id, [])
                event["receipt_lines"] = [{
                    "line_id": str(line.requisition_line_id),
                    "received_quantity": str(line.received_quantity),
                    "exception_quantity": str(line.exception_quantity),
                    "exception_type_code": line.exception_type_code,
                } for line in receipt_lines if line.event_id == event_id]
        data["stock_order_no"] = await repository.stock_order_no(session, row.stock_order_id)
        warehouse = await repository.warehouse(session, row.warehouse_id)
        data["warehouse_no"] = warehouse.warehouse_no if warehouse else None
        data["warehouse_name"] = warehouse.warehouse_name if warehouse else None
        data.update((await warehouse_service.requisition_approval_contexts(session, [warehouse]))[warehouse.id]
                    if warehouse else RequisitionApprovalContext().model_dump(mode="json"))
        return data

    async def _visible(
        self,
        session: AsyncSession,
        row: InvMaterialRequisition,
        user: AuthenticatedUser,
        *,
        permission: str | None = None,
        allow_owner: bool = True,
    ) -> None:
        if allow_owner and row.applicant_user_id == user.user_id and PERM_CREATE in user.permissions:
            return
        candidates = [permission] if permission else [PERM_DETAIL, PERM_LIST, PERM_APPROVE, PERM_ISSUE]
        for key in candidates:
            if key is None or key not in user.permissions:
                continue
            if await repository.is_visible(session, row, user, key):
                return
        raise AppException("物资领用申请不存在或无权查看", status_code=status.HTTP_404_NOT_FOUND)

    async def material_options(
        self,
        keyword: str | None,
        warehouse_id: UUID | None,
        user: AuthenticatedUser,
    ) -> list[dict]:
        self._require_org(user)
        async with get_session_context() as session:
            warehouses = await repository.accessible_warehouses(session, user, self._warehouse_permission(user))
            if warehouse_id is not None and warehouse_id not in warehouses:
                raise AppException("申请仓库不存在或无权使用", status_code=status.HTTP_403_FORBIDDEN)
            warehouse_ids = {warehouse_id} if warehouse_id is not None else set(warehouses)
            rows = await repository.material_options(session, warehouse_ids, keyword)
            if PERM_APPLY_CANTEEN not in user.permissions and not any(
                key in user.permissions for key in (PERM_LIST, PERM_APPROVE, PERM_ISSUE)
            ):
                food_ids = await restricted_item_ids(session, GENERAL_WAREHOUSE_SCOPE, {row["id"] for row in rows})
                rows = [row for row in rows if row["id"] not in food_ids]
            unit_names = await repository.unit_names(session, {row["unit_code"] for row in rows})
        return [
            {
                **row,
                "id": str(row["id"]),
                "warehouse_id": str(row["warehouse_id"]),
                "unit_name": unit_names.get(row["unit_code"], row["unit_code"]),
                "available_quantity": str(row["available_quantity"]),
            }
            for row in rows
        ]

    async def create(self, payload: RequisitionCreate, user: AuthenticatedUser) -> dict:
        self._require_org(user)
        if payload.photo_file_ids and len({line.warehouse_id for line in payload.lines}) != 1:
            raise AppException("带照片的申请请按仓库分别提交", status_code=422)
        async with get_session_context() as session:
            items = await repository.items(session, {line.item_id for line in payload.lines})
            if len(items) != len({line.item_id for line in payload.lines}):
                raise AppException("申请中包含不存在或已停用的物资", status_code=status.HTTP_400_BAD_REQUEST)
            warehouses = await repository.accessible_warehouses(session, user, PERM_CREATE, lock=True)
            selected_warehouse_ids = {line.warehouse_id for line in payload.lines}
            if not selected_warehouse_ids.issubset(warehouses):
                raise AppException("申请中包含无权使用或不存在的仓库", status_code=status.HTTP_403_FORBIDDEN)
            if PERM_APPLY_CANTEEN not in user.permissions:
                food_ids = await restricted_item_ids(session, GENERAL_WAREHOUSE_SCOPE, set(items))
                if food_ids:
                    raise AppException("当前账号无权申请食堂食材", status_code=status.HTTP_403_FORBIDDEN)
            keys = {(line.item_id, line.warehouse_id) for line in payload.lines}
            available = await repository.available_by_item_warehouse(session, keys)
            for line in payload.lines:
                requested = qty(line.quantity)
                if requested <= 0:
                    raise AppException("领用数量必须大于 0", status_code=status.HTTP_400_BAD_REQUEST)
                if (line.item_id, line.warehouse_id) not in available:
                    raise AppException(
                        f"{items[line.item_id].item_name}不属于所选仓库，请重新选择物资",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            grouped: dict[UUID, list] = defaultdict(list)
            for line in payload.lines:
                grouped[line.warehouse_id].append(line)
            batch_no = self._request_no()
            department_name = await repository.department_name(session, user.department_id)
            applicant_org_name = await repository.organization_name(session, user.org_id)
            requests: list[InvMaterialRequisition] = []
            for sequence, (warehouse_id, sources) in enumerate(grouped.items(), start=1):
                warehouse_org_id = warehouses[warehouse_id].org_id
                row = InvMaterialRequisition(
                    org_id=warehouse_org_id,
                    request_no=f"{batch_no}-{sequence:02d}",
                    submission_batch_no=batch_no,
                    warehouse_id=warehouse_id,
                    applicant_user_id=user.user_id,
                    applicant_name_snapshot=self._name(user),
                    applicant_org_id=user.org_id,
                    applicant_org_name_snapshot=applicant_org_name,
                    department_id=user.department_id,
                    department_name_snapshot=department_name,
                    purpose=payload.purpose.strip(),
                    custody_location_note=(payload.custody_location_note or "").strip() or None,
                    status_code="submitted",
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
                lines = []
                for index, source in enumerate(sources, start=1):
                    item = items[source.item_id]
                    lines.append(
                        InvMaterialRequisitionLine(
                            org_id=warehouse_org_id,
                            requisition_id=row.id,
                            line_no=index,
                            item_id=item.id,
                            item_no_snapshot=item.item_no,
                            item_name_snapshot=item.item_name,
                            specification_snapshot=item.specification,
                            unit_code_snapshot=item.unit_code,
                            quantity=qty(source.quantity),
                            created_by=user.user_id,
                        )
                    )
                event = self._event(row, user, "submit", None, "submitted", payload.purpose.strip())
                await repository.add(
                    session,
                    row,
                    lines,
                    event,
                )
                await self._bind_photos(session, event, payload.photo_file_ids, user, "requisition_apply")
                warehouse = warehouses[warehouse_id]
                warehouse_name = getattr(warehouse, "warehouse_name", None) or warehouse.warehouse_no
                department_label = department_name or "未关联部门"
                await self._notify_transition(
                    session,
                    row,
                    user,
                    scene_key="inventory.requisition_submitted",
                    event_suffix="submitted",
                    title=f"新物资申领：{row.request_no}",
                    content=(
                        f"{row.applicant_name_snapshot}（{department_label}）提交了"
                        f"{warehouse_name}物资申领，请及时审批。"
                    ),
                    payload={
                        "applicant_name": row.applicant_name_snapshot,
                        "department_name": department_label,
                        "warehouse_name": warehouse_name,
                    },
                )
                requests.append(row)
            for request in requests:
                await self._sync_todos(session, request, user)
            await session.commit()
            return {
                "submission_batch_no": batch_no,
                "requests": [await self._serialize(session, row) for row in requests],
            }

    async def list(self, query: RequisitionListQuery, user: AuthenticatedUser, *, mine: bool) -> dict:
        async with get_session_context() as session:
            total, rows = await repository.list_requests(session, query, user, mine=mine)
            items = [await self._serialize(session, row) for row in rows]
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def detail(self, request_id: UUID, user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await repository.get(session, request_id)
            if row is None:
                raise AppException("物资领用申请不存在", status_code=status.HTTP_404_NOT_FOUND)
            await self._visible(session, row, user)
            data = await self._serialize(session, row)
            from .detail_extension import detail_fields
            data["extension_fields"] = await detail_fields(session, row, user)
            data["can_receive"] = row.applicant_user_id == user.user_id and PERM_CREATE in user.permissions and row.status_code in {"issued", "pending_receipt"}
            data["can_withdraw"] = row.applicant_user_id == user.user_id and PERM_CREATE in user.permissions and row.status_code == "submitted"
            data["can_issue"] = (row.status_code == "approved" and PERM_ISSUE in user.permissions
                                 and await repository.is_visible(session, row, user, PERM_ISSUE))
            if data["can_issue"]:
                from app.modules.asset_management.stock_service import stock_service
                items = await repository.items(session, {UUID(line["item_id"]) for line in data["lines"]})
                required = await stock_service.selection_required_item_ids_in_session(session, items.values())
                for line in data["lines"]:
                    line["requires_asset_selection"] = UUID(line["item_id"]) in required
            return data

    async def approve(self, request_id: UUID, payload: RequisitionDecision, user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None:
                raise AppException("物资领用申请不存在", status_code=status.HTTP_404_NOT_FOUND)
            await self._visible(session, row, user, permission=PERM_APPROVE, allow_owner=False)
            self._check_version(row, payload.version_no)
            if row.status_code != "submitted":
                raise AppException("只有待审批申请可以通过", status_code=status.HTTP_409_CONFLICT)
            now = utc_now()
            row.status_code = "approved"
            row.approval_note = (payload.note or "同意领用").strip()
            row.approved_by = user.user_id
            row.approved_by_name_snapshot = self._name(user)
            row.approved_at = now
            row.updated_by = user.user_id
            row.updated_at = now
            row.version_no += 1
            session.add(row)
            session.add(self._event(row, user, "approve", "submitted", "approved", row.approval_note))
            await self._notify_transition(
                session,
                row,
                user,
                scene_key="inventory.requisition_approved",
                event_suffix="approved",
                title=f"物资申领待发放：{row.request_no}",
                content=f"{self._name(user)}已审批通过申请 {row.request_no}，请及时发放物资。",
            )
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)

    async def reject(self, request_id: UUID, payload: RequisitionReject, user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None:
                raise AppException("物资领用申请不存在", status_code=status.HTTP_404_NOT_FOUND)
            await self._visible(session, row, user, permission=PERM_APPROVE, allow_owner=False)
            self._check_version(row, payload.version_no)
            if row.status_code != "submitted":
                raise AppException("只有待审批申请可以驳回", status_code=status.HTTP_409_CONFLICT)
            now = utc_now()
            row.status_code = "rejected"
            row.approval_note = payload.note.strip()
            row.rejected_by = user.user_id
            row.rejected_by_name_snapshot = self._name(user)
            row.rejected_at = now
            row.updated_by = user.user_id
            row.updated_at = now
            row.version_no += 1
            session.add(row)
            session.add(self._event(row, user, "reject", "submitted", "rejected", row.approval_note))
            await self._notify_transition(
                session,
                row,
                user,
                scene_key="inventory.requisition_rejected",
                event_suffix="rejected",
                title=f"物资申领已驳回：{row.request_no}",
                content=f"申请 {row.request_no} 已被驳回：{row.approval_note}",
                recipients=[row.applicant_user_id],
            )
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)

    async def withdraw(self, request_id: UUID, payload: RequisitionVersion, user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None or row.applicant_user_id != user.user_id:
                raise AppException("物资领用申请不存在", status_code=status.HTTP_404_NOT_FOUND)
            self._check_version(row, payload.version_no)
            if row.status_code != "submitted":
                raise AppException("只有待审批申请可以撤回", status_code=status.HTTP_409_CONFLICT)
            now = utc_now()
            row.status_code = "withdrawn"
            row.withdrawn_at = now
            row.updated_by = user.user_id
            row.updated_at = now
            row.version_no += 1
            session.add(row)
            session.add(self._event(row, user, "withdraw", "submitted", "withdrawn", "申请人撤回"))
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)

    async def issue(self, request_id: UUID, payload: RequisitionIssue, user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None:
                raise AppException("物资领用申请不存在", status_code=status.HTTP_404_NOT_FOUND)
            await self._visible(session, row, user, permission=PERM_ISSUE, allow_owner=False)
            self._check_version(row, payload.version_no)
            if row.status_code != "approved":
                raise AppException("只有审批通过的申请可以发放", status_code=status.HTTP_409_CONFLICT)
            order_type = await repository.requisition_type(session)
            if order_type is None:
                raise AppException("领用出库单据类型未初始化", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            request_lines = await repository.lines(session, row.id)
            quantities = {line.id: line.quantity for line in request_lines}
            if payload.lines is not None:
                supplied = {line.line_id: line.quantity for line in payload.lines}
                if len(supplied) != len(payload.lines) or set(supplied) != set(quantities):
                    raise AppException("发放明细必须完整且不能重复或包含其他申请的物资", status_code=422)
                if any(supplied[key] > quantities[key] for key in quantities):
                    raise AppException("发放数量不能超过申请数量", status_code=422)
                quantities = supplied
            for line in request_lines:
                line.issued_quantity = quantities[line.id]
                session.add(line)
            order = InvStockOrder(
                org_id=row.org_id,
                order_no=f"CK-{row.request_no}",
                order_type_id=order_type.id,
                status_code="approved",
                business_date=local_now().date(),
                from_warehouse_id=row.warehouse_id,
                counterparty_party_id=user.party_id if row.applicant_user_id == user.user_id else None,
                counterparty_name_snapshot=row.applicant_name_snapshot,
                department_id=row.department_id,
                purpose=row.purpose,
                source_doc_type_code="inv_requisition",
                source_doc_id=row.id,
                remark=(payload.note or f"由领用申请 {row.request_no} 发放").strip(),
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            stock_lines = [
                InvStockOrderLine(
                    org_id=row.org_id,
                    stock_order_id=order.id,
                    line_no=index,
                    item_id=request_line.item_id,
                    from_warehouse_id=row.warehouse_id,
                    from_stock_status_code=STOCK_AVAILABLE,
                    quantity=qty(quantities[request_line.id]),
                    unit_code=request_line.unit_code_snapshot,
                    remark=f"领用申请 {row.request_no}",
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
                for index, request_line in enumerate(request_lines, start=1)
            ]
            session.add(order)
            row.stock_order_id = order.id
            session.add(row)
            session.add_all(stock_lines)
            await session.flush()
            from app.modules.inventory.stock_order.tracking import save_tracking
            if payload.lines is not None:
                by_id = {line.line_id: line for line in payload.lines}
                await save_tracking(session, order, stock_lines, [by_id[line.id] for line in request_lines], user)
            posting_result = await post_order(session, order, order_type, stock_lines, user.user_id, current_user=user)
            if posting_result["alerts"]:
                await notify_stock_alerts(
                    session,
                    alerts=posting_result["alerts"],
                    stock_order_id=order.id,
                    operator_user_id=user.user_id,
                    org_names=await stock_order_repository.org_names(
                        session,
                        {UUID(alert["org_id"]) for alert in posting_result["alerts"]},
                    ),
                    warehouse_names=await stock_order_repository.warehouse_names(
                        session,
                        {UUID(alert["warehouse_id"]) for alert in posting_result["alerts"]},
                    ),
                    unit_names=await stock_order_repository.unit_names(session),
                )
            now = utc_now()
            order.status_code = ORDER_CONFIRMED
            order.confirmed_at = now
            order.confirmed_by = user.user_id
            order.updated_at = now
            row.status_code = "pending_receipt"
            row.issued_by = user.user_id
            row.issued_by_name_snapshot = self._name(user)
            row.issued_at = now
            row.stock_order_id = order.id
            row.updated_by = user.user_id
            row.updated_at = now
            row.version_no += 1
            session.add(order)
            session.add(row)
            event = self._event(row, user, "issue", "approved", "pending_receipt", payload.note or "物资已发放，等待申请人签收")
            session.add(event)
            await session.flush()
            await self._bind_photos(session, event, payload.photo_file_ids, user, "requisition_issue")
            await self._notify_transition(
                session,
                row,
                user,
                scene_key="inventory.requisition_issued",
                event_suffix="issued",
                title=f"物资申领已发放：{row.request_no}",
                content=f"申请 {row.request_no} 的物资已经发放，请领取后核对数量、规格和完好情况并确认收货；有问题请反馈收货异常。",
                recipients=[row.applicant_user_id],
            )
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)


    async def receive(self, request_id: UUID, payload: RequisitionReceipt, user: AuthenticatedUser, *, exception: bool = False) -> dict:
        """申请人核对交接；不修改库存，异常明细和照片随本次事件只追加。"""
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None or row.applicant_user_id != user.user_id or PERM_CREATE not in user.permissions:
                raise AppException("仅申请人可以确认收货或反馈异常", status_code=403)
            self._check_version(row, payload.version_no)
            if row.status_code not in {"issued", "pending_receipt"}:
                raise AppException("只有已发放待签收的申请可以核对收货", status_code=409)
            lines = await repository.lines(session, row.id)
            by_id = {line.id: line for line in lines}
            supplied = {line.line_id: line for line in payload.lines}
            if len(supplied) != len(payload.lines) or set(supplied) != set(by_id):
                raise AppException("请完整核对本申请的全部明细，不能重复或混入其他申请的物资", status_code=422)
            has_exception = False
            needs_photo = False
            for line_id, check in supplied.items():
                original = by_id[line_id]
                issued = original.issued_quantity if original.issued_quantity is not None else original.quantity
                if check.received_quantity > issued:
                    raise AppException("实际收到数量不能超过发放数量，超发请联系发放人员核实", status_code=422)
                kind = check.exception_type_code
                if kind is None:
                    if check.received_quantity != issued or check.exception_quantity != 0:
                        raise AppException("数量不符时请选择异常类型并填写问题数量", status_code=422)
                    continue
                has_exception = True
                if check.exception_quantity <= 0:
                    raise AppException("异常物资的问题数量必须大于零", status_code=422)
                if kind in {"shortage", "not_received"}:
                    if check.exception_quantity != issued - check.received_quantity or (kind == "not_received" and check.received_quantity != 0):
                        raise AppException("少发或未收到的问题数量必须与实际缺少数量一致", status_code=422)
                else:
                    if check.exception_quantity > check.received_quantity:
                        raise AppException("破损或错发的问题数量不能超过实际收到数量；同时少发请在说明中补充", status_code=422)
                    needs_photo = True
            if exception != has_exception:
                raise AppException("请通过收货异常反馈问题；正常签收须确认全部物资数量和完好情况", status_code=422)
            if exception and not (payload.note or "").strip():
                raise AppException("请填写收货异常说明", status_code=422)
            if needs_photo and not payload.photo_file_ids:
                raise AppException("破损或错发请至少上传一张问题照片", status_code=422)
            from_status = row.status_code
            row.status_code = "receipt_exception" if exception else "received"
            now = utc_now()
            if not exception:
                row.received_by = user.user_id
                row.received_by_name_snapshot = self._name(user)
                row.received_at = now
            row.updated_by = user.user_id
            row.updated_at = now
            row.version_no += 1
            event = self._event(row, user, "receipt_exception" if exception else "receive", from_status, row.status_code,
                                (payload.note or "数量、规格及完好情况已核对，确认收货").strip())
            session.add(row)
            session.add(event)
            await session.flush()
            for check in payload.lines:
                session.add(InvMaterialRequisitionReceiptLine(
                    org_id=row.org_id, event_id=event.id, requisition_line_id=check.line_id,
                    received_quantity=check.received_quantity, exception_quantity=check.exception_quantity,
                    exception_type_code=check.exception_type_code, created_by=user.user_id,
                ))
            await self._bind_photos(session, event, payload.photo_file_ids, user,
                                    "requisition_exception" if exception else "requisition_receive")
            await self._notify_transition(session, row, user,
                scene_key="inventory.requisition_receipt_exception" if exception else "inventory.requisition_received",
                event_suffix=event.event_type_code,
                title=f"物资申领{'收货异常' if exception else '已签收'}：{row.request_no}",
                content=f"申请 {row.request_no} {'存在收货异常，请核实处理' if exception else '已由申请人确认收货'}。",
            )
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)

    async def resolve_exception(self, request_id: UUID, payload: RequisitionEvidence, user: AuthenticatedUser) -> dict:
        if not (payload.note or "").strip():
            raise AppException("请记录核实结果、处理方式及相关补发或退库单号", status_code=422)
        async with get_session_context() as session:
            row = await repository.get(session, request_id, for_update=True)
            if row is None:
                raise AppException("物资领用申请不存在", status_code=404)
            await self._visible(session, row, user, permission=PERM_ISSUE, allow_owner=False)
            self._check_version(row, payload.version_no)
            if row.status_code != "receipt_exception":
                raise AppException("只有收货异常申请可以登记处理结果", status_code=409)
            row.status_code = "pending_receipt"
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            row.version_no += 1
            event = self._event(row, user, "resolve_exception", "receipt_exception", "pending_receipt", payload.note.strip())
            session.add(row)
            session.add(event)
            await session.flush()
            await self._bind_photos(session, event, payload.photo_file_ids, user, "requisition_resolve")
            await self._notify_transition(session, row, user,
                scene_key="inventory.requisition_receipt_resolved", event_suffix="resolved",
                title=f"物资收货异常已处理：{row.request_no}",
                content=f"申请 {row.request_no} 的收货异常已登记处理结果，请核对后确认收货；仍有问题可再次反馈。",
                recipients=[row.applicant_user_id],
            )
            await self._sync_todos(session, row, user)
            await session.commit()
            return await self._serialize(session, row)


service = RequisitionService()


async def _personal_custody_context(session, order, user):
    """只认可申领发放事务建立的出库单绑定，不能靠客户端来源字段冒用。"""
    row = await repository.get(session, order.source_doc_id, for_update=True)
    if (row is None or row.status_code != "approved" or row.stock_order_id != order.id
        or row.org_id != order.org_id or row.warehouse_id != order.from_warehouse_id):
        raise AppException("申领出库来源不一致，请从物资申领办理发放", status_code=409)
    await service._visible(session, row, user, permission=PERM_ISSUE, allow_owner=False)
    recipient = await repository.personal_custody_recipient(session, row)
    if recipient is None:
        raise AppException("申领人、部门或仓库申领范围已失效，请核对后重新办理", status_code=409)
    return {"asset": recipient}


register_tracking_source("inv_requisition", _personal_custody_context)


async def _can_read_requisition_files(session, user, event_id):
    event = await repository.event(session, event_id)
    if event is None:
        return False
    row = await repository.get(session, event.requisition_id)
    if row is None:
        return False
    try:
        await service._visible(session, row, user)
        return True
    except AppException:
        return False


register_file_access(FILE_BUSINESS_TYPE, _can_read_requisition_files)


async def _validate_warehouse_delete(session, warehouse) -> None:
    if await repository.has_open_warehouse_requests(session, warehouse.id):
        raise AppException("仓库存在待审批或待发放的领用申请，请先处理后再删除", status_code=status.HTTP_409_CONFLICT)


register_warehouse_delete_validator(_validate_warehouse_delete)
