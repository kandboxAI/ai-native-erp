from __future__ import annotations

import hashlib
from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, has_global_access
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context

from .import_excel import build_organization_import_template, parse_organization_import_workbook
from .import_models import (
    OrganizationImportError,
    OrganizationImportOptions,
    OrganizationImportResult,
    OrganizationImportRow,
    OrganizationImportSummary,
    OrganizationValidationResult,
)
from .import_repository import repository
from .models import SysOrg

PERMISSION = "organization:import"
NODE_TYPE_LABELS = {"group": "集团", "organization": "组织"}


def _count(result: OrganizationImportResult, prefix: str, node_type: str) -> None:
    field = {"group": "groups", "organization": "organizations"}[node_type]
    name = f"{prefix}_{field}"
    setattr(result, name, getattr(result, name) + 1)


class OrganizationImportService:
    async def build_template(self, current_user: AuthenticatedUser) -> bytes:
        return build_organization_import_template()

    async def validate_import(
        self,
        content: bytes,
        filename: str,
        current_user: AuthenticatedUser,
        options: OrganizationImportOptions,
    ) -> OrganizationValidationResult:
        rows, parse_errors = parse_organization_import_workbook(content, filename)
        async with get_session_context() as session:
            return await self._validate_rows(session, rows, parse_errors, current_user, options)

    async def import_data(
        self,
        content: bytes,
        filename: str,
        current_user: AuthenticatedUser,
        options: OrganizationImportOptions,
    ) -> OrganizationImportResult:
        rows, parse_errors = parse_organization_import_workbook(content, filename)
        async with get_session_context() as session:
            validation = await self._validate_rows(session, rows, parse_errors, current_user, options)
            result = OrganizationImportResult(**validation.model_dump())
            if not validation.valid:
                return result
            try:
                await self._apply_rows(session, rows, current_user, options, result)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return result

    async def _validate_rows(
        self,
        session,
        rows: list[OrganizationImportRow],
        errors: list[OrganizationImportError],
        current_user: AuthenticatedUser,
        options: OrganizationImportOptions,
    ) -> OrganizationValidationResult:
        errors = list(errors)
        if not rows and not errors:
            errors.append(OrganizationImportError(sheet="组织架构", row=1, message="至少需要一行组织架构数据"))

        seen_organizations: dict[str, int] = {}
        seen_departments: dict[tuple[str, str], int] = {}
        organization_rows: set[str] = set()
        for row in rows:
            organization_key = row.org_name.strip()
            if row.node_type in NODE_TYPE_LABELS:
                node_type_label = NODE_TYPE_LABELS[row.node_type]
                expected_org_type = row.node_type
                if organization_key in seen_organizations:
                    errors.append(OrganizationImportError(
                        sheet="组织架构",
                        row=row.row_no,
                        field="组织名称",
                        message=f"组织重复，首次出现在第 {seen_organizations[organization_key]} 行",
                    ))
                seen_organizations[organization_key] = row.row_no
                organization_rows.add(organization_key)
                existing = await repository.get_org_by_name(session, organization_key)
                if existing is None and not has_global_access(current_user, PERMISSION):
                    errors.append(OrganizationImportError(
                        sheet="组织架构",
                        row=row.row_no,
                        field="组织名称",
                        message=f"当前账号无权新建{node_type_label}；请使用全局权限账号导入组织",
                    ))
                if existing is not None:
                    if existing.org_type_code != expected_org_type:
                        errors.append(OrganizationImportError(
                            sheet="组织架构",
                            row=row.row_no,
                            field="组织名称",
                            message=f"该名称已被其他类型组织使用，不能作为{node_type_label}导入或更新",
                        ))
                        continue
                    ensure_org_access(current_user, existing.id, PERMISSION)
                    if not options.allow_update_existing:
                        errors.append(OrganizationImportError(
                            sheet="组织架构",
                            row=row.row_no,
                            field="组织名称",
                            message=f"该{node_type_label}已存在；如确需更新，请勾选允许更新已有数据",
                        ))
                if row.parent_org_name:
                    parent = await repository.get_org_by_name(session, row.parent_org_name)
                    if parent is None and row.parent_org_name not in organization_rows:
                        errors.append(OrganizationImportError(
                            sheet="组织架构",
                            row=row.row_no,
                            field="上级组织名称",
                            message="未找到上级组织；请先在前面的组织行创建或使用已有组织",
                        ))
                if row.department_name:
                    await self._validate_department_row(
                        session,
                        row,
                        organization_key,
                        existing,
                        seen_departments,
                        errors,
                        options,
                    )
            else:
                if not row.department_name:
                    errors.append(OrganizationImportError(
                        sheet="组织架构", row=row.row_no, field="部门名称", message="类型为部门时部门名称必填"
                    ))
                    continue
                org = await repository.get_org_by_name(session, organization_key)
                if org is None and organization_key not in organization_rows:
                    errors.append(OrganizationImportError(
                        sheet="组织架构", row=row.row_no, field="组织名称", message="部门所属组织不存在"
                    ))
                    continue
                if org is not None:
                    ensure_org_access(current_user, org.id, PERMISSION)
                await self._validate_department_row(
                    session,
                    row,
                    organization_key,
                    org,
                    seen_departments,
                    errors,
                    options,
                )

        summary = OrganizationImportSummary(
            rows=len(rows),
            groups=len({r.org_name for r in rows if r.node_type == "group"}),
            organizations=len({r.org_name for r in rows if r.node_type == "organization"}),
            departments=len({(r.org_name, r.department_name) for r in rows if r.department_name}),
        )
        return OrganizationValidationResult(valid=not errors, summary=summary, errors=errors)

    async def _validate_department_row(
        self,
        session,
        row: OrganizationImportRow,
        organization_key: str,
        organization: SysOrg | None,
        seen_departments: dict[tuple[str, str], int],
        errors: list[OrganizationImportError],
        options: OrganizationImportOptions,
    ) -> None:
        if not row.department_name:
            return
        key = (organization_key, row.department_name.strip())
        if key in seen_departments:
            errors.append(OrganizationImportError(
                sheet="组织架构",
                row=row.row_no,
                field="部门名称",
                message=f"同一组织部门重复，首次出现在第 {seen_departments[key]} 行",
            ))
        seen_departments[key] = row.row_no
        if organization is None:
            if row.parent_department_name:
                parent_in_file = (organization_key, row.parent_department_name.strip()) in seen_departments
                if not parent_in_file:
                    errors.append(OrganizationImportError(
                        sheet="组织架构",
                        row=row.row_no,
                        field="上级部门名称",
                        message="未找到上级部门；请先在前面的部门行创建或使用已有部门",
                    ))
            return
        department = await repository.get_department_by_name(session, organization.id, row.department_name)
        if department is not None and not options.allow_update_existing:
            errors.append(OrganizationImportError(
                sheet="组织架构",
                row=row.row_no,
                field="部门名称",
                message="该部门已存在；如确需更新，请勾选允许更新已有数据",
            ))
        if row.parent_department_name:
            parent = await repository.get_department_by_name(session, organization.id, row.parent_department_name)
            parent_in_file = (organization_key, row.parent_department_name.strip()) in seen_departments
            if parent is None and not parent_in_file:
                errors.append(OrganizationImportError(
                    sheet="组织架构",
                    row=row.row_no,
                    field="上级部门名称",
                    message="未找到上级部门；请先在前面的部门行创建或使用已有部门",
                ))

    async def _apply_rows(
        self,
        session,
        rows: list[OrganizationImportRow],
        current_user: AuthenticatedUser,
        options: OrganizationImportOptions,
        result: OrganizationImportResult,
    ) -> None:
        organizations: dict[str, SysOrg] = {}
        departments: dict[tuple[str, str], object] = {}
        for row in rows:
            organization_key = row.org_name.strip()
            if row.node_type in NODE_TYPE_LABELS:
                node_type_label = NODE_TYPE_LABELS[row.node_type]
                expected_org_type = row.node_type
                parent_id = await self._resolve_parent_organization_id(session, row.parent_org_name, organizations)
                existing = await repository.get_org_by_name(session, organization_key)
                if existing is None:
                    if not has_global_access(current_user, PERMISSION):
                        raise AppException(f"当前账号无权新建{node_type_label}", status_code=403)
                    organization = await repository.create_org(
                        session,
                        row,
                        self._code("ORG", organization_key),
                        parent_id,
                        current_user.user_id,
                    )
                    _count(result, "created", row.node_type)
                else:
                    if existing.org_type_code != expected_org_type:
                        raise AppException(f"该名称已被其他类型组织使用，不能作为{node_type_label}导入或更新：{organization_key}", status_code=400)
                    ensure_org_access(current_user, existing.id, PERMISSION)
                    if not options.allow_update_existing:
                        raise AppException(f"{node_type_label}已存在，未启用更新：{organization_key}", status_code=400)
                    await repository.update_org(session, existing, row, parent_id, current_user.user_id)
                    organization = existing
                    _count(result, "updated", row.node_type)
                organizations[organization_key] = organization
                if row.department_name:
                    department = await self._apply_department_row(
                        session,
                        row,
                        organization,
                        organization_key,
                        departments,
                        current_user,
                        options,
                        result=result,
                    )
                    departments[(organization_key, row.department_name)] = department
                continue

            organization = organizations.get(organization_key)
            if organization is None:
                organization = await repository.get_org_by_name(session, organization_key)
                if organization is None:
                    raise AppException(f"部门所属组织不存在：{organization_key}", status_code=400)
                ensure_org_access(current_user, organization.id, PERMISSION)
                organizations[organization_key] = organization
            parent_department_id = await self._resolve_parent_department_id(
                session, organization.id, organization_key, row.parent_department_name, departments
            )
            department_key = (organization_key, row.department_name or "")
            department = await self._apply_department_row(
                session,
                row,
                organization,
                organization_key,
                departments,
                current_user,
                options,
                parent_department_id=parent_department_id,
                result=result,
            )
            departments[department_key] = department

    async def _apply_department_row(
        self,
        session,
        row: OrganizationImportRow,
        organization: SysOrg,
        organization_key: str,
        departments: dict[tuple[str, str], object],
        current_user: AuthenticatedUser,
        options: OrganizationImportOptions,
        *,
        parent_department_id: UUID | None = None,
        result: OrganizationImportResult | None = None,
    ) -> object:
        if parent_department_id is None:
            parent_department_id = await self._resolve_parent_department_id(
                session, organization.id, organization_key, row.parent_department_name, departments
            )
        existing_department = await repository.get_department_by_name(session, organization.id, row.department_name or "")
        if existing_department is None:
            department = await repository.create_department(
                session,
                row,
                organization.id,
                self._code("DEPT", organization.id, row.department_name),
                parent_department_id,
                current_user.user_id,
            )
            if result is not None:
                result.created_departments += 1
            return department
        if not options.allow_update_existing:
            raise AppException(f"部门已存在，未启用更新：{row.department_name}", status_code=400)
        await repository.update_department(
            session, existing_department, row, parent_department_id, current_user.user_id
        )
        if result is not None:
            result.updated_departments += 1
        return existing_department

    async def _resolve_parent_organization_id(
        self, session, parent_name: str | None, organizations: dict[str, SysOrg]
    ) -> UUID | None:
        if not parent_name:
            root = await repository.get_root_org(session)
            return root.id if root else None
        parent = organizations.get(parent_name.strip())
        if parent is None:
            parent = await repository.get_org_by_name(session, parent_name)
        return parent.id if parent else None

    async def _resolve_parent_department_id(
        self,
        session,
        organization_id: UUID,
        branch_name: str,
        parent_name: str | None,
        departments: dict[tuple[str, str], object],
    ) -> UUID | None:
        if not parent_name:
            return None
        key = (branch_name, parent_name.strip())
        parent = departments.get(key)
        if parent is None:
            parent = await repository.get_department_by_name(session, organization_id, parent_name)
        return parent.id if parent else None

    @staticmethod
    def _code(prefix: str, *parts) -> str:
        raw = "|".join(str(part).strip().lower() for part in parts)
        return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


service = OrganizationImportService()
