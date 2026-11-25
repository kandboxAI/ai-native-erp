"""系统管理各模块 Repository 共用的小工具。"""

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.framework.db.models import utc_now

__all__ = ["dedupe", "normalize_uuid", "row_to_dict", "scalar_count", "utc_now"]


def normalize_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise AppException("无效的 ID", status_code=status.HTTP_400_BAD_REQUEST) from exc


def dedupe(values) -> list:
    """去重并保持顺序（忽略 None）。"""
    return list(dict.fromkeys(item for item in values if item is not None))


async def scalar_count(session: AsyncSession, statement: Select) -> int:
    result = await session.execute(statement.with_only_columns(func.count()).order_by(None))
    return int(result.scalar_one() or 0)


def row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)
