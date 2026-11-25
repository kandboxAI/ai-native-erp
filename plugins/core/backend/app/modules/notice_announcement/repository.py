"""公告数据访问：只有这里写 ORM。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import table_scope_condition
from app.framework.db.models import utc_now
from app.modules.role.models import SysRole
from app.modules.user_profile.models import SysUser
from app.modules.user_role.models import SysUserRole

from .models import NtfNotice, NtfNoticeRead, NtfNoticeTarget


def _like(value: str) -> str:
    return f"%{value.strip()}%"


class NoticeRepository:
    # ───────── 条件 ─────────
    def scope_condition(self, user: AuthenticatedUser, action: str):
        return table_scope_condition(NtfNotice, user, f"notice_announcement:{action}")

    def recipient_condition(self, user_id: UUID):
        """当前用户是否在公告接收范围内：全部、指定用户、或拥有指定角色（租户配置的接收范围）。"""
        targets = select(NtfNoticeTarget.id).where(NtfNoticeTarget.notice_id == NtfNotice.id)
        no_targets = ~exists(targets)
        to_all = exists(targets.where(NtfNoticeTarget.target_type_code == "all"))
        to_user = exists(targets.where(NtfNoticeTarget.target_type_code == "user", NtfNoticeTarget.user_id == user_id))
        to_role = exists(
            targets.where(
                NtfNoticeTarget.target_type_code == "role",
                NtfNoticeTarget.role_id.in_(select(SysUserRole.role_id).where(SysUserRole.user_id == user_id)),
            )
        )
        return or_(no_targets, to_all, to_user, to_role)

    def _read_exists(self, user_id: UUID):
        return exists(select(NtfNoticeRead.id).where(NtfNoticeRead.notice_id == NtfNotice.id, NtfNoticeRead.user_id == user_id))

    def _filters(self, params: Any) -> list[Any]:
        conditions: list[Any] = [NtfNotice.deleted_at.is_(None)]
        if params.keyword:
            kw = _like(params.keyword)
            conditions.append(or_(NtfNotice.title.ilike(kw), NtfNotice.summary.ilike(kw), NtfNotice.publisher_name_snapshot.ilike(kw)))
        for field in ("notice_type_code", "is_shown_on_home", "status_code", "org_id"):
            value = getattr(params, field, None)
            if value is not None:
                conditions.append(getattr(NtfNotice, field) == value)
        return conditions

    # ───────── 查询 ─────────
    async def list(
        self, session: AsyncSession, params: Any, user: AuthenticatedUser, *, mine: bool
    ) -> tuple[list[tuple[NtfNotice, Any]], int]:
        conditions = self._filters(params)
        if mine:
            conditions.append(NtfNotice.status_code == "published")
            conditions.append(self.recipient_condition(user.user_id))
        else:
            scope = self.scope_condition(user, "list")
            if scope is not None:
                conditions.append(scope)
        if params.read_status == "read":
            conditions.append(self._read_exists(user.user_id))
        elif params.read_status == "unread":
            conditions.append(~self._read_exists(user.user_id))
        total = int((await session.exec(select(func.count()).select_from(NtfNotice).where(*conditions))).one() or 0)
        read_at = (
            select(NtfNoticeRead.read_at)
            .where(NtfNoticeRead.notice_id == NtfNotice.id, NtfNoticeRead.user_id == user.user_id)
            .limit(1)
            .scalar_subquery()
        )
        order = [desc(NtfNotice.published_at).nulls_last(), desc(NtfNotice.updated_at)] if mine else [desc(NtfNotice.updated_at)]
        rows = (
            await session.exec(
                select(NtfNotice, read_at.label("read_at"))
                .where(*conditions)
                .order_by(*order)
                .limit(params.page_size)
                .offset((params.page - 1) * params.page_size)
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    async def get(
        self, session: AsyncSession, notice_id: UUID, user: AuthenticatedUser, *, action: str | None, for_update: bool = False
    ) -> NtfNotice | None:
        """action 为空时按接收范围（本人可见）取。"""
        statement = select(NtfNotice).where(NtfNotice.id == notice_id, NtfNotice.deleted_at.is_(None))
        if action is None:
            statement = statement.where(NtfNotice.status_code == "published", self.recipient_condition(user.user_id))
        else:
            scope = self.scope_condition(user, action)
            if scope is not None:
                statement = statement.where(scope)
        if for_update:
            statement = statement.with_for_update(of=NtfNotice)
        return (await session.exec(statement)).first()

    async def read_at(self, session: AsyncSession, notice_id: UUID, user_id: UUID):
        return (
            await session.exec(select(NtfNoticeRead.read_at).where(NtfNoticeRead.notice_id == notice_id, NtfNoticeRead.user_id == user_id))
        ).first()

    async def targets(self, session: AsyncSession, notice_ids: list[UUID]) -> dict[UUID, list[NtfNoticeTarget]]:
        if not notice_ids:
            return {}
        rows = await session.exec(select(NtfNoticeTarget).where(NtfNoticeTarget.notice_id.in_(notice_ids)))
        result: dict[UUID, list[NtfNoticeTarget]] = {}
        for row in rows.all():
            result.setdefault(row.notice_id, []).append(row)
        return result

    async def roles(self, session: AsyncSession, role_ids: list[UUID]) -> dict[UUID, SysRole]:
        if not role_ids:
            return {}
        rows = await session.exec(select(SysRole).where(SysRole.id.in_(role_ids), SysRole.deleted_at.is_(None)))
        return {row.id: row for row in rows.all()}

    async def users(self, session: AsyncSession, user_ids: list[UUID], *, active_only: bool = False) -> dict[UUID, SysUser]:
        if not user_ids:
            return {}
        statement = select(SysUser).where(SysUser.id.in_(user_ids), SysUser.deleted_at.is_(None))
        if active_only:
            statement = statement.where(SysUser.is_active.is_(True))
        rows = await session.exec(statement)
        return {row.id: row for row in rows.all()}

    def _audience_condition(self, notice_id: UUID):
        """某条公告的接收用户（sys_user 条件）。"""
        targets = select(NtfNoticeTarget.id).where(NtfNoticeTarget.notice_id == notice_id)
        return and_(
            SysUser.deleted_at.is_(None),
            SysUser.is_active.is_(True),
            or_(
                ~exists(targets),
                exists(targets.where(NtfNoticeTarget.target_type_code == "all")),
                exists(targets.where(NtfNoticeTarget.target_type_code == "user", NtfNoticeTarget.user_id == SysUser.id)),
                exists(
                    targets.where(
                        NtfNoticeTarget.target_type_code == "role",
                        NtfNoticeTarget.role_id.in_(select(SysUserRole.role_id).where(SysUserRole.user_id == SysUser.id)),
                    )
                ),
            ),
        )

    async def audience_stats(self, session: AsyncSession, notice_id: UUID) -> tuple[int, int]:
        """（接收人数, 已读人数）"""
        condition = self._audience_condition(notice_id)
        total = int((await session.exec(select(func.count()).select_from(SysUser).where(condition))).one() or 0)
        read = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(SysUser)
                    .join(NtfNoticeRead, and_(NtfNoticeRead.user_id == SysUser.id, NtfNoticeRead.notice_id == notice_id))
                    .where(condition)
                )
            ).one()
            or 0
        )
        return total, read

    async def list_readers(
        self, session: AsyncSession, notice_id: UUID, *, read_status: str, page: int, page_size: int
    ) -> tuple[list[tuple[UUID, str, Any]], int]:
        join = and_(NtfNoticeRead.user_id == SysUser.id, NtfNoticeRead.notice_id == notice_id)
        conditions: list[Any] = [self._audience_condition(notice_id)]
        if read_status == "read":
            conditions.append(NtfNoticeRead.id.is_not(None))
        elif read_status == "unread":
            conditions.append(NtfNoticeRead.id.is_(None))
        total = int(
            (await session.exec(select(func.count()).select_from(SysUser).outerjoin(NtfNoticeRead, join).where(*conditions))).one() or 0
        )
        rows = (
            await session.exec(
                select(SysUser.id, SysUser.display_name, NtfNoticeRead.read_at)
                .select_from(SysUser)
                .outerjoin(NtfNoticeRead, join)
                .where(*conditions)
                .order_by(NtfNoticeRead.read_at.desc().nulls_last(), SysUser.display_name)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    async def role_options(self, session: AsyncSession) -> list[SysRole]:
        rows = await session.exec(
            select(SysRole).where(SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)).order_by(SysRole.role_name)
        )
        return list(rows.all())

    async def user_options(self, session: AsyncSession, keyword: str | None, limit: int) -> list[SysUser]:
        statement = select(SysUser).where(SysUser.deleted_at.is_(None), SysUser.is_active.is_(True))
        if keyword:
            statement = statement.where(SysUser.display_name.ilike(_like(keyword)))
        rows = await session.exec(statement.order_by(SysUser.display_name).limit(limit))
        return list(rows.all())

    # ───────── 写入 ─────────
    def add(self, session: AsyncSession, row: Any) -> Any:
        session.add(row)
        return row

    async def replace_targets(
        self, session: AsyncSession, notice: NtfNotice, *, scope: str, role_ids: list[UUID], user_ids: list[UUID], by: UUID
    ) -> None:
        await session.exec(delete(NtfNoticeTarget).where(NtfNoticeTarget.notice_id == notice.id))
        common = {"org_id": notice.org_id, "notice_id": notice.id, "created_by": by, "updated_by": by}
        if scope == "all":
            session.add(NtfNoticeTarget(target_type_code="all", **common))
            return
        for role_id in role_ids:
            session.add(NtfNoticeTarget(target_type_code="role", role_id=role_id, **common))
        for user_id in user_ids:
            session.add(NtfNoticeTarget(target_type_code="user", user_id=user_id, **common))

    async def mark_read(self, session: AsyncSession, notice: NtfNotice, user_id: UUID) -> int:
        now = utc_now()
        result = await session.exec(
            pg_insert(NtfNoticeRead)
            .values(org_id=notice.org_id, notice_id=notice.id, user_id=user_id, read_at=now, created_by=user_id, updated_by=user_id)
            .on_conflict_do_nothing(index_elements=["notice_id", "user_id"])
        )
        return int(result.rowcount or 0)

    async def unread_published(self, session: AsyncSession, user_id: UUID) -> list[NtfNotice]:
        rows = await session.exec(
            select(NtfNotice).where(
                NtfNotice.deleted_at.is_(None),
                NtfNotice.status_code == "published",
                self.recipient_condition(user_id),
                ~self._read_exists(user_id),
            )
        )
        return list(rows.all())


repository = NoticeRepository()
