"""资产交接业务：建单、提交、分项接收并更新资产当前责任关系。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.notification_center.service import notify

from .handover_models import AssetHandover, AssetHandoverLine
from .integration import (
    dispatch_handover_completed, validate_handover_receiver,
    handover_source_context, lock_handover_source,
)
from .handover_repository import handover_repository as repo
from .handover_schemas import (
    AssetHandoverCreate,
    AssetHandoverLineCreate,
    AssetHandoverLineResubmit,
    AssetHandoverQuery,
    AssetHandoverUpdate,
)
from .models import AssetLocationItem, AssetRegister
from .repository import repository as asset_repo
from .service import service as asset_service

HANDOVER_ELIGIBLE_ASSET_STATUS_CODES = frozenset({"in_use", "idle"})
HANDOVER_TARGET_ASSET_STATUS_CODES = {
    "return_logistics": "idle",
    "transfer_teacher": "in_use",
}
logger = logging.getLogger(__name__)


class AssetHandoverService:
    async def _lock_source(self, session, handover_id):
        row = await repo.by_id(session, handover_id)
        if row is not None:
            await lock_handover_source(session, row)

    @staticmethod
    def _ensure_manual_lifecycle(row):
        if row.source_id is not None:
            raise AppException("该资产单由来源业务统一提交和撤回，请返回来源单据办理", status_code=409)

    @staticmethod
    def _name(user: AuthenticatedUser) -> str:
        return (user.display_name or user.email or str(user.user_id)).strip()

    @staticmethod
    def _conflict(message: str) -> AppException:
        return AppException(message, status_code=status.HTTP_409_CONFLICT)

    @staticmethod
    def _line_item(
        row: dict[str, Any], user: AuthenticatedUser | None = None
    ) -> dict[str, Any]:
        line: AssetHandoverLine = row["AssetHandoverLine"]
        can_receive = bool(
            user
            and line.status_code == "pending"
            and (
                (
                    line.disposition_code == "transfer_teacher"
                    and line.to_custodian_user_id == user.user_id
                    and bool({"asset_handover:mine", "asset_handover:receive"}.intersection(user.permissions))
                )
                or (
                    line.disposition_code == "return_logistics"
                    and "asset_handover:receive" in user.permissions
                )
            )
        )
        return {
            **line.model_dump(mode="json"),
            "from_location_name": row["from_location_name"] or f"个人保管 · {row['from_custodian_name'] or '未命名账号'}",
            "to_location_name": row["to_location_name"],
            "from_department_name": row["from_department_name"],
            "to_department_name": row["to_department_name"],
            "from_custodian_name": row["from_custodian_name"],
            "to_custodian_name": row["to_custodian_name"],
            "confirmed_by_name": row["confirmed_by_name"],
            "can_receive": can_receive,
        }

    async def _item(
        self,
        session: AsyncSession,
        row: AssetHandover,
        user: AuthenticatedUser | None = None,
        *,
        receiver_user_id: UUID | None = None,
    ) -> dict[str, Any]:
        lines = await repo.lines(session, row.id, receiver_user_id=receiver_user_id)
        return {
            **row.model_dump(mode="json"),
            "lines": [self._line_item(line, user if row.status_code == "awaiting_receipt" else None) for line in lines],
            "line_count": len(lines),
            "received_count": sum(
                1 for line in lines if line["AssetHandoverLine"].status_code == "received"
            ),
            "pending_count": sum(
                1 for line in lines if row.status_code != "voided" and line["AssetHandoverLine"].status_code == "pending"
            ),
            "rejected_count": sum(
                1 for line in lines if row.status_code != "voided" and line["AssetHandoverLine"].status_code == "rejected"
            ),
            "source_context": await handover_source_context(session, row, user),
        }

    async def list(self, query: AssetHandoverQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repo.list(session, query, user)
            items = [await self._item(session, row, user) for row in rows]
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def list_mine(
        self, query: AssetHandoverQuery, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repo.list_mine(session, query, user.user_id)
            items = [
                await self._item(session, row, user, receiver_user_id=user.user_id)
                for row in rows
            ]
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    async def detail(self, handover_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            if "asset_handover:list" in user.permissions:
                row = await repo.get(session, handover_id, user, "asset_handover:list")
            else:
                row = await repo.participant_get(session, handover_id, user.user_id)
                if row is None:
                    candidate = await repo.by_id(session, handover_id)
                    if candidate and await handover_source_context(session, candidate, user):
                        return await self._item(session, candidate, user)
            if row is None:
                raise AppException("资产交接单不存在或无权查看", status_code=404)
            receiver_user_id = None
            if "asset_handover:list" not in user.permissions and row.transferor_user_id != user.user_id:
                receiver_user_id = user.user_id
            return await self._item(
                session,
                row,
                user,
                receiver_user_id=receiver_user_id,
            )

    async def _build_line(
        self,
        session: AsyncSession,
        header: AssetHandover,
        body: AssetHandoverLineCreate,
        user: AuthenticatedUser | None,
        sort_no: int,
        *,
        enforce_scope: bool,
        source_org_ids: set[UUID] | None = None,
        reference_cache: dict | None = None,
    ) -> AssetHandoverLine:
        # 仅内部批量生成共享事务内只读档案缓存，不缓存资产占用或接收状态。
        async def reference(key, lookup):
            if enforce_scope or reference_cache is None:
                return await lookup()
            if key not in reference_cache:
                reference_cache[key] = await lookup()
            return reference_cache[key]

        if body.asset_register_id:
            asset = (
                await asset_repo.get_register(session, body.asset_register_id, user, "asset_handover:create")
                if enforce_scope and user is not None
                else await repo.register(session, body.asset_register_id)
            )
        else:
            asset = (
                await asset_repo.get_location_item(
                    session, body.location_item_id, user, "asset_handover:create"
                )
                if enforce_scope and user is not None
                else await repo.location_item(session, body.location_item_id)
            )
        if asset is None or asset.org_id != header.org_id:
            raise AppException("交接资产不存在、不属于当前组织或无权操作", status_code=400)
        if asset.registration_status_code != "confirmed":
            raise AppException("只有已确认登记的资产才能交接", status_code=409)
        if asset.status_code not in HANDOVER_ELIGIBLE_ASSET_STATUS_CODES:
            raise AppException("只有在用或闲置资产才能交接", status_code=409)
        if header.transferor_user_id and asset.custodian_user_id != header.transferor_user_id:
            raise AppException("交接资产的当前保管人与交出人不一致", status_code=409)
        if isinstance(asset, AssetLocationItem) and body.quantity > Decimal(asset.quantity):
            raise AppException("交接数量不能超过当前数量", status_code=409)
        if await repo.target_has_open_handover(
            session,
            asset_register_id=body.asset_register_id,
            location_item_id=body.location_item_id,
            exclude_handover_id=header.id,
        ):
            raise AppException("该资产已有未完成的交接单", status_code=409)
        location = await reference(("location", body.to_location_id, header.org_id), lambda: asset_repo.location_for_org(session, body.to_location_id, header.org_id, user=user))
        if location is None or not location.is_active:
            raise AppException("目标资产位置不存在、已停用或不属于当前组织", status_code=400)
        body = body.model_copy(update={"to_location_id": location.id})
        if enforce_scope and user is not None:
            department = await asset_repo.department_in_scope(
                session,
                body.to_department_id,
                user,
                "asset_handover:create",
            )
            custodian = (
                await asset_repo.user_in_scope(
                    session,
                    body.to_custodian_user_id,
                    user,
                    "asset_handover:create",
                )
                if body.to_custodian_user_id
                else None
            )
        else:
            if source_org_ids is not None and header.source_type_code == "teacher_offboarding":
                if header.org_id not in source_org_ids:
                    raise AppException("资产所属组织不在来源业务授权范围内", status_code=403)
                department = await reference(("department", body.to_department_id, frozenset(source_org_ids)), lambda: asset_repo.department_for_orgs(session, body.to_department_id, source_org_ids))
            else:
                department = await asset_repo.department_for_org(session, body.to_department_id, header.org_id)
            custodian = (
                await reference(("user", body.to_custodian_user_id, header.org_id), lambda: asset_repo.user_for_org(
                    session,
                    body.to_custodian_user_id,
                    header.org_id,
                ))
                if body.to_custodian_user_id
                else None
            )
        if department is None:
            asset_label = getattr(asset, "asset_no", None) or str(asset.id)
            raise AppException(f"资产 {asset_label} 的目标责任部门不存在、已停用或不在授权组织范围内，请核对台账责任部门及接任教师部门", status_code=400)
        if body.to_custodian_user_id and custodian is None:
            # 来源模块已校验来源范围；教师资格由行业提供器验证学校/校区关系。
            if (not enforce_scope and header.source_type_code == "teacher_offboarding"
                    and body.disposition_code == "transfer_teacher"
                    and await reference(("receiver", body.to_custodian_user_id, header.org_id), lambda: validate_handover_receiver(session, body.to_custodian_user_id, header.org_id))):
                custodian = await reference(("active_user", body.to_custodian_user_id), lambda: repo.active_user(session, body.to_custodian_user_id))
            if custodian is None:
                raise AppException("目标保管人不存在、已停用或无权选择", status_code=400)
        if (
            body.disposition_code == "transfer_teacher"
            and body.to_custodian_user_id is not None
            and not await reference(("receiver", body.to_custodian_user_id, header.org_id), lambda: validate_handover_receiver(
                session, body.to_custodian_user_id, header.org_id
            ))
        ):
            raise AppException("接收人不是当前组织内的有效教师，不能接收教师资产", status_code=400)
        item = await reference(("item", asset.item_id), lambda: repo.item(session, asset.item_id))
        if item is None:
            raise AppException("资产对应物料不存在", status_code=409)
        return AssetHandoverLine(
            org_id=header.org_id,
            handover_id=header.id,
            asset_register_id=asset.id if isinstance(asset, AssetRegister) else None,
            location_item_id=asset.id if isinstance(asset, AssetLocationItem) else None,
            asset_no_snapshot=asset.asset_no if isinstance(asset, AssetRegister) else None,
            asset_name_snapshot=item.item_name,
            specification_snapshot=item.specification,
            quantity=body.quantity,
            unit_code_snapshot=item.unit_code,
            disposition_code=body.disposition_code,
            from_location_id=asset.location_id,
            from_department_id=asset.department_id,
            from_custodian_user_id=asset.custodian_user_id,
            to_location_id=body.to_location_id,
            to_department_id=body.to_department_id,
            to_custodian_user_id=body.to_custodian_user_id,
            status_code="pending",
            sort_no=sort_no,
            created_by=user.user_id if user else None,
            updated_by=user.user_id if user else None,
        )

    async def _replace_lines(
        self,
        session: AsyncSession,
        header: AssetHandover,
        lines: list[AssetHandoverLineCreate],
        user: AuthenticatedUser,
    ) -> None:
        existing = {
            (item["AssetHandoverLine"].asset_register_id, item["AssetHandoverLine"].location_item_id): item["AssetHandoverLine"]
            for item in await repo.lines(session, header.id)
        }
        keys = [(body.asset_register_id, body.location_item_id) for body in lines]
        if len(keys) != len(set(keys)):
            raise AppException("同一资产不能重复添加到交接单", status_code=400)
        if header.source_id is not None and set(keys) != set(existing):
            raise self._conflict("来源业务资产清单不能在此增删，请返回来源单据核对")
        for index, body in enumerate(lines):
            candidate = await self._build_line(
                session, header, body, user, index, enforce_scope=True
            )
            row = existing.pop((body.asset_register_id, body.location_item_id), None)
            if row is None:
                row = candidate
            else:
                for name in candidate.__class__.model_fields:
                    if name not in {"id", "created_at", "created_by", "flex_form"}:
                        setattr(row, name, getattr(candidate, name))
            session.add(row)
        for row in existing.values():
            await session.delete(row)

    async def create(self, body: AssetHandoverCreate, user: AuthenticatedUser) -> dict[str, Any]:
        if body.source_type_code != "manual" or body.source_id is not None:
            raise AppException("业务来源交接单只能由对应业务模块创建", status_code=400)
        org_id = resolve_write_org_id(user, body.org_id, "asset_handover:create")
        async with get_session_context() as session, session.begin():
            if body.transferor_user_id and await asset_repo.user_in_scope(
                session,
                body.transferor_user_id,
                user,
                "asset_handover:create",
            ) is None:
                raise AppException("交出人不存在、已停用或无权选择", status_code=400)
            row = AssetHandover(
                org_id=org_id,
                handover_no="PENDING",
                source_type_code=body.source_type_code,
                source_id=body.source_id,
                transferor_user_id=body.transferor_user_id,
                transferor_name_snapshot=body.transferor_name_snapshot.strip(),
                remark=body.remark,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            session.add(row)
            await session.flush()
            row.handover_no = f"ZCJJ-{local_now():%Y%m%d}-{str(row.id).split('-')[0].upper()}"
            await self._replace_lines(session, row, body.lines, user)
            await session.flush()
            result = await self._item(session, row, user)
        return result

    async def update(
        self, handover_id: UUID, body: AssetHandoverUpdate, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.get(session, handover_id, user, "asset_handover:manage", for_update=True)
            if row is None:
                raise AppException("资产交接单不存在或无权修改", status_code=404)
            if row.version_no != body.expected_version:
                raise self._conflict("交接单已被其他人员修改，请刷新后重试")
            if row.status_code != "draft":
                raise self._conflict("只有草稿交接单可以修改")
            row.remark = body.remark
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            await self._replace_lines(session, row, body.lines, user)
            session.add(row)
            await session.flush()
            result = await self._item(session, row, user)
        return result

    async def submit(
        self, handover_id: UUID, expected_version: int, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.get(session, handover_id, user, "asset_handover:manage", for_update=True)
            if row is None:
                raise AppException("资产交接单不存在或无权提交", status_code=404)
            self._ensure_manual_lifecycle(row)
            if row.version_no != expected_version:
                raise self._conflict("交接单已被其他人员修改，请刷新后重试")
            lines = await repo.lines(session, row.id)
            if row.status_code != "draft" or not lines:
                raise self._conflict("只有包含资产明细的草稿交接单可以提交")
            row.status_code = "awaiting_receipt"
            row.submitted_at = utc_now()
            row.submitted_by = user.user_id
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            session.add(row)
            await session.flush()
            await self._notify_pending_receipt(session, row, lines, user)
            result = await self._item(session, row, user)
        return result

    async def submit_in_session(
        self, session: AsyncSession, handover: AssetHandover, user: AuthenticatedUser
    ) -> None:
        """跨模块公开能力：在来源单据事务内提交尚未接收的资产交接单。"""
        if handover.status_code in {"awaiting_receipt", "completed"}:
            return
        if handover.status_code != "draft":
            raise self._conflict("资产交接单当前不能提交")
        lines = await repo.lines(session, handover.id)
        if not lines:
            raise AppException("资产交接单没有资产明细", status_code=409)
        handover.status_code = "awaiting_receipt"
        handover.submitted_at = utc_now()
        handover.submitted_by = user.user_id
        handover.version_no += 1
        handover.updated_at = utc_now()
        handover.updated_by = user.user_id
        session.add(handover)
        await session.flush()
        await self._notify_pending_receipt(session, handover, lines, user)

    async def _notify_pending_receipt(
        self,
        session: AsyncSession,
        row: AssetHandover,
        lines: list[dict[str, Any]],
        user: AuthenticatedUser,
        *,
        is_resubmitted: bool = False,
    ) -> None:
        recipients = sorted(
            {
                line["AssetHandoverLine"].to_custodian_user_id
                for line in lines
                if line["AssetHandoverLine"].disposition_code == "transfer_teacher"
                and line["AssetHandoverLine"].to_custodian_user_id is not None
            },
            key=str,
        )
        if not recipients:
            return
        try:
            async with session.begin_nested():
                await notify(
                    session,
                    scene_key="asset_handover.pending_receipt",
                    recipients=recipients,
                    business_type_code="asset_handover",
                    business_id=row.id,
                    payload={
                        "title": (
                            "被拒收的资产交接已重新发起"
                            if is_resubmitted
                            else "您有新的资产交接待接收"
                        ),
                        "content": (
                            f"交接单 {row.handover_no} 已由后勤处理并重新发起，"
                            "请再次核对并确认。"
                            if is_resubmitted
                            else f"交接单 {row.handover_no} 已提交，请核对并确认接收。"
                        ),
                        "handover_no": row.handover_no,
                    },
                    org_id=row.org_id,
                    event_key=f"asset_handover:{row.id}:{row.version_no}:pending_receipt",
                    redirect_url=f"/education/my-asset-handovers?id={row.id}",
                    source_module_code="logistics",
                    created_by=user.user_id,
                )
        except Exception:  # 通知失败不影响资产交接事务
            logger.warning("asset handover pending notification failed", exc_info=True)

    async def _notify_rejected(
        self,
        session: AsyncSession,
        row: AssetHandover,
        line: AssetHandoverLine,
        user: AuthenticatedUser,
    ) -> None:
        if row.submitted_by is None:
            return
        try:
            async with session.begin_nested():
                await notify(
                    session,
                    scene_key="asset_handover.rejected",
                    recipients=[row.submitted_by],
                    business_type_code="asset_handover",
                    business_id=row.id,
                    payload={
                        "title": "资产交接已被拒收",
                        "content": (
                            f"交接单 {row.handover_no} 中的“{line.asset_name_snapshot}”"
                            f"被拒收：{line.rejection_reason}"
                        ),
                        "handover_no": row.handover_no,
                    },
                    org_id=row.org_id,
                    event_key=f"asset_handover:{row.id}:{row.version_no}:line:{line.id}:rejected",
                    redirect_url=f"/logistics-management/assets/handovers?id={row.id}",
                    source_module_code="logistics",
                    created_by=user.user_id,
                )
        except Exception:  # 通知失败不影响资产交接事务
            logger.warning("asset handover rejection notification failed", exc_info=True)

    async def void(self, handover_id: UUID, expected_version: int, reason: str, user: AuthenticatedUser) -> dict[str, Any]:
        """作废未发生接收的人工交接；保留明细和审计，不改变资产责任关系。"""
        if "asset_handover:manage" not in user.permissions:
            raise AppException("无权作废资产交接单", status_code=403)
        reason = reason.strip()
        if not reason or len(reason) > 1000:
            raise AppException("请填写作废原因，最多 1000 字", status_code=400)
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.get(session, handover_id, user, "asset_handover:manage", for_update=True)
            if row is None:
                raise AppException("资产交接单不存在或无权作废", status_code=404)
            if row.source_id is not None or row.source_type_code != "manual":
                raise self._conflict("来源业务生成的资产单不能直接作废，请返回来源单据办理")
            if row.version_no != expected_version:
                raise self._conflict("交接单已被其他人员修改，请刷新后重试")
            if row.status_code not in {"draft", "awaiting_receipt"}:
                raise self._conflict("只有未接收的草稿或待接收交接单可以作废")
            lines = await repo.lines(session, row.id)
            if row.completed_at is not None or any(
                line.status_code == "received" or line.confirmed_at is not None or line.confirmed_by is not None
                for item in lines if (line := item["AssetHandoverLine"])
            ):
                raise self._conflict("交接单已有接收记录，不能作废")
            row.status_code = "voided"
            row.voided_at = utc_now()
            row.voided_by = user.user_id
            row.void_reason = reason
            row.updated_at, row.updated_by = row.voided_at, user.user_id
            row.version_no += 1
            session.add(row)
            await session.flush()
            result = await self._item(session, row, user)
        return result

    async def withdraw_in_session(
        self, session: AsyncSession, handover: AssetHandover, user: AuthenticatedUser
    ) -> None:
        """跨模块公开能力：在来源单据事务内撤回尚未发生接收的资产交接单。"""
        if handover.status_code == "draft":
            return
        lines = await repo.lines(session, handover.id)
        if handover.status_code != "awaiting_receipt" or any(
            item["AssetHandoverLine"].status_code == "received" for item in lines
        ):
            raise self._conflict("资产交接已有接收记录，不能随离职交接撤回")
        for item in lines:
            line = item["AssetHandoverLine"]
            line.status_code = "pending"
            line.rejection_reason = None
            line.updated_at = utc_now()
            line.updated_by = user.user_id
            session.add(line)
        handover.status_code = "draft"
        handover.submitted_at = None
        handover.submitted_by = None
        handover.version_no += 1
        handover.updated_at = utc_now()
        handover.updated_by = user.user_id
        session.add(handover)

    async def withdraw(
        self, handover_id: UUID, expected_version: int, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.get(session, handover_id, user, "asset_handover:manage", for_update=True)
            if row is None:
                raise AppException("资产交接单不存在或无权撤回", status_code=404)
            self._ensure_manual_lifecycle(row)
            if row.version_no != expected_version:
                raise self._conflict("交接单已被其他人员修改，请刷新后重试")
            lines = await repo.lines(session, row.id)
            if row.status_code != "awaiting_receipt" or any(
                item["AssetHandoverLine"].status_code == "received" for item in lines
            ):
                raise self._conflict("只有尚未接收任何资产的待接收交接单可以撤回")
            for item in lines:
                line = item["AssetHandoverLine"]
                line.status_code = "pending"
                line.rejection_reason = None
                line.updated_at = utc_now()
                line.updated_by = user.user_id
                session.add(line)
            row.status_code = "draft"
            row.submitted_at = None
            row.submitted_by = None
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            session.add(row)
            await session.flush()
            result = await self._item(session, row, user)
        return result

    async def _apply_line(
        self,
        session: AsyncSession,
        header: AssetHandover,
        line: AssetHandoverLine,
        user: AuthenticatedUser,
    ) -> None:
        if line.asset_register_id:
            asset = await repo.register(session, line.asset_register_id, for_update=True)
        else:
            asset = await repo.location_item(session, line.location_item_id, for_update=True)
        if asset is None or asset.registration_status_code != "confirmed":
            raise self._conflict("交接资产不存在或登记状态已变化")
        await asset_service._protect_stock_asset(session, asset)
        target_status = HANDOVER_TARGET_ASSET_STATUS_CODES[line.disposition_code]
        if (
            asset.location_id != line.from_location_id
            or asset.department_id != line.from_department_id
            or asset.custodian_user_id != line.from_custodian_user_id
        ):
            raise self._conflict("资产责任关系已变化，请撤回交接单后重新生成")
        now = utc_now()
        if isinstance(asset, AssetRegister):
            before_location = asset.location_id
            before_department = asset.department_id
            before_custodian = asset.custodian_user_id
            before_status = asset.status_code
            asset.location_id = line.to_location_id
            asset.custody_location_note = None
            asset.department_id = line.to_department_id
            asset.custodian_user_id = line.to_custodian_user_id
            asset.status_code = target_status
            asset.version_no += 1
            asset.updated_at = now
            asset.updated_by = user.user_id
            session.add(asset)
            session.add(
                asset_service.event(
                    asset,
                    user,
                    "handover",
                    f"按交接单 {header.handover_no} 完成接收",
                    from_location_id=before_location,
                    to_location_id=asset.location_id,
                    from_department_id=before_department,
                    to_department_id=asset.department_id,
                    from_custodian_user_id=before_custodian,
                    to_custodian_user_id=asset.custodian_user_id,
                    from_status_code=before_status,
                    to_status_code=asset.status_code,
                    source_type_code="asset_handover",
                    source_id=header.id,
                )
            )
            return

        quantity = Decimal(line.quantity)
        if quantity > Decimal(asset.quantity):
            raise self._conflict("场所资产当前数量不足，请撤回交接单后重新生成")
        same_location = asset.location_id == line.to_location_id
        full_transfer = quantity == Decimal(asset.quantity)
        if same_location and not full_transfer:
            raise AppException("同一地点的批量资产不能拆分给不同责任人，请整批交接或先调拨到独立地点", status_code=409)
        if full_transfer:
            before_location = asset.location_id
            before_department = asset.department_id
            before_custodian = asset.custodian_user_id
            before_status = asset.status_code
            asset.location_id = line.to_location_id
            asset.custody_location_note = None
            asset.department_id = line.to_department_id
            asset.custodian_user_id = line.to_custodian_user_id
            asset.status_code = target_status
            asset.version_no += 1
            asset.updated_at = now
            asset.updated_by = user.user_id
            session.add(asset)
            session.add(
                asset_service.event(
                    asset,
                    user,
                    "handover",
                    f"按交接单 {header.handover_no} 完成接收",
                    quantity_before=quantity,
                    quantity_after=quantity,
                    from_location_id=before_location,
                    to_location_id=asset.location_id,
                    from_department_id=before_department,
                    to_department_id=asset.department_id,
                    from_custodian_user_id=before_custodian,
                    to_custodian_user_id=asset.custodian_user_id,
                    from_status_code=before_status,
                    to_status_code=asset.status_code,
                    source_type_code="asset_handover",
                    source_id=header.id,
                )
            )
            return

        target = await repo.target_location_item(session, line.to_location_id, asset.item_id)
        if target is not None and target.registration_status_code != "confirmed":
            raise self._conflict("目标地点的同类资产尚未完成登记确认，不能合并接收")
        if target is not None and target.acquisition_source_code != asset.acquisition_source_code:
            raise self._conflict("不同登记来源的数量资产不能直接合并")
        if target is not None:
            await asset_service._protect_stock_asset(session, target)
        before_quantity = Decimal(asset.quantity)
        asset.quantity = before_quantity - quantity
        asset.version_no += 1
        asset.updated_at = now
        asset.updated_by = user.user_id
        session.add(asset)
        session.add(
            asset_service.event(
                asset,
                user,
                "transfer_out",
                f"按交接单 {header.handover_no} 转出",
                quantity_before=before_quantity,
                quantity_after=asset.quantity,
                from_location_id=asset.location_id,
                to_location_id=line.to_location_id,
                from_department_id=asset.department_id,
                to_department_id=line.to_department_id,
                from_custodian_user_id=asset.custodian_user_id,
                to_custodian_user_id=line.to_custodian_user_id,
                source_type_code="asset_handover",
                source_id=header.id,
            )
        )
        if target is None:
            target = AssetLocationItem(
                acquisition_source_code=asset.acquisition_source_code,
                org_id=asset.org_id,
                location_id=line.to_location_id,
                item_id=asset.item_id,
                asset_type_code=asset.asset_type_code,
                quantity=quantity,
                unit_code_snapshot=asset.unit_code_snapshot,
                department_id=line.to_department_id,
                custodian_user_id=line.to_custodian_user_id,
                status_code=target_status,
                registration_status_code="confirmed",
                registered_at=asset.registered_at,
                registered_by=asset.registered_by,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            session.add(target)
            await session.flush()
            target_before = Decimal("0")
        else:
            target_before = Decimal(target.quantity)
            target.quantity = target_before + quantity
            target.department_id = line.to_department_id
            target.custodian_user_id = line.to_custodian_user_id
            target.status_code = target_status
            target.version_no += 1
            target.updated_at = now
            target.updated_by = user.user_id
            session.add(target)
        from .stock_service import stock_service
        await stock_service.move_batch_bindings(session, asset, target, quantity)
        session.add(
            asset_service.event(
                target,
                user,
                "transfer_in",
                f"按交接单 {header.handover_no} 接收",
                quantity_before=target_before,
                quantity_after=Decimal(target.quantity),
                from_location_id=asset.location_id,
                to_location_id=target.location_id,
                from_department_id=asset.department_id,
                to_department_id=target.department_id,
                from_custodian_user_id=asset.custodian_user_id,
                to_custodian_user_id=target.custodian_user_id,
                from_status_code=asset.status_code,
                to_status_code=target.status_code,
                source_type_code="asset_handover",
                source_id=header.id,
            )
        )

    async def receive_line(
        self, handover_id: UUID, line_id: UUID, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.by_id(session, handover_id, for_update=True)
            line = await repo.line(session, line_id, for_update=True)
            if row is None or line is None or line.handover_id != row.id:
                raise AppException("资产交接明细不存在", status_code=404)
            if row.status_code != "awaiting_receipt" or line.status_code != "pending":
                raise self._conflict("只有后勤已发起接收的资产明细可以确认接收")
            if line.disposition_code == "transfer_teacher":
                if line.to_custodian_user_id != user.user_id:
                    raise AppException("只有指定的接任教师可以确认接收", status_code=403)
            elif "asset_handover:receive" not in user.permissions:
                raise AppException("缺少后勤资产接收权限", status_code=403)
            else:
                ensure_org_access(user, row.org_id, "asset_handover:receive")
            await self._apply_line(session, row, line, user)
            line.status_code = "received"
            line.confirmed_at = utc_now()
            line.confirmed_by = user.user_id
            line.updated_at = utc_now()
            line.updated_by = user.user_id
            session.add(line)
            await session.flush()
            if await repo.pending_line_count(session, row.id) == 0:
                row.status_code = "completed"
                row.completed_at = utc_now()
                row.completed_by = user.user_id
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            session.add(row)
            if row.status_code == "completed":
                await dispatch_handover_completed(session, row, user)
            await session.flush()
            result = await self._item(
                session,
                row,
                user,
                receiver_user_id=(
                    None
                    if "asset_handover:list" in user.permissions
                    or row.transferor_user_id == user.user_id
                    else user.user_id
                ),
            )
        return result

    async def resubmit_line(
        self,
        handover_id: UUID,
        line_id: UUID,
        body: AssetHandoverLineResubmit,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        """后勤修正被拒收明细，并重新交由指定接收人确认。"""
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.get(
                session,
                handover_id,
                user,
                "asset_handover:manage",
                for_update=True,
            )
            line = await repo.line(session, line_id, for_update=True)
            if row is None or line is None or line.handover_id != row.id:
                raise AppException("资产交接明细不存在或无权处理", status_code=404)
            if row.version_no != body.expected_version:
                raise self._conflict("交接单已被其他人员修改，请刷新后重试")
            if row.status_code != "awaiting_receipt" or line.status_code != "rejected":
                raise self._conflict("只有已拒收的资产明细可以重新发起接收")
            if row.source_id is not None and body.quantity != line.quantity:
                raise self._conflict("来源业务交接须完整交清原资产数量，不能在拒收重办时减少数量")

            candidate = await self._build_line(
                session,
                row,
                AssetHandoverLineCreate(
                    asset_register_id=line.asset_register_id,
                    location_item_id=line.location_item_id,
                    quantity=body.quantity,
                    disposition_code=body.disposition_code,
                    to_location_id=body.to_location_id,
                    to_department_id=body.to_department_id,
                    to_custodian_user_id=body.to_custodian_user_id,
                ),
                user,
                line.sort_no,
                enforce_scope=True,
            )
            line.quantity = candidate.quantity
            line.disposition_code = candidate.disposition_code
            line.to_location_id = candidate.to_location_id
            line.to_department_id = candidate.to_department_id
            line.to_custodian_user_id = candidate.to_custodian_user_id
            line.status_code = "pending"
            line.confirmed_at = None
            line.confirmed_by = None
            line.updated_at = utc_now()
            line.updated_by = user.user_id
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            session.add_all([row, line])
            await session.flush()
            await self._notify_pending_receipt(
                session,
                row,
                [{"AssetHandoverLine": line}],
                user,
                is_resubmitted=True,
            )
            result = await self._item(session, row, user)
        return result

    async def reject_line(
        self, handover_id: UUID, line_id: UUID, reason: str, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            await self._lock_source(session, handover_id)
            row = await repo.by_id(session, handover_id, for_update=True)
            line = await repo.line(session, line_id, for_update=True)
            if row is None or line is None or line.handover_id != row.id:
                raise AppException("资产交接明细不存在", status_code=404)
            if row.status_code != "awaiting_receipt" or line.status_code != "pending":
                raise self._conflict("只有待接收的资产明细可以拒收")
            if line.disposition_code == "transfer_teacher" and line.to_custodian_user_id != user.user_id:
                raise AppException("只有指定的接任教师可以拒收", status_code=403)
            if line.disposition_code == "return_logistics" and "asset_handover:receive" not in user.permissions:
                raise AppException("缺少后勤资产接收权限", status_code=403)
            if line.disposition_code == "return_logistics":
                ensure_org_access(user, row.org_id, "asset_handover:receive")
            line.status_code = "rejected"
            line.rejection_reason = reason.strip()
            line.updated_at = utc_now()
            line.updated_by = user.user_id
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            session.add_all([row, line])
            await session.flush()
            await self._notify_rejected(session, row, line, user)
            result = await self._item(
                session,
                row,
                user,
                receiver_user_id=(
                    None
                    if "asset_handover:list" in user.permissions
                    or row.transferor_user_id == user.user_id
                    else user.user_id
                ),
            )
        return result

    async def ensure_for_teacher_offboarding(
        self,
        session: AsyncSession,
        *,
        source_id: UUID,
        org_id: UUID,
        transferor_user_id: UUID | None,
        transferor_name: str,
        receiver_user_id: UUID | None,
        receiver_department_id: UUID | None,
        user: AuthenticatedUser,
        refresh: bool = False,
        source_org_ids: set[UUID] | None = None,
    ) -> AssetHandover | None:
        """跨模块公开能力：在离职交接事务内为教师当前保管资产创建交接单。"""
        if source_org_ids is not None and org_id not in source_org_ids:
            raise AppException("资产所属组织不在来源业务授权范围内", status_code=403)
        existing = await repo.get_by_source(session, "teacher_offboarding", source_id, for_update=True, org_id=org_id)
        if existing is not None and not refresh:
            return existing
        if existing is not None and existing.status_code != "draft":
            raise self._conflict("资产单已提交，请先从离职单撤回后核对资产")
        if transferor_user_id is None:
            raise AppException("离职教师尚未关联租户用户，请先完善人员档案后核对资产", status_code=409)
        registers, location_items = await asset_repo.assets_by_custodian(
            session, org_id, transferor_user_id
        )
        if not registers and not location_items:
            return existing
        if receiver_user_id is None:
            raise AppException("接任教师尚未关联租户用户，不能接收资产", status_code=409)
        row = existing or AssetHandover(
            org_id=org_id,
            handover_no="PENDING",
            source_type_code="teacher_offboarding",
            source_id=source_id,
            transferor_user_id=transferor_user_id,
            transferor_name_snapshot=transferor_name,
            created_by=user.user_id,
            updated_by=user.user_id,
        )
        known = await repo.line_asset_ids(session, row.id) if existing is not None else set()
        new_assets = [asset for asset in [*registers, *location_items] if asset.id not in known]
        if not new_assets:
            return row
        session.add(row)
        await session.flush()
        if existing is None:
            row.handover_no = f"ZCJJ-{local_now():%Y%m%d}-{row.id.hex.upper()}"
        department_cache, reference_cache = {}, {}
        for index, asset in enumerate(new_assets, start=len(known)):
            if asset.department_id not in department_cache:
                department_cache[asset.department_id] = await self._source_department(session, org_id, receiver_department_id, asset.department_id, source_org_ids=source_org_ids)
            department_id = department_cache[asset.department_id]
            if department_id is None:
                asset_label = getattr(asset, "asset_no", None) or str(asset.id)
                raise AppException(f"资产 {asset_label} 没有可用的目标责任部门，请核对台账责任部门及接任教师部门是否启用、属于本校授权范围", status_code=409)
            body = AssetHandoverLineCreate(
                asset_register_id=asset.id if isinstance(asset, AssetRegister) else None,
                location_item_id=asset.id if isinstance(asset, AssetLocationItem) else None,
                quantity=Decimal("1") if isinstance(asset, AssetRegister) else Decimal(asset.quantity),
                disposition_code="transfer_teacher",
                to_location_id=asset.location_id,
                to_department_id=department_id,
                to_custodian_user_id=receiver_user_id,
            )
            session.add(
                await self._build_line(
                    session, row, body, user, index, enforce_scope=False, source_org_ids=source_org_ids, reference_cache=reference_cache
                )
            )
        await session.flush()
        if existing is not None:
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
        return row

    async def source_record(self, session, source_type_code, source_id, *, lock=False):
        """来源模块已鉴权、锁定来源单据后使用的公开查询契约。"""
        return await repo.get_by_source(session, source_type_code, source_id, for_update=lock)

    async def source_records(self, session, source_type_code, source_id, *, lock=False):
        """已鉴权来源单据的全部组织分单；锁顺序固定为组织、主键。"""
        return await repo.list_by_source(session, source_type_code, source_id, for_update=lock)

    async def source_details(self, session, source_type_code, source_id, user=None):
        rows = await self.source_records(session, source_type_code, source_id)
        return [{**await self._item(session, row, user), "org_name": await repo.org_name(session, row.org_id)} for row in rows]

    async def _source_department(self, session, org_id, receiver_department_id, fallback_id, *, source_org_ids=None):
        """优先同组织接任部门，再保留本校授权范围内原部门，最后使用本校接任部门。"""
        org_ids = source_org_ids if source_org_ids is not None else {org_id}
        if org_id not in org_ids:
            raise AppException("资产所属组织不在来源业务授权范围内", status_code=403)
        if receiver_department_id and await asset_repo.department_for_org(session, receiver_department_id, org_id):
            return receiver_department_id
        for department_id in dict.fromkeys([fallback_id, receiver_department_id]):
            if department_id and await asset_repo.department_for_orgs(session, department_id, org_ids):
                return department_id
        return None

    async def offboarding_assets(self, session, org_id, user_id):
        """来源单据同组织、同保管人的核对清单；含未确认登记资产，避免误报无资产。"""
        if user_id is None:
            raise AppException("离职教师尚未关联租户用户，不能确认名下资产", status_code=409)
        registers, items = await asset_repo.assets_by_custodian(
            session, org_id, user_id, include_unconfirmed=True
        )
        result = []
        for asset in [*registers, *items]:
            item = await repo.item(session, asset.item_id)
            result.append({
                "asset_id": str(asset.id),
                "asset_type_key": "register" if isinstance(asset, AssetRegister) else "location_item",
                "org_id": str(asset.org_id),
                "asset_no": getattr(asset, "asset_no", None),
                "name": item.item_name if item else "未找到物品档案",
                "specification": item.specification if item else None,
                "quantity": str(1 if isinstance(asset, AssetRegister) else asset.quantity),
                "registration_status_code": asset.registration_status_code,
            })
        return result

    async def validate_offboarding_assets(self, session, org_id, user_id, handover):
        """提交前必须完整覆盖当前保管资产；已接收项允许已离开原保管人。"""
        assets = await self.offboarding_assets(session, org_id, user_id)
        lines = await repo.lines(session, handover.id) if handover else []
        quantities = {
            str(line.asset_register_id or line.location_item_id): line.quantity
            for item in lines if (line := item["AssetHandoverLine"]).status_code != "received"
        }
        if any(asset["registration_status_code"] != "confirmed"
               or quantities.get(asset["asset_id"]) != Decimal(asset["quantity"]) for asset in assets):
            raise self._conflict("仍有资产未完整纳入交接或登记未确认，请核对名下资产后重新提交")

    async def change_source_receiver(self, session, source_id, old_user_id, new_user_id, department_id, user, *, source_org_ids=None):
        handovers = await self.source_records(session, "teacher_offboarding", source_id, lock=True)
        for handover in handovers:
            await self._change_handover_receiver(session, handover, old_user_id, new_user_id, department_id, user, source_org_ids=source_org_ids)

    async def _change_handover_receiver(self, session, handover, old_user_id, new_user_id, department_id, user, *, source_org_ids=None):
        if handover.status_code != "draft":
            raise self._conflict("资产单已有提交或接收记录，不能直接更换接任教师")
        if new_user_id is None:
            raise self._conflict("接任教师尚未关联租户用户，不能接收资产")
        for item in await repo.lines(session, handover.id):
            line = item["AssetHandoverLine"]
            if line.disposition_code != "transfer_teacher" or line.to_custodian_user_id != old_user_id:
                continue
            target_department_id = await self._source_department(session, handover.org_id, department_id, line.to_department_id, source_org_ids=source_org_ids)
            if target_department_id is None:
                raise self._conflict(f"资产 {line.asset_no_snapshot or line.asset_register_id or line.location_item_id} 没有可用的目标责任部门，请先核对部门档案")
            candidate = await self._build_line(session, handover, AssetHandoverLineCreate(
                asset_register_id=line.asset_register_id, location_item_id=line.location_item_id,
                quantity=line.quantity, disposition_code=line.disposition_code,
                to_location_id=line.to_location_id,
                to_department_id=target_department_id,
                to_custodian_user_id=new_user_id,
            ), user, line.sort_no, enforce_scope=False, source_org_ids=source_org_ids)
            line.to_custodian_user_id = candidate.to_custodian_user_id
            line.to_department_id = candidate.to_department_id
            line.updated_at, line.updated_by = utc_now(), user.user_id
            session.add(line)
        handover.version_no += 1
        handover.updated_at, handover.updated_by = utc_now(), user.user_id
        session.add(handover)

    async def source_detail(
        self,
        session: AsyncSession,
        source_type_code: str,
        source_id: UUID,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any] | None:
        row = await repo.get_by_source(session, source_type_code, source_id)
        return await self._item(session, row, user) if row else None


handover_service = AssetHandoverService()
