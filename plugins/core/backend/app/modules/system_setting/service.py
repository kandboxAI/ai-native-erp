from __future__ import annotations

from app.auth.schemas import AuthenticatedUser
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import DEFAULT_SETTINGS, repository


class SystemSettingService(CrudService):
    async def seed_defaults(self, current_user: AuthenticatedUser) -> dict[str, int]:
        async with get_session_context() as session:
            created = await repository.ensure_defaults(session, current_user.user_id)
            await session.commit()
        return {"created": created}

    async def get_raw(self, setting_key: str, default: str | None = None) -> str | None:
        """读取参数值（会话须在租户上下文中）；未配置或停用时取代码默认值，再取 default。"""
        async with get_session_context() as session:
            row = await repository.get_by_key(session, setting_key)
        if row is not None and row.is_active:
            return row.setting_value
        fallback = next((item for item in DEFAULT_SETTINGS if item["setting_key"] == setting_key), None)
        return fallback["setting_value"] if fallback else default

    async def get_bool(self, setting_key: str, *, default: bool = False) -> bool:
        raw = await self.get_raw(setting_key, "true" if default else "false")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}

    async def get_int(self, setting_key: str, *, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
        try:
            value = int(float(str(await self.get_raw(setting_key, str(default))).strip()))
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value


service = SystemSettingService(repository=repository, session_getter=get_session_context)
