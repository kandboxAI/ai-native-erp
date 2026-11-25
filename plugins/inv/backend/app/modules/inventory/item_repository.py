"""跨业务选料及按编号建档的数据访问，不返回价格、库存或供应商。"""
from sqlalchemy import or_, select, func

from .models import MdItem


async def active_item_options(session, keyword: str, limit: int):
    statement = select(MdItem.id, MdItem.item_no, MdItem.item_name, MdItem.unit_code, MdItem.specification).where(
        MdItem.deleted_at.is_(None), MdItem.is_active.is_(True),
    )
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        statement = statement.where(or_(MdItem.item_no.ilike(pattern), MdItem.item_name.ilike(pattern)))
    return (await session.execute(statement.order_by(MdItem.item_no, MdItem.id).limit(limit))).mappings().all()


async def active_items_by_numbers(session, numbers):
    if not numbers:
        return []
    statement = select(MdItem.id, MdItem.item_no, MdItem.item_name, MdItem.unit_code, MdItem.specification).where(
        MdItem.deleted_at.is_(None), MdItem.is_active.is_(True),
        func.lower(func.trim(MdItem.item_no)).in_(numbers))
    return (await session.execute(statement.order_by(MdItem.item_no, MdItem.id))).mappings().all()


async def lock_item_number(session, item_no):
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"inv.item:{item_no.lower()}", 0))))


async def items_by_number(session, item_no):
    return (await session.execute(select(MdItem).where(MdItem.deleted_at.is_(None),
        func.lower(MdItem.item_no) == item_no.lower()).with_for_update())).scalars().all()
