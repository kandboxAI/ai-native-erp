"""位置 SQL、组织互斥锁和持久化，依赖当前租户事务 search_path。"""
from sqlalchemy import text
from sqlmodel import select
from app.auth.scope_filters import scoped_conditions
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.organization.models import SysOrg
from .models import MdLocation


class LocationRepository:
    def name_matches(self, location_id_column, org_id_column, pattern):
        return select(MdLocation.id).where(
            MdLocation.id == location_id_column, MdLocation.org_id == org_id_column,
            MdLocation.deleted_at.is_(None), MdLocation.location_name.ilike(pattern)).exists()

    async def lock_org(self, session, org_id):
        # 同组织变更串行化，协调位置维护和业务引用。
        await session.execute(text("select pg_advisory_xact_lock(hashtextextended(current_schema() || :key, 0))"), {"key": f":md_location:{org_id}"})

    async def table_exists(self, session, table_name):
        return bool(await session.scalar(text("select to_regclass(:name) is not null"), {"name": table_name}))

    async def get(self, session, location_id, *, user=None, permission=None, for_update=False):
        conditions = [MdLocation.id == location_id, MdLocation.deleted_at.is_(None)]
        if user is not None:
            conditions.extend(scoped_conditions(MdLocation, user, permission))
        statement = select(MdLocation).where(*conditions)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.exec(statement)).first()

    async def rows(self, session, user, permission, org_id=None):
        statement = select(MdLocation).where(*scoped_conditions(MdLocation, user, permission))
        if org_id:
            statement = statement.where(MdLocation.org_id == org_id)
        return list((await session.exec(statement.order_by(MdLocation.sort_no, MdLocation.location_no).limit(10001))).all())

    async def number_exists(self, session, org_id, number, exclude_id=None):
        statement = select(MdLocation.id).where(MdLocation.org_id == org_id, MdLocation.location_no == number, MdLocation.deleted_at.is_(None))
        if exclude_id:
            statement = statement.where(MdLocation.id != exclude_id)
        return (await session.exec(statement)).first() is not None

    async def organization_exists(self, session, org_id):
        return (await session.exec(select(SysOrg.id).where(SysOrg.id == org_id, SysOrg.deleted_at.is_(None), SysOrg.is_active.is_(True)))).first() is not None

    async def organizations(self, session, user, permission):
        rows = (await session.exec(select(SysOrg.id, SysOrg.org_name).where(*scoped_conditions(SysOrg, user, permission), SysOrg.is_active.is_(True)).order_by(SysOrg.org_name))).all()
        return [{"id": str(row[0]), "org_name": row[1]} for row in rows]

    async def dictionary_items(self, session, dict_code):
        rows = (await session.exec(select(SysDictItem.item_code, SysDictItem.item_name).join(SysDict, SysDict.id == SysDictItem.dict_id).where(SysDict.dict_code == dict_code, SysDict.deleted_at.is_(None), SysDict.is_active.is_(True), SysDictItem.deleted_at.is_(None), SysDictItem.is_active.is_(True)).order_by(SysDictItem.sort_no, SysDictItem.item_code))).all()
        return [{"value": row[0], "label": row[1]} for row in rows]

    def add(self, session, row):
        session.add(row)


repository = LocationRepository()
