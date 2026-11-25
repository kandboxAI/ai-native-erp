"""受控的列表展示排序，保留仓储既有的范围条件、联查和分页边界。"""
from contextvars import ContextVar
from dataclasses import dataclass, field
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.sql import Select

from app.core.exceptions import AppException


# 展示排序只能使用这些普通业务字段；不接受 SQL、关联路径或私密存储字段。
DISPLAY_FIELDS = frozenset(
    """
    code created_at department_name dict_code dict_name display_name duration_ms email end_date
    event_key event_name failure_count full_name http_status id is_active item_code item_label
    menu_key menu_name module_code name notification_no occurred_at org_name permission_count
    permission_key published_at request_method request_path reviewed_at role_count role_name
    role_no scene_key scene_name sort_no start_date status_code subject submitted_at
    success_count summary title total_count updated_at user_count username valid_from valid_to
    """.split()
)


@dataclass(frozen=True)
class ListSortPolicy:
    method: str
    path: str
    fields: frozenset[str] = DISPLAY_FIELDS
    aliases: tuple[tuple[str, str], ...] = ()


@dataclass
class ListSortContext:
    policy: ListSortPolicy
    sort_by: str | None = None
    sort_order: str = "asc"
    available_fields: set[str] = field(default_factory=set)
    applied: bool = False


list_sort_context: ContextVar[ListSortContext | None] = ContextVar("list_sort_context", default=None)


def resolve_sort_policy(method: str, path: str, policies) -> ListSortPolicy | None:
    for policy in policies:
        pattern = re.sub(r"\{[^}]+\}", r"[^/]+", policy.path)
        if method.upper() == policy.method and re.fullmatch(pattern, path):
            return policy
    return None


def apply_list_sort(statement):
    """只处理仓储的分页 SELECT；COUNT、下拉、写入和未声明端点不参与。"""
    context = list_sort_context.get()
    if context is None or not isinstance(statement, Select):
        return statement
    if statement._limit_clause is None or statement._offset_clause is None:
        return statement
    selected = {}
    duplicates = set()
    for column in statement.selected_columns:
        key = column.key
        if key in selected:
            duplicates.add(key)
        selected[key] = column
    aliases = dict(context.policy.aliases)
    available = {
        key: selected[aliases.get(key, key)]
        for key in context.policy.fields
        if aliases.get(key, key) in selected and aliases.get(key, key) not in duplicates
    }
    context.available_fields.update(available)
    if not context.sort_by or context.sort_by not in available:
        return statement
    column = available[context.sort_by]
    order = column.desc() if context.sort_order == "desc" else column.asc()
    # 原有排序作为同值次序保留，主键补齐稳定分页；WHERE/租户/范围均原样保留。
    tie_breakers = list(statement._order_by_clauses)
    if "id" in selected and "id" not in duplicates:
        tie_breakers.append(selected["id"].asc())
    context.applied = True
    return statement.order_by(None).order_by(order.nulls_last(), *tie_breakers)


def validate_sort(sort_by: str | None, sort_order: str, policy: ListSortPolicy) -> None:
    if sort_order not in {"asc", "desc"}:
        raise AppException("排序方向必须是 asc 或 desc", status_code=422)
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", sort_by or "").lower()
    if sort_by and sort_by not in policy.fields and normalized not in policy.fields:
        raise AppException("该字段不允许用于列表排序", status_code=422)


def sort_list_records(records, *, model=None, getters=None):
    """既有全量取数后分页的列表，在原范围过滤完成后、切片前排序。"""
    context = list_sort_context.get()
    if context is None:
        return records
    getters = getters or {}
    sample = records[0] if records else None
    names = set(getattr(model or type(sample), "model_fields", {}))
    if isinstance(sample, dict):
        names.update(sample)
    names.update(getters)
    available = {name for name in names if name in context.policy.fields or re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() in context.policy.fields}
    context.available_fields.update(available)
    if not records:
        # 空结果同样完成排序，避免更改筛选后将合法排序误报为不支持。
        context.applied = bool(context.sort_by)
        return records
    if not context.sort_by or context.sort_by not in available:
        return records
    def value(record):
        if context.sort_by in getters:
            return getters[context.sort_by](record)
        return record.get(context.sort_by) if isinstance(record, dict) else getattr(record, context.sort_by, None)
    def comparable(record):
        item = value(record)
        if isinstance(item, (datetime, date)):
            return (1, item.isoformat())
        if isinstance(item, bool):
            return (0, Decimal(int(item)))
        if isinstance(item, (int, float, Decimal)):
            return (0, Decimal(str(item)))
        if isinstance(item, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", item):
            try:
                return (0, Decimal(item))
            except InvalidOperation:
                pass
        return (2, str(item).casefold())
    populated = [record for record in records if value(record) not in (None, "")]
    empty = [record for record in records if value(record) in (None, "")]
    context.applied = True
    return sorted(populated, key=comparable, reverse=context.sort_order == "desc") + empty
