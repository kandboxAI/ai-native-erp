"""资产管理数据访问；所有查询、范围过滤和持久化集中在本文件。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.data_scope import ORG_ACCESS_ALL
from app.auth.scope_filters import accessible_org_ids, register_related_scope, scoped_conditions
from app.modules.department.models import SysDepartment
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.inventory.models import MdItem, MdItemCategory
from app.modules.organization.models import SysOrg
from app.modules.user_profile.models import SysUser

from app.modules.location.models import MdLocation
from app.modules.location.public import require_location, register_consumer
from app.modules.location.service import location_views

from .models import AssetChangeEvent, AssetLocation, AssetLocationItem, AssetRegister
from .schemas import AssetLedgerQuery, AssetRegisterQuery, LocationAssetQuery


def _custody_related_scope(table, user):
    """资产的关联人是当前保管人；建档人、历史申领人不代表当前保管责任。"""
    condition = table.custodian_user_id == user.user_id
    if user.org_access_mode_code != ORG_ACCESS_ALL:
        # 共享仓库发放给本人后，个人保管关系仍有效，资产权属不随申领人主组织改变。
        condition &= or_(table.org_id.in_(accessible_org_ids(user)), table.location_id.is_(None))
    return condition


register_related_scope(AssetRegister.__tablename__, _custody_related_scope)


class AssetRepository:
    async def disposal_custody_event(self, session, event_id, asset_id, org_id, source_id):
        return (await session.exec(select(AssetChangeEvent).where(
            AssetChangeEvent.id == event_id, AssetChangeEvent.asset_register_id == asset_id,
            AssetChangeEvent.org_id == org_id, AssetChangeEvent.source_type_code == "asset_disposal",
            AssetChangeEvent.source_id == source_id, AssetChangeEvent.event_type_code == "transfer",
        ))).first()

    async def custody_restore_available(self, session, event):
        for model, key in ((AssetLocation, event.from_location_id), (SysDepartment, event.from_department_id),
                           (SysUser, event.from_custodian_user_id)):
            if key is not None and (await session.exec(select(model.id).where(
                model.id == key, model.deleted_at.is_(None), model.is_active.is_(True),
            ))).first() is None:
                return False
        return True

    async def lock_stock_item_for_asset(self, session, model, asset_id):
        """先取得库存物料锁，再锁资产，所有库存关联资产动作使用相同锁序。"""
        item_id = (await session.exec(select(model.item_id).where(model.id == asset_id,
            model.acquisition_source_code.in_(["stock_receipt", "stock_opening"])))).first()
        if item_id is not None:
            from app.modules.inventory.public import lock_inventory_items
            await lock_inventory_items(session, {item_id})

    @staticmethod
    def adapter_number(location_id):
        return f"AL-{location_id.hex.upper()}"

    @staticmethod
    def location_order():
        # 优先使用启用的内部主关联，其余历史别名按创建顺序稳定选择。
        return (AssetLocation.is_active.desc(), (AssetLocation.id == AssetLocation.physical_location_id).desc(),
                AssetLocation.created_at, AssetLocation.id)

    def location_filter(self, asset_model, location_id):
        member, selected = aliased(AssetLocation), aliased(AssetLocation)
        physical = select(selected.physical_location_id).where(
            selected.id == location_id, selected.org_id == member.org_id,
            selected.deleted_at.is_(None), selected.physical_location_id.is_not(None)).correlate(member)
        direct_physical = select(MdLocation.id).where(
            MdLocation.id == location_id, MdLocation.org_id == member.org_id,
            MdLocation.deleted_at.is_(None)).correlate(member)
        members = select(member.id).where(
            member.org_id == asset_model.org_id, member.deleted_at.is_(None),
            or_(member.id == location_id, member.physical_location_id.in_(direct_physical),
                member.physical_location_id.in_(physical))).correlate(asset_model)
        return asset_model.location_id.in_(members)

    async def has_custody_for_user(self, session, *, org_id, user_id):
        """内部跨域只读契约：指定组织/保管人是否仍有有效实物资产，不返回人员信息。"""
        for model in (AssetRegister, AssetLocationItem):
            conditions = [model.org_id == org_id, model.custodian_user_id == user_id,
                model.deleted_at.is_(None), model.registration_status_code == "confirmed",
                model.status_code != "disposed"]
            if model is AssetLocationItem:
                conditions.append(model.quantity > 0)
            if (await session.exec(select(model.id).where(*conditions).limit(1))).first() is not None:
                return True
        return False

    async def list_ledger(
        self,
        session: AsyncSession,
        query: AssetLedgerQuery,
        user: AuthenticatedUser,
    ) -> tuple[int, list[dict[str, Any]]]:
        """统一读取两类资产；只合并展示字段，不混合各自的数据生命周期。"""

        statements = []
        if query.management_mode in (None, "batch"):
            department = aliased(SysDepartment)
            custodian = aliased(SysUser)
            conditions = list(scoped_conditions(AssetLocationItem, user, "asset_register:list"))
            if query.item_id:
                conditions.append(AssetLocationItem.item_id == query.item_id)
            if query.is_asset_managed is not None:
                conditions.append(MdItem.is_asset_managed == query.is_asset_managed)
            if query.org_id:
                conditions.append(AssetLocationItem.org_id == query.org_id)
            if query.location_id:
                conditions.append(self.location_filter(AssetLocationItem, query.location_id))
            if query.asset_type_code:
                conditions.append(AssetLocationItem.asset_type_code == query.asset_type_code)
            if query.status_code:
                conditions.append(AssetLocationItem.status_code == query.status_code)
            if query.registration_status_code:
                conditions.append(AssetLocationItem.registration_status_code == query.registration_status_code)
            if query.department_id:
                conditions.append(AssetLocationItem.department_id == query.department_id)
            if query.custodian_user_id:
                conditions.append(AssetLocationItem.custodian_user_id == query.custodian_user_id)
            if query.keyword:
                word = f"%{query.keyword.strip()}%"
                conditions.append(
                    or_(
                        MdItem.item_no.ilike(word),
                        MdItem.item_name.ilike(word),
                        MdItem.specification.ilike(word),
                        AssetLocation.location_name.ilike(word),
                    )
                )
            statements.append(
                select(
                    sa.literal("batch").label("management_mode"),
                    AssetLocationItem.id.label("id"),
                    AssetLocationItem.acquisition_source_code.label("acquisition_source_code"),
                    AssetLocationItem.org_id.label("org_id"),
                    sa.cast(sa.null(), sa.String()).label("asset_no"),
                    AssetLocationItem.item_id.label("item_id"),
                    MdItem.item_no.label("item_no"),
                    MdItem.item_name.label("item_name"),
                    MdItem.is_asset_managed.label("is_asset_managed"),
                    MdItem.specification.label("specification"),
                    AssetLocationItem.asset_type_code.label("asset_type_code"),
                    sa.cast(sa.null(), sa.String()).label("serial_no"),
                    AssetLocationItem.location_id.label("location_id"),
                    AssetLocationItem.custody_location_note.label("custody_location_note"),
                    AssetLocation.location_no.label("location_no"),
                    AssetLocation.location_name.label("location_name"),
                    AssetLocationItem.quantity.label("quantity"),
                    AssetLocationItem.unit_code_snapshot.label("unit_code"),
                    AssetLocationItem.department_id.label("department_id"),
                    department.department_name.label("department_name"),
                    AssetLocationItem.custodian_user_id.label("custodian_user_id"),
                    custodian.display_name.label("custodian_name"),
                    AssetLocationItem.status_code.label("status_code"),
                    AssetLocationItem.registration_status_code.label("registration_status_code"),
                    AssetLocationItem.registered_at.label("registered_at"),
                    AssetLocationItem.voided_at.label("voided_at"),
                    AssetLocationItem.void_reason.label("void_reason"),
                    sa.cast(sa.null(), sa.Date()).label("acquired_date"),
                    sa.cast(sa.null(), sa.Numeric(18, 2)).label("original_amount"),
                    AssetLocationItem.version_no.label("version_no"),
                    AssetLocationItem.remark.label("remark"),
                    AssetLocationItem.created_at.label("created_at"),
                    AssetLocationItem.updated_at.label("updated_at"),
                )
                .join(MdItem, MdItem.id == AssetLocationItem.item_id)
                .join(AssetLocation, AssetLocation.id == AssetLocationItem.location_id, isouter=True)
                .join(department, department.id == AssetLocationItem.department_id, isouter=True)
                .join(custodian, custodian.id == AssetLocationItem.custodian_user_id, isouter=True)
                .where(*conditions)
            )

        if query.management_mode in (None, "individual"):
            department = aliased(SysDepartment)
            custodian = aliased(SysUser)
            conditions = list(scoped_conditions(AssetRegister, user, "asset_register:list"))
            if query.item_id:
                conditions.append(AssetRegister.item_id == query.item_id)
            if query.is_asset_managed is not None:
                conditions.append(MdItem.is_asset_managed == query.is_asset_managed)
            if query.org_id:
                conditions.append(AssetRegister.org_id == query.org_id)
            if query.location_id:
                conditions.append(self.location_filter(AssetRegister, query.location_id))
            if query.asset_type_code:
                conditions.append(AssetRegister.asset_type_code == query.asset_type_code)
            if query.status_code:
                conditions.append(AssetRegister.status_code == query.status_code)
            if query.registration_status_code:
                conditions.append(AssetRegister.registration_status_code == query.registration_status_code)
            if query.department_id:
                conditions.append(AssetRegister.department_id == query.department_id)
            if query.custodian_user_id:
                conditions.append(AssetRegister.custodian_user_id == query.custodian_user_id)
            if query.keyword:
                word = f"%{query.keyword.strip()}%"
                conditions.append(
                    or_(
                        AssetRegister.asset_no.ilike(word),
                        AssetRegister.serial_no.ilike(word),
                        MdItem.item_no.ilike(word),
                        MdItem.item_name.ilike(word),
                        MdItem.specification.ilike(word),
                        AssetLocation.location_name.ilike(word),
                    )
                )
            statements.append(
                select(
                    sa.literal("individual").label("management_mode"),
                    AssetRegister.id.label("id"),
                    AssetRegister.acquisition_source_code.label("acquisition_source_code"),
                    AssetRegister.org_id.label("org_id"),
                    AssetRegister.asset_no.label("asset_no"),
                    AssetRegister.item_id.label("item_id"),
                    MdItem.item_no.label("item_no"),
                    MdItem.item_name.label("item_name"),
                    MdItem.is_asset_managed.label("is_asset_managed"),
                    MdItem.specification.label("specification"),
                    AssetRegister.asset_type_code.label("asset_type_code"),
                    AssetRegister.serial_no.label("serial_no"),
                    AssetRegister.location_id.label("location_id"),
                    AssetRegister.custody_location_note.label("custody_location_note"),
                    AssetLocation.location_no.label("location_no"),
                    AssetLocation.location_name.label("location_name"),
                    sa.literal(Decimal("1"), type_=sa.Numeric(18, 3)).label("quantity"),
                    MdItem.unit_code.label("unit_code"),
                    AssetRegister.department_id.label("department_id"),
                    department.department_name.label("department_name"),
                    AssetRegister.custodian_user_id.label("custodian_user_id"),
                    custodian.display_name.label("custodian_name"),
                    AssetRegister.status_code.label("status_code"),
                    AssetRegister.registration_status_code.label("registration_status_code"),
                    AssetRegister.registered_at.label("registered_at"),
                    AssetRegister.voided_at.label("voided_at"),
                    AssetRegister.void_reason.label("void_reason"),
                    AssetRegister.acquired_date.label("acquired_date"),
                    AssetRegister.original_amount.label("original_amount"),
                    AssetRegister.version_no.label("version_no"),
                    AssetRegister.remark.label("remark"),
                    AssetRegister.created_at.label("created_at"),
                    AssetRegister.updated_at.label("updated_at"),
                )
                .join(MdItem, MdItem.id == AssetRegister.item_id)
                .join(AssetLocation, AssetLocation.id == AssetRegister.location_id, isouter=True)
                .join(department, department.id == AssetRegister.department_id, isouter=True)
                .join(custodian, custodian.id == AssetRegister.custodian_user_id, isouter=True)
                .where(*conditions)
            )

        combined = statements[0] if len(statements) == 1 else sa.union_all(*statements)
        ledger = combined.subquery("asset_ledger")
        total = (
            await session.execute(select(func.count()).select_from(ledger))
        ).scalar_one()
        result = await session.execute(
            select(ledger)
            .order_by(ledger.c.updated_at.desc(), ledger.c.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return int(total or 0), [dict(row) for row in result.mappings().all()]

    async def valid_dict_item(self, session: AsyncSession, dict_code: str, item_code: str) -> bool:
        return (
            await session.exec(
                select(SysDictItem.id)
                .join(SysDict, SysDict.id == SysDictItem.dict_id)
                .where(
                    SysDict.dict_code == dict_code,
                    SysDict.is_active.is_(True),
                    SysDict.deleted_at.is_(None),
                    SysDictItem.item_code == item_code,
                    SysDictItem.is_active.is_(True),
                    SysDictItem.deleted_at.is_(None),
                )
            )
        ).first() is not None

    async def dictionary_options(self, session: AsyncSession, codes: set[str]) -> dict[str, list[dict[str, str]]]:
        rows = (
            await session.exec(
                select(SysDict.dict_code, SysDictItem.item_code, SysDictItem.item_name)
                .join(SysDictItem, SysDictItem.dict_id == SysDict.id)
                .where(
                    SysDict.dict_code.in_(codes),
                    SysDict.is_active.is_(True),
                    SysDict.deleted_at.is_(None),
                    SysDictItem.is_active.is_(True),
                    SysDictItem.deleted_at.is_(None),
                )
                .order_by(SysDict.dict_code, SysDictItem.sort_no, SysDictItem.item_code)
            )
        ).all()
        result = {code: [] for code in codes}
        for dict_code, item_code, item_name in rows:
            result[dict_code].append({"value": item_code, "label": item_name})
        return result

    @staticmethod
    def asset_item_statement(keyword: str | None = None):
        # md_item 为当前租户共享主数据；调用方先验证目标组织权限。
        statement = (
            select(MdItem, MdItemCategory.category_name)
            .join(MdItemCategory, sa.and_(MdItemCategory.id == MdItem.category_id,
                                       MdItemCategory.deleted_at.is_(None)), isouter=True)
            .where(MdItem.deleted_at.is_(None), MdItem.is_active.is_(True),
                   MdItem.is_asset_managed.is_(True))
            .order_by(MdItem.item_name, MdItem.item_no, MdItem.id)
        )
        if keyword and keyword.strip():
            word = f"%{keyword.strip()}%"
            statement = statement.where(sa.or_(MdItem.item_no.ilike(word),
                MdItem.item_name.ilike(word), MdItem.specification.ilike(word)))
        return statement

    @staticmethod
    def asset_item_option(item, category_name):
        return {
            "id": str(item.id), "item_no": item.item_no, "item_name": item.item_name,
            "specification": item.specification, "unit_code": item.unit_code,
            "unit_price": str(item.unit_price) if item.unit_price is not None else None,
            "category_name": category_name,
            "default_asset_type_code": item.default_asset_type_code,
            "default_asset_management_mode_code": "individual",
        }

    async def asset_item_options(self, session, query):
        statement = self.asset_item_statement(query.keyword)
        total = (await session.exec(select(sa.func.count()).select_from(statement.order_by(None).subquery()))).one()
        rows = (await session.exec(statement.offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return {"items": [self.asset_item_option(item, category) for item, category in rows],
                "total": total, "page": query.page, "page_size": query.page_size}

    async def option_rows(
        self,
        session: AsyncSession,
        org_id: UUID,
        user: AuthenticatedUser,
        permission: str,
    ) -> dict[str, list[dict[str, Any]]]:
        item_rows = (await session.exec(self.asset_item_statement().limit(50))).all()
        master_rows = (await session.exec(select(MdLocation).where(
            MdLocation.org_id == org_id, *scoped_conditions(MdLocation, user, permission)
        ))).all()
        masters = [item for item in location_views(master_rows) if item["is_selectable"]]
        asset_rows = (await session.exec(select(AssetLocation).where(
            AssetLocation.org_id == org_id, AssetLocation.deleted_at.is_(None)
        ).order_by(*self.location_order()))).all()
        mapped, aliases = {}, {}
        for row in asset_rows:
            if row.physical_location_id:
                key = str(row.physical_location_id)
                mapped.setdefault(key, row)
                aliases.setdefault(key, []).append(str(row.id))
        locations = []
        for master in masters:
            config = mapped.get(master["id"])
            if config is not None and not config.is_active:
                continue
            locations.append({
                "id": str(config.id) if config else master["id"],
                "physical_location_id": master["id"],
                "asset_location_ids": aliases.get(master["id"], []),
                "location_no": master["location_no"], "location_name": master["location_name"],
            })
        active_location_count = (
            select(func.count(MdLocation.id))
            .where(
                MdLocation.org_id == SysOrg.id,
                MdLocation.deleted_at.is_(None),
                MdLocation.is_active.is_(True),
            )
            .correlate(SysOrg)
            .scalar_subquery()
        )
        organizations = (
            await session.exec(
                select(SysOrg, active_location_count.label("active_location_count"))
                .where(
                    *scoped_conditions(SysOrg, user, permission),
                    SysOrg.is_active.is_(True),
                )
                .order_by(SysOrg.org_name, SysOrg.org_no)
            )
        ).all()
        departments = (
            await session.exec(
                select(SysDepartment, SysOrg.org_name)
                .join(SysOrg, SysOrg.id == SysDepartment.org_id)
                .where(
                    *scoped_conditions(SysDepartment, user, permission),
                    SysDepartment.is_active.is_(True),
                    SysOrg.deleted_at.is_(None),
                    SysOrg.is_active.is_(True),
                )
                .order_by(
                    SysOrg.org_name,
                    SysDepartment.department_name,
                    SysDepartment.department_no,
                )
            )
        ).all()
        users = (
            await session.exec(
                select(SysUser)
                .where(
                    *scoped_conditions(SysUser, user, permission),
                    SysUser.is_active.is_(True),
                )
                .order_by(SysUser.display_name)
                .limit(500)
            )
        ).all()
        return {
            "organizations": [
                {
                    "id": str(organization.id),
                    "org_no": organization.org_no,
                    "org_name": organization.org_name,
                    "active_location_count": int(location_count or 0),
                }
                for organization, location_count in organizations
            ],
            "items": [self.asset_item_option(item, category_name) for item, category_name in item_rows],
            "locations": locations,
            "departments": [
                {
                    "id": str(department.id),
                    "org_id": str(department.org_id),
                    "org_name": org_name,
                    "department_no": department.department_no,
                    "department_name": department.department_name,
                }
                for department, org_name in departments
            ],
            "users": [{"id": str(row.id), "display_name": row.display_name} for row in users],
        }

    async def item(self, session: AsyncSession, item_id: UUID) -> MdItem | None:
        return (
            await session.exec(
                select(MdItem).where(MdItem.id == item_id, MdItem.deleted_at.is_(None), MdItem.is_active.is_(True))
                .with_for_update(read=True)
            )
        ).first()

    async def department_for_org(
        self,
        session: AsyncSession,
        department_id: UUID | None,
        org_id: UUID,
    ) -> SysDepartment | None:
        if department_id is None:
            return None
        return (
            await session.exec(
                select(SysDepartment).where(
                    SysDepartment.id == department_id,
                    SysDepartment.org_id == org_id,
                    SysDepartment.deleted_at.is_(None),
                    SysDepartment.is_active.is_(True),
                )
            )
        ).first()

    async def department_for_orgs(self, session, department_id, org_ids):
        """来源服务传入已鉴权组织集合；不接受客户端直接指定核对范围。"""
        if department_id is None or not org_ids:
            return None
        return (await session.exec(select(SysDepartment).where(
            SysDepartment.id == department_id,
            SysDepartment.org_id.in_(org_ids),
            SysDepartment.deleted_at.is_(None),
            SysDepartment.is_active.is_(True),
        ))).first()

    async def department_in_scope(
        self,
        session: AsyncSession,
        department_id: UUID | None,
        user: AuthenticatedUser,
        permission: str,
    ) -> SysDepartment | None:
        if department_id is None:
            return None
        return (
            await session.exec(
                select(SysDepartment).where(
                    SysDepartment.id == department_id,
                    *scoped_conditions(SysDepartment, user, permission),
                    SysDepartment.is_active.is_(True),
                )
            )
        ).first()

    async def user_for_org(
        self,
        session: AsyncSession,
        user_id: UUID | None,
        org_id: UUID,
    ) -> SysUser | None:
        if user_id is None:
            return None
        return (
            await session.exec(
                select(SysUser).where(
                    SysUser.id == user_id,
                    SysUser.org_id == org_id,
                    SysUser.deleted_at.is_(None),
                    SysUser.is_active.is_(True),
                )
            )
        ).first()

    async def user_in_scope(
        self,
        session: AsyncSession,
        user_id: UUID | None,
        current_user: AuthenticatedUser,
        permission: str,
    ) -> SysUser | None:
        if user_id is None:
            return None
        return (
            await session.exec(
                select(SysUser).where(
                    SysUser.id == user_id,
                    *scoped_conditions(SysUser, current_user, permission),
                    SysUser.is_active.is_(True),
                )
            )
        ).first()

    async def location_for_org(
        self, session: AsyncSession, location_id: UUID, org_id: UUID, *, for_update: bool = False, user=None
    ) -> AssetLocation | None:
        statement = select(AssetLocation).where(
            or_(AssetLocation.id == location_id, AssetLocation.physical_location_id == location_id),
            AssetLocation.org_id == org_id, AssetLocation.deleted_at.is_(None),
        )
        statement = statement.order_by((AssetLocation.id == location_id).desc(), *self.location_order())
        row = (await session.exec(statement)).first()
        master_id = row.physical_location_id if row else location_id
        if master_id is None:
            return None
        master = await require_location(session, master_id, org_id, for_update=True)
        if row is None:
            row = await self.asset_location_for_physical(session, master.id)
        if row is None:
            row = AssetLocation(id=master.id, org_id=org_id, physical_location_id=master.id,
                created_by=user.user_id if user else None, updated_by=user.user_id if user else None,
                location_no=self.adapter_number(master.id), location_name=master.location_name,
                location_type_code=master.location_type_code)
            session.add(row)
            await session.flush()
        return row

    async def asset_location_for_physical(self, session, location_id):
        return (await session.exec(select(AssetLocation).where(
            AssetLocation.physical_location_id == location_id, AssetLocation.deleted_at.is_(None)
        ).order_by(*self.location_order()))).first()

    async def location_no_exists(
        self, session: AsyncSession, org_id: UUID, location_no: str, *, exclude_id: UUID | None = None
    ) -> bool:
        conditions = [
            AssetLocation.org_id == org_id,
            AssetLocation.location_no == location_no,
            AssetLocation.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            conditions.append(AssetLocation.id != exclude_id)
        return (await session.exec(select(AssetLocation.id).where(*conditions))).first() is not None


    async def get_location(
        self,
        session: AsyncSession,
        location_id: UUID,
        user: AuthenticatedUser,
        permission: str,
        *,
        for_update: bool = False,
    ) -> AssetLocation | None:
        statement = select(AssetLocation).where(
            AssetLocation.id == location_id,
            *scoped_conditions(AssetLocation, user, permission),
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def location_has_children_or_assets(self, session: AsyncSession, location_id: UUID) -> bool:
        child = (
            await session.exec(
                select(AssetLocation.id).where(AssetLocation.parent_id == location_id, AssetLocation.deleted_at.is_(None))
            )
        ).first()
        if child is not None:
            return True
        quantity_asset = (
            await session.exec(
                select(AssetLocationItem.id).where(
                    AssetLocationItem.location_id == location_id, AssetLocationItem.deleted_at.is_(None)
                )
            )
        ).first()
        if quantity_asset is not None:
            return True
        return (
            await session.exec(
                select(AssetRegister.id).where(AssetRegister.location_id == location_id, AssetRegister.deleted_at.is_(None))
            )
        ).first() is not None

    async def location_parent_would_cycle(
        self, session: AsyncSession, location_id: UUID, parent_id: UUID | None
    ) -> bool:
        """沿父链检查环；Repository 负责所有层级查询。"""
        seen = {location_id}
        current_id = parent_id
        while current_id is not None:
            if current_id in seen:
                return True
            seen.add(current_id)
            current_id = (
                await session.exec(
                    select(AssetLocation.parent_id).where(
                        AssetLocation.id == current_id,
                        AssetLocation.deleted_at.is_(None),
                    )
                )
            ).first()
        return False

    async def location_item_by_key(
        self,
        session: AsyncSession,
        location_id: UUID,
        item_id: UUID,
        *,
        for_update: bool = False,
    ) -> AssetLocationItem | None:
        statement = select(AssetLocationItem).where(
            AssetLocationItem.location_id == location_id,
            AssetLocationItem.item_id == item_id,
            AssetLocationItem.deleted_at.is_(None),
            AssetLocationItem.registration_status_code != "voided",
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def get_location_item(
        self,
        session: AsyncSession,
        row_id: UUID,
        user: AuthenticatedUser,
        permission: str,
        *,
        for_update: bool = False,
    ) -> AssetLocationItem | None:
        if for_update:
            await self.lock_stock_item_for_asset(session, AssetLocationItem, row_id)
        statement = select(AssetLocationItem).where(
            AssetLocationItem.id == row_id,
            *scoped_conditions(AssetLocationItem, user, permission),
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def list_location_items(
        self, session: AsyncSession, query: LocationAssetQuery, user: AuthenticatedUser
    ) -> tuple[int, list[Any]]:
        conditions = list(scoped_conditions(AssetLocationItem, user, "asset_register:list"))
        if query.org_id:
            conditions.append(AssetLocationItem.org_id == query.org_id)
        if query.location_id:
            conditions.append(self.location_filter(AssetLocationItem, query.location_id))
        if query.asset_type_code:
            conditions.append(AssetLocationItem.asset_type_code == query.asset_type_code)
        if query.status_code:
            conditions.append(AssetLocationItem.status_code == query.status_code)
        if query.registration_status_code:
            conditions.append(AssetLocationItem.registration_status_code == query.registration_status_code)
        if query.department_id:
            conditions.append(AssetLocationItem.department_id == query.department_id)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    MdItem.item_no.ilike(word),
                    MdItem.item_name.ilike(word),
                    MdItem.specification.ilike(word),
                    AssetLocation.location_name.ilike(word),
                )
            )
        base = (
            select(AssetLocationItem.id)
            .join(MdItem, MdItem.id == AssetLocationItem.item_id)
            .join(AssetLocation, AssetLocation.id == AssetLocationItem.location_id, isouter=True)
            .where(*conditions)
        )
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        department = aliased(SysDepartment)
        custodian = aliased(SysUser)
        statement = (
            select(AssetLocationItem, MdItem, AssetLocation, department.department_name, custodian.display_name)
            .join(MdItem, MdItem.id == AssetLocationItem.item_id)
            .join(AssetLocation, AssetLocation.id == AssetLocationItem.location_id, isouter=True)
            .join(department, department.id == AssetLocationItem.department_id, isouter=True)
            .join(custodian, custodian.id == AssetLocationItem.custodian_user_id, isouter=True)
            .where(*conditions)
            .order_by(AssetLocation.location_name, MdItem.item_name)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return int(total or 0), list((await session.exec(statement)).all())

    async def location_item_view(self, session: AsyncSession, row_id: UUID) -> Any | None:
        department = aliased(SysDepartment)
        custodian = aliased(SysUser)
        return (
            await session.exec(
                select(AssetLocationItem, MdItem, AssetLocation, department.department_name, custodian.display_name)
                .join(MdItem, MdItem.id == AssetLocationItem.item_id)
                .join(AssetLocation, AssetLocation.id == AssetLocationItem.location_id, isouter=True)
                .join(department, department.id == AssetLocationItem.department_id, isouter=True)
                .join(custodian, custodian.id == AssetLocationItem.custodian_user_id, isouter=True)
                .where(AssetLocationItem.id == row_id)
            )
        ).first()

    async def register_no_exists(
        self, session: AsyncSession, org_id: UUID, asset_no: str, *, exclude_id: UUID | None = None
    ) -> bool:
        conditions = [
            AssetRegister.org_id == org_id,
            AssetRegister.asset_no == asset_no,
            AssetRegister.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            conditions.append(AssetRegister.id != exclude_id)
        return (await session.exec(select(AssetRegister.id).where(*conditions))).first() is not None

    async def get_register(
        self,
        session: AsyncSession,
        register_id: UUID,
        user: AuthenticatedUser,
        permission: str,
        *,
        for_update: bool = False,
    ) -> AssetRegister | None:
        if for_update:
            await self.lock_stock_item_for_asset(session, AssetRegister, register_id)
        statement = select(AssetRegister).where(
            AssetRegister.id == register_id,
            *scoped_conditions(AssetRegister, user, permission),
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def reference_options(self, session, *, org_id, user, permission, keyword, page, page_size):
        """单件资产引用目录：仅必要字段，沿用调用业务的范围和软删除约束。"""
        statement = (
            select(AssetRegister.id, AssetRegister.asset_no, MdItem.item_name,
                   AssetRegister.asset_type_code, AssetLocation.location_name,
                   AssetRegister.custody_location_note)
            .join(MdItem, MdItem.id == AssetRegister.item_id)
            .outerjoin(AssetLocation, AssetLocation.id == AssetRegister.location_id)
            .where(
                *scoped_conditions(AssetRegister, user, permission),
                or_(AssetRegister.org_id == org_id,
                    sa.and_(AssetRegister.custodian_user_id == user.user_id, AssetRegister.location_id.is_(None))),
                AssetRegister.registration_status_code == "confirmed",
                AssetRegister.status_code.not_in(["pending_disposal", "disposed"]),
                MdItem.deleted_at.is_(None),
                AssetLocation.deleted_at.is_(None),
            )
        )
        if keyword.strip():
            word = f"%{keyword.strip()}%"
            statement = statement.where(or_(AssetRegister.asset_no.ilike(word), MdItem.item_name.ilike(word),
                                            AssetLocation.location_name.ilike(word)))
        total = (await session.exec(select(func.count()).select_from(statement.subquery()))).one()
        rows = (await session.exec(statement.order_by(AssetRegister.asset_no, AssetRegister.id)
                                  .offset((page - 1) * page_size).limit(page_size))).mappings().all()
        return int(total or 0), rows

    async def register_for_reference(
        self,
        session: AsyncSession,
        register_id: UUID,
        org_id: UUID | None,
        *,
        user: AuthenticatedUser | None = None,
        permission: str | None = None,
        for_update: bool = False,
    ) -> AssetRegister | None:
        if org_id is None and (user is None or permission is None):
            return None
        if for_update:
            await self.lock_stock_item_for_asset(session, AssetRegister, register_id)
        conditions = [
            AssetRegister.id == register_id,
            AssetRegister.deleted_at.is_(None),
        ]
        if org_id is not None:
            conditions.append(AssetRegister.org_id == org_id)
        if user is not None:
            conditions.extend(scoped_conditions(AssetRegister, user, permission))
        statement = select(AssetRegister).where(*conditions)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def register_by_no_for_reference(
        self,
        session: AsyncSession,
        asset_no: str,
        org_id: UUID,
        *,
        user: AuthenticatedUser,
        permission: str,
    ) -> AssetRegister | None:
        return (
            await session.exec(
                select(AssetRegister).where(
                    AssetRegister.asset_no == asset_no,
                    AssetRegister.org_id == org_id,
                    *scoped_conditions(AssetRegister, user, permission),
                )
            )
        ).first()

    async def list_registers(
        self, session: AsyncSession, query: AssetRegisterQuery, user: AuthenticatedUser
    ) -> tuple[int, list[Any]]:
        conditions = list(scoped_conditions(AssetRegister, user, "asset_register:list"))
        if query.org_id:
            conditions.append(AssetRegister.org_id == query.org_id)
        if query.location_id:
            conditions.append(self.location_filter(AssetRegister, query.location_id))
        if query.asset_type_code:
            conditions.append(AssetRegister.asset_type_code == query.asset_type_code)
        if query.status_code:
            conditions.append(AssetRegister.status_code == query.status_code)
        if query.registration_status_code:
            conditions.append(AssetRegister.registration_status_code == query.registration_status_code)
        if query.department_id:
            conditions.append(AssetRegister.department_id == query.department_id)
        if query.custodian_user_id:
            conditions.append(AssetRegister.custodian_user_id == query.custodian_user_id)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(
                or_(
                    AssetRegister.asset_no.ilike(word),
                    AssetRegister.serial_no.ilike(word),
                    MdItem.item_no.ilike(word),
                    MdItem.item_name.ilike(word),
                    MdItem.specification.ilike(word),
                    AssetLocation.location_name.ilike(word),
                )
            )
        base = (
            select(AssetRegister.id)
            .join(MdItem, MdItem.id == AssetRegister.item_id)
            .join(AssetLocation, AssetLocation.id == AssetRegister.location_id, isouter=True)
            .where(*conditions)
        )
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        department = aliased(SysDepartment)
        custodian = aliased(SysUser)
        statement = (
            select(AssetRegister, MdItem, AssetLocation, department.department_name, custodian.display_name)
            .join(MdItem, MdItem.id == AssetRegister.item_id)
            .join(AssetLocation, AssetLocation.id == AssetRegister.location_id, isouter=True)
            .join(department, department.id == AssetRegister.department_id, isouter=True)
            .join(custodian, custodian.id == AssetRegister.custodian_user_id, isouter=True)
            .where(*conditions)
            .order_by(AssetRegister.created_at.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return int(total or 0), list((await session.exec(statement)).all())

    async def register_view(self, session: AsyncSession, register_id: UUID) -> Any | None:
        department = aliased(SysDepartment)
        custodian = aliased(SysUser)
        return (
            await session.exec(
                select(AssetRegister, MdItem, AssetLocation, department.department_name, custodian.display_name)
                .join(MdItem, MdItem.id == AssetRegister.item_id)
                .join(AssetLocation, AssetLocation.id == AssetRegister.location_id, isouter=True)
                .join(department, department.id == AssetRegister.department_id, isouter=True)
                .join(custodian, custodian.id == AssetRegister.custodian_user_id, isouter=True)
                .where(AssetRegister.id == register_id)
            )
        ).first()

    async def events(
        self,
        session: AsyncSession,
        *,
        asset_register_id: UUID | None,
        location_item_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[AssetChangeEvent]]:
        target = (
            AssetChangeEvent.asset_register_id == asset_register_id
            if asset_register_id is not None
            else AssetChangeEvent.location_item_id == location_item_id
        )
        base = select(AssetChangeEvent).where(target)
        total = (await session.exec(select(func.count()).select_from(base.subquery()))).one()
        rows = (
            await session.exec(
                base.order_by(AssetChangeEvent.created_at.desc(), AssetChangeEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return int(total or 0), list(rows)

    async def summary(self, session: AsyncSession, user: AuthenticatedUser) -> dict[str, Any]:
        quantity_conditions = scoped_conditions(AssetLocationItem, user, "asset_register:list")
        register_conditions = scoped_conditions(AssetRegister, user, "asset_register:list")
        quantity = (
            await session.exec(select(func.coalesce(func.sum(AssetLocationItem.quantity), 0)).where(*quantity_conditions))
        ).one()
        register_count = (
            await session.exec(select(func.count()).select_from(AssetRegister).where(*register_conditions))
        ).one()
        location_count = (
            await session.exec(
                select(func.count()).select_from(AssetLocation).where(
                    *scoped_conditions(AssetLocation, user, "asset_register:list"), AssetLocation.is_active.is_(True)
                )
            )
        ).one()
        repair_count = (
            await session.exec(
                select(func.count()).select_from(AssetRegister).where(
                    *register_conditions, AssetRegister.status_code == "maintenance"
                )
            )
        ).one()
        pending_registration_count = (
            await session.exec(
                select(func.count()).select_from(
                    sa.union_all(
                        select(AssetLocationItem.id).where(
                            *quantity_conditions,
                            AssetLocationItem.registration_status_code == "pending_confirmation",
                        ),
                        select(AssetRegister.id).where(
                            *register_conditions,
                            AssetRegister.registration_status_code == "pending_confirmation",
                        ),
                    ).subquery()
                )
            )
        ).one()
        return {
            "location_asset_quantity": str(quantity or 0),
            "registered_asset_count": int(register_count or 0),
            "active_location_count": int(location_count or 0),
            "maintenance_asset_count": int(repair_count or 0),
            "pending_registration_count": int(pending_registration_count or 0),
        }

    async def assets_by_custodian(
        self, session: AsyncSession, org_id: UUID, custodian_user_id: UUID,
        *, include_unconfirmed: bool = False,
    ) -> tuple[list[AssetRegister], list[AssetLocationItem]]:
        registers = (
            await session.exec(
                select(AssetRegister).where(
                    AssetRegister.org_id == org_id,
                    AssetRegister.custodian_user_id == custodian_user_id,
                    AssetRegister.deleted_at.is_(None),
                    AssetRegister.registration_status_code != "voided",
                    *([] if include_unconfirmed else [AssetRegister.registration_status_code == "confirmed"]),
                    AssetRegister.status_code != "disposed",
                )
            )
        ).all()
        location_items = (
            await session.exec(
                select(AssetLocationItem).where(
                    AssetLocationItem.org_id == org_id,
                    AssetLocationItem.custodian_user_id == custodian_user_id,
                    AssetLocationItem.deleted_at.is_(None),
                    AssetLocationItem.registration_status_code != "voided",
                    *([] if include_unconfirmed else [AssetLocationItem.registration_status_code == "confirmed"]),
                    AssetLocationItem.quantity > 0,
                )
            )
        ).all()
        return list(registers), list(location_items)

    @staticmethod
    def add(session: AsyncSession, *rows: SQLModel) -> None:
        session.add_all(rows)


repository = AssetRepository()


async def _location_referenced(session, location_id):
    # 引用检查及兼容投影由数据所有者维护，保留历史关联。
    return (await session.exec(select(AssetLocation.id).where(AssetLocation.physical_location_id == location_id).limit(1))).first() is not None


async def _location_changed(session, master, user):
    # 引用检查及兼容投影由数据所有者维护，保留历史关联。
    rows = (await session.exec(select(AssetLocation).where(
        AssetLocation.physical_location_id == master.id, AssetLocation.org_id == master.org_id))).all()
    for row in rows:
        row.location_name, row.location_type_code = master.location_name, master.location_type_code
        row.version_no += 1
        row.updated_by = user.user_id
        session.add(row)


register_consumer("asset", table_name="asset_location", reference=_location_referenced, changed=_location_changed,
    permissions=("asset_location:manage", "asset_location:list", "asset_register:create", "asset_register:transfer", "asset_handover:create", "asset_handover:manage"))
