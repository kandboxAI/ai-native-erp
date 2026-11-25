"""审批人解析：按权限与关系数据，不按角色（整改方案 §2.18）。

审批人类型（字典 wf_assignee_type）：
- user：指定用户 sys_user.id（可逗号分隔多个）；
- permission：拥有该权限（permission_key）的启用用户，如 leave:approve（学生科）；
- business_owner：业务关系人，由业务模块登记（如 class_head_teacher：请假学生所在班级当前班主任）；
- department_manager：部门（department_no）的负责人 sys_department.manager_user_id；
- initiator_leader：发起人所在部门的负责人；
- starter：发起人本人；starter_select：发起时由发起人选择。

所有候选人还须：启用、可访问流程实例所属组织、拥有办理权限 workflow_task:complete。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.user_org_access import user_can_access_org_condition
from app.core.exceptions import AppException
from app.modules.department.models import SysDepartment
from app.modules.permission.models import SysPermission
from app.modules.role.models import SysRole
from app.modules.role_permission.models import SysRolePermission
from app.modules.user_profile.models import SysUser
from app.modules.user_role.models import SysUserRole
from app.modules.workflow.design_models import ASSIGNEE_TYPE_LABELS
from app.modules.workflow.integration.registry import business_owner_def
from app.modules.workflow.spiff_runner import AssigneeSpec

WORKFLOW_TASK_COMPLETE_PERMISSION = "workflow_task:complete"


def _alive_user_conditions():
    return [SysUser.is_active.is_(True), SysUser.deleted_at.is_(None)]


def permission_holder_condition(permission_key: str):
    """SQL 条件：SysUser 拥有某权限（经启用的角色）。"""
    from sqlalchemy import exists

    return (
        exists()
        .where(
            SysUserRole.user_id == SysUser.id,
            SysRole.id == SysUserRole.role_id,
            SysRole.is_active.is_(True),
            SysRole.deleted_at.is_(None),
            SysRolePermission.role_id == SysRole.id,
            SysPermission.id == SysRolePermission.permission_id,
            SysPermission.permission_key == permission_key,
            SysPermission.is_active.is_(True),
            SysPermission.deleted_at.is_(None),
        )
        .correlate(SysUser)
    )


async def list_user_ids_with_permission(
    session: AsyncSession,
    *,
    permission_key: str,
    org_id: UUID | None,
) -> list[UUID]:
    stmt = select(SysUser.id).where(*_alive_user_conditions(), permission_holder_condition(permission_key))
    if org_id is not None:
        stmt = stmt.where(user_can_access_org_condition(org_id))
    rows = (await session.exec(stmt.order_by(SysUser.created_at))).scalars().all()
    return list(rows)


async def list_user_ids_with_role(session: AsyncSession, *, role_no: str, org_id: UUID) -> list[UUID]:
    """按启用角色及组织范围选候选人，办理仍经过工作流权限校验。"""
    stmt = (
        select(SysUser.id)
        .join(SysUserRole, SysUserRole.user_id == SysUser.id)
        .join(SysRole, SysRole.id == SysUserRole.role_id)
        .where(
            *_alive_user_conditions(), SysRole.role_no == role_no, SysRole.is_active.is_(True),
            SysRole.deleted_at.is_(None), user_can_access_org_condition(org_id),
        )
    )
    return list((await session.exec(stmt)).scalars().all())


async def list_department_manager_ids(session: AsyncSession, *, department_no: str, org_id: UUID | None) -> list[UUID]:
    stmt = select(SysDepartment.manager_user_id).where(
        SysDepartment.department_no == department_no,
        SysDepartment.deleted_at.is_(None),
        SysDepartment.is_active.is_(True),
        SysDepartment.manager_user_id.is_not(None),
    )
    if org_id is not None:
        stmt = stmt.where(SysDepartment.org_id == org_id)
    return [value for value in (await session.exec(stmt)).scalars().all() if value]


async def list_initiator_leader_ids(session: AsyncSession, *, starter_user_id: UUID | None) -> list[UUID]:
    if starter_user_id is None:
        return []
    stmt = (
        select(SysDepartment.manager_user_id)
        .join(SysUser, SysUser.department_id == SysDepartment.id)
        .where(SysUser.id == starter_user_id, SysDepartment.deleted_at.is_(None), SysDepartment.manager_user_id.is_not(None))
    )
    return [value for value in (await session.exec(stmt)).scalars().all() if value]


async def list_business_owner_ids(
    session: AsyncSession,
    *,
    owner_key: str,
    business_type_code: str | None,
    business_id: UUID | None,
) -> list[UUID]:
    definition = business_owner_def(business_type_code or "", owner_key)
    if definition is None:
        raise AppException(f"业务类型「{business_type_code}」未登记业务负责人「{owner_key}」", status_code=400)
    if business_id is None:
        return []
    return list(dict.fromkeys(await definition.resolve(session, business_id)))


def _parse_user_ids(value: str | None) -> list[UUID]:
    result: list[UUID] = []
    for raw in (value or "").split(","):
        try:
            result.append(UUID(raw.strip()))
        except ValueError:
            continue
    return list(dict.fromkeys(result))


async def resolve_assignee_user_ids(
    session: AsyncSession,
    *,
    assignee_type: str,
    assignee_value: str | None,
    org_id: UUID | None,
    business_type_code: str | None = None,
    business_id: UUID | None = None,
    starter_user_id: UUID | None = None,
    starter_choices: dict[str, list[str]] | None = None,
) -> list[UUID]:
    """按配置解析出候选用户（未做启用/组织/办理权限过滤）。业务单据未知时 business_owner 返回空。"""
    if assignee_type == "user":
        return _parse_user_ids(assignee_value)
    if assignee_type == "permission":
        return await list_user_ids_with_permission(session, permission_key=assignee_value or "", org_id=org_id)
    if assignee_type == "business_owner":
        return await list_business_owner_ids(
            session, owner_key=assignee_value or "", business_type_code=business_type_code, business_id=business_id
        )
    if assignee_type == "department_manager":
        return await list_department_manager_ids(session, department_no=assignee_value or "", org_id=org_id)
    if assignee_type == "initiator_leader":
        return await list_initiator_leader_ids(session, starter_user_id=starter_user_id)
    if assignee_type == "starter":
        return [starter_user_id] if starter_user_id else []
    if assignee_type == "starter_select":
        return _parse_user_ids(",".join((starter_choices or {}).get(assignee_value or "", [])))
    raise AppException(f"不支持的审批人类型「{assignee_type}」，请改为权限或业务关系", status_code=400)


async def validate_selectable_user_ids(
    session: AsyncSession,
    *,
    user_ids: list[UUID],
    org_id: UUID | None,
) -> list[UUID]:
    """返回仍启用且可访问流程所属组织的用户（保持原顺序）。"""
    if not user_ids:
        return []
    stmt = select(SysUser.id).where(SysUser.id.in_(user_ids), *_alive_user_conditions())
    if org_id is not None:
        stmt = stmt.where(user_can_access_org_condition(org_id))
    valid = set((await session.exec(stmt)).scalars().all())
    return [user_id for user_id in user_ids if user_id in valid]


async def validate_workflow_approver_user_ids(session: AsyncSession, *, user_ids: list[UUID]) -> list[UUID]:
    """返回拥有办理权限 workflow_task:complete 的用户（保持原顺序）。"""
    if not user_ids:
        return []
    stmt = select(SysUser.id).where(
        SysUser.id.in_(user_ids), permission_holder_condition(WORKFLOW_TASK_COMPLETE_PERMISSION)
    )
    valid = set((await session.exec(stmt)).scalars().all())
    return [user_id for user_id in user_ids if user_id in valid]


async def search_selectable_users(
    session: AsyncSession,
    *,
    keyword: str | None,
    org_id: UUID | None,
    limit: int,
) -> list[SysUser]:
    stmt = select(SysUser).where(*_alive_user_conditions())
    if org_id is not None:
        stmt = stmt.where(user_can_access_org_condition(org_id))
    if keyword and keyword.strip():
        stmt = stmt.where(or_(SysUser.display_name.ilike(f"%{keyword.strip()}%")))
    rows = (await session.exec(stmt.order_by(SysUser.display_name).limit(min(max(limit, 1), 100)))).scalars().all()
    return list(rows)


async def user_display_names(session: AsyncSession, user_ids: set[UUID]) -> dict[UUID, str]:
    if not user_ids:
        return {}
    rows = (await session.exec(select(SysUser.id, SysUser.display_name).where(SysUser.id.in_(user_ids)))).all()
    return {user_id: (name or "").strip() or "—" for user_id, name in rows}


async def assignee_label(session: AsyncSession, *, assignee_type: str, assignee_value: str | None, business_type_code: str | None) -> str:
    """审批对象的展示名称，如“拥有权限：审批学生请假”“业务负责人：班主任”。"""
    if assignee_type == "permission":
        name = (
            await session.exec(select(SysPermission.permission_name).where(SysPermission.permission_key == (assignee_value or "")))
        ).scalars().first()
        return name or assignee_value or ""
    if assignee_type == "business_owner":
        definition = business_owner_def(business_type_code or "", assignee_value or "")
        return definition.label if definition else (assignee_value or "")
    if assignee_type == "department_manager":
        name = (
            await session.exec(select(SysDepartment.department_name).where(SysDepartment.department_no == (assignee_value or "")))
        ).scalars().first()
        return f"{name or assignee_value}负责人"
    if assignee_type == "user":
        return "指定审批人"
    return ASSIGNEE_TYPE_LABELS.get(assignee_type, assignee_type)


def can_act_on_task(user_permissions: list[str], user_id: UUID, task_status_code: str, candidate_user_ids: set[UUID],
                    *, assignee_type_code: str | None = None, assignee_value: str | None = None) -> bool:
    """当前用户能否办理待办：待处理、有办理权限、且是候选人（wf_task_candidate）。"""
    if task_status_code != "pending":
        return False
    if WORKFLOW_TASK_COMPLETE_PERMISSION not in user_permissions:
        return False
    if assignee_type_code == "permission" and assignee_value not in user_permissions:
        return False
    return user_id in candidate_user_ids


def assignee_spec_for_task(assignees: list[AssigneeSpec], task_key: str) -> AssigneeSpec | None:
    for spec in assignees:
        if spec.task_key == task_key:
            return spec
    return None
