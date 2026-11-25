"""认证数据访问。

- public：登录账号、租户目录、账号可进入的租户；
- 当前租户 schema（调用方已切换 search_path）：租户内用户、角色、权限、组织授权、人员与身份。
租户由 schema 隔离，这里的业务表查询不带 tenant_id。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.data_scope import merge_data_scopes
from app.auth.models import AuthIdentity, AuthMembership, AuthTenant, AuthUser
from app.framework.db.models import utc_now
from app.integrations.redis_client import get_redis
from app.auth.identity_flags import identity_flags
from app.modules.masterdata.models import MdPerson
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_profile.models import SysUser, SysUserOrg
from app.modules.user_role.models import SysUserRole

LOGIN_CAPTCHA_KEY_PREFIX = "auth:login_captcha:"


@dataclass
class UserGrants:
    role_nos: list[str] = field(default_factory=list)
    role_names: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    data_scope_code: str = "organization"
    permission_scopes: dict[str, str] = field(default_factory=dict)


class AuthRepository:
    # ───────── 验证码（Redis） ─────────
    async def save_login_captcha(self, captcha_id: str, code: str, ttl_seconds: int) -> None:
        await get_redis().setex(f"{LOGIN_CAPTCHA_KEY_PREFIX}{captcha_id}", ttl_seconds, code.lower())

    async def consume_login_captcha(self, captcha_id: str) -> str | None:
        value = await get_redis().eval(
            "local v=redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]); end; return v",
            1,
            f"{LOGIN_CAPTCHA_KEY_PREFIX}{captcha_id}",
        )
        return str(value) if value is not None else None

    # ───────── 登录账号 ─────────
    async def get_auth_user(self, session: AsyncSession, auth_user_id: UUID) -> AuthUser | None:
        return await session.get(AuthUser, auth_user_id)

    async def find_auth_user_by_login(self, session: AsyncSession, *, email: str | None, mobile: str | None) -> AuthUser | None:
        if email:
            condition = func.lower(AuthUser.email) == email.lower()
        elif mobile:
            condition = AuthUser.mobile == mobile
        else:
            return None
        return (await session.exec(select(AuthUser).where(condition).limit(1))).scalars().first()

    async def find_auth_identity(
        self,
        session: AsyncSession,
        *,
        provider: str,
        appid: str,
        external_user_no: str,
    ) -> AuthIdentity | None:
        statement = select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.appid == appid,
            AuthIdentity.external_user_no == external_user_no,
        )
        return (await session.exec(statement.limit(1))).scalars().first()

    async def find_auth_identity_for_user(
        self,
        session: AsyncSession,
        *,
        provider: str,
        appid: str,
        auth_user_id: UUID,
    ) -> AuthIdentity | None:
        statement = select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.appid == appid,
            AuthIdentity.auth_user_id == auth_user_id,
        )
        return (await session.exec(statement.limit(1))).scalars().first()

    async def list_memberships(self, session: AsyncSession, auth_user_id: UUID) -> list[tuple[AuthMembership, AuthTenant]]:
        """账号可进入的、启用中的租户，最近进入的排在前面。"""
        statement = (
            select(AuthMembership, AuthTenant)
            .join(AuthTenant, AuthTenant.id == AuthMembership.tenant_id)
            .where(
                AuthMembership.auth_user_id == auth_user_id,
                AuthMembership.is_active.is_(True),
                AuthTenant.is_active.is_(True),
            )
            .order_by(AuthMembership.last_entered_at.desc().nulls_last(), AuthMembership.created_at)
        )
        return [(row[0], row[1]) for row in (await session.exec(statement)).all()]

    async def get_tenant(self, session: AsyncSession, tenant_id: UUID) -> AuthTenant | None:
        return await session.get(AuthTenant, tenant_id)

    async def get_membership(self, session: AsyncSession, auth_user_id: UUID, tenant_id: UUID) -> AuthMembership | None:
        statement = select(AuthMembership).where(
            AuthMembership.auth_user_id == auth_user_id,
            AuthMembership.tenant_id == tenant_id,
            AuthMembership.is_active.is_(True),
        )
        return (await session.exec(statement)).scalars().first()

    async def touch_membership(self, session: AsyncSession, membership: AuthMembership) -> None:
        membership.last_entered_at = utc_now()
        session.add(membership)

    # ───────── 租户内用户 ─────────
    async def get_tenant_user(self, session: AsyncSession, auth_user_id: UUID) -> SysUser | None:
        statement = select(SysUser).where(
            SysUser.auth_user_id == auth_user_id,
            SysUser.deleted_at.is_(None),
        )
        return (await session.exec(statement)).scalars().first()

    async def get_user_orgs(self, session: AsyncSession, user_id: UUID) -> list[SysUserOrg]:
        statement = (
            select(SysUserOrg)
            .where(SysUserOrg.user_id == user_id)
            .order_by(SysUserOrg.is_primary.desc(), SysUserOrg.created_at)
        )
        return list((await session.exec(statement)).scalars().all())

    async def get_person(self, session: AsyncSession, user_id: UUID) -> MdPerson | None:
        statement = select(MdPerson).where(
            MdPerson.user_id == user_id,
            MdPerson.deleted_at.is_(None),
        )
        return (await session.exec(statement)).scalars().first()

    async def get_identity_flags(self, session: AsyncSession, party_id: UUID | None, *, enabled_plugin_keys: set[str] | frozenset[str] = frozenset()) -> tuple[bool, bool]:
        """人员在本租户是否有监护人、教师身份（按身份数据判断门户，不按角色判断）；判断由上层模块登记（identity_flags）。"""
        flags = await identity_flags(session, party_id, enabled_plugin_keys=enabled_plugin_keys)
        return flags.get("guardian", False), flags.get("teacher", False)

    async def get_grants(self, session: AsyncSession, user_id: UUID, blocked_module_codes: set[str] | None = None) -> UserGrants:
        """用户经 sys_user_role → sys_role → sys_role_permission → sys_permission 获得的权限与数据范围。"""
        role_rows = (
            await session.exec(
                select(SysRole.id, SysRole.role_no, SysRole.role_name, SysRole.data_scope_code)
                .join(SysUserRole, SysUserRole.role_id == SysRole.id)
                .where(
                    SysUserRole.user_id == user_id,
                    SysRole.is_active.is_(True),
                    SysRole.deleted_at.is_(None),
                )
                .order_by(SysRole.role_no)
            )
        ).all()
        if not role_rows:
            return UserGrants()
        role_ids = [row.id for row in role_rows]
        permission_statement = (
            select(
                    SysPermission.permission_key,
                    func.coalesce(SysRolePermission.data_scope_code, SysRole.data_scope_code).label("data_scope_code"),
                )
                .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
                .join(SysRole, SysRole.id == SysRolePermission.role_id)
                .where(
                    SysRolePermission.role_id.in_(role_ids),
                    SysPermission.is_active.is_(True),
                    SysPermission.deleted_at.is_(None),
                )
        )
        if blocked_module_codes:
            permission_statement = permission_statement.where(SysPermission.module_code.not_in(blocked_module_codes))
        permission_rows = (await session.exec(permission_statement)).all()
        scopes: dict[str, list[str]] = {}
        for row in permission_rows:
            scopes.setdefault(row.permission_key, []).append(row.data_scope_code)
        return UserGrants(
            role_nos=[row.role_no for row in role_rows],
            role_names=[row.role_name for row in role_rows],
            permissions=sorted(scopes),
            data_scope_code=merge_data_scopes([row.data_scope_code for row in role_rows]),
            permission_scopes={key: merge_data_scopes(values) for key, values in scopes.items()},
        )

    async def extend_grants(self, session, user, grants, enabled_plugin_keys):
        """按已启用插件补充动态功能授权；只接纳目录中启用的权限，沿用原有范围合并。"""
        from app.framework.catalog import iter_module_attr
        from app.framework.plugin import loaded_plugin_manifests
        modules = {name for manifest in loaded_plugin_manifests() if manifest.key in enabled_plugin_keys
                   for name in manifest.module_names}
        extra = {}
        for module in iter_module_attr("auth_grants", only=modules):
            for key, scope in (await module.permission_scopes(session, user)).items():
                extra.setdefault(key, []).append(scope)
        if not extra:
            return grants
        active = (await session.exec(select(SysPermission.permission_key).where(
            SysPermission.permission_key.in_(extra), SysPermission.is_active.is_(True),
            SysPermission.deleted_at.is_(None)))).all()
        for key, in active:
            previous = [grants.permission_scopes[key]] if key in grants.permission_scopes else []
            grants.permission_scopes[key] = merge_data_scopes([*previous, *extra[key]])
        grants.permissions = sorted(grants.permission_scopes)
        return grants

    async def record_login_failure(self, session: AsyncSession, user: AuthUser, *, threshold: int, lock_until: datetime) -> None:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= threshold:
            user.locked_until = lock_until
        session.add(user)
        await session.commit()

    async def reset_login_failures(self, session: AsyncSession, user: AuthUser) -> None:
        if user.failed_login_count or user.locked_until is not None:
            user.failed_login_count = 0
            user.locked_until = None
            session.add(user)

    @staticmethod
    def profile_payload(sys_user: SysUser, person: MdPerson | None, auth_user: AuthUser) -> dict[str, Any]:
        return {
            "user_id": str(sys_user.id),
            "auth_user_id": str(auth_user.id),
            "display_name": sys_user.display_name,
            "full_name": person.full_name if person else sys_user.display_name,
            "avatar_url": sys_user.avatar_url,
            "email": auth_user.email,
            "mobile": auth_user.mobile,
            "is_password_change_required": auth_user.is_password_change_required,
        }


repository = AuthRepository()
