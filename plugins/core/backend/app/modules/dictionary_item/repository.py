from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository
from app.modules.dictionary.models import SysDict

from .models import SysDictItem
from .schemas import DictionaryItemItem

WRITABLE_COLUMNS = ["dict_id", "item_code", "item_name", "sort_no", "is_active", "remark"]


async def normalize_dictionary_item_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysDictItem | None,
) -> dict[str, Any]:
    data = dict(payload)
    if entity is not None:
        if "dict_id" in data and data["dict_id"] != entity.dict_id:
            raise AppException("字典项不能移到其他字典", status_code=status.HTTP_400_BAD_REQUEST)
        if entity.is_builtin and "item_code" in data and data["item_code"] != entity.item_code:
            raise AppException("内置字典项的编码不可修改", status_code=status.HTTP_403_FORBIDDEN)
    dict_id = data.get("dict_id", getattr(entity, "dict_id", None))
    if dict_id is None:
        raise AppException("请选择字典", status_code=status.HTTP_400_BAD_REQUEST)
    dict_row = await session.get(SysDict, dict_id)
    if dict_row is None or dict_row.deleted_at is not None:
        raise AppException("字典不存在", status_code=status.HTTP_400_BAD_REQUEST)
    if entity is None and not dict_row.is_tenant_extensible:
        raise AppException("该字典由平台统一维护，不允许新增字典项", status_code=status.HTTP_403_FORBIDDEN)
    if "item_code" in data:
        item_code = str(data["item_code"] or "").strip()
        if not item_code:
            raise AppException("字典项编码不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        statement = select(SysDictItem.id).where(
            SysDictItem.dict_id == dict_id, SysDictItem.item_code == item_code, SysDictItem.deleted_at.is_(None)
        )
        if entity is not None:
            statement = statement.where(SysDictItem.id != entity.id)
        if (await session.exec(statement)).first() is not None:
            raise AppException("该字典下已存在相同编码的字典项", status_code=status.HTTP_409_CONFLICT)
        data["item_code"] = item_code
    return data


class DictionaryItemRepository(SqlModelCrudRepository):
    async def delete(self, session, item_id: str, current_user: AuthenticatedUser) -> bool:
        entity = await session.get(SysDictItem, self._normalize_id(item_id))
        if entity is None or entity.deleted_at is not None:
            return False
        if entity.is_builtin:
            raise AppException("内置字典项不可删除，可以停用", status_code=status.HTTP_403_FORBIDDEN)
        return await super().delete(session, item_id, current_user)


repository = DictionaryItemRepository(
    table_model=SysDictItem,
    item_model=DictionaryItemItem,
    writable_columns=WRITABLE_COLUMNS,
    searchable_columns=["item_code", "item_name", "remark"],
    filterable_columns=["dict_id", "is_active", "is_builtin"],
    create_payload_normalizer=normalize_dictionary_item_payload,
    update_payload_normalizer=normalize_dictionary_item_payload,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="dictionary_item",
)
