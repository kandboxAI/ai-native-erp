"""公告：发布、接收范围、阅读记录、首页显示。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context

from .models import NtfNotice, NtfNoticeTarget
from .repository import repository
from .schemas import NoticeCreate, NoticeItem, NoticeListQuery, NoticeReaderItem, NoticeReaderListQuery, NoticeUpdate

NOTICE_TYPES = {"notice", "announcement"}
NOTICE_STATUSES = {"draft", "published", "offline"}
NOTICE_FIELDS = ("title", "summary", "notice_type_code", "is_shown_on_home", "status_code")


def _bad_request(message: str) -> AppException:
    return AppException(message, status_code=status.HTTP_400_BAD_REQUEST)


def _check(data: dict[str, Any]) -> None:
    if data.get("notice_type_code") is not None and data["notice_type_code"] not in NOTICE_TYPES:
        raise _bad_request("无效的公告类型")
    if data.get("status_code") is not None and data["status_code"] not in NOTICE_STATUSES:
        raise _bad_request("无效的公告状态")
    if "title" in data and not (data["title"] or "").strip():
        raise _bad_request("标题不能为空")


def _publisher_name(user: AuthenticatedUser) -> str:
    profile = user.profile or {}
    name = profile.get("full_name") or user.display_name or profile.get("display_name") or (user.email or "").split("@")[0]
    return str(name or "系统")[:128]


def _stamp_publish(notice: NtfNotice, user: AuthenticatedUser, previous_status: str | None) -> None:
    if notice.status_code == "published" and (previous_status != "published" or notice.published_at is None):
        notice.published_at = utc_now()
        notice.published_by = user.user_id
        notice.publisher_name_snapshot = _publisher_name(user)


def _target_scope(targets: list[NtfNoticeTarget]) -> str:
    kinds = {row.target_type_code for row in targets}
    if not kinds or "all" in kinds:
        return "all"
    if kinds == {"role"}:
        return "role"
    if kinds == {"user"}:
        return "user"
    return "mixed"


async def _items(session, rows: list[tuple[NtfNotice, Any]]) -> list[NoticeItem]:
    targets = await repository.targets(session, [notice.id for notice, _ in rows])
    role_ids = [t.role_id for items in targets.values() for t in items if t.role_id]
    user_ids = [t.user_id for items in targets.values() for t in items if t.user_id]
    roles = await repository.roles(session, role_ids)
    users = await repository.users(session, user_ids)
    result = []
    for notice, read_at in rows:
        notice_targets = targets.get(notice.id, [])
        total, read = await repository.audience_stats(session, notice.id)
        role_targets = [t.role_id for t in notice_targets if t.role_id]
        user_targets = [t.user_id for t in notice_targets if t.user_id]
        result.append(
            NoticeItem.model_validate(
                {
                    **notice.model_dump(),
                    "target_scope": _target_scope(notice_targets),
                    "target_role_ids": role_targets,
                    "target_user_ids": user_targets,
                    "target_roles": [
                        {"id": str(r.id), "role_no": r.role_no, "role_name": r.role_name} for rid in role_targets if (r := roles.get(rid))
                    ],
                    "target_users": [{"id": str(u.id), "display_name": u.display_name} for uid in user_targets if (u := users.get(uid))],
                    "is_read": read_at is not None,
                    "read_at": read_at,
                    "read_count": read,
                    "unread_count": max(total - read, 0),
                }
            )
        )
    return result


async def _validate_targets(session, scope: str, role_ids: list[UUID], user_ids: list[UUID]) -> tuple[list[UUID], list[UUID]]:
    role_ids = list(dict.fromkeys(role_ids)) if scope in {"role", "mixed"} else []
    user_ids = list(dict.fromkeys(user_ids)) if scope in {"user", "mixed"} else []
    if len(await repository.roles(session, role_ids)) != len(role_ids):
        raise _bad_request("接收角色不存在")
    if len(await repository.users(session, user_ids, active_only=True)) != len(user_ids):
        raise _bad_request("接收用户不存在或已停用")
    return role_ids, user_ids


class NoticeService:
    async def list(self, params: NoticeListQuery, user: AuthenticatedUser, *, mine: bool) -> dict[str, Any]:
        async with get_session_context() as session:
            rows, total = await repository.list(session, params, user, mine=mine)
            items = await _items(session, rows)
        return {"items": [item.model_dump(mode="json") for item in items], "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, notice_id: UUID, user: AuthenticatedUser, *, mine: bool = False) -> NoticeItem | None:
        async with get_session_context() as session:
            notice = await repository.get(session, notice_id, user, action=None if mine else "detail")
            if notice is None:
                return None
            read_at = await repository.read_at(session, notice.id, user.user_id)
            return (await _items(session, [(notice, read_at)]))[0]

    async def create(self, payload: NoticeCreate, user: AuthenticatedUser) -> NoticeItem:
        data = payload.model_dump(include=set(NOTICE_FIELDS))
        _check(data)
        org_id = resolve_write_org_id(user, payload.org_id, "notice_announcement:create")
        async with get_session_context() as session:
            role_ids, user_ids = await _validate_targets(session, payload.target_scope, payload.target_role_ids, payload.target_user_ids)
            notice = repository.add(session, NtfNotice(org_id=org_id, created_by=user.user_id, updated_by=user.user_id, **data))
            notice.title = notice.title.strip()
            _stamp_publish(notice, user, None)
            await session.flush()
            await repository.replace_targets(session, notice, scope=payload.target_scope, role_ids=role_ids, user_ids=user_ids, by=user.user_id)
            await session.commit()
            notice_id = notice.id
        item = await self.detail(notice_id, user)
        assert item is not None
        return item

    async def update(self, notice_id: UUID, payload: NoticeUpdate, user: AuthenticatedUser) -> NoticeItem | None:
        data = payload.model_dump(exclude_unset=True)
        _check(data)
        async with get_session_context() as session:
            notice = await repository.get(session, notice_id, user, action="update", for_update=True)
            if notice is None:
                return None
            previous_status = notice.status_code
            for field in NOTICE_FIELDS:
                if field in data and (data[field] is not None or field == "summary"):
                    setattr(notice, field, data[field])
            if data.get("org_id"):
                notice.org_id = resolve_write_org_id(user, data["org_id"], "notice_announcement:update")
            _stamp_publish(notice, user, previous_status)
            notice.updated_by = user.user_id
            notice.updated_at = utc_now()
            repository.add(session, notice)
            if payload.target_scope is not None:
                role_ids, user_ids = await _validate_targets(
                    session, payload.target_scope, payload.target_role_ids or [], payload.target_user_ids or []
                )
                await repository.replace_targets(session, notice, scope=payload.target_scope, role_ids=role_ids, user_ids=user_ids, by=user.user_id)
            await session.commit()
        return await self.detail(notice_id, user)

    async def delete(self, notice_id: UUID, user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            notice = await repository.get(session, notice_id, user, action="delete", for_update=True)
            if notice is None:
                return False
            notice.deleted_at = utc_now()
            notice.deleted_by = user.user_id
            notice.updated_by = user.user_id
            repository.add(session, notice)
            await session.commit()
            return True

    async def mark_read(self, notice_id: UUID, user: AuthenticatedUser) -> NoticeItem | None:
        async with get_session_context() as session:
            notice = await repository.get(session, notice_id, user, action=None)
            if notice is None:
                return None
            await repository.mark_read(session, notice, user.user_id)
            await session.commit()
        return await self.detail(notice_id, user, mine=True)

    async def mark_all_read(self, user: AuthenticatedUser) -> int:
        async with get_session_context() as session:
            count = 0
            for notice in await repository.unread_published(session, user.user_id):
                count += await repository.mark_read(session, notice, user.user_id)
            await session.commit()
            return count

    async def target_options(self, keyword: str | None, limit: int) -> dict[str, Any]:
        async with get_session_context() as session:
            roles = await repository.role_options(session)
            users = await repository.user_options(session, keyword, limit)
        return {
            "roles": [{"id": str(r.id), "role_no": r.role_no, "role_name": r.role_name} for r in roles],
            "users": [{"id": str(u.id), "display_name": u.display_name} for u in users],
        }

    async def list_readers(self, notice_id: UUID, params: NoticeReaderListQuery, user: AuthenticatedUser) -> dict[str, Any] | None:
        async with get_session_context() as session:
            if await repository.get(session, notice_id, user, action="list") is None:
                return None
            rows, total = await repository.list_readers(
                session, notice_id, read_status=params.read_status, page=params.page, page_size=params.page_size
            )
        items = [
            NoticeReaderItem(user_id=uid, display_name=name or "—", is_read=read_at is not None, read_at=read_at).model_dump(mode="json")
            for uid, name, read_at in rows
        ]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


service = NoticeService()
