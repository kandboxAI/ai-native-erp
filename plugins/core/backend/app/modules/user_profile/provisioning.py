"""开通租户内用户：登录账号（public）+ 租户成员关系 + 租户内用户 + 人员 + 主组织 + 角色。

供用户管理、租户开通、各模块演示数据复用。调用时会话须已切换到目标租户 schema（use_tenant_schema）。
可重复执行：已存在的账号、用户、人员不重复创建，也不覆盖已有密码。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import AuthMembership, AuthUser
from app.auth.password import hash_password
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.masterdata.models import MdParty, MdPerson
from app.modules.role.models import SysRole
from app.modules.user_profile.models import SysUser, SysUserOrg
from app.modules.user_role.models import SysUserRole


async def ensure_auth_user(session: AsyncSession, *, email: str | None = None, mobile: str | None = None,
                           password: str, is_password_change_required: bool = False,
                           require_new: bool = False, created_by: UUID | None = None) -> AuthUser:
    if not email and not mobile:
        raise ValueError("email 或 mobile 至少提供一个")
    condition = AuthUser.email == email.strip().lower() if email else AuthUser.mobile == mobile
    user = (await session.exec(select(AuthUser).where(condition))).scalars().first()
    if user is not None and require_new:
        raise AppException("该登录账号已被使用，请核对手机号或邮箱", status_code=409)
    if user is None:
        user = AuthUser(
            email=email.strip().lower() if email else None,
            mobile=mobile,
            password_hash=hash_password(password),
            is_email_verified=bool(email),
            password_changed_at=utc_now(),
            is_password_change_required=is_password_change_required,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(user)
        await session.flush()
    return user


async def ensure_membership(session: AsyncSession, auth_user_id: UUID, tenant_id: UUID, *, created_by: UUID | None = None) -> None:
    exists = (
        await session.exec(
            select(AuthMembership.id).where(AuthMembership.auth_user_id == auth_user_id, AuthMembership.tenant_id == tenant_id)
        )
    ).scalars().first()
    if exists is None:
        session.add(AuthMembership(auth_user_id=auth_user_id, tenant_id=tenant_id, created_by=created_by, updated_by=created_by))


async def ensure_person_for_user(session: AsyncSession, user: SysUser, *, full_name: str, created_by: UUID | None = None) -> MdPerson:
    person = (await session.exec(select(MdPerson).where(MdPerson.user_id == user.id, MdPerson.deleted_at.is_(None)))).scalars().first()
    if person is None:
        party = MdParty(party_type_code="person", display_name=full_name, created_by=created_by, updated_by=created_by)
        session.add(party)
        await session.flush()
        person = MdPerson(party_id=party.id, full_name=full_name, user_id=user.id, created_by=created_by, updated_by=created_by)
        session.add(person)
        await session.flush()
    return person


async def assign_roles(session: AsyncSession, user_id: UUID, role_nos: list[str], *, created_by: UUID | None = None) -> None:
    if not role_nos:
        return
    roles = (await session.exec(select(SysRole).where(SysRole.role_no.in_(role_nos), SysRole.deleted_at.is_(None)))).scalars().all()
    have = set((await session.exec(select(SysUserRole.role_id).where(SysUserRole.user_id == user_id))).scalars().all())
    for role in roles:
        if role.id not in have:
            session.add(SysUserRole(user_id=user_id, role_id=role.id, created_by=created_by, updated_by=created_by))


async def ensure_tenant_user(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    org_id: UUID,
    display_name: str,
    password: str,
    email: str | None = None,
    mobile: str | None = None,
    role_nos: list[str] | None = None,
    department_id: UUID | None = None,
    org_access_mode_code: str = "primary_only",
    created_by: UUID | None = None,
    auth_actor_id: UUID | None = None,
    person: MdPerson | None = None,
    is_password_change_required: bool = False,
    require_new_account: bool = False,
) -> tuple[SysUser, MdPerson]:
    """确保账号与租户身份，返回（租户内用户, 人员）。tenant_id为public.auth_tenant.id。

    person用于关联已建档人员，不另建MdParty/MdPerson；冲突与停用不自动覆盖。
    首次改密选项仅用于新账号，现有账号的密码和改密状态保持。
    """
    if person is not None and person.deleted_at is not None:
        raise AppException("人员已删除，不能关联登录账号", status_code=409)
    auth_user = await ensure_auth_user(session, email=email, mobile=mobile, password=password,
        is_password_change_required=is_password_change_required, require_new=require_new_account, created_by=auth_actor_id)
    await ensure_membership(session, auth_user.id, tenant_id, created_by=auth_actor_id)
    user = (await session.exec(select(SysUser).where(SysUser.auth_user_id == auth_user.id, SysUser.deleted_at.is_(None)))).scalars().first()
    if user is None:
        user = SysUser(
            org_id=org_id,
            auth_user_id=auth_user.id,
            display_name=display_name,
            department_id=department_id,
            org_access_mode_code=org_access_mode_code,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(user)
        await session.flush()
        session.add(SysUserOrg(org_id=org_id, user_id=user.id, access_type_code="primary", is_primary=True, created_by=created_by, updated_by=created_by))
    if person is None:
        person = await ensure_person_for_user(session, user, full_name=display_name, created_by=created_by)
    else:
        holder = (await session.exec(select(MdPerson).where(
            MdPerson.user_id == user.id, MdPerson.deleted_at.is_(None)))).scalars().first()
        if holder is not None and holder.party_id != person.party_id:
            raise AppException("登录账号已关联其他人员，不能覆盖关联", status_code=409)
        if person.user_id not in (None, user.id):
            raise AppException("该人员已有其他登录账号，不能覆盖关联", status_code=409)
        if not user.is_active or not auth_user.is_active:
            raise AppException("登录账号或租户用户已停用，不能自动重新启用", status_code=409)
        if person.user_id is None:
            person.user_id = user.id
            person.updated_by = created_by
            person.updated_at = utc_now()
            session.add(person)
    await assign_roles(session, user.id, role_nos or [], created_by=created_by)
    return user, person


def guardian_login_mobile(value: str | None) -> str:
    """家长登录使用手机号。去掉空白后须为有效的 11 位手机号。"""
    from app.auth.login_email import normalize_login_mobile

    try:
        return normalize_login_mobile(value)
    except ValueError as exc:
        raise AppException("请填写有效的 11 位手机号，用于开通家长登录账号") from exc


async def ensure_login_for_person(
    session: AsyncSession,
    person: MdPerson,
    *,
    tenant_id: UUID,
    org_id: UUID,
    mobile: str,
    full_name: str,
    initial_password: str,
    role_nos: list[str],
    created_by: UUID | None = None,
) -> tuple[SysUser, str]:
    """给已有人员开通登录账号，并挂到这同一个人。返回 (用户, created|linked|exists)。

    created：新建登录账号，使用指定初始密码，下次登录必须修改。
    linked：该手机号已有账号，挂到这个人，不改密码。
    exists：这个人已经有登录账号。
    """
    mobile = guardian_login_mobile(mobile)
    if person.user_id is not None:
        current = await session.get(SysUser, person.user_id)
        if current is not None and current.deleted_at is None:
            await _require_roles(session, role_nos)
            await assign_roles(session, current.id, role_nos, created_by=created_by)
            return current, "exists"
    auth_user = (await session.exec(select(AuthUser).where(AuthUser.mobile == mobile))).scalars().first()
    created_auth = False
    if auth_user is None:
        auth_user = AuthUser(
            mobile=mobile,
            password_hash=hash_password(initial_password),
            is_email_verified=False,
            is_password_change_required=True,
            password_changed_at=utc_now(),
        )
        session.add(auth_user)
        await session.flush()
        created_auth = True
    await ensure_membership(session, auth_user.id, tenant_id)
    user = (
        await session.exec(select(SysUser).where(SysUser.auth_user_id == auth_user.id, SysUser.deleted_at.is_(None)))
    ).scalars().first()
    if user is None:
        user = SysUser(
            org_id=org_id,
            auth_user_id=auth_user.id,
            display_name=full_name,
            org_access_mode_code="primary_only",
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(user)
        await session.flush()
        session.add(
            SysUserOrg(
                org_id=org_id,
                user_id=user.id,
                access_type_code="primary",
                is_primary=True,
                created_by=created_by,
                updated_by=created_by,
            )
        )
    holder = (
        await session.exec(select(MdPerson).where(MdPerson.user_id == user.id, MdPerson.deleted_at.is_(None)))
    ).scalars().first()
    if holder is not None and holder.party_id != person.party_id:
        raise AppException("该手机号已绑定其他人员，请改用关联已有监护人", status_code=409)
    if person.user_id not in (None, user.id):
        raise AppException("该监护人已有其他登录账号", status_code=409)
    if person.user_id is None:
        person.user_id = user.id
        person.updated_by = created_by
        person.updated_at = utc_now()
        session.add(person)
    await _require_roles(session, role_nos)
    await assign_roles(session, user.id, role_nos, created_by=created_by)
    if created_auth:
        return user, "created"
    return user, "linked"


async def _require_roles(session: AsyncSession, role_nos: list[str]) -> None:
    found = (await session.exec(select(SysRole.role_no).where(SysRole.role_no.in_(role_nos), SysRole.deleted_at.is_(None)))).scalars().all()
    missing = [role_no for role_no in role_nos if role_no not in set(found)]
    if missing:
        raise AppException("学校尚未配置家长角色，无法开通家长账号", status_code=409)
