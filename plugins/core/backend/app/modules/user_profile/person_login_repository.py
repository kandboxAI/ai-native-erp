"""人员账号联动的数据访问；不包含任何行业身份规则。"""
from sqlalchemy import select, text, func
from uuid import UUID

from app.auth.models import AuthMembership, AuthUser
from app.auth.scope_filters import scoped_conditions
from app.modules.role.models import SysRole
from .models import SysUser
from app.modules.user_role.models import SysUserRole
from app.framework.db.models import utc_now


class PersonLoginRepository:
    async def user_by_id(self, session, user_id):
        return await session.get(SysUser, UUID(str(user_id)))

    async def user_roles(self, session, user_id):
        return set((await session.execute(select(SysRole.role_no).join(
            SysUserRole, SysUserRole.role_id == SysRole.id).where(
            SysUserRole.user_id == user_id, SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)))).scalars())

    async def lock_email(self, session, email):
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "person-login-email:" + email})

    async def auth_by_email(self, session, email):
        return (await session.execute(select(AuthUser).where(func.lower(AuthUser.email) == email))).scalars().first()

    async def update_email(self, session, auth, email, actor_id):
        auth.email = email
        auth.is_email_verified = False
        auth.updated_by = actor_id
        auth.updated_at = utc_now()
        session.add(auth)
        await session.flush()

    async def active_roles(self, session, role_nos):
        return set((await session.execute(select(SysRole.role_no).where(
            SysRole.role_no.in_(role_nos), SysRole.deleted_at.is_(None), SysRole.is_active.is_(True)))).scalars())

    async def lock_mobile(self, session, mobile):
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                  {"key": "person-login:" + mobile})

    async def auth_by_mobile(self, session, mobile):
        return (await session.execute(select(AuthUser).where(AuthUser.mobile == mobile).with_for_update())).scalars().first()

    async def membership(self, session, auth_user_id, tenant_id):
        return (await session.execute(select(AuthMembership).where(
            AuthMembership.auth_user_id == auth_user_id, AuthMembership.tenant_id == tenant_id).with_for_update())).scalars().first()

    async def user_by_auth(self, session, auth_user_id):
        # 包含历史删除记录，重新开通前仍须核对身份和学校维护范围。
        return (await session.execute(select(SysUser).where(
            SysUser.auth_user_id == auth_user_id).order_by(SysUser.deleted_at.asc().nulls_first(), SysUser.created_at.desc()).with_for_update())).scalars().first()

    async def accessible_user(self, session, user_id, actor, permission, *, include_deleted=False):
        return (await session.execute(select(SysUser).where(
            SysUser.id == user_id, *scoped_conditions(SysUser, actor, permission,
                include_deleted=include_deleted)).with_for_update())).scalars().first()

    async def reactivate_membership(self, session, membership, actor_id):
        membership.is_active = True
        membership.updated_by = actor_id
        membership.updated_at = utc_now()
        session.add(membership)
        await session.flush()

    async def auth_for_user(self, session, user):
        return await session.get(AuthUser, user.auth_user_id)

    async def account_briefs(self, session, user_ids):
        if not user_ids:
            return {}
        rows = (await session.execute(select(SysUser, AuthUser).join(
            AuthUser, AuthUser.id == SysUser.auth_user_id).where(SysUser.id.in_(user_ids)))).all()
        return {user.id: {"email": auth.email, "login_mobile_masked": (auth.mobile[:3] + "****" + auth.mobile[-4:]) if auth.mobile and len(auth.mobile) >= 7 else "***",
                          "account_status": "active" if user.is_active and auth.is_active and user.deleted_at is None else "disabled"}
                for user, auth in rows}


repository = PersonLoginRepository()
