"""通知中心数据访问：只有这里写 ORM。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, delete, exists, func, or_, true, update
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now
from .scene_policies import is_family_inbox_scene, non_message_inbox_scene_keys, individual_read_scene_keys
from app.modules.organization.models import SysOrg
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_profile.models import SysUser, SysUserOrg
from app.modules.user_role.models import SysUserRole

from .models import (
    NtfChannelBinding,
    NtfDeliveryLog,
    NtfEventLog,
    NtfNotification,
    NtfPreference,
    NtfRecipient,
    NtfRoute,
    NtfScene,
    NtfSceneChannel,
    NtfTemplate,
)


def _page(statement, page: int, page_size: int):
    return statement.limit(page_size).offset((page - 1) * page_size)


def _like(value: str) -> str:
    return f"%{value.strip()}%"


class NotificationCenterRepository:
    async def purge_retired_scenes(self, session: AsyncSession, scene_keys: set[str]) -> None:
        scene_ids = select(NtfScene.id).where(NtfScene.scene_key.in_(scene_keys))
        notification_ids = select(NtfNotification.id).where(NtfNotification.scene_id.in_(scene_ids))
        recipient_ids = select(NtfRecipient.id).where(NtfRecipient.notification_id.in_(notification_ids))
        await session.execute(delete(NtfDeliveryLog).where(NtfDeliveryLog.recipient_id.in_(recipient_ids)))
        await session.execute(delete(NtfRecipient).where(NtfRecipient.notification_id.in_(notification_ids)))
        for model in (NtfNotification, NtfEventLog, NtfPreference, NtfRoute, NtfTemplate, NtfSceneChannel):
            await session.execute(delete(model).where(model.scene_id.in_(scene_ids)))
        await session.execute(delete(NtfScene).where(NtfScene.scene_key.in_(scene_keys)))

    async def notification_recipients(self, session: AsyncSession, notification_id: UUID) -> list[NtfRecipient]:
        rows = await session.exec(select(NtfRecipient).where(NtfRecipient.notification_id == notification_id))
        return list(rows.all())

    async def latest_delivery_logs(
        self, session: AsyncSession, notification_ids: list[UUID],
    ) -> list[tuple[UUID, NtfDeliveryLog, UUID]]:
        if not notification_ids:
            return []
        rows = (await session.exec(
            select(NtfRecipient.notification_id, NtfDeliveryLog, NtfRecipient.user_id)
            .select_from(NtfDeliveryLog)
            .join(NtfRecipient, NtfRecipient.id == NtfDeliveryLog.recipient_id)
            .where(NtfRecipient.notification_id.in_(notification_ids))
            .order_by(NtfDeliveryLog.created_at.desc(), NtfDeliveryLog.id.desc())
        )).all()
        # 同一收件人、同一渠道只看最近一次尝试；旧失败记录仍保留供审计。
        latest = {}
        for notification_id, log, user_id in rows:
            latest.setdefault((log.recipient_id, log.channel_code), (notification_id, log, user_id))
        return list(latest.values())

    # ───────── 场景 ─────────
    async def scene_by_key(self, session: AsyncSession, scene_key: str) -> NtfScene | None:
        return (
            await session.exec(select(NtfScene).where(NtfScene.scene_key == scene_key.strip(), NtfScene.deleted_at.is_(None)))
        ).first()

    async def scene_by_id(self, session: AsyncSession, scene_id: UUID, *, for_update: bool = False) -> NtfScene | None:
        statement = select(NtfScene).where(NtfScene.id == scene_id, NtfScene.deleted_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return (await session.exec(statement)).first()

    async def scene_key_exists(self, session: AsyncSession, scene_key: str, *, exclude_id: UUID | None = None) -> bool:
        statement = select(NtfScene.id).where(NtfScene.scene_key == scene_key, NtfScene.deleted_at.is_(None))
        if exclude_id is not None:
            statement = statement.where(NtfScene.id != exclude_id)
        return (await session.exec(statement)).first() is not None

    async def list_scenes(
        self,
        session: AsyncSession,
        *,
        keyword: str | None,
        module_code: str | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[NtfScene], int]:
        conditions: list[Any] = [NtfScene.deleted_at.is_(None)]
        if keyword:
            kw = _like(keyword)
            conditions.append(or_(NtfScene.scene_key.ilike(kw), NtfScene.scene_name.ilike(kw), NtfScene.description.ilike(kw)))
        if module_code:
            conditions.append(NtfScene.module_code == module_code)
        if is_active is not None:
            conditions.append(NtfScene.is_active.is_(is_active))
        total = int((await session.exec(select(func.count()).select_from(NtfScene).where(*conditions))).one() or 0)
        rows = (
            await session.exec(
                _page(select(NtfScene).where(*conditions).order_by(NtfScene.module_code, NtfScene.scene_key), page, page_size)
            )
        ).all()
        return list(rows), total

    async def list_active_scenes(self, session: AsyncSession) -> list[NtfScene]:
        rows = await session.exec(
            select(NtfScene)
            .where(NtfScene.deleted_at.is_(None), NtfScene.is_active.is_(True))
            .order_by(NtfScene.module_code, NtfScene.scene_key)
        )
        return list(rows.all())

    async def active_channel_map(self, session: AsyncSession, scene_ids: list[UUID]) -> dict[UUID, list[str]]:
        if not scene_ids:
            return {}
        rows = (
            await session.exec(
                select(NtfSceneChannel.scene_id, NtfSceneChannel.channel_code)
                .where(NtfSceneChannel.scene_id.in_(scene_ids), NtfSceneChannel.is_active.is_(True))
                .order_by(NtfSceneChannel.channel_code)
            )
        ).all()
        result: dict[UUID, list[str]] = {}
        for scene_id, channel_code in rows:
            result.setdefault(scene_id, []).append(channel_code)
        return result

    async def scene_channels(self, session: AsyncSession, scene_id: UUID) -> list[NtfSceneChannel]:
        rows = await session.exec(select(NtfSceneChannel).where(NtfSceneChannel.scene_id == scene_id).order_by(NtfSceneChannel.channel_code))
        return list(rows.all())

    async def scene_templates(self, session: AsyncSession, scene_id: UUID, *, active_only: bool = False) -> list[NtfTemplate]:
        statement = select(NtfTemplate).where(NtfTemplate.scene_id == scene_id, NtfTemplate.deleted_at.is_(None))
        if active_only:
            statement = statement.where(NtfTemplate.is_active.is_(True))
        rows = await session.exec(statement.order_by(NtfTemplate.channel_code))
        return list(rows.all())

    async def scene_routes(self, session: AsyncSession, scene_id: UUID, *, active_only: bool = False) -> list[NtfRoute]:
        statement = select(NtfRoute).where(NtfRoute.scene_id == scene_id, NtfRoute.deleted_at.is_(None))
        if active_only:
            statement = statement.where(NtfRoute.is_active.is_(True))
        rows = await session.exec(statement.order_by(NtfRoute.created_at))
        return list(rows.all())

    def add(self, session: AsyncSession, row: Any) -> Any:
        session.add(row)
        return row

    async def flush(self, session: AsyncSession) -> None:
        await session.flush()

    async def commit(self, session: AsyncSession) -> None:
        await session.commit()

    async def upsert_channels(
        self, session: AsyncSession, scene_id: UUID, channels: list[dict[str, Any]], user_id: UUID | None
    ) -> None:
        """按渠道补齐；未出现在列表中的渠道停用。"""
        existing = {row.channel_code: row for row in await self.scene_channels(session, scene_id)}
        wanted = {item["channel_code"]: bool(item.get("is_active", True)) for item in channels}
        for code, active in wanted.items():
            row = existing.get(code)
            if row is None:
                session.add(NtfSceneChannel(scene_id=scene_id, channel_code=code, is_active=active, created_by=user_id, updated_by=user_id))
            elif row.is_active != active:
                row.is_active = active
                row.updated_by = user_id
                session.add(row)
        for code, row in existing.items():
            if code not in wanted and row.is_active:
                row.is_active = False
                row.updated_by = user_id
                session.add(row)

    async def upsert_templates(
        self, session: AsyncSession, scene_id: UUID, templates: list[dict[str, Any]], user_id: UUID | None
    ) -> None:
        """按渠道更新模板；未出现在列表中的模板软删除。"""
        existing = {row.channel_code: row for row in await self.scene_templates(session, scene_id)}
        fields = ("title_template", "content_template", "wechat_template_no", "data_mapping_config", "is_active")
        wanted: set[str] = set()
        for item in templates:
            code = item["channel_code"]
            wanted.add(code)
            row = existing.get(code)
            if row is None:
                session.add(
                    NtfTemplate(scene_id=scene_id, channel_code=code, created_by=user_id, updated_by=user_id, **{key: item.get(key) for key in fields if key in item})
                )
                continue
            for key in fields:
                if key in item:
                    setattr(row, key, item[key])
            row.updated_by = user_id
            session.add(row)
        now = utc_now()
        for code, row in existing.items():
            if code not in wanted:
                row.deleted_at = now
                row.deleted_by = user_id
                session.add(row)

    async def replace_routes(
        self, session: AsyncSession, scene_id: UUID, routes: list[dict[str, Any]], user_id: UUID | None
    ) -> None:
        await session.exec(delete(NtfRoute).where(NtfRoute.scene_id == scene_id))
        for item in routes:
            session.add(NtfRoute(scene_id=scene_id, created_by=user_id, updated_by=user_id, **item))

    async def soft_delete_scene(self, session: AsyncSession, scene: NtfScene, user_id: UUID | None) -> None:
        now = utc_now()
        scene.deleted_at = now
        scene.deleted_by = user_id
        scene.updated_by = user_id
        session.add(scene)
        await session.exec(
            update(NtfTemplate)
            .where(NtfTemplate.scene_id == scene.id, NtfTemplate.deleted_at.is_(None))
            .values(deleted_at=now, deleted_by=user_id)
        )
        await session.exec(
            update(NtfRoute).where(NtfRoute.scene_id == scene.id, NtfRoute.deleted_at.is_(None)).values(deleted_at=now, deleted_by=user_id)
        )

    # ───────── 路由目标展示与校验 ─────────
    async def roles_by_ids(self, session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, SysRole]:
        ids = list({item for item in ids if item})
        if not ids:
            return {}
        rows = await session.exec(select(SysRole).where(SysRole.id.in_(ids), SysRole.deleted_at.is_(None)))
        return {row.id: row for row in rows.all()}

    async def permissions_by_ids(self, session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, SysPermission]:
        ids = list({item for item in ids if item})
        if not ids:
            return {}
        rows = await session.exec(select(SysPermission).where(SysPermission.id.in_(ids), SysPermission.deleted_at.is_(None)))
        return {row.id: row for row in rows.all()}

    async def permission_by_key(self, session: AsyncSession, permission_key: str) -> SysPermission | None:
        return (
            await session.exec(
                select(SysPermission).where(SysPermission.permission_key == permission_key.strip(), SysPermission.deleted_at.is_(None))
            )
        ).first()

    async def users_by_ids(self, session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, SysUser]:
        ids = list({item for item in ids if item})
        if not ids:
            return {}
        rows = await session.exec(select(SysUser).where(SysUser.id.in_(ids), SysUser.deleted_at.is_(None)))
        return {row.id: row for row in rows.all()}

    async def route_options(self, session: AsyncSession) -> dict[str, list[Any]]:
        roles = (
            await session.exec(
                select(SysRole).where(SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)).order_by(SysRole.role_name)
            )
        ).all()
        permissions = (
            await session.exec(
                select(SysPermission)
                .where(SysPermission.deleted_at.is_(None), SysPermission.is_active.is_(True))
                .order_by(SysPermission.module_code, SysPermission.permission_key)
            )
        ).all()
        return {"roles": list(roles), "permissions": list(permissions)}

    async def search_users(self, session: AsyncSession, keyword: str | None, limit: int) -> list[SysUser]:
        statement = select(SysUser).where(SysUser.deleted_at.is_(None), SysUser.is_active.is_(True))
        if keyword:
            statement = statement.where(SysUser.display_name.ilike(_like(keyword)))
        rows = await session.exec(statement.order_by(SysUser.display_name).limit(limit))
        return list(rows.all())

    # ───────── 接收人解析 ─────────
    def _user_org_condition(self, org_id: UUID | None):
        if org_id is None:
            return None
        return or_(
            SysUser.org_id == org_id,
            exists(select(SysUserOrg.id).where(SysUserOrg.user_id == SysUser.id, SysUserOrg.org_id == org_id)),
        )

    async def _user_ids(self, session: AsyncSession, statement, org_id: UUID | None) -> set[UUID]:
        statement = statement.where(SysUser.deleted_at.is_(None), SysUser.is_active.is_(True))
        org_condition = self._user_org_condition(org_id)
        if org_condition is not None:
            statement = statement.where(org_condition)
        return set((await session.exec(statement.distinct())).all())

    async def active_user_ids(self, session: AsyncSession, user_ids: Iterable[UUID], org_id: UUID | None = None) -> set[UUID]:
        ids = list({item for item in user_ids if item})
        if not ids:
            return set()
        return await self._user_ids(session, select(SysUser.id).where(SysUser.id.in_(ids)), org_id)

    async def user_ids_by_role(self, session: AsyncSession, role_id: UUID, org_id: UUID | None = None) -> set[UUID]:
        statement = (
            select(SysUser.id)
            .join(SysUserRole, SysUserRole.user_id == SysUser.id)
            .join(SysRole, SysRole.id == SysUserRole.role_id)
            .where(SysUserRole.role_id == role_id, SysRole.deleted_at.is_(None), SysRole.is_active.is_(True))
        )
        return await self._user_ids(session, statement, org_id)

    async def user_ids_by_permission(self, session: AsyncSession, permission_id: UUID, org_id: UUID | None = None) -> set[UUID]:
        statement = (
            select(SysUser.id)
            .join(SysUserRole, SysUserRole.user_id == SysUser.id)
            .join(SysRole, SysRole.id == SysUserRole.role_id)
            .join(SysRolePermission, SysRolePermission.role_id == SysRole.id)
            .where(
                SysRolePermission.permission_id == permission_id,
                SysRole.deleted_at.is_(None),
                SysRole.is_active.is_(True),
            )
        )
        return await self._user_ids(session, statement, org_id)

    async def all_user_ids(self, session: AsyncSession, org_id: UUID | None = None) -> set[UUID]:
        return await self._user_ids(session, select(SysUser.id), org_id)

    async def root_org_id(self, session: AsyncSession) -> UUID | None:
        return (
            await session.exec(
                select(SysOrg.id).where(SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None)).order_by(SysOrg.created_at)
            )
        ).first()

    async def user_org_id(self, session: AsyncSession, user_id: UUID) -> UUID | None:
        return (await session.exec(select(SysUser.org_id).where(SysUser.id == user_id))).first()

    # ───────── 发送 ─────────
    async def notification_by_event_key(self, session: AsyncSession, event_key: str) -> UUID | None:
        return (await session.exec(select(NtfNotification.id).where(NtfNotification.event_key == event_key))).first()

    async def disabled_preferences(self, session: AsyncSession, scene_id: UUID, user_ids: list[UUID]) -> set[tuple[UUID, str]]:
        if not user_ids:
            return set()
        rows = (
            await session.exec(
                select(NtfPreference.user_id, NtfPreference.channel_code).where(
                    NtfPreference.scene_id == scene_id,
                    NtfPreference.user_id.in_(user_ids),
                    NtfPreference.is_enabled_by_user.is_(False),
                )
            )
        ).all()
        return {(user_id, channel_code) for user_id, channel_code in rows}

    async def active_bindings(self, session: AsyncSession, channel_code: str, user_ids: list[UUID]) -> dict[UUID, NtfChannelBinding]:
        if not user_ids:
            return {}
        rows = (
            await session.exec(
                select(NtfChannelBinding)
                .where(
                    NtfChannelBinding.user_id.in_(user_ids),
                    NtfChannelBinding.channel_code == channel_code,
                    NtfChannelBinding.is_active.is_(True),
                    NtfChannelBinding.deleted_at.is_(None),
                )
                .order_by(NtfChannelBinding.updated_at.desc())
            )
        ).all()
        result: dict[UUID, NtfChannelBinding] = {}
        for row in rows:
            result.setdefault(row.user_id, row)
        return result

    # ───────── 我的通知 ─────────
    def _message_scene_condition(self):
        excluded = non_message_inbox_scene_keys()
        return NtfScene.scene_key.not_in(excluded) if excluded else true()

    def _mine_conditions(self, user_id: UUID, status_code: str, scene_key: str | None) -> list[Any]:
        conditions: list[Any] = [NtfRecipient.user_id == user_id]
        if not scene_key or not is_family_inbox_scene(scene_key.strip()):
            conditions.append(self._message_scene_condition())
        if status_code == "all":
            conditions.append(NtfRecipient.status_code != "archived")
        else:
            conditions.append(NtfRecipient.status_code == status_code)
        if scene_key:
            conditions.append(NtfScene.scene_key == scene_key.strip())
        return conditions

    async def list_mine(
        self, session: AsyncSession, user_id: UUID, *, status_code: str, scene_key: str | None, page: int, page_size: int
    ) -> tuple[list[tuple[NtfRecipient, NtfNotification, str | None]], int]:
        conditions = self._mine_conditions(user_id, status_code, scene_key)
        base = (
            select(func.count())
            .select_from(NtfRecipient)
            .join(NtfNotification, NtfNotification.id == NtfRecipient.notification_id)
            .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
            .where(*conditions)
        )
        total = int((await session.exec(base)).one() or 0)
        rows = (
            await session.exec(
                _page(
                    select(NtfRecipient, NtfNotification, NtfScene.scene_key)
                    .join(NtfNotification, NtfNotification.id == NtfRecipient.notification_id)
                    .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
                    .where(*conditions)
                    .order_by(desc(NtfNotification.occurred_at), desc(NtfRecipient.created_at)),
                    page,
                    page_size,
                )
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    async def unread_count(self, session: AsyncSession, user_id: UUID) -> int:
        statement = (select(func.count()).select_from(NtfRecipient)
                     .join(NtfNotification, NtfNotification.id == NtfRecipient.notification_id)
                     .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
                     .where(*self._mine_conditions(user_id, "unread", None)))
        return int((await session.exec(statement)).one() or 0)

    async def recipient_for_user(self, session: AsyncSession, recipient_id: UUID, user_id: UUID) -> NtfRecipient | None:
        return (
            await session.exec(select(NtfRecipient).where(NtfRecipient.id == recipient_id, NtfRecipient.user_id == user_id))
        ).first()

    async def mine_detail(self, session: AsyncSession, recipient_id: UUID, user_id: UUID):
        return (await session.exec(
            select(NtfNotification).join(NtfRecipient, NtfRecipient.notification_id == NtfNotification.id)
            .where(NtfRecipient.id == recipient_id, NtfRecipient.user_id == user_id,
                   NtfRecipient.status_code != "archived")
        )).first()

    async def mark_all_read(self, session: AsyncSession, user_id: UUID) -> int:
        now = utc_now()
        message_ids = select(NtfNotification.id).join(
            NtfScene, NtfScene.id == NtfNotification.scene_id
        ).where(self._message_scene_condition(), NtfScene.scene_key.not_in(individual_read_scene_keys()))
        result = await session.exec(
            update(NtfRecipient)
            .where(NtfRecipient.user_id == user_id, NtfRecipient.status_code == "unread",
                   NtfRecipient.notification_id.in_(message_ids))
            .values(status_code="read", read_at=now, updated_at=now, updated_by=user_id)
        )
        return int(result.rowcount or 0)

    # ───────── 通知历史 ─────────
    async def list_notifications(self, session: AsyncSession, params: Any) -> tuple[list[tuple[NtfNotification, str]], int]:
        conditions: list[Any] = []
        if params.keyword:
            kw = _like(params.keyword)
            conditions.append(
                or_(
                    NtfNotification.title.ilike(kw),
                    NtfNotification.content.ilike(kw),
                    NtfNotification.scene_name_snapshot.ilike(kw),
                    NtfNotification.event_key.ilike(kw),
                    NtfScene.scene_key.ilike(kw),
                )
            )
        if params.scene_id:
            conditions.append(NtfNotification.scene_id == params.scene_id)
        if params.business_type_code:
            conditions.append(NtfNotification.business_type_code == params.business_type_code)
        if params.severity_code:
            conditions.append(NtfNotification.severity_code == params.severity_code)
        if params.status_code:
            conditions.append(NtfNotification.status_code == params.status_code)
        if params.occurred_start:
            conditions.append(NtfNotification.occurred_at >= params.occurred_start)
        if params.occurred_end:
            conditions.append(NtfNotification.occurred_at <= params.occurred_end)
        total = int(
            (
                await session.exec(
                    select(func.count()).select_from(NtfNotification).join(NtfScene, NtfScene.id == NtfNotification.scene_id).where(*conditions)
                )
            ).one()
            or 0
        )
        rows = (
            await session.exec(
                _page(
                    select(NtfNotification, NtfScene.scene_key)
                    .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
                    .where(*conditions)
                    .order_by(desc(NtfNotification.occurred_at)),
                    params.page,
                    params.page_size,
                )
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    async def recipient_stats(self, session: AsyncSession, notification_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
        if not notification_ids:
            return {}
        rows = (
            await session.exec(
                select(NtfRecipient.notification_id, func.count(NtfRecipient.id), func.count(NtfRecipient.read_at))
                .where(NtfRecipient.notification_id.in_(notification_ids))
                .group_by(NtfRecipient.notification_id)
            )
        ).all()
        return {nid: (int(total or 0), int(read or 0)) for nid, total, read in rows}

    async def delivery_stats(self, session: AsyncSession, notification_ids: list[UUID]) -> dict[UUID, dict[str, dict[str, int]]]:
        if not notification_ids:
            return {}
        rows = (
            await session.exec(
                select(NtfRecipient.notification_id, NtfDeliveryLog.channel_code, NtfDeliveryLog.status_code, func.count(NtfDeliveryLog.id))
                .join(NtfRecipient, NtfRecipient.id == NtfDeliveryLog.recipient_id)
                .where(NtfRecipient.notification_id.in_(notification_ids))
                .group_by(NtfRecipient.notification_id, NtfDeliveryLog.channel_code, NtfDeliveryLog.status_code)
            )
        ).all()
        result: dict[UUID, dict[str, dict[str, int]]] = {}
        for nid, channel, status_code, count in rows:
            result.setdefault(nid, {}).setdefault(channel, {})[status_code] = int(count or 0)
        return result

    async def list_recipients(
        self, session: AsyncSession, notification_id: UUID, *, status_code: str, page: int, page_size: int
    ) -> tuple[list[tuple[NtfRecipient, str | None]], int]:
        conditions: list[Any] = [NtfRecipient.notification_id == notification_id]
        if status_code != "all":
            conditions.append(NtfRecipient.status_code == status_code)
        total = int((await session.exec(select(func.count()).select_from(NtfRecipient).where(*conditions))).one() or 0)
        rows = (
            await session.exec(
                _page(
                    select(NtfRecipient, SysUser.display_name)
                    .outerjoin(SysUser, SysUser.id == NtfRecipient.user_id)
                    .where(*conditions)
                    .order_by(NtfRecipient.read_at.desc().nulls_last(), SysUser.display_name),
                    page,
                    page_size,
                )
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    async def list_delivery_logs(self, session: AsyncSession, params: Any) -> tuple[list[tuple], int]:
        conditions: list[Any] = []
        if params.keyword:
            kw = _like(params.keyword)
            conditions.append(
                or_(
                    NtfNotification.title.ilike(kw),
                    NtfScene.scene_key.ilike(kw),
                    NtfDeliveryLog.target_address.ilike(kw),
                    NtfDeliveryLog.error_message.ilike(kw),
                    SysUser.display_name.ilike(kw),
                )
            )
        if params.notification_id:
            conditions.append(NtfRecipient.notification_id == params.notification_id)
        if params.scene_id:
            conditions.append(NtfNotification.scene_id == params.scene_id)
        if params.channel_code:
            conditions.append(NtfDeliveryLog.channel_code == params.channel_code)
        if params.status_code:
            conditions.append(NtfDeliveryLog.status_code == params.status_code)
        if params.provider_code:
            conditions.append(NtfDeliveryLog.provider_code == params.provider_code)
        if params.created_start:
            conditions.append(NtfDeliveryLog.created_at >= params.created_start)
        if params.created_end:
            conditions.append(NtfDeliveryLog.created_at <= params.created_end)

        def joined(statement):
            return (
                statement.join(NtfRecipient, NtfRecipient.id == NtfDeliveryLog.recipient_id)
                .join(NtfNotification, NtfNotification.id == NtfRecipient.notification_id)
                .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
                .outerjoin(SysUser, SysUser.id == NtfRecipient.user_id)
                .where(*conditions)
            )

        total = int((await session.exec(joined(select(func.count()).select_from(NtfDeliveryLog)))).one() or 0)
        rows = (
            await session.exec(
                _page(
                    joined(select(NtfDeliveryLog, NtfRecipient, NtfNotification, NtfScene.scene_key, SysUser.display_name).select_from(NtfDeliveryLog)).order_by(
                        desc(NtfDeliveryLog.created_at)
                    ),
                    params.page,
                    params.page_size,
                )
            )
        ).all()
        return [tuple(row) for row in rows], total

    async def list_event_logs(self, session: AsyncSession, params: Any) -> tuple[list[tuple[NtfEventLog, str | None]], int]:
        conditions: list[Any] = []
        if params.keyword:
            kw = _like(params.keyword)
            conditions.append(
                or_(
                    NtfEventLog.message.ilike(kw),
                    NtfEventLog.business_type_code.ilike(kw),
                    NtfScene.scene_key.ilike(kw),
                    cast(NtfEventLog.payload, Text).ilike(kw),
                )
            )
        if params.scene_id:
            conditions.append(NtfEventLog.scene_id == params.scene_id)
        if params.business_type_code:
            conditions.append(NtfEventLog.business_type_code == params.business_type_code)
        if params.status_code:
            conditions.append(NtfEventLog.status_code == params.status_code)
        if params.created_start:
            conditions.append(NtfEventLog.created_at >= params.created_start)
        if params.created_end:
            conditions.append(NtfEventLog.created_at <= params.created_end)
        total = int(
            (
                await session.exec(
                    select(func.count()).select_from(NtfEventLog).outerjoin(NtfScene, NtfScene.id == NtfEventLog.scene_id).where(*conditions)
                )
            ).one()
            or 0
        )
        rows = (
            await session.exec(
                _page(
                    select(NtfEventLog, NtfScene.scene_key)
                    .outerjoin(NtfScene, NtfScene.id == NtfEventLog.scene_id)
                    .where(*conditions)
                    .order_by(desc(NtfEventLog.created_at)),
                    params.page,
                    params.page_size,
                )
            )
        ).all()
        return [tuple(row) for row in rows], total  # type: ignore[misc]

    # ───────── 投递 ─────────
    async def pending_deliveries(
        self, session: AsyncSession, channel_code: str, limit: int
    ) -> list[tuple[NtfDeliveryLog, NtfNotification, str]]:
        rows = (
            await session.exec(
                select(NtfDeliveryLog, NtfNotification, NtfScene.scene_key)
                .join(NtfRecipient, NtfRecipient.id == NtfDeliveryLog.recipient_id)
                .join(NtfNotification, NtfNotification.id == NtfRecipient.notification_id)
                .join(NtfScene, NtfScene.id == NtfNotification.scene_id)
                .where(NtfDeliveryLog.channel_code == channel_code, NtfDeliveryLog.status_code == "pending")
                .order_by(NtfDeliveryLog.created_at)
                .limit(limit)
                .with_for_update(of=NtfDeliveryLog, skip_locked=True)
            )
        ).all()
        return [tuple(row) for row in rows]  # type: ignore[misc]

    # ───────── 偏好 ─────────
    async def user_preferences(self, session: AsyncSession, user_id: UUID) -> dict[tuple[UUID, str], NtfPreference]:
        rows = await session.exec(select(NtfPreference).where(NtfPreference.user_id == user_id))
        return {(row.scene_id, row.channel_code): row for row in rows.all()}

    # ───────── 渠道绑定 ─────────
    async def user_bindings(self, session: AsyncSession, user_id: UUID) -> list[NtfChannelBinding]:
        rows = await session.exec(
            select(NtfChannelBinding)
            .where(NtfChannelBinding.user_id == user_id, NtfChannelBinding.deleted_at.is_(None))
            .order_by(NtfChannelBinding.channel_code, desc(NtfChannelBinding.updated_at))
        )
        return list(rows.all())

    async def binding_by_external(
        self, session: AsyncSession, *, channel_code: str, provider_code: str, appid: str, external_user_no: str
    ) -> NtfChannelBinding | None:
        return (
            await session.exec(
                select(NtfChannelBinding).where(
                    NtfChannelBinding.channel_code == channel_code,
                    NtfChannelBinding.provider_code == provider_code,
                    NtfChannelBinding.appid == appid,
                    NtfChannelBinding.external_user_no == external_user_no,
                    NtfChannelBinding.deleted_at.is_(None),
                )
            )
        ).first()

    async def deactivate_other_bindings(
        self, session: AsyncSession, *, user_id: UUID, channel_code: str, keep_id: UUID
    ) -> None:
        await session.exec(
            update(NtfChannelBinding)
            .where(
                NtfChannelBinding.user_id == user_id,
                NtfChannelBinding.channel_code == channel_code,
                NtfChannelBinding.id != keep_id,
                NtfChannelBinding.is_active.is_(True),
                NtfChannelBinding.deleted_at.is_(None),
            )
            .values(is_active=False, updated_at=utc_now(), updated_by=user_id)
        )

    async def binding_for_user(self, session: AsyncSession, binding_id: UUID, user_id: UUID) -> NtfChannelBinding | None:
        return (
            await session.exec(
                select(NtfChannelBinding).where(
                    NtfChannelBinding.id == binding_id, NtfChannelBinding.user_id == user_id, NtfChannelBinding.deleted_at.is_(None)
                )
            )
        ).first()



repository = NotificationCenterRepository()

__all__ = ["NotificationCenterRepository", "repository"]
