"""当前事务内的公共选项名称读取，只返回请求的字典值/名称，不提交。"""
from sqlmodel import select
from .models import SysDict
from app.modules.dictionary_item.models import SysDictItem


async def labels_for_values(session, pairs):
    if not pairs:
        return {}
    rows = (await session.exec(select(SysDict.dict_code, SysDictItem.item_code, SysDictItem.item_name)
        .join(SysDictItem, SysDictItem.dict_id == SysDict.id).where(
            SysDict.dict_code.in_({pair[0] for pair in pairs}),
            SysDictItem.item_code.in_({pair[1] for pair in pairs}),
            SysDict.deleted_at.is_(None), SysDictItem.deleted_at.is_(None),
        ))).all()
    return {(row[0], row[1]): row[2] for row in rows if (row[0], row[1]) in pairs}
