"""资产交接数据访问。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import aliased
from sqlalchemy.exc import MultipleResultsFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.modules.department.models import SysDepartment
from app.modules.inventory.models import MdItem
from app.modules.user_profile.models import SysUser

from .handover_models import AssetHandover, AssetHandoverLine
from .models import AssetLocation, AssetLocationItem, AssetRegister
from .handover_schemas import AssetHandoverQuery


class AssetHandoverRepository:
    async def by_id(
        self, session: AsyncSession, handover_id: UUID, *, for_update: bool = False
    ) -> AssetHandover | None:
        statement = select(AssetHandover).where(AssetHandover.id == handover_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def participant_get(
        self, session: AsyncSession, handover_id: UUID, user_id: UUID
    ) -> AssetHandover | None:
        receiver_line = exists(
            select(AssetHandoverLine.id).where(
                AssetHandoverLine.handover_id == AssetHandover.id,
                AssetHandoverLine.to_custodian_user_id == user_id,
            )
        )
        return (
            await session.exec(
                select(AssetHandover).where(
                    AssetHandover.id == handover_id,
                    or_(AssetHandover.transferor_user_id == user_id, receiver_line),
                )
            )
        ).first()

    async def get(
        self,
        session: AsyncSession,
        handover_id: UUID,
        user: AuthenticatedUser,
        permission: str,
        *,
        for_update: bool = False,
    ) -> AssetHandover | None:
        statement = select(AssetHandover).where(
            AssetHandover.id == handover_id,
            *scoped_conditions(AssetHandover, user, permission),
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def get_by_source(
        self, session: AsyncSession, source_type_code: str, source_id: UUID,
        *, for_update: bool = False, org_id: UUID | None = None,
    ) -> AssetHandover | None:
        statement = select(AssetHandover).where(
            AssetHandover.source_type_code == source_type_code,
            AssetHandover.source_id == source_id,
            AssetHandover.status_code != "voided",
        )
        if org_id is not None:
            statement = statement.where(AssetHandover.org_id == org_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        try:
            return (await session.exec(statement)).one_or_none()
        except MultipleResultsFound as exc:
            raise AppException("同一来源存在多张有效资产单，请先核实重复单据", status_code=409) from exc

    async def list_by_source(self, session, source_type_code, source_id, *, for_update=False):
        statement = select(AssetHandover).where(
            AssetHandover.source_type_code == source_type_code,
            AssetHandover.source_id == source_id,
            AssetHandover.status_code != "voided",
        ).order_by(AssetHandover.org_id, AssetHandover.id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        rows = list((await session.exec(statement)).all())
        if len({row.org_id for row in rows}) != len(rows):
            raise AppException("同一来源、同一组织存在重复有效资产单，请先核实", 409)
        return rows

    async def org_name(self, session, org_id):
        from app.modules.organization.models import SysOrg
        return (await session.exec(select(SysOrg.org_name).where(
            SysOrg.id == org_id, SysOrg.deleted_at.is_(None),
        ))).first() or "组织已失效"

    async def active_user(self, session, user_id):
        return (await session.exec(select(SysUser).where(
            SysUser.id == user_id, SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
        ))).first()

    async def list(
        self, session: AsyncSession, query: AssetHandoverQuery, user: AuthenticatedUser
    ) -> tuple[int, list[AssetHandover]]:
        conditions = list(scoped_conditions(AssetHandover, user, "asset_handover:list"))
        if query.org_id:
            conditions.append(AssetHandover.org_id == query.org_id)
        if query.status_code:
            conditions.append(AssetHandover.status_code == query.status_code)
        if query.transferor_user_id:
            conditions.append(AssetHandover.transferor_user_id == query.transferor_user_id)
        if query.source_type_code:
            conditions.append(AssetHandover.source_type_code == query.source_type_code)
        if query.source_id:
            conditions.append(AssetHandover.source_id == query.source_id)
        if query.receiver_user_id:
            conditions.append(
                AssetHandover.id.in_(
                    select(AssetHandoverLine.handover_id).where(
                        AssetHandoverLine.to_custodian_user_id == query.receiver_user_id
                    )
                )
            )
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    AssetHandover.handover_no.ilike(word),
                    AssetHandover.transferor_name_snapshot.ilike(word),
                    AssetHandover.id.in_(
                        select(AssetHandoverLine.handover_id).where(
                            or_(
                                AssetHandoverLine.asset_no_snapshot.ilike(word),
                                AssetHandoverLine.asset_name_snapshot.ilike(word),
                            )
                        )
                    ),
                )
            )
        statement = select(AssetHandover).where(*conditions)
        total = (await session.exec(select(func.count()).select_from(statement.subquery()))).one()
        rows = (
            await session.exec(
                statement.order_by(AssetHandover.created_at.desc(), AssetHandover.id.desc())
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return int(total or 0), list(rows)

    async def list_mine(
        self, session: AsyncSession, query: AssetHandoverQuery, user_id: UUID
    ) -> tuple[int, list[AssetHandover]]:
        receiver_handover_ids = select(AssetHandoverLine.handover_id).where(
            AssetHandoverLine.to_custodian_user_id == user_id,
            AssetHandoverLine.disposition_code == "transfer_teacher",
        )
        conditions = [AssetHandover.id.in_(receiver_handover_ids)]
        if query.status_code:
            conditions.append(AssetHandover.status_code == query.status_code)
        if query.source_type_code:
            conditions.append(AssetHandover.source_type_code == query.source_type_code)
        if query.source_id:
            conditions.append(AssetHandover.source_id == query.source_id)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    AssetHandover.handover_no.ilike(word),
                    AssetHandover.transferor_name_snapshot.ilike(word),
                    AssetHandover.id.in_(
                        select(AssetHandoverLine.handover_id).where(
                            AssetHandoverLine.to_custodian_user_id == user_id,
                            or_(
                                AssetHandoverLine.asset_no_snapshot.ilike(word),
                                AssetHandoverLine.asset_name_snapshot.ilike(word),
                            ),
                        )
                    ),
                )
            )
        statement = select(AssetHandover).where(*conditions)
        total = (await session.exec(select(func.count()).select_from(statement.subquery()))).one()
        rows = (
            await session.exec(
                statement.order_by(AssetHandover.created_at.desc(), AssetHandover.id.desc())
                .offset((query.page - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return int(total or 0), list(rows)

    async def lines(
        self,
        session: AsyncSession,
        handover_id: UUID,
        *,
        receiver_user_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        from_location = aliased(AssetLocation)
        to_location = aliased(AssetLocation)
        from_department = aliased(SysDepartment)
        to_department = aliased(SysDepartment)
        from_custodian = aliased(SysUser)
        to_custodian = aliased(SysUser)
        confirmed_user = aliased(SysUser)
        rows = (
            await session.execute(
                select(
                    AssetHandoverLine,
                    from_location.location_name.label("from_location_name"),
                    to_location.location_name.label("to_location_name"),
                    from_department.department_name.label("from_department_name"),
                    to_department.department_name.label("to_department_name"),
                    from_custodian.display_name.label("from_custodian_name"),
                    to_custodian.display_name.label("to_custodian_name"),
                    confirmed_user.display_name.label("confirmed_by_name"),
                )
                .join(from_location, from_location.id == AssetHandoverLine.from_location_id, isouter=True)
                .join(to_location, to_location.id == AssetHandoverLine.to_location_id)
                .join(from_department, from_department.id == AssetHandoverLine.from_department_id, isouter=True)
                .join(to_department, to_department.id == AssetHandoverLine.to_department_id)
                .join(from_custodian, from_custodian.id == AssetHandoverLine.from_custodian_user_id, isouter=True)
                .join(to_custodian, to_custodian.id == AssetHandoverLine.to_custodian_user_id, isouter=True)
                .join(confirmed_user, confirmed_user.id == AssetHandoverLine.confirmed_by, isouter=True)
                .where(
                    AssetHandoverLine.handover_id == handover_id,
                    *(
                        [AssetHandoverLine.to_custodian_user_id == receiver_user_id]
                        if receiver_user_id is not None
                        else []
                    ),
                )
                .order_by(AssetHandoverLine.sort_no, AssetHandoverLine.created_at)
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def line_asset_ids(self, session, handover_id):
        rows = (await session.exec(select(
            AssetHandoverLine.asset_register_id, AssetHandoverLine.location_item_id,
        ).where(AssetHandoverLine.handover_id == handover_id))).all()
        return {register_id or location_item_id for register_id, location_item_id in rows}

    async def line(
        self, session: AsyncSession, line_id: UUID, *, for_update: bool = False
    ) -> AssetHandoverLine | None:
        statement = select(AssetHandoverLine).where(AssetHandoverLine.id == line_id)
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).first()

    async def target_has_open_handover(
        self,
        session: AsyncSession,
        *,
        asset_register_id: UUID | None,
        location_item_id: UUID | None,
        exclude_handover_id: UUID | None = None,
    ) -> bool:
        target = (
            AssetHandoverLine.asset_register_id == asset_register_id
            if asset_register_id is not None
            else AssetHandoverLine.location_item_id == location_item_id
        )
        conditions = [
            target,
            AssetHandoverLine.status_code.in_(["pending", "rejected"]),
            AssetHandover.id == AssetHandoverLine.handover_id,
            AssetHandover.status_code.in_(["draft", "awaiting_receipt"]),
        ]
        if exclude_handover_id:
            conditions.append(AssetHandover.id != exclude_handover_id)
        return (await session.exec(select(AssetHandoverLine.id).where(*conditions))).first() is not None

    async def delete_lines(self, session: AsyncSession, handover_id: UUID) -> None:
        rows = (
            await session.exec(select(AssetHandoverLine).where(AssetHandoverLine.handover_id == handover_id))
        ).all()
        for row in rows:
            await session.delete(row)

    async def register(
        self, session: AsyncSession, asset_id: UUID, *, for_update: bool = False
    ) -> AssetRegister | None:
        if for_update:
            from .repository import repository
            await repository.lock_stock_item_for_asset(session, AssetRegister, asset_id)
        statement = select(AssetRegister).where(
            AssetRegister.id == asset_id, AssetRegister.deleted_at.is_(None)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).first()

    async def location_item(
        self, session: AsyncSession, asset_id: UUID, *, for_update: bool = False
    ) -> AssetLocationItem | None:
        if for_update:
            from .repository import repository
            await repository.lock_stock_item_for_asset(session, AssetLocationItem, asset_id)
        statement = select(AssetLocationItem).where(
            AssetLocationItem.id == asset_id, AssetLocationItem.deleted_at.is_(None)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).first()

    async def item(self, session: AsyncSession, item_id: UUID) -> MdItem | None:
        return await session.get(MdItem, item_id)

    async def target_location_item(
        self, session: AsyncSession, location_id: UUID, item_id: UUID
    ) -> AssetLocationItem | None:
        return (
            await session.exec(
                select(AssetLocationItem)
                .where(
                    AssetLocationItem.location_id == location_id,
                    AssetLocationItem.item_id == item_id,
                    AssetLocationItem.deleted_at.is_(None),
                    AssetLocationItem.registration_status_code != "voided",
                )
                .with_for_update()
            )
        ).first()

    async def pending_line_count(self, session: AsyncSession, handover_id: UUID) -> int:
        return int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(AssetHandoverLine)
                    .where(
                        AssetHandoverLine.handover_id == handover_id,
                        AssetHandoverLine.status_code != "received",
                    )
                )
            ).one()
        )


handover_repository = AssetHandoverRepository()
