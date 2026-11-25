"""租户内用户（sys_user）的数据访问：列表展示的姓名、手机号来自 md_person / md_person_contact / public.auth_user。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.data_scope import DATA_SCOPE_ALL
from app.auth.models import AuthMembership, AuthUser
from app.modules.department.models import SysDepartment
from app.modules.masterdata.models import MdPerson, MdPersonContact
from app.modules.organization.models import SysOrg
from app.modules.permission.models import SysPermission
from app.modules.rbac_repository_utils import normalize_uuid, utc_now
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_role.models import SysUserRole

from .models import SysUser, SysUserOrg, SysUserPosition
from .schemas import UserDetailItem, UserListItem, UserListQuery, UserPermissionBrief, UserRoleBrief

CONTACT_MOBILE = "mobile"


def _mobile_subquery():
    return (
        select(MdPersonContact.contact_value)
        .where(
            MdPersonContact.party_id == MdPerson.party_id,
            MdPersonContact.contact_type_code == CONTACT_MOBILE,
            MdPersonContact.deleted_at.is_(None),
        )
        .order_by(MdPersonContact.is_primary.desc(), MdPersonContact.created_at)
        .limit(1)
        .correlate(MdPerson)
        .scalar_subquery()
    )


def _role_count():
    return (
        select(func.count())
        .select_from(SysUserRole)
        .join(SysRole, SysRole.id == SysUserRole.role_id)
        .where(SysUserRole.user_id == SysUser.id, SysRole.deleted_at.is_(None))
        .correlate(SysUser)
        .scalar_subquery()
    )


class UserRepository:
    async def business_assignees(self, session, *, tenant_id, keyword="", user_id=None, limit=100,
                                 org_id=None, condition=None, user_ids=None, for_update=False):
        """业务人员引用：当前租户有效登录成员及有效责任部门，不返回认证资料。"""
        statement = (select(SysUser, SysDepartment.department_name)
            .join(AuthUser, AuthUser.id == SysUser.auth_user_id)
            .join(SysOrg, and_(SysOrg.id == SysUser.org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True)))
            .join(AuthMembership, and_(AuthMembership.auth_user_id == AuthUser.id, AuthMembership.tenant_id == tenant_id))
            .outerjoin(SysDepartment, and_(SysDepartment.id == SysUser.department_id,
                SysDepartment.deleted_at.is_(None), SysDepartment.is_active.is_(True), SysDepartment.org_id == SysUser.org_id))
            .where(SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
                AuthUser.is_active.is_(True), AuthMembership.is_active.is_(True)))
        if user_id is not None:
            statement = statement.where(SysUser.id == user_id).with_for_update(of=SysUser)
        if org_id is not None:
            statement = statement.where(SysUser.org_id == org_id)
        if condition is not None:
            statement = statement.where(condition)
        if user_ids is not None:
            statement = statement.where(SysUser.id.in_(user_ids))
        if for_update:
            statement = statement.with_for_update(of=SysUser).execution_options(populate_existing=True)
        if keyword.strip():
            statement = statement.where(SysUser.display_name.icontains(keyword.strip(), autoescape=True))
        return (await session.execute(statement.order_by(SysUser.display_name, SysUser.id).limit(limit))).all()

    async def current_contact(self, session, user_id: UUID, auth_user_id: UUID):
        """本人联系信息；绑定租户用户和认证账号，不提供任意人员检索。"""
        statement = (
            select(
                func.coalesce(func.nullif(MdPerson.full_name, ""), SysUser.display_name).label("contact_name"),
                func.coalesce(func.nullif(_mobile_subquery(), ""), AuthUser.mobile, "").label("contact_phone"),
            )
            .select_from(SysUser)
            .join(AuthUser, AuthUser.id == SysUser.auth_user_id)
            .outerjoin(MdPerson, and_(MdPerson.user_id == SysUser.id, MdPerson.deleted_at.is_(None)))
            .where(
                SysUser.id == user_id, SysUser.auth_user_id == auth_user_id,
                SysUser.deleted_at.is_(None), SysUser.is_active.is_(True), AuthUser.is_active.is_(True),
            )
        )
        return (await session.execute(statement)).mappings().first()

    def name_matching_ids(self, keyword: str):
        """仅供业务查询作为子查询；调用方必须继续过滤业务记录的数据范围。"""
        return select(SysUser.id).where(SysUser.deleted_at.is_(None), SysUser.display_name.ilike(f"%{keyword.strip()}%"))

    async def assignee_options(self, session, org_id: UUID, keyword: str, limit: int):
        membership = exists(select(SysUserOrg.id).where(
            SysUserOrg.user_id == SysUser.id, SysUserOrg.org_id == org_id,
        ))
        statement = select(SysUser.id, SysUser.display_name).where(
            SysUser.deleted_at.is_(None), SysUser.is_active.is_(True),
            or_(SysUser.org_id == org_id, SysUser.org_access_mode_code == "all", membership),
        )
        if keyword.strip():
            statement = statement.where(SysUser.display_name.ilike(f"%{keyword.strip()}%"))
        return (await session.execute(statement.order_by(SysUser.display_name, SysUser.id).limit(limit))).mappings().all()

    async def display_names(self, session, user_ids):
        if not user_ids:
            return {}
        rows = (await session.execute(select(SysUser.id, SysUser.display_name).where(
            SysUser.id.in_(user_ids), SysUser.deleted_at.is_(None),
        ))).all()
        return {row.id: row.display_name for row in rows}

    def _base_select(self):
        mobile = func.coalesce(_mobile_subquery(), AuthUser.mobile).label("mobile")
        return (
            select(
                SysUser.id,
                SysUser.auth_user_id,
                MdPerson.party_id,
                SysUser.display_name,
                MdPerson.full_name,
                AuthUser.email,
                mobile,
                SysUser.avatar_url,
                SysUser.org_id,
                SysOrg.org_name,
                SysUser.org_access_mode_code,
                SysUser.department_id,
                SysDepartment.department_name,
                SysUser.is_active,
                AuthUser.is_active.label("account_is_active"),
                _role_count().label("role_count"),
                SysUser.created_at,
                SysUser.updated_at,
                SysUser.updated_by,
            )
            .select_from(SysUser)
            .join(AuthUser, AuthUser.id == SysUser.auth_user_id)
            .outerjoin(MdPerson, and_(MdPerson.user_id == SysUser.id, MdPerson.deleted_at.is_(None)))
            .outerjoin(SysOrg, SysOrg.id == SysUser.org_id)
            .outerjoin(SysDepartment, SysDepartment.id == SysUser.department_id)
            .where(SysUser.deleted_at.is_(None))
        )

    @staticmethod
    def _conditions(params: UserListQuery) -> list[Any]:
        conditions: list[Any] = []
        mobile_match = lambda pattern: or_(  # noqa: E731
            AuthUser.mobile.ilike(pattern),
            exists().where(
                MdPersonContact.party_id == MdPerson.party_id,
                MdPersonContact.contact_type_code == CONTACT_MOBILE,
                MdPersonContact.deleted_at.is_(None),
                MdPersonContact.contact_value.ilike(pattern),
            ),
        )
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            conditions.append(
                or_(
                    SysUser.display_name.ilike(keyword),
                    func.coalesce(MdPerson.full_name, "").ilike(keyword),
                    func.coalesce(AuthUser.email, "").ilike(keyword),
                    mobile_match(keyword),
                )
            )
        if params.full_name:
            pattern = f"%{params.full_name.strip()}%"
            conditions.append(or_(func.coalesce(MdPerson.full_name, "").ilike(pattern), SysUser.display_name.ilike(pattern)))
        if params.email:
            conditions.append(func.coalesce(AuthUser.email, "").ilike(f"%{params.email.strip()}%"))
        if params.mobile:
            conditions.append(mobile_match(f"%{params.mobile.strip()}%"))
        if params.org_id:
            conditions.append(SysUser.org_id == params.org_id)
        if params.department_id:
            conditions.append(SysUser.department_id == params.department_id)
        if params.role_id:
            conditions.append(exists().where(SysUserRole.user_id == SysUser.id, SysUserRole.role_id == params.role_id))
        if params.role_no:
            conditions.append(
                exists().where(
                    SysUserRole.user_id == SysUser.id,
                    SysUserRole.role_id == SysRole.id,
                    SysRole.role_no == params.role_no.strip(),
                )
            )
        if params.is_active is not None:
            conditions.append(SysUser.is_active.is_(params.is_active))
        return conditions

    async def _role_map(self, session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, list[UserRoleBrief]]:
        result: dict[UUID, list[UserRoleBrief]] = defaultdict(list)
        if not user_ids:
            return result
        rows = (
            await session.execute(
                select(SysUserRole.user_id, SysRole.id, SysRole.role_no, SysRole.role_name)
                .join(SysRole, SysRole.id == SysUserRole.role_id)
                .where(SysUserRole.user_id.in_(user_ids), SysRole.deleted_at.is_(None))
                .order_by(SysRole.role_no)
            )
        ).all()
        for row in rows:
            result[row.user_id].append(UserRoleBrief(id=row.id, role_no=row.role_no, role_name=row.role_name))
        return result

    async def _org_ids_map(self, session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        result: dict[UUID, list[UUID]] = defaultdict(list)
        if not user_ids:
            return result
        rows = (
            await session.execute(
                select(SysUserOrg.user_id, SysUserOrg.org_id)
                .where(SysUserOrg.user_id.in_(user_ids))
                .order_by(SysUserOrg.is_primary.desc(), SysUserOrg.created_at)
            )
        ).all()
        for row in rows:
            result[row.user_id].append(row.org_id)
        return result

    async def position_ids_map(self, session, user_ids):
        rows = (await session.execute(select(SysUserPosition.user_id, SysUserPosition.position_id).where(
            SysUserPosition.user_id.in_(user_ids), SysUserPosition.deleted_at.is_(None), SysUserPosition.valid_to.is_(None)))).all() if user_ids else []
        result = defaultdict(list)
        for user_id, position_id in rows:
            result[user_id].append(position_id)
        return result

    async def replace_positions(self, session, user, position_ids, operator_id):
        rows = (await session.execute(select(SysUserPosition).where(
            SysUserPosition.user_id == user.id, SysUserPosition.deleted_at.is_(None), SysUserPosition.valid_to.is_(None)))).scalars().all()
        wanted = set(position_ids)
        current = {row.position_id for row in rows}
        for row in rows:
            if row.position_id not in wanted:
                row.valid_to = row.updated_at = utc_now()
                row.updated_by = operator_id
                session.add(row)
        session.add_all(SysUserPosition(org_id=user.org_id, user_id=user.id, position_id=position_id,
            created_by=operator_id, updated_by=operator_id) for position_id in wanted - current)

    def _item(self, row, roles, org_ids, model=UserListItem, position_ids=None):
        data = dict(row._mapping)
        data["role_count"] = int(data.get("role_count") or 0)
        data["roles"] = roles
        data["org_ids"] = org_ids
        data["position_ids"] = position_ids or []
        return model.model_validate(data)

    async def list(self, session: AsyncSession, params: UserListQuery, scope_condition) -> dict[str, Any]:
        statement = self._base_select()
        conditions = self._conditions(params)
        if scope_condition is not None:
            conditions.append(scope_condition)
        if conditions:
            statement = statement.where(*conditions)
        total = int((await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one() or 0)
        sort_map = {
            "updated_at": SysUser.updated_at,
            "created_at": SysUser.created_at,
            "display_name": SysUser.display_name,
            "email": AuthUser.email,
            "role_count": _role_count(),
        }
        order = sort_map[params.sort_by]
        order = order.asc() if params.sort_order == "asc" else order.desc()
        rows = (
            await session.execute(
                statement.order_by(order.nulls_last(), SysUser.id).limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
        ).all()
        user_ids = [row.id for row in rows]
        roles = await self._role_map(session, user_ids)
        org_ids = await self._org_ids_map(session, user_ids)
        positions = await self.position_ids_map(session, user_ids)
        items = [self._item(row, roles.get(row.id, []), org_ids.get(row.id, []), position_ids=positions.get(row.id, [])).model_dump(mode="json") for row in rows]
        return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}

    async def detail(self, session: AsyncSession, user_id: str | UUID, scope_condition=None) -> UserDetailItem | None:
        statement = self._base_select().where(SysUser.id == normalize_uuid(user_id))
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        roles = await self._role_map(session, [row.id])
        org_ids = await self._org_ids_map(session, [row.id])
        positions = await self.position_ids_map(session, [row.id])
        item = self._item(row, roles.get(row.id, []), org_ids.get(row.id, []), UserDetailItem, positions.get(row.id, []))
        permission_rows = (
            await session.execute(
                select(SysPermission.id, SysPermission.permission_key, SysPermission.permission_name, SysPermission.module_code)
                .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
                .join(SysRole, SysRole.id == SysRolePermission.role_id)
                .join(SysUserRole, SysUserRole.role_id == SysRole.id)
                .where(
                    SysUserRole.user_id == row.id,
                    SysRole.is_active.is_(True),
                    SysRole.deleted_at.is_(None),
                    SysPermission.is_active.is_(True),
                    SysPermission.deleted_at.is_(None),
                )
                .distinct()
                .order_by(SysPermission.permission_key)
            )
        ).all()
        item.permissions = [UserPermissionBrief(**r._mapping) for r in permission_rows]
        return item

    # ───────── 单条读写 ─────────
    async def get(self, session: AsyncSession, user_id: str | UUID, scope_condition=None, *, for_update: bool = False) -> SysUser | None:
        statement = select(SysUser).where(SysUser.id == normalize_uuid(user_id), SysUser.deleted_at.is_(None))
        if scope_condition is not None:
            statement = statement.where(scope_condition)
        if for_update:
            statement = statement.with_for_update(of=SysUser)
        return (await session.execute(statement)).scalar_one_or_none()

    async def get_by_auth_user(self, session: AsyncSession, auth_user_id: UUID) -> SysUser | None:
        statement = select(SysUser).where(SysUser.auth_user_id == auth_user_id, SysUser.deleted_at.is_(None))
        return (await session.execute(statement)).scalar_one_or_none()

    async def login_availability(
        self, session: AsyncSession, tenant_id: UUID, user_ids: list[UUID],
    ) -> dict[UUID, bool]:
        if not user_ids:
            return {}
        rows = await session.execute(
            select(SysUser.id, SysUser.is_active, AuthUser.is_active, AuthMembership.is_active)
            .join(AuthUser, AuthUser.id == SysUser.auth_user_id)
            .outerjoin(AuthMembership, and_(
                AuthMembership.auth_user_id == SysUser.auth_user_id,
                AuthMembership.tenant_id == tenant_id,
            ))
            .where(SysUser.id.in_(user_ids), SysUser.deleted_at.is_(None))
        )
        return {user_id: bool(active and account_active and membership_active)
                for user_id, active, account_active, membership_active in rows}

    async def map_by_auth_users(self, session: AsyncSession, auth_user_ids: list[UUID]) -> dict[str, dict[str, Any]]:
        if not auth_user_ids:
            return {}
        rows = (
            await session.execute(
                select(SysUser.auth_user_id, SysUser.id, SysUser.display_name).where(
                    SysUser.auth_user_id.in_(auth_user_ids), SysUser.deleted_at.is_(None)
                )
            )
        ).all()
        return {str(row.auth_user_id): {"user_id": str(row.id), "display_name": row.display_name} for row in rows}

    async def get_org(self, session: AsyncSession, org_id: UUID) -> SysOrg | None:
        org = await session.get(SysOrg, org_id)
        return org if org is not None and org.deleted_at is None else None

    async def get_department(self, session: AsyncSession, department_id: UUID) -> SysDepartment | None:
        dept = await session.get(SysDepartment, department_id)
        return dept if dept is not None and dept.deleted_at is None else None

    async def get_roles(self, session: AsyncSession, role_ids: list[UUID]) -> list[SysRole]:
        if not role_ids:
            return []
        statement = select(SysRole).where(SysRole.id.in_(role_ids), SysRole.deleted_at.is_(None))
        return list((await session.execute(statement)).scalars().all())

    async def roles_of_user(self, session: AsyncSession, user_id: UUID) -> list[SysRole]:
        statement = (
            select(SysRole)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(SysUserRole.user_id == user_id, SysRole.deleted_at.is_(None))
        )
        return list((await session.execute(statement)).scalars().all())

    async def has_all_scope_role(self, session: AsyncSession, user_id: UUID) -> bool:
        """用户是否拥有数据范围为全部的角色（如内置管理员）。"""
        return any(role.data_scope_code == DATA_SCOPE_ALL for role in await self.roles_of_user(session, user_id))

    async def replace_roles(self, session: AsyncSession, user_id: UUID, role_ids: list[UUID], operator_id: UUID) -> None:
        await session.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
        session.add_all(SysUserRole(user_id=user_id, role_id=rid, created_by=operator_id, updated_by=operator_id) for rid in role_ids)

    async def replace_orgs(self, session: AsyncSession, user_id: UUID, primary_org_id: UUID, org_ids: list[UUID], operator_id: UUID) -> None:
        """可访问组织：主组织 + 额外授权的组织。"""
        await session.execute(delete(SysUserOrg).where(SysUserOrg.user_id == user_id))
        await session.flush()
        ordered = list(dict.fromkeys([primary_org_id, *org_ids]))
        for org_id in ordered:
            is_primary = org_id == primary_org_id
            session.add(
                SysUserOrg(
                    org_id=org_id,
                    user_id=user_id,
                    access_type_code="primary" if is_primary else "assigned",
                    is_primary=is_primary,
                    created_by=operator_id,
                    updated_by=operator_id,
                )
            )

    async def list_org_ids(self, session: AsyncSession, user_id: UUID) -> list[UUID]:
        return (await self._org_ids_map(session, [user_id])).get(user_id, [])

    async def touch(self, session: AsyncSession, user: SysUser, operator_id: UUID) -> None:
        user.updated_by = operator_id
        user.updated_at = utc_now()
        session.add(user)

    async def set_membership_active(self, session: AsyncSession, auth_user_id: UUID, tenant_id: UUID, is_active: bool, operator_auth_user_id: UUID) -> None:
        membership = (
            await session.execute(
                select(AuthMembership).where(AuthMembership.auth_user_id == auth_user_id, AuthMembership.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if membership is not None and membership.is_active != is_active:
            membership.is_active = is_active
            membership.updated_by = operator_auth_user_id
            membership.updated_at = utc_now()
            session.add(membership)

    async def soft_delete(self, session: AsyncSession, user: SysUser, operator_id: UUID) -> None:
        await session.execute(delete(SysUserRole).where(SysUserRole.user_id == user.id))
        user.is_active = False
        user.deleted_at = utc_now()
        user.deleted_by = operator_id
        user.updated_by = operator_id
        session.add(user)
        person = (await session.execute(select(MdPerson).where(MdPerson.user_id == user.id))).scalars().all()
        for item in person:  # 人员保留（可能有学籍、任职等身份），解除与已删除用户的关联
            item.user_id = None
            session.add(item)

    async def campus_options(self, session: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(SysOrg.id, SysOrg.org_name, SysOrg.org_type_code)
                .where(SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True))
                .order_by(SysOrg.sort_no.nulls_last(), SysOrg.org_name)
            )
        ).all()
        return [{"id": str(row.id), "org_name": row.org_name, "org_type_code": row.org_type_code} for row in rows]


repository = UserRepository()
