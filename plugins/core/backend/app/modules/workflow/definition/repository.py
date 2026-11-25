from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import alive_condition
from app.core.exceptions import AppException
from app.framework.crud.repository import SqlModelCrudRepository
from app.framework.db.models import utc_now
from app.modules.organization.models import SysOrg

from ..models import WfDefinition, WfDefinitionVersion
from ..schemas import (
    WorkflowDefinitionDetailItem,
    WorkflowDefinitionItem,
    WorkflowDefinitionListQuery,
    WorkflowDefinitionVersionItem,
)

DESIGNER_SOURCES = {"designer_v1", "designer_v2", "designer_v3"}
VERSION_DRAFT = "draft"
VERSION_PUBLISHED = "published"
VERSION_OFFLINE = "offline"


def version_item(version: WfDefinitionVersion, *, current_version_id: UUID | None = None) -> WorkflowDefinitionVersionItem:
    snapshot = version.spiff_spec_snapshot if isinstance(version.spiff_spec_snapshot, dict) else {}
    item = WorkflowDefinitionVersionItem.model_validate(version)
    return item.model_copy(
        update={
            "remark": (version.flex_form or {}).get("remark"),
            "design": snapshot.get("design"),
            "source": snapshot.get("source"),
            "is_current": current_version_id is not None and current_version_id == version.id,
        }
    )


class WorkflowDefinitionRepository(SqlModelCrudRepository):
    def __init__(self) -> None:
        super().__init__(
            table_model=WfDefinition,
            item_model=WorkflowDefinitionItem,
            writable_columns=[
                "org_id",
                "definition_no",
                "definition_name",
                "business_type_code",
                "description",
                "is_active",
                "is_default",
            ],
            searchable_columns=["definition_no", "definition_name", "business_type_code"],
            filterable_columns=["business_type_code", "org_id", "is_active"],
            scope_resource="workflow_definition",
            organization_write_kind="any",
        )

    async def get_entity(self, session: AsyncSession, item_id: UUID) -> WfDefinition:
        entity = await session.get(WfDefinition, item_id)
        if entity is None or entity.deleted_at is not None:
            raise AppException("流程定义不存在", status_code=404)
        return entity

    async def _to_item(self, session: AsyncSession, entity: WfDefinition, *, org_name: str | None = None) -> WorkflowDefinitionItem:
        version_no: int | None = None
        if entity.current_version_id:
            ver = await session.get(WfDefinitionVersion, entity.current_version_id)
            version_no = ver.version_no if ver else None
        if org_name is None:
            org = await session.get(SysOrg, entity.org_id)
            org_name = org.org_name if org else None
        return WorkflowDefinitionItem.model_validate(entity).model_copy(
            update={"current_version_no": version_no, "org_name": org_name}
        )

    async def to_item(self, session: AsyncSession, entity: WfDefinition) -> WorkflowDefinitionItem:
        return await self._to_item(session, entity)

    async def disable_other_active_in_org(
        self,
        session: AsyncSession,
        *,
        business_type_code: str,
        org_id: UUID,
        exclude_definition_id: UUID,
        user_id: UUID | None,
    ) -> None:
        """同一组织同一业务类型只保留一个启用的默认流程。"""
        await session.execute(
            update(WfDefinition)
            .where(
                WfDefinition.business_type_code == business_type_code,
                WfDefinition.org_id == org_id,
                WfDefinition.is_active.is_(True),
                WfDefinition.deleted_at.is_(None),
                WfDefinition.id != exclude_definition_id,
                WfDefinition.is_default.is_(True),
            )
            .values(is_active=False, updated_at=utc_now(), updated_by=user_id)
        )

    async def assert_org_exists(self, session: AsyncSession, org_id: UUID | None) -> None:
        if org_id is None:
            return
        org = await session.get(SysOrg, org_id)
        if org is None or org.deleted_at is not None:
            raise AppException("组织不存在", status_code=404)

    async def list_versions(self, session: AsyncSession, definition_id: UUID) -> list[WfDefinitionVersion]:
        stmt = (
            select(WfDefinitionVersion)
            .where(WfDefinitionVersion.definition_id == definition_id)
            .order_by(desc(WfDefinitionVersion.version_no))
        )
        return list((await session.exec(stmt)).scalars().all())

    async def get_detail(self, session: AsyncSession, item_id: UUID) -> WorkflowDefinitionDetailItem:
        entity = await self.get_entity(session, item_id)
        base = await self._to_item(session, entity)
        versions = await self.list_versions(session, item_id)
        return WorkflowDefinitionDetailItem(
            **base.model_dump(),
            versions=[version_item(v, current_version_id=entity.current_version_id) for v in versions],
        )

    async def get_latest_design_snapshot(self, session: AsyncSession, definition_id: UUID) -> dict | None:
        versions = await self.list_versions(session, definition_id)
        row = versions[0] if versions else None
        if row is None or not isinstance(row.spiff_spec_snapshot, dict):
            return None
        if row.spiff_spec_snapshot.get("source") not in DESIGNER_SOURCES:
            return None
        return row.spiff_spec_snapshot.get("design")

    async def get_next_version_no(self, session: AsyncSession, definition_id: UUID) -> int:
        stmt = select(func.max(WfDefinitionVersion.version_no)).where(WfDefinitionVersion.definition_id == definition_id)
        current = (await session.exec(stmt)).scalar_one()
        return int(current or 0) + 1

    async def create_version(
        self,
        session: AsyncSession,
        *,
        definition_id: UUID,
        bpmn_xml: str,
        bpmn_process_no: str,
        user_id: UUID | None,
        remark: str | None,
        spiff_spec_snapshot: dict | None = None,
    ) -> WfDefinitionVersion:
        row = WfDefinitionVersion(
            definition_id=definition_id,
            version_no=await self.get_next_version_no(session, definition_id),
            bpmn_xml=bpmn_xml,
            bpmn_process_no=bpmn_process_no,
            spiff_spec_snapshot=spiff_spec_snapshot,
            status_code=VERSION_DRAFT,
            created_by=user_id,
            updated_by=user_id,
            flex_form={"remark": remark} if remark else {},
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row

    async def get_version(self, session: AsyncSession, version_id: UUID) -> WfDefinitionVersion:
        row = await session.get(WfDefinitionVersion, version_id)
        if row is None:
            raise AppException("流程版本不存在", status_code=404)
        return row

    async def publish_version(
        self,
        session: AsyncSession,
        *,
        version: WfDefinitionVersion,
        definition: WfDefinition,
        user_id: UUID | None,
    ) -> WfDefinition:
        now = utc_now()
        if definition.current_version_id and definition.current_version_id != version.id:
            previous = await session.get(WfDefinitionVersion, definition.current_version_id)
            if previous is not None and previous.status_code == VERSION_PUBLISHED:
                previous.status_code = VERSION_OFFLINE
                previous.updated_at = now
                previous.updated_by = user_id
                session.add(previous)
        version.status_code = VERSION_PUBLISHED
        version.published_at = now
        version.updated_at = now
        version.updated_by = user_id
        definition.current_version_id = version.id
        definition.is_active = True
        definition.updated_at = now
        definition.updated_by = user_id
        if definition.is_default:
            await self.disable_other_active_in_org(
                session,
                business_type_code=definition.business_type_code,
                org_id=definition.org_id,
                exclude_definition_id=definition.id,
                user_id=user_id,
            )
        session.add(version)
        session.add(definition)
        await session.flush()
        await session.refresh(definition)
        return definition

    async def list_with_filters(
        self,
        session: AsyncSession,
        params: WorkflowDefinitionListQuery,
        *,
        current_user: AuthenticatedUser,
    ) -> tuple[list[WorkflowDefinitionItem], int]:
        stmt = (
            select(WfDefinition, SysOrg.org_name)
            .outerjoin(SysOrg, WfDefinition.org_id == SysOrg.id)
            .where(alive_condition(WfDefinition))
        )
        scope = self._scope_condition(current_user, "list")
        if scope is not None:
            stmt = stmt.where(scope)
        if params.keyword:
            kw = f"%{params.keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    WfDefinition.definition_no.ilike(kw),
                    WfDefinition.definition_name.ilike(kw),
                    WfDefinition.business_type_code.ilike(kw),
                )
            )
        if params.business_type_code:
            stmt = stmt.where(WfDefinition.business_type_code == params.business_type_code)
        if params.org_id is not None:
            stmt = stmt.where(WfDefinition.org_id == params.org_id)
        if params.is_active is not None:
            stmt = stmt.where(WfDefinition.is_active == params.is_active)

        total = int((await session.exec(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
        stmt = (
            stmt.order_by(desc(WfDefinition.updated_at))
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        rows = (await session.exec(stmt)).all()
        return [await self._to_item(session, entity, org_name=org_name or "") for entity, org_name in rows], total

    async def org_chain(self, session: AsyncSession, org_id: UUID) -> list[UUID]:
        """本组织及其上级组织（由近到远）。"""
        chain: list[UUID] = []
        current: UUID | None = org_id
        while current is not None and current not in chain:
            chain.append(current)
            org = await session.get(SysOrg, current)
            current = org.parent_id if org is not None else None
        return chain

    async def find_active_definition(
        self,
        session: AsyncSession,
        *,
        business_type_code: str,
        org_id: UUID,
        definition_id: UUID | None = None,
    ) -> tuple[WfDefinition, WfDefinitionVersion] | None:
        """按组织由近到远查找已启用且已发布的流程定义。"""
        for candidate_org_id in await self.org_chain(session, org_id):
            stmt = (
                select(WfDefinition, WfDefinitionVersion)
                .join(WfDefinitionVersion, WfDefinition.current_version_id == WfDefinitionVersion.id)
                .where(
                    WfDefinition.business_type_code == business_type_code,
                    WfDefinition.org_id == candidate_org_id,
                    WfDefinition.is_active.is_(True),
                    WfDefinition.deleted_at.is_(None),
                    WfDefinitionVersion.status_code == VERSION_PUBLISHED,
                    WfDefinition.id == definition_id if definition_id else WfDefinition.is_default.is_(True),
                )
                .order_by(desc(WfDefinition.updated_at))
                .limit(1)
            )
            row = (await session.exec(stmt)).first()
            if row is not None:
                return row[0], row[1]
        return None

    async def published_definition_options(self, session, *, business_type_code, org_id):
        """业务模块配置审核流程时，只读适用组织的已发布定义元数据。"""
        chain = await self.org_chain(session, org_id)
        rows = (await session.execute(select(WfDefinition.id, WfDefinition.definition_name).join(
            WfDefinitionVersion, WfDefinitionVersion.id == WfDefinition.current_version_id).where(
            WfDefinition.org_id.in_(chain), WfDefinition.business_type_code == business_type_code,
            WfDefinition.is_active.is_(True), WfDefinition.deleted_at.is_(None),
            WfDefinitionVersion.status_code == VERSION_PUBLISHED).order_by(WfDefinition.definition_name))).all()
        return [{"id": str(row.id), "name": row.definition_name} for row in rows]

    async def get_by_definition_no(self, session: AsyncSession, definition_no: str) -> WfDefinition | None:
        stmt = select(WfDefinition).where(WfDefinition.definition_no == definition_no, WfDefinition.deleted_at.is_(None))
        return (await session.exec(stmt)).scalars().first()

    async def has_default_for_org(self, session: AsyncSession, *, org_id: UUID, business_type_code: str) -> bool:
        statement = select(WfDefinition.id).where(
            WfDefinition.org_id == org_id,
            WfDefinition.business_type_code == business_type_code,
            WfDefinition.is_default.is_(True),
            alive_condition(WfDefinition),
        ).limit(1)
        return (await session.exec(statement)).first() is not None

    async def add(self, session: AsyncSession, entity: Any) -> None:
        session.add(entity)
        await session.flush()


repository = WorkflowDefinitionRepository()
