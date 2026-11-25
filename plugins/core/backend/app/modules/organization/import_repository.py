from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now
from app.modules.department.models import SysDepartment

from .import_models import OrganizationImportRow
from .models import SysOrg


class OrganizationImportRepository:
    async def get_root_org(self, session: AsyncSession) -> SysOrg | None:
        statement = select(SysOrg).where(SysOrg.parent_id.is_(None), SysOrg.deleted_at.is_(None)).order_by(SysOrg.created_at)
        return (await session.exec(statement)).scalars().first()

    async def get_org_by_name(self, session: AsyncSession, name: str) -> SysOrg | None:
        rows = (
            await session.exec(select(SysOrg).where(SysOrg.org_name == name.strip(), SysOrg.deleted_at.is_(None)).limit(2))
        ).scalars().all()
        return rows[0] if len(rows) == 1 else None

    async def get_department_by_name(self, session: AsyncSession, org_id: UUID, name: str) -> SysDepartment | None:
        rows = (
            await session.exec(
                select(SysDepartment)
                .where(
                    SysDepartment.org_id == org_id,
                    SysDepartment.department_name == name.strip(),
                    SysDepartment.deleted_at.is_(None),
                )
                .limit(2)
            )
        ).scalars().all()
        return rows[0] if len(rows) == 1 else None

    async def create_org(
        self,
        session: AsyncSession,
        row: OrganizationImportRow,
        org_no: str,
        parent_id: UUID | None,
        user_id: UUID,
    ) -> SysOrg:
        entity = SysOrg(
            org_no=org_no,
            org_name=row.org_name,
            org_type_code=row.node_type,
            parent_id=parent_id,
            contact_name=row.leader_name,
            contact_phone=row.contact_phone,
            province=row.province,
            city=row.city,
            district=row.district,
            address=row.address,
            sort_no=row.sort_no,
            is_active=row.is_active,
            remark=row.remark,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(entity)
        await session.flush()
        return entity

    async def update_org(
        self,
        session: AsyncSession,
        entity: SysOrg,
        row: OrganizationImportRow,
        parent_id: UUID | None,
        user_id: UUID,
    ) -> None:
        if parent_id is not None and parent_id != entity.id:
            entity.parent_id = parent_id
        entity.contact_name = row.leader_name
        entity.contact_phone = row.contact_phone
        entity.province = row.province
        entity.city = row.city
        entity.district = row.district
        entity.address = row.address
        entity.sort_no = row.sort_no
        entity.is_active = row.is_active
        entity.remark = row.remark or entity.remark
        entity.updated_by = user_id
        entity.updated_at = utc_now()
        session.add(entity)
        await session.flush()

    async def create_department(
        self,
        session: AsyncSession,
        row: OrganizationImportRow,
        org_id: UUID,
        department_no: str,
        parent_id: UUID | None,
        user_id: UUID,
    ) -> SysDepartment:
        entity = SysDepartment(
            org_id=org_id,
            department_no=department_no,
            department_name=row.department_name or "",
            parent_id=parent_id,
            sort_no=row.sort_no,
            is_active=row.is_active,
            remark=row.remark,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(entity)
        await session.flush()
        return entity

    async def update_department(
        self,
        session: AsyncSession,
        entity: SysDepartment,
        row: OrganizationImportRow,
        parent_id: UUID | None,
        user_id: UUID,
    ) -> None:
        entity.parent_id = parent_id
        entity.sort_no = row.sort_no
        entity.is_active = row.is_active
        entity.remark = row.remark or entity.remark
        entity.updated_by = user_id
        entity.updated_at = utc_now()
        session.add(entity)
        await session.flush()


repository = OrganizationImportRepository()
