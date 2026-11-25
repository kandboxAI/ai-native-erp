from __future__ import annotations

from collections.abc import Callable

from app.integrations.redis_client import get_redis

from .qr_login_models import EmployeeQrLoginSessionRecord


class EmployeeQrLoginRepository:
    SESSION_PREFIX = "auth:employee_qr_login:session:"
    SCENE_PREFIX = "auth:employee_qr_login:scene:"

    async def create(self, record: EmployeeQrLoginSessionRecord, ttl: int) -> None:
        redis = get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(f"{self.SESSION_PREFIX}{record.session_id}", record.model_dump_json(), ex=ttl, nx=True)
            pipe.set(f"{self.SCENE_PREFIX}{record.scene}", record.session_id, ex=ttl, nx=True)
            results = await pipe.execute()
        if not all(results):
            await redis.delete(f"{self.SESSION_PREFIX}{record.session_id}", f"{self.SCENE_PREFIX}{record.scene}")
            raise RuntimeError("qr login session collision")

    async def get(self, session_id: str) -> EmployeeQrLoginSessionRecord | None:
        raw = await get_redis().get(f"{self.SESSION_PREFIX}{session_id}")
        return EmployeeQrLoginSessionRecord.model_validate_json(raw) if raw else None

    async def get_by_scene(self, scene: str) -> EmployeeQrLoginSessionRecord | None:
        session_id = await get_redis().get(f"{self.SCENE_PREFIX}{scene}")
        return await self.get(str(session_id)) if session_id else None

    async def ttl(self, session_id: str) -> int:
        return max(0, int(await get_redis().ttl(f"{self.SESSION_PREFIX}{session_id}")))

    async def transition(self, session_id: str, *, allowed: set[str], mutate: Callable) -> tuple[EmployeeQrLoginSessionRecord | None, bool]:
        redis = get_redis()
        key = f"{self.SESSION_PREFIX}{session_id}"
        for _ in range(4):
            async with redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if not raw:
                        return None, False
                    record = EmployeeQrLoginSessionRecord.model_validate_json(raw)
                    if record.status not in allowed:
                        return record, False
                    ttl = await pipe.ttl(key)
                    if ttl <= 0:
                        return None, False
                    mutate(record)
                    pipe.multi()
                    pipe.set(key, record.model_dump_json(), ex=ttl)
                    await pipe.execute()
                    return record, True
                except Exception as exc:
                    if exc.__class__.__name__ != "WatchError":
                        raise
        return await self.get(session_id), False


repository = EmployeeQrLoginRepository()
