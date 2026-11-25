"""身份标志扩展点（L1）。

门户按身份数据判断（如“是否监护人”“是否教师”），而不是按角色判断。这些身份属于上层（如 L3 教育），
L1 不引用上层的表：由上层模块用 register_identity_flag 登记判断函数，认证时逐个调用。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

IdentityFlagProvider = Callable[[AsyncSession, UUID], Awaitable[bool]]
_providers: dict[str, IdentityFlagProvider] = {}


def register_identity_flag(name: str, provider: IdentityFlagProvider) -> None:
    _providers[name] = provider


async def identity_flags(session: AsyncSession, party_id: UUID | None, *, enabled_plugin_keys: set[str] | frozenset[str] = frozenset()) -> dict[str, bool]:
    if party_id is None:
        return {name: False for name in _providers}
    from app.framework.plugin_manifest import builtin_plugin_manifests

    owners = {module: item.key for item in builtin_plugin_manifests() for module in item.module_names}
    flags = {}
    for name, provider in _providers.items():
        parts = provider.__module__.split('.')
        owner = owners.get(parts[2]) if parts[:2] == ['app', 'modules'] and len(parts) > 2 else None
        # A deployed plugin may not yet have tables in this tenant. Do not call
        # its provider until provisioning and activation are complete.
        flags[name] = bool(await provider(session, party_id)) if owner is None or owner in enabled_plugin_keys else False
    return flags
