"""Pydantic 与业务时间字段配合使用。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, field_serializer, field_validator

from app.framework.datetime_local import format_display_datetime, parse_business_datetime_input


def before_naive_local_datetime(value: Any) -> Any:
    """用于 ``field_validator(..., mode='before')``：业务时间入参 → 带时区的上海时间。"""
    if value is None or value == "":
        return None
    parsed = parse_business_datetime_input(value)
    return parsed if parsed is not None else value


def serialize_display_datetime(value: datetime | str | None) -> str | None:
    """API JSON 出参：``YYYY-MM-DD HH:mm:ss``。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return format_display_datetime(value)


class DisplayDatetimeJsonMixin(BaseModel):
    """列表/详情 Schema：JSON 出参格式化墙钟时间。"""

    __display_datetime_fields__: ClassVar[tuple[str, ...]] = ("created_at", "updated_at")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is DisplayDatetimeJsonMixin:
            return
        fields = tuple(getattr(cls, "__display_datetime_fields__", ()))

        @field_serializer(*fields, when_used="json")
        def _serialize_display_datetimes(self, value: datetime | str | None) -> str | None:
            return serialize_display_datetime(value)

        cls._serialize_display_datetimes = _serialize_display_datetimes  # type: ignore[attr-defined]


class CoerceDatetimeQueryMixin(BaseModel):
    """分页查询 Schema：``*_start`` / ``*_end`` 等 datetime 查询入参规范化。"""

    __coerce_datetime_fields__: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is CoerceDatetimeQueryMixin:
            return
        fields = tuple(getattr(cls, "__coerce_datetime_fields__", ()))
        if not fields:
            return

        @field_validator(*fields, mode="before")
        @classmethod
        def _coerce_datetime_query(cls, value: object) -> object:
            return before_naive_local_datetime(value)

        cls._coerce_datetime_query = _coerce_datetime_query  # type: ignore[attr-defined]
