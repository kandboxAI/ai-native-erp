"""行业档案维护物料本体的最小持久化契约；行业扩展由调用方拥有。"""
from sqlmodel import select
from app.core.exceptions import AppException
from .models import MdItem, MdItemCategory


async def save_item(session, values, item_id, user_id, *, user=None):
    statement = select(MdItem.id).where(MdItem.item_no == values["item_no"], MdItem.deleted_at.is_(None))
    if item_id is not None:
        statement = statement.where(MdItem.id != item_id)
    duplicate = (await session.exec(statement)).first()
    if duplicate:
        raise AppException("物品编码已存在", status_code=409)
    category = (await session.exec(select(MdItemCategory).where(
        MdItemCategory.category_name == values.pop("category_name"), MdItemCategory.deleted_at.is_(None)))).first()
    if category is None:
        raise AppException("物料分类不存在，请先在物料分类中维护", status_code=422)
    item = (await session.exec(select(MdItem).where(MdItem.id == item_id, MdItem.deleted_at.is_(None))
        .with_for_update())).first() if item_id else MdItem(created_by=user_id)
    if item is None:
        raise AppException("物料不存在", status_code=404)
    if item_id:
        if user is None:
            raise AppException("维护物料基础信息必须校验当前账号", 403)
        from .products.warehouse_repository import repository as warehouse_links
        await warehouse_links.require_basic_edit(session, item, {**values, "category_id": category.id}, user)
    for key, value in values.items():
        setattr(item, key, value)
    item.category_id = category.id
    item.updated_by = user_id
    session.add(item)
    await session.flush()
    return item


async def toggle_item(session, item_id, is_active, user_id, *, user=None):
    item = (await session.exec(select(MdItem).where(MdItem.id == item_id, MdItem.deleted_at.is_(None))
        .with_for_update())).first()
    if item is None:
        raise AppException("物料不存在", status_code=404)
    if user is None:
        raise AppException("维护物料状态必须校验当前账号", 403)
    from .products.warehouse_repository import repository as warehouse_links
    await warehouse_links.require_basic_edit(session, item, {"is_active": is_active}, user)
    item.is_active = is_active
    item.updated_by = user_id
    session.add(item)
    await session.flush()
    return item
