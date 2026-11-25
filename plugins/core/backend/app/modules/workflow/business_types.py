"""审批业务类型：字典 wf_business_type。"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import AppException
from app.modules.dictionary.models import SysDict
from app.modules.dictionary_item.models import SysDictItem

WORKFLOW_BUSINESS_TYPE_DICT_CODE = "wf_business_type"


async def list_workflow_business_types(session: AsyncSession) -> list[dict[str, str]]:
    stmt = (
        select(SysDictItem.item_code, SysDictItem.item_name)
        .join(SysDict, SysDictItem.dict_id == SysDict.id)
        .where(
            SysDict.dict_code == WORKFLOW_BUSINESS_TYPE_DICT_CODE,
            SysDict.is_active.is_(True),
            SysDict.deleted_at.is_(None),
            SysDictItem.is_active.is_(True),
            SysDictItem.deleted_at.is_(None),
        )
        .order_by(SysDictItem.sort_no.asc(), SysDictItem.item_code.asc())
    )
    rows = (await session.exec(stmt)).all()
    return [{"value": code, "label": name} for code, name in rows]


async def assert_valid_workflow_business_type(session: AsyncSession, business_type_code: str | None) -> None:
    code = (business_type_code or "").strip()
    if not code:
        raise AppException("请选择业务类型", status_code=400)
    allowed = {item["value"] for item in await list_workflow_business_types(session)}
    if code not in allowed:
        raise AppException(
            f"无效的业务类型「{code}」，请在系统字典「{WORKFLOW_BUSINESS_TYPE_DICT_CODE}」中配置",
            status_code=400,
        )


def label_for_business_type(business_type_code: str, options: list[dict[str, str]]) -> str:
    for item in options:
        if item["value"] == business_type_code:
            return item["label"]
    return business_type_code
