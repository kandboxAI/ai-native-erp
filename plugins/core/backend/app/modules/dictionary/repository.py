from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy import func, or_, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository
from app.framework.db.models import utc_now
from app.modules.dictionary_item.models import SysDictItem

from .builtin_dicts import BUILTIN_DICTS
from .models import SysDict
from .schemas import DictionaryEntryListQuery, DictionaryEntryRow, DictionaryItem

BUILTIN_DICT_CODES = frozenset(spec["dict_code"] for spec in BUILTIN_DICTS)
DICT_CODE_MAX = 64


async def ensure_builtin_definitions(session, definitions):
    """模块开通时幂等补缺；不覆盖学校改名、停用等已有配置。"""
    for code, name, values in definitions:
        dictionary = (await session.exec(select(SysDict).where(SysDict.dict_code == code, SysDict.deleted_at.is_(None)))).first()
        if dictionary is None:
            dictionary = SysDict(dict_code=code, dict_name=name)
            session.add(dictionary)
            await session.flush()
        existing = set((await session.exec(select(SysDictItem.item_code).where(SysDictItem.dict_id == dictionary.id, SysDictItem.deleted_at.is_(None)))).all())
        for sort_no, (value, label) in enumerate(values):
            if value not in existing:
                session.add(SysDictItem(dict_id=dictionary.id, item_code=value, item_name=label, sort_no=sort_no, is_builtin=True))
    await session.flush()


async def normalize_dictionary_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysDict | None,
) -> dict[str, Any]:
    data = dict(payload)
    if entity is not None:
        if "dict_code" in data and data["dict_code"] != entity.dict_code:
            raise AppException("字典编码创建后不可修改", status_code=status.HTTP_400_BAD_REQUEST)
        if entity.dict_code in BUILTIN_DICT_CODES and "is_tenant_extensible" in data and data["is_tenant_extensible"] != entity.is_tenant_extensible:
            raise AppException("内置字典不能修改“租户可否扩展”", status_code=status.HTTP_403_FORBIDDEN)
        return data
    code = str(data.get("dict_code") or "").strip()
    if not code:
        raise AppException("字典编码不能为空", status_code=status.HTTP_400_BAD_REQUEST)
    duplicate = (await session.exec(select(SysDict.id).where(SysDict.dict_code == code, SysDict.deleted_at.is_(None)))).first()
    if duplicate is not None:
        raise AppException("字典编码已存在", status_code=status.HTTP_409_CONFLICT)
    data["dict_code"] = code
    return data


class DictionaryRepository(SqlModelCrudRepository):
    def _parse_entity(self, entity):
        item = DictionaryItem.model_validate(entity)
        item.is_builtin = entity.dict_code in BUILTIN_DICT_CODES
        return item

    async def delete(self, session, item_id: str, current_user: AuthenticatedUser) -> bool:
        entity = await session.get(SysDict, self._normalize_id(item_id))
        if entity is None or entity.deleted_at is not None:
            return False
        if entity.dict_code in BUILTIN_DICT_CODES:
            raise AppException("内置字典不可删除，可以停用", status_code=status.HTTP_403_FORBIDDEN)
        builtin_items = await session.scalar(
            select(func.count()).select_from(SysDictItem).where(
                SysDictItem.dict_id == entity.id, SysDictItem.is_builtin.is_(True), SysDictItem.deleted_at.is_(None)
            )
        )
        if builtin_items:
            raise AppException("字典下有内置项，不可删除", status_code=status.HTTP_403_FORBIDDEN)
        await session.execute(
            update(SysDictItem)
            .where(SysDictItem.dict_id == entity.id, SysDictItem.deleted_at.is_(None))
            .values(deleted_at=utc_now(), deleted_by=current_user.user_id)
        )
        return await super().delete(session, item_id, current_user)


repository = DictionaryRepository(
    table_model=SysDict,
    item_model=DictionaryItem,
    writable_columns=["dict_code", "dict_name", "description", "is_tenant_extensible", "is_active"],
    searchable_columns=["dict_code", "dict_name", "description"],
    filterable_columns=["is_active", "is_tenant_extensible"],
    create_payload_normalizer=normalize_dictionary_payload,
    update_payload_normalizer=normalize_dictionary_payload,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="dictionary",
)


class DictionaryEntryRepository:
    async def reference(self, session, dict_code, item_code, *, lock=False):
        """租户公共选项最小投影；不读取备注，不拥有事务提交权。"""
        statement = select(SysDict.id, SysDictItem.id.label("item_id")).join(
            SysDictItem, SysDictItem.dict_id == SysDict.id).where(
                SysDict.dict_code == dict_code, SysDictItem.item_code == item_code,
                SysDict.deleted_at.is_(None), SysDictItem.deleted_at.is_(None),
                SysDict.is_active.is_(True), SysDictItem.is_active.is_(True))
        if lock:
            statement = statement.with_for_update()
        return (await session.exec(statement)).one_or_none()

    async def list_entries(self, session: AsyncSession, params: DictionaryEntryListQuery) -> dict[str, Any]:
        conditions: list[Any] = [SysDictItem.deleted_at.is_(None), SysDict.deleted_at.is_(None)]
        if params.dict_id:
            conditions.append(SysDictItem.dict_id == params.dict_id)
        if params.dict_code and params.dict_code.strip():
            conditions.append(SysDict.dict_code.ilike(f"%{params.dict_code.strip()}%"))
        if params.item_name and params.item_name.strip():
            conditions.append(SysDictItem.item_name.ilike(f"%{params.item_name.strip()}%"))
        if params.is_active is not None:
            conditions.append(SysDictItem.is_active.is_(params.is_active))
        if params.keyword and params.keyword.strip():
            kw = f"%{params.keyword.strip()}%"
            conditions.append(
                or_(
                    SysDict.dict_code.ilike(kw),
                    SysDict.dict_name.ilike(kw),
                    SysDictItem.item_code.ilike(kw),
                    SysDictItem.item_name.ilike(kw),
                    func.coalesce(SysDictItem.remark, "").ilike(kw),
                )
            )
        base = select(SysDictItem, SysDict).join(SysDict, SysDictItem.dict_id == SysDict.id).where(*conditions)
        total = (
            await session.exec(select(func.count()).select_from(SysDictItem).join(SysDict, SysDictItem.dict_id == SysDict.id).where(*conditions))
        ).one()
        rows = (
            await session.exec(
                base.order_by(SysDict.dict_code, SysDictItem.sort_no.nulls_last(), SysDictItem.item_code)
                .limit(params.page_size)
                .offset((params.page - 1) * params.page_size)
            )
        ).all()
        items = [
            DictionaryEntryRow(
                id=item.id,
                dict_id=dict_row.id,
                dict_code=dict_row.dict_code,
                dict_name=dict_row.dict_name,
                is_tenant_extensible=dict_row.is_tenant_extensible,
                item_code=item.item_code,
                item_name=item.item_name,
                sort_no=item.sort_no,
                is_builtin=item.is_builtin,
                is_active=item.is_active,
                remark=item.remark,
                updated_at=item.updated_at,
            ).model_dump(mode="json")
            for item, dict_row in rows
        ]
        return {"items": items, "total": int(total or 0), "page": params.page, "page_size": params.page_size}

    async def options(self, session: AsyncSession, dict_codes: list[str], *, include_inactive: bool = False) -> dict[str, list[dict[str, Any]]]:
        conditions = [SysDict.dict_code.in_(dict_codes), SysDict.deleted_at.is_(None), SysDictItem.deleted_at.is_(None)]
        if not include_inactive:
            conditions += [SysDict.is_active.is_(True), SysDictItem.is_active.is_(True)]
        rows = (
            await session.exec(
                select(SysDict.dict_code, SysDictItem.item_code, SysDictItem.item_name, SysDictItem.sort_no, SysDictItem.is_active)
                .join(SysDict, SysDictItem.dict_id == SysDict.id)
                .where(*conditions)
                .order_by(SysDict.dict_code, SysDictItem.sort_no.nulls_last(), SysDictItem.item_code)
            )
        ).all()
        result: dict[str, list[dict[str, Any]]] = {code: [] for code in dict_codes}
        for row in rows:
            result[row[0]].append({"item_code": row[1], "item_name": row[2], "sort_no": row[3], "is_active": row[4]})
        return result


entry_list_repository = DictionaryEntryRepository()
