from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.auth.token import revoke_all_refresh_tokens
from app.integrations.redis_client import get_redis

ONLINE_ZSET_KEY = "online_users"
ONLINE_DETAIL_PREFIX = "online:detail:"
SESSION_REVOKED_PREFIX = "session:revoked:"


@dataclass
class OnlineUser:
    """在线用户快照：按登录账号（public.auth_user.id）记录；role_nos 仅用于展示。"""

    auth_user_id: UUID
    email: str | None
    role_nos: list[str]
    last_seen_at: datetime
    display_name: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


def _serialize_online_user(user: OnlineUser) -> dict[str, object]:
    return {
        "auth_user_id": str(user.auth_user_id),
        "email": user.email,
        "role_nos": user.role_nos,
        "last_seen_at": user.last_seen_at.isoformat(),
        "display_name": user.display_name,
        "ip_address": user.ip_address or "",
        "user_agent": user.user_agent or "",
    }


class OnlineUserRegistry:
    """会话与在线状态都按登录账号 auth_user_id 记录（一个账号的会话跨租户统一吊销）。"""

    async def is_session_revoked(self, auth_user_id: UUID) -> bool:
        redis = get_redis()
        return bool(await redis.exists(f"{SESSION_REVOKED_PREFIX}{auth_user_id}"))

    async def clear_session_revocation(self, auth_user_id: UUID) -> None:
        redis = get_redis()
        await redis.delete(f"{SESSION_REVOKED_PREFIX}{auth_user_id}")

    async def kick_user(self, auth_user_id: UUID, ttl_seconds: int = 86400) -> None:
        redis = get_redis()
        key = str(auth_user_id)
        await redis.setex(f"{SESSION_REVOKED_PREFIX}{auth_user_id}", ttl_seconds, "1")
        await redis.zrem(ONLINE_ZSET_KEY, key)
        await redis.delete(f"{ONLINE_DETAIL_PREFIX}{auth_user_id}")
        await revoke_all_refresh_tokens(auth_user_id)

    async def touch(
        self,
        auth_user_id: UUID,
        email: str | None,
        role_nos: list[str],
        *,
        display_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        redis = get_redis()
        now = datetime.now(UTC)
        user = OnlineUser(
            auth_user_id=auth_user_id,
            email=email,
            role_nos=role_nos,
            last_seen_at=now,
            display_name=display_name,
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(user_agent or "")[:512] or None,
        )
        detail_ttl_seconds = 35 * 60
        await redis.setex(
            f"{ONLINE_DETAIL_PREFIX}{auth_user_id}",
            detail_ttl_seconds,
            json.dumps(_serialize_online_user(user), ensure_ascii=False),
        )
        await redis.zadd(ONLINE_ZSET_KEY, {str(auth_user_id): time.time()})

    async def list_active(self, ttl_minutes: int = 30) -> list[dict[str, object]]:
        redis = get_redis()
        threshold = time.time() - ttl_minutes * 60
        auth_user_ids = await redis.zrangebyscore(ONLINE_ZSET_KEY, threshold, "+inf")
        items: list[dict[str, object]] = []
        for auth_user_id in reversed(auth_user_ids):
            raw = await redis.get(f"{ONLINE_DETAIL_PREFIX}{auth_user_id}")
            if raw:
                try:
                    items.append(json.loads(raw))
                    continue
                except json.JSONDecodeError:
                    pass
            items.append({"auth_user_id": auth_user_id})
        return items

    async def prune_stale_online_snapshots(self, ttl_minutes: int = 35) -> int:
        redis = get_redis()
        threshold = time.time() - ttl_minutes * 60
        stale_ids = await redis.zrangebyscore(ONLINE_ZSET_KEY, "-inf", threshold)
        if stale_ids:
            detail_keys = [f"{ONLINE_DETAIL_PREFIX}{user_id}" for user_id in stale_ids]
            await redis.delete(*detail_keys)
        removed = await redis.zremrangebyscore(ONLINE_ZSET_KEY, "-inf", threshold)
        return int(removed or 0)


@dataclass
class ScheduledJob:
    name: str
    cron: str
    description: str
    enabled: bool = True


class SchedulerRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}

    def register(self, name: str, cron: str, description: str, enabled: bool = True) -> None:
        self._jobs[name] = ScheduledJob(name=name, cron=cron, description=description, enabled=enabled)

    def bootstrap_defaults(self) -> None:
        if self._jobs:
            return
        self.register("sync-role-cache", "*/10 * * * *", "同步角色与权限缓存占位任务")
        self.register("clean-online-users", "*/5 * * * *", "清理在线用户快照占位任务")

    def list_jobs(self) -> list[dict[str, object]]:
        return [asdict(job) for job in self._jobs.values()]


online_user_registry = OnlineUserRegistry()
scheduler_registry = SchedulerRegistry()
