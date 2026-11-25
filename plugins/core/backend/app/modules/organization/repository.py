from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import Text, cast, desc, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import org_column_scope_condition
from app.core.exceptions import AppException
from app.framework.crud.repository import SqlModelCrudRepository
from app.modules.department.models import SysDepartment
from app.modules.department.repository import repository as department_repository
from app.modules.user_profile.models import SysUser

from .models import SysOrg
from .schemas import (
    ORG_TYPE_GROUP,
    ORG_TYPE_ORGANIZATION,
    OrganizationDepartmentItem,
    OrganizationItem,
    OrganizationListWithDepartmentsQuery,
    OrganizationWithDepartmentsItem,
)

WRITABLE_COLUMNS = [
    "org_no",
    "org_name",
    "org_type_code",
    "parent_id",
    "contact_name",
    "contact_phone",
    "province",
    "city",
    "district",
    "address",
    "sort_no",
    "is_active",
    "remark",
]
SEARCHABLE_COLUMNS = ["org_no", "org_name", "contact_name", "contact_phone", "province", "city", "district", "address", "remark"]


async def writable_org_options(session, user, permission: str, keyword: str, limit: int):
    statement = select(SysOrg.id, SysOrg.org_name).where(
        SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
    )
    scope = org_column_scope_condition(SysOrg.id, user, permission)
    if scope is not None:
        statement = statement.where(scope)
    if keyword.strip():
        statement = statement.where(SysOrg.org_name.ilike(f"%{keyword.strip()}%"))
    return (await session.execute(statement.order_by(SysOrg.org_name, SysOrg.id).limit(limit))).mappings().all()
ORG_TYPE_LABELS = {ORG_TYPE_GROUP: "集团", ORG_TYPE_ORGANIZATION: "组织"}


async def _ensure_parent(session: AsyncSession, parent_id: UUID | None, self_id: UUID | None) -> None:
    if parent_id is None:
        return
    seen: set[UUID] = set()
    current: UUID | None = UUID(str(parent_id))
    while current is not None:
        if self_id is not None and current == self_id:
            raise AppException("上级组织不能是自己或自己的下级", status_code=status.HTTP_400_BAD_REQUEST)
        if current in seen:
            break
        seen.add(current)
        row = await session.get(SysOrg, current)
        if row is None or row.deleted_at is not None:
            raise AppException("上级组织不存在", status_code=status.HTTP_400_BAD_REQUEST)
        current = row.parent_id


async def normalize_org_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysOrg | None,
) -> dict[str, Any]:
    data = dict(payload)
    for key in ("org_no", "org_name"):
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip()
            if not data[key]:
                raise AppException(f"{key} 不能为空", status_code=status.HTTP_400_BAD_REQUEST)
    if data.get("org_type_code") is not None:
        from app.modules.dictionary.models import SysDict
        from app.modules.dictionary_item.models import SysDictItem
        valid = await session.scalar(select(SysDictItem.id).join(SysDict, SysDictItem.dict_id == SysDict.id).where(
            SysDict.dict_code == "sys_org_type", SysDict.is_active.is_(True), SysDict.deleted_at.is_(None),
            SysDictItem.item_code == data["org_type_code"], SysDictItem.is_active.is_(True), SysDictItem.deleted_at.is_(None)))
        if valid is None:
            raise AppException("组织类型不存在或已停用，请检查系统字典", status_code=400)
    if "parent_id" in data:
        await _ensure_parent(session, data["parent_id"], entity.id if entity else None)
    org_type = data.get("org_type_code") if "org_type_code" in data else (entity.org_type_code if entity else None)
    parent_id = data["parent_id"] if "parent_id" in data else (entity.parent_id if entity else None)
    if entity is None and data.get("parent_id") is None:
        has_root = await session.scalar(
            select(func.count()).select_from(SysOrg).where(SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None))
        )
        if has_root:
            raise AppException("请选择上级组织（每个租户只有一个根组织）", status_code=status.HTTP_400_BAD_REQUEST)
    return data


class OrganizationRepository(SqlModelCrudRepository):
    def descendant_ids_query(self, org_ids: list[UUID]):
        """公共组织目录查询契约：有效节点及其有效下级 ID，不授予业务数据访问权。"""
        descendants = select(SysOrg.id).where(
            SysOrg.id.in_(org_ids), SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
        ).cte("directory_org_descendants", recursive=True)
        descendants = descendants.union(select(SysOrg.id).join(
            descendants, SysOrg.parent_id == descendants.c.id,
        ).where(SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True)))
        return select(descendants.c.id)

    def ancestor_ids_query(self, org_ids: list[UUID]):
        """公共只读查询契约：给定组织及其有效祖先的 ID，不返回人员或其他组织字段。

        用于组织级公开配置的向下继承，不扩大调用者的业务数据权限。
        UNION 去重保证异常循环关系也能终止；停用或已删除节点不参与继承。
        """
        ancestors = select(SysOrg.id, SysOrg.parent_id).where(
            SysOrg.id.in_(org_ids), SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True),
        ).cte("visible_org_ancestors", recursive=True)
        ancestors = ancestors.union(select(SysOrg.id, SysOrg.parent_id).join(
            ancestors, SysOrg.id == ancestors.c.parent_id,
        ).where(SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True)))
        return select(ancestors.c.id)

    def _structure_conditions(self, params: OrganizationListWithDepartmentsQuery) -> list[Any]:
        conditions: list[Any] = []
        if params.keyword:
            keyword = f"%{params.keyword.strip()}%"
            conditions.append(or_(*[cast(getattr(SysOrg, name), Text).ilike(keyword) for name in SEARCHABLE_COLUMNS]))
        for name in ["org_no", "org_name", "contact_name", "contact_phone", "province", "city", "district", "address"]:
            value = getattr(params, name)
            if value:
                conditions.append(cast(getattr(SysOrg, name), Text).ilike(f"%{value.strip()}%"))
        if params.parent_id is not None:
            conditions.append(SysOrg.parent_id == params.parent_id)
        if params.org_type_code is not None:
            conditions.append(SysOrg.org_type_code == params.org_type_code)
        if params.is_active is not None:
            conditions.append(SysOrg.is_active.is_(params.is_active))
        if params.created_at_start is not None:
            conditions.append(SysOrg.created_at >= params.created_at_start)
        if params.created_at_end is not None:
            conditions.append(SysOrg.created_at <= params.created_at_end)
        return conditions

    async def _departments_by_org(self, session, org_ids: list[UUID], current_user, action: str) -> dict[UUID, list[OrganizationDepartmentItem]]:
        if not org_ids:
            return {}
        statement = select(SysDepartment).where(SysDepartment.org_id.in_(org_ids))
        statement = department_repository._apply_alive(department_repository._apply_scope(statement, current_user, action))
        statement = statement.order_by(SysDepartment.sort_no.nulls_last(), SysDepartment.created_at)
        result: dict[UUID, list[OrganizationDepartmentItem]] = {}
        for row in (await session.exec(statement)).all():
            result.setdefault(row.org_id, []).append(OrganizationDepartmentItem.model_validate(row))
        return result

    async def _query_structure(self, session, params, current_user, *, action: str, limit: int, offset: int):
        conditions = self._structure_conditions(params)
        total_statement = self._apply_alive(self._apply_scope(select(func.count()).select_from(SysOrg), current_user, action))
        items_statement = self._apply_alive(self._apply_scope(select(SysOrg), current_user, action))
        for condition in conditions:
            total_statement = total_statement.where(condition)
            items_statement = items_statement.where(condition)
        total = (await session.exec(total_statement)).one() or 0
        items_statement = items_statement.order_by(SysOrg.sort_no.nulls_last(), desc(SysOrg.created_at)).limit(limit).offset(offset)
        orgs = (await session.exec(items_statement)).all()
        departments = await self._departments_by_org(session, [org.id for org in orgs], current_user, action)
        items = [
            OrganizationWithDepartmentsItem.model_validate({**org.model_dump(), "children": departments.get(org.id, [])})
            for org in orgs
        ]
        return int(total), items

    async def list_with_departments(self, session, params, current_user) -> dict:
        total, items = await self._query_structure(
            session, params, current_user, action="list", limit=params.page_size, offset=(params.page - 1) * params.page_size
        )
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }

    async def tree(self, session, current_user) -> list[dict[str, Any]]:
        statement = self._apply_alive(self._apply_scope(select(SysOrg), current_user, "list"))
        rows = (await session.exec(statement.order_by(SysOrg.sort_no.nulls_last(), SysOrg.created_at))).all()
        # 校区账号仍需知道所属学校；只补可见节点的祖先，不带出其他校区。
        included = {row.id for row in rows}
        pending = {row.parent_id for row in rows if row.parent_id and row.parent_id not in included}
        while pending:
            parents = (await session.exec(select(SysOrg).where(
                SysOrg.id.in_(pending), SysOrg.deleted_at.is_(None)
            ))).all()
            rows.extend(parents)
            included.update(row.id for row in parents)
            pending = {row.parent_id for row in parents if row.parent_id and row.parent_id not in included}
        nodes: dict[UUID, dict[str, Any]] = {}
        for row in rows:
            nodes[row.id] = {
                "id": str(row.id),
                "parent_id": str(row.parent_id) if row.parent_id else None,
                "org_no": row.org_no,
                "org_name": row.org_name,
                "org_type_code": row.org_type_code,
                "sort_no": row.sort_no,
                "is_active": row.is_active,
                "children": [],
            }
        roots: list[dict[str, Any]] = []
        for row in rows:
            node = nodes[row.id]
            if row.parent_id in nodes:
                nodes[row.parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    async def export_rows(self, session, params, current_user, *, limit: int) -> list[dict[str, Any]]:
        """与 list_with_departments 相同筛选；组织 + 下属部门展开为多行。"""
        _total, items = await self._query_structure(session, params, current_user, action="export", limit=limit, offset=0)
        flat: list[dict[str, Any]] = []
        for org in items:
            packed = org.model_dump(mode="json")
            base = {
                "org_no": packed.get("org_no") or "",
                "org_name": packed.get("org_name") or "",
                "province": packed.get("province") or "",
                "city": packed.get("city") or "",
                "district": packed.get("district") or "",
                "address": packed.get("address") or "",
            }
            flat.append(
                {
                    "structure_node_type": ORG_TYPE_LABELS.get(packed.get("org_type_code"), "组织"),
                    **base,
                    "department_no": "",
                    "department_name": "",
                    "contact_name": packed.get("contact_name") or "",
                    "contact_phone": packed.get("contact_phone") or "",
                    "remark": packed.get("remark") or "",
                    "created_at": packed.get("created_at"),
                }
            )
            for child in packed.get("children") or []:
                flat.append(
                    {
                        "structure_node_type": "部门",
                        **base,
                        "department_no": child.get("department_no") or "",
                        "department_name": child.get("department_name") or "",
                        "contact_name": "",
                        "contact_phone": "",
                        "remark": child.get("remark") or "",
                        "created_at": child.get("created_at"),
                    }
                )
        return flat

    async def delete(self, session, item_id: str, current_user: AuthenticatedUser) -> bool:
        org_id = self._normalize_id(item_id)
        child = await session.scalar(
            select(func.count()).select_from(SysOrg).where(SysOrg.parent_id == org_id, SysOrg.deleted_at.is_(None))
        )
        if child:
            raise AppException("该组织下还有下级组织，不能删除", status_code=status.HTTP_409_CONFLICT)
        dept = await session.scalar(
            select(func.count()).select_from(SysDepartment).where(SysDepartment.org_id == org_id, SysDepartment.deleted_at.is_(None))
        )
        if dept:
            raise AppException("该组织下还有部门，不能删除", status_code=status.HTTP_409_CONFLICT)
        users = await session.scalar(
            select(func.count()).select_from(SysUser).where(SysUser.org_id == org_id, SysUser.deleted_at.is_(None))
        )
        if users:
            raise AppException("该组织下还有用户，不能删除", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)


repository = OrganizationRepository(
    table_model=SysOrg,
    item_model=OrganizationItem,
    writable_columns=WRITABLE_COLUMNS,
    searchable_columns=SEARCHABLE_COLUMNS,
    filterable_columns=["org_type_code", "parent_id", "is_active"],
    create_payload_normalizer=normalize_org_payload,
    update_payload_normalizer=normalize_org_payload,
    scope_resource="organization",
    organization_write_kind="any",
)
