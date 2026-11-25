"""用户管理：新增用户 = 登录账号 + 账号可进入的租户 + 租户内用户 + 人员 + 组织 + 角色。"""

from __future__ import annotations

from uuid import UUID

from fastapi import status

from app.auth.data_scope import DATA_SCOPE_ALL, DATA_SCOPE_SELF, ORG_ACCESS_ASSIGNED
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, has_global_access, resolve_effective_data_scope, table_scope_condition
from app.core.exceptions import AppException
from app.core.runtime import online_user_registry
from app.framework.db.session import get_session_context
from app.integrations import user_auth
from app.modules.masterdata.repository import CONTACT_TYPE_MOBILE
from app.modules.masterdata.repository import repository as masterdata_repository

from app.modules.position.service import user_position_options

from .models import SysUser
from .provisioning import ensure_tenant_user
from .repository import repository
from .schemas import UserCreate, UserListQuery, UserResetPassword, UserUpdate


def scope_condition(current_user: AuthenticatedUser, permission_key: str):
    """sys_user 的数据范围：本人按 id；其余按组织 / 部门（框架 scope_filters）。"""
    if resolve_effective_data_scope(current_user, permission_key) == DATA_SCOPE_SELF:
        return SysUser.id == current_user.user_id
    return table_scope_condition(SysUser, current_user, permission_key)


class UserService:
    def __init__(self, session_getter) -> None:
        self.session_getter = session_getter

    # ───────── 校验 ─────────
    @staticmethod
    async def _check_org_dept(session, current_user, permission_key: str, org_id: UUID, department_id: UUID | None) -> None:
        org = await repository.get_org(session, org_id)
        if org is None or not org.is_active:
            raise AppException("所属组织不存在或已停用")
        ensure_org_access(current_user, org_id, permission_key)
        if department_id is not None:
            dept = await repository.get_department(session, department_id)
            if dept is None:
                raise AppException("部门不存在")
            if dept.org_id != org_id:
                raise AppException("部门不属于所选组织")

    @staticmethod
    async def _check_org_ids(session, current_user, permission_key: str, mode: str, org_ids: list[UUID]) -> list[UUID]:
        if mode != ORG_ACCESS_ASSIGNED:
            return []
        result = []
        for org_id in dict.fromkeys(org_ids):
            org = await repository.get_org(session, org_id)
            if org is None or not org.is_active:
                raise AppException("授权的组织不存在或已停用")
            ensure_org_access(current_user, org_id, permission_key)
            result.append(org_id)
        return result

    @staticmethod
    def _check_org_access_mode(current_user, permission_key: str, mode: str | None) -> None:
        if mode == "all" and not has_global_access(current_user, permission_key):
            raise AppException("只有数据范围为全部的管理员可以授予“全部组织”访问方式", status_code=status.HTTP_403_FORBIDDEN)

    @staticmethod
    async def _check_roles(session, current_user, permission_key: str, role_ids: list[UUID]) -> list[UUID]:
        role_ids = list(dict.fromkeys(role_ids))
        roles = await repository.get_roles(session, role_ids)
        found = {role.id for role in roles}
        missing = [str(rid) for rid in role_ids if rid not in found]
        if missing:
            raise AppException(f"角色不存在：{', '.join(missing)}")
        if any(role.data_scope_code == DATA_SCOPE_ALL for role in roles) and not has_global_access(current_user, permission_key):
            raise AppException("只有数据范围为全部的管理员可以分配数据范围为全部的角色", status_code=status.HTTP_403_FORBIDDEN)
        return role_ids

    @staticmethod
    async def _check_role_change(session, current_user, permission_key: str, user: SysUser, role_ids: list[UUID]) -> None:
        """移除“全部数据范围”的角色同样只允许全局管理员操作。"""
        current = await repository.roles_of_user(session, user.id)
        removed = [role for role in current if role.id not in set(role_ids)]
        if any(role.data_scope_code == DATA_SCOPE_ALL for role in removed) and not has_global_access(current_user, permission_key):
            raise AppException("只有数据范围为全部的管理员可以调整管理员角色", status_code=status.HTTP_403_FORBIDDEN)

    async def position_options(self, current_user, permission, org_id):
        ensure_org_access(current_user, org_id, permission)
        async with self.session_getter() as session:
            return await user_position_options(session, current_user, permission, org_id)

    async def _check_positions(self, session, current_user, permission, org_id, position_ids, existing=()):
        ensure_org_access(current_user, org_id, permission)
        if not position_ids:
            return []
        choices = {row["id"]: row for row in await user_position_options(session, current_user, permission, org_id)}
        selected = list(dict.fromkeys(position_ids))
        if any(identifier not in choices or (identifier not in existing and not choices[identifier]["is_active"])
               for identifier in selected):
            raise AppException("所选岗位不存在、已停用或不在该组织的授权范围内", status_code=422)
        return selected

    # ───────── 查询 ─────────
    async def list(self, params: UserListQuery, current_user: AuthenticatedUser) -> dict:
        async with self.session_getter() as session:
            return await repository.list(session, params, scope_condition(current_user, "user_profile:list"))

    async def detail(self, user_id: str, current_user: AuthenticatedUser):
        async with self.session_getter() as session:
            return await repository.detail(session, user_id, scope_condition(current_user, "user_profile:detail"))

    async def map_tenant_users_by_auth_user(self, auth_user_ids: list[UUID]) -> dict[str, dict]:
        async with self.session_getter() as session:
            return await repository.map_by_auth_users(session, auth_user_ids)

    async def org_options(self) -> list[dict]:
        async with self.session_getter() as session:
            return await repository.campus_options(session)

    # ───────── 新增 ─────────
    async def create(self, payload: UserCreate, current_user: AuthenticatedUser):
        permission_key = "user_profile:create"
        if not payload.email and not payload.mobile:
            raise AppException("邮箱和手机号至少填写一个")
        self._check_org_access_mode(current_user, permission_key, payload.org_access_mode_code)
        async with self.session_getter() as session:
            await self._check_org_dept(session, current_user, permission_key, payload.org_id, payload.department_id)
            org_ids = await self._check_org_ids(session, current_user, permission_key, payload.org_access_mode_code, payload.org_ids)
            role_ids = await self._check_roles(session, current_user, permission_key, payload.role_ids)
            position_ids = await self._check_positions(session, current_user, permission_key, payload.org_id, payload.position_ids)

            auth_user = await user_auth.find_auth_user(session, email=payload.email, mobile=payload.mobile)
            if auth_user is None:
                auth_user = await user_auth.create_auth_user(
                    session, email=payload.email, mobile=payload.mobile, password=payload.password, created_by=current_user.auth_user_id
                )
            elif await repository.get_by_auth_user(session, auth_user.id) is not None:
                raise AppException("该账号已经是本租户的用户", status_code=status.HTTP_409_CONFLICT)

            display_name = payload.display_name or payload.full_name
            user, person = await ensure_tenant_user(
                session,
                tenant_id=current_user.tenant_id,
                org_id=payload.org_id,
                display_name=display_name,
                password=payload.password,
                email=auth_user.email,
                mobile=auth_user.mobile if not auth_user.email else None,
                department_id=payload.department_id,
                org_access_mode_code=payload.org_access_mode_code,
                created_by=current_user.user_id,
            )
            if person.full_name != payload.full_name:
                await masterdata_repository.rename_person(session, person, payload.full_name, updated_by=current_user.user_id)
            if payload.mobile:
                await masterdata_repository.set_primary_contact(
                    session, person.party_id, CONTACT_TYPE_MOBILE, payload.mobile, updated_by=current_user.user_id
                )
            await repository.set_membership_active(session, auth_user.id, current_user.tenant_id, True, current_user.auth_user_id)
            await repository.replace_orgs(session, user.id, payload.org_id, org_ids, current_user.user_id)
            await repository.replace_roles(session, user.id, role_ids, current_user.user_id)
            await repository.replace_positions(session, user, position_ids, current_user.user_id)
            if not payload.is_active:
                user.is_active = False
                await repository.set_membership_active(session, auth_user.id, current_user.tenant_id, False, current_user.auth_user_id)
            await session.commit()
            return await repository.detail(session, user.id)

    # ───────── 修改 ─────────
    async def update(self, user_id: str, payload: UserUpdate, current_user: AuthenticatedUser):
        permission_key = "user_profile:update"
        fields = payload.model_fields_set
        if "mobile" in fields:
            raise AppException("手机号暂不允许修改")
        async with self.session_getter() as session:
            user = await repository.get(session, user_id, scope_condition(current_user, permission_key), for_update=True)
            if user is None:
                return None
            operator = current_user.user_id

            if {"org_id", "department_id"} & fields:
                org_id = payload.org_id if "org_id" in fields and payload.org_id else user.org_id
                department_id = payload.department_id if "department_id" in fields else user.department_id
                await self._check_org_dept(session, current_user, permission_key, org_id, department_id)
                user.org_id, user.department_id = org_id, department_id
            if "org_access_mode_code" in fields and payload.org_access_mode_code:
                self._check_org_access_mode(current_user, permission_key, payload.org_access_mode_code)
                user.org_access_mode_code = payload.org_access_mode_code
            if {"org_id", "org_access_mode_code", "org_ids"} & fields:
                requested = payload.org_ids if "org_ids" in fields and payload.org_ids is not None else await repository.list_org_ids(session, user.id)
                org_ids = await self._check_org_ids(session, current_user, permission_key, user.org_access_mode_code, requested)
                await repository.replace_orgs(session, user.id, user.org_id, org_ids, operator)

            if "display_name" in fields and payload.display_name:
                user.display_name = payload.display_name
            if "avatar_url" in fields:
                user.avatar_url = payload.avatar_url
            if "full_name" in fields:
                person = await masterdata_repository.get_person_by_user(session, user.id)
                if person is None:
                    person = await masterdata_repository.create_person(
                        session, full_name=payload.full_name or user.display_name, user_id=user.id, created_by=operator
                    )
                if "full_name" in fields and payload.full_name:
                    await masterdata_repository.rename_person(session, person, payload.full_name, updated_by=operator)

            if "role_ids" in fields and payload.role_ids is not None:
                role_ids = await self._check_roles(session, current_user, permission_key, payload.role_ids)
                await self._check_role_change(session, current_user, permission_key, user, role_ids)
                await repository.replace_roles(session, user.id, role_ids, operator)

            if "position_ids" in fields or "org_id" in fields:
                existing = (await repository.position_ids_map(session, [user.id])).get(user.id, [])
                requested = payload.position_ids if payload.position_ids is not None else existing
                position_ids = await self._check_positions(session, current_user, permission_key, user.org_id, requested, existing)
                await repository.replace_positions(session, user, position_ids, operator)

            kicked = False
            if "is_active" in fields and payload.is_active is not None and payload.is_active != user.is_active:
                kicked = await self._apply_status(session, user, payload.is_active, current_user)
            await repository.touch(session, user, operator)
            await session.commit()
            auth_user_id = user.auth_user_id
        if kicked:
            await online_user_registry.kick_user(auth_user_id)
        async with self.session_getter() as session:
            return await repository.detail(session, user_id)

    # ───────── 启停、删除、改密 ─────────
    async def _apply_status(self, session, user: SysUser, is_active: bool, current_user: AuthenticatedUser) -> bool:
        """停用 = sys_user.is_active 为否，并停用该账号进入本租户（auth_membership）。返回是否需要踢下线。"""
        if not is_active and user.id == current_user.user_id:
            raise AppException("不能停用当前登录用户")
        user.is_active = is_active
        await repository.set_membership_active(session, user.auth_user_id, current_user.tenant_id, is_active, current_user.auth_user_id)
        return not is_active

    async def update_status(self, user_id: str, *, is_active: bool, current_user: AuthenticatedUser) -> bool:
        async with self.session_getter() as session:
            user = await repository.get(session, user_id, scope_condition(current_user, "user_profile:update"), for_update=True)
            if user is None:
                return False
            if not is_active and await repository.has_all_scope_role(session, user.id) and not has_global_access(current_user, "user_profile:update"):
                raise AppException("不能停用管理员账号", status_code=status.HTTP_403_FORBIDDEN)
            kick = await self._apply_status(session, user, is_active, current_user)
            await repository.touch(session, user, current_user.user_id)
            await session.commit()
            auth_user_id = user.auth_user_id
        if kick:
            await online_user_registry.kick_user(auth_user_id)
        return True

    async def login_availability(self, session, tenant_id: UUID, user_ids: list[UUID]) -> dict[UUID, bool]:
        """Return only login availability for user IDs authorized by the calling workflow."""
        return await repository.login_availability(session, tenant_id, user_ids)

    async def disable_linked_user_in_session(
        self, session, user_id: UUID, current_user: AuthenticatedUser, *, permission_key: str,
    ) -> UUID | None:
        """Disable a tenant user identified by an authorized workflow. The caller owns the transaction."""
        if permission_key not in current_user.permissions:
            raise AppException("没有权限停用关联账号", 403)
        user = await repository.get(session, user_id, for_update=True)
        if user is None:
            return None
        ensure_org_access(current_user, user.org_id, permission_key)
        if await repository.has_all_scope_role(session, user.id) and (
            "user_profile:update" not in current_user.permissions
            or not has_global_access(current_user, "user_profile:update")
        ):
            raise AppException("不能停用管理员账号", 403)
        await self._apply_status(session, user, False, current_user)
        await repository.touch(session, user, current_user.user_id)
        return user.auth_user_id

    async def revoke_account_sessions(self, auth_user_id: UUID) -> None:
        await online_user_registry.kick_user(auth_user_id)

    async def delete(self, user_id: str, current_user: AuthenticatedUser) -> bool:
        """删除（软删除）租户内用户：解除角色，停用其进入本租户；登录账号与人员保留。"""
        permission_key = "user_profile:delete"
        async with self.session_getter() as session:
            user = await repository.get(session, user_id, scope_condition(current_user, permission_key), for_update=True)
            if user is None:
                return False
            if user.id == current_user.user_id:
                raise AppException("不能删除当前登录用户")
            if await repository.has_all_scope_role(session, user.id) and not has_global_access(current_user, permission_key):
                raise AppException("不能删除管理员账号", status_code=status.HTTP_403_FORBIDDEN)
            await repository.set_membership_active(session, user.auth_user_id, current_user.tenant_id, False, current_user.auth_user_id)
            await repository.soft_delete(session, user, current_user.user_id)
            await session.commit()
            auth_user_id = user.auth_user_id
        await online_user_registry.kick_user(auth_user_id)
        return True

    async def reset_password(self, user_id: str, payload: UserResetPassword, current_user: AuthenticatedUser) -> bool:
        """重置登录密码（public.auth_user）。注意：登录账号跨租户共用，密码对该账号可进入的所有租户生效。"""
        permission_key = "user_profile:reset_password"
        async with self.session_getter() as session:
            user = await repository.get(session, user_id, scope_condition(current_user, permission_key))
            if user is None:
                return False
            if await repository.has_all_scope_role(session, user.id) and not has_global_access(current_user, permission_key):
                raise AppException("不能修改管理员账号的密码", status_code=status.HTTP_403_FORBIDDEN)
            await user_auth.set_password(
                session,
                user.auth_user_id,
                payload.password,
                updated_by=current_user.auth_user_id,
                is_password_change_required=payload.is_password_change_required,
            )
            await repository.touch(session, user, current_user.user_id)
            await session.commit()
        return True


service = UserService(session_getter=get_session_context)
