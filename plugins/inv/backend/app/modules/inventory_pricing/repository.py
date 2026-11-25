"""报价按调用方权限读取共享物料/供应商的编号与名称，不读取敏感联系人。"""
from sqlalchemy import select, func, or_
from app.auth.scope_filters import scoped_conditions
from app.modules.masterdata.models import MdParty
from app.modules.supplier.models import MdSupplier
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem
from app.modules.inventory.models import MdItem
from .models import InvSupplierPrice


class SupplierPriceRepository:
    def add(self, session, row): session.add(row)

    async def options(self, session, kind, keyword):
        word = f"%{keyword.strip()}%"
        if kind == "suppliers":
            statement = select(MdSupplier.id, MdSupplier.supplier_no, MdParty.display_name).join(MdParty, MdParty.id == MdSupplier.party_id).where(
                MdSupplier.deleted_at.is_(None), MdSupplier.is_active.is_(True), MdParty.deleted_at.is_(None), or_(MdSupplier.supplier_no.ilike(word), MdParty.display_name.ilike(word))).order_by(MdSupplier.supplier_no)
        else:
            statement = select(MdItem.id, MdItem.item_no, MdItem.item_name).where(MdItem.deleted_at.is_(None), MdItem.is_active.is_(True),
                or_(MdItem.item_no.ilike(word), MdItem.item_name.ilike(word))).order_by(MdItem.item_no)
        return [dict(id=identifier, label=f"{number} · {name}") for identifier, number, name in (await session.execute(statement.limit(50))).all()]

    async def lock(self, session, org_id):
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"inv.supplier_price:{org_id}", 0))))

    async def get(self, session, identifier, user):
        return (await session.execute(select(InvSupplierPrice).where(InvSupplierPrice.id == identifier,
            *scoped_conditions(InvSupplierPrice, user, "inventory_supplier_price:manage")))).scalars().first()

    async def references(self, session, supplier_id, item_id, currency):
        supplier = (await session.execute(select(MdSupplier.id).join(MdParty, MdParty.id == MdSupplier.party_id).where(MdSupplier.id == supplier_id,
            MdSupplier.deleted_at.is_(None), MdSupplier.is_active.is_(True), MdParty.deleted_at.is_(None)))).first()
        item = (await session.execute(select(MdItem).where(MdItem.id == item_id, MdItem.deleted_at.is_(None), MdItem.is_active.is_(True)))).scalars().first()
        code = (await session.execute(select(SysDictItem.id).join(SysDict, SysDict.id == SysDictItem.dict_id).where(SysDict.dict_code == "md_currency",
            SysDict.deleted_at.is_(None), SysDictItem.item_code == currency, SysDictItem.deleted_at.is_(None), SysDictItem.is_active.is_(True)))).first()
        return supplier is not None, item, code is not None

    async def overlaps(self, session, body, exclude=None):
        conditions = [InvSupplierPrice.org_id == body.org_id, InvSupplierPrice.supplier_id == body.supplier_id,
            InvSupplierPrice.item_id == body.item_id, InvSupplierPrice.currency_code == body.currency_code,
            InvSupplierPrice.is_active.is_(True), InvSupplierPrice.deleted_at.is_(None),
            or_(InvSupplierPrice.valid_to.is_(None), InvSupplierPrice.valid_to > body.valid_from)]
        if body.valid_to: conditions.append(InvSupplierPrice.valid_from < body.valid_to)
        if exclude: conditions.append(InvSupplierPrice.id != exclude)
        return (await session.execute(select(InvSupplierPrice.id).where(*conditions).limit(1))).first() is not None

    async def page(self, session, query, user):
        conditions = scoped_conditions(InvSupplierPrice, user, "inventory_supplier_price:list")
        if query.org_id: conditions.append(InvSupplierPrice.org_id == query.org_id)
        if query.is_active is not None: conditions.append(InvSupplierPrice.is_active == query.is_active)
        if query.keyword:
            word = f"%{query.keyword.strip()}%"
            conditions.append(or_(MdSupplier.supplier_no.ilike(word), MdParty.display_name.ilike(word), MdItem.item_no.ilike(word), MdItem.item_name.ilike(word)))
        statement = select(InvSupplierPrice, MdSupplier.supplier_no, MdParty.display_name, MdItem.item_no, MdItem.item_name).join(
            MdSupplier, MdSupplier.id == InvSupplierPrice.supplier_id).join(MdParty, MdParty.id == MdSupplier.party_id).join(MdItem, MdItem.id == InvSupplierPrice.item_id).where(*conditions)
        total = (await session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
        rows = (await session.execute(statement.order_by(InvSupplierPrice.updated_at.desc(), InvSupplierPrice.id)
            .offset((query.page-1)*query.page_size).limit(query.page_size))).all()
        return [dict(**row.model_dump(exclude={"deleted_at", "deleted_by", "flex_form", "unit_price"}), unit_price=str(row.unit_price), supplier_no=supplier_no, supplier_name=supplier_name,
            item_no=item_no, item_name=item_name) for row, supplier_no, supplier_name, item_no, item_name in rows], total


price_repository = SupplierPriceRepository()
