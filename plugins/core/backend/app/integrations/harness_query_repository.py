"""Registered, scope-aware SQL reads for the Harness query endpoint.

Queries run in the current tenant schema: the request passed ``get_current_user``, which set the
tenant schema, and the SQLModel session switches ``search_path`` at the start of every transaction.
Statements never carry a schema prefix and there is no ``tenant_id``; isolation comes from the schema,
data scope from ``app.auth.scope_filters`` (``org_id``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter
from sqlalchemy import Float, Integer, Numeric, func, select
from resource_query.compiler import is_text_type
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import SQLModel

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import alive_condition, table_scope_condition
from app.framework.db.registry import import_all_models
from app.framework.db.session import get_session_context
from app.framework.db.tenant import require_tenant_schema
from app.framework.ai_catalog import registered_ai_resources

from .harness_query_policy import (
    TENANT_WIDE_RESOURCES,
)
from .harness_query_schemas import QueryAggregate, QueryFilter, QueryRequest
from .harness_value_policy import model_scalar


@dataclass(frozen=True)
class QueryResource:
    name: str
    table_model: type[SQLModel]
    permission: str
    ai_fields: tuple[str, ...]
    api_entity: str | None = None
    plugin_key: str | None = None
    domain: str = "system"

    @property
    def table_name(self) -> str:
        return self.table_model.__tablename__


@lru_cache(maxsize=1)
def _table_models() -> dict[str, type[SQLModel]]:
    import_all_models()
    result: dict[str, type[SQLModel]] = {}
    for mapper in SQLModel._sa_registry.mappers:
        model = mapper.class_
        if model.__module__.endswith("_legacy"):
            continue
        result[getattr(model, "__tablename__", "")] = model
    return result


def _validate(name: str, model: type[SQLModel]) -> None:
    table = model.__table__
    if name.startswith("auth_") or table.schema is not None:
        raise RuntimeError(f"Harness policy must not expose {name}")
    if name not in TENANT_WIDE_RESOURCES and name != "sys_org" and "org_id" not in table.columns:
        raise RuntimeError(f"Harness resource {name} cannot be scoped by org_id")


def canonical_resource_name(name: str | None) -> str | None:
    """Resources use tenant-independent table names from the current catalog."""
    return name


def _build_resources() -> dict[str, QueryResource]:
    models = _table_models()
    declarations = registered_ai_resources()
    unknown = sorted(set(declarations) - set(models))
    if unknown:
        raise RuntimeError(f"Harness policy refers to unknown tables: {unknown}")
    result: dict[str, QueryResource] = {}
    for name, item in declarations.items():
        _validate(name, models[name])
        # 资源仍须登记权限与范围，字段直接来自模型，不再另设隐私白名单。
        fields = tuple(column.name for column in models[name].__table__.columns
                       if column.name in models[name].model_fields)
        result[name] = QueryResource(name, models[name], item.definition.permission, fields,
                                     item.definition.api_entity, item.plugin_key, item.domain)
    return result


RESOURCES = _build_resources()


def resource_authorized(spec: QueryResource, user: AuthenticatedUser) -> bool:
    return spec.permission in user.permissions and (spec.plugin_key is None or spec.plugin_key in user.enabled_plugin_keys)


def readable_fields(spec: QueryResource) -> tuple[str, ...]:
    return spec.ai_fields


def _column(spec: QueryResource, field: str):
    return getattr(spec.table_model, field)


def _column_value(spec: QueryResource, field: str, value: Any) -> Any:
    try:
        annotation = spec.table_model.model_fields[field].annotation
        return TypeAdapter(annotation).validate_python(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid value for {field}") from exc


def filter_condition(spec: QueryResource, item: QueryFilter, allowed: set[str]) -> ColumnElement[bool]:
    if item.field not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Field is not queryable: {item.field}")
    column = _column(spec, item.field)
    if item.op == "is_null":
        if not isinstance(item.value, bool):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="is_null requires a boolean value")
        return column.is_(None) if item.value else column.is_not(None)
    if item.op == "in":
        if not isinstance(item.value, list) or not 1 <= len(item.value) <= 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="in requires 1 to 100 values")
        return column.in_([_column_value(spec, item.field, value) for value in item.value])
    if item.op in {"like", "ilike"}:
        if not is_text_type(spec.table_model.__table__.columns[item.field].type):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="like requires a text field")
        if not isinstance(item.value, str) or len(item.value) > 128:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="like requires a short string")
        return column.like(item.value) if item.op == "like" else column.ilike(item.value)
    value = _column_value(spec, item.field, item.value) if item.value is not None else None
    if item.op == "eq":
        return column.is_(None) if value is None else column == value
    if item.op == "neq":
        return column.is_not(None) if value is None else column != value
    if value is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{item.op} requires a value")
    if item.op == "gt":
        return column > value
    if item.op == "gte":
        return column >= value
    if item.op == "lt":
        return column < value
    return column <= value


def scope_condition(spec: QueryResource, current_user: AuthenticatedUser) -> Any:
    """Server-owned data scope (org_id / department / self / related) for the resource permission."""
    return table_scope_condition(spec.table_model, current_user, spec.permission)


def conditions(spec: QueryResource, request: QueryRequest, current_user: AuthenticatedUser, allowed: set[str]) -> list[Any]:
    result: list[Any] = []
    scope = scope_condition(spec, current_user)
    if scope is not None:
        result.append(scope)
    alive = alive_condition(spec.table_model)
    if alive is not None:
        result.append(alive)
    definition = registered_ai_resources().get(spec.name)
    if definition is not None and definition.definition.additional_filters is not None:
        result.extend(definition.definition.additional_filters(spec.table_model, current_user))
    result.extend(filter_condition(spec, item, allowed) for item in request.filters)
    return result


def aggregate_column(spec: QueryResource, aggregate: QueryAggregate, allowed: set[str]) -> Any:
    if aggregate.function == "count" and aggregate.field is None:
        return func.count()
    if aggregate.field is None or aggregate.field not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown aggregate field")
    column = spec.table_model.__table__.columns[aggregate.field]
    if aggregate.function in {"sum", "avg"} and not isinstance(column.type, (Integer, Float, Numeric)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aggregate requires a numeric field")
    return getattr(func, aggregate.function)(_column(spec, aggregate.field))


async def read_query(spec: QueryResource, request: QueryRequest, current_user: AuthenticatedUser) -> dict[str, Any]:
    from app.integrations.erp_discovery.catalog import validate_query
    validate_query(request, current_user)
    allowed = set(readable_fields(spec))
    fields = request.fields or list(readable_fields(spec))
    if len(fields) != len(set(fields)) or any(field not in allowed for field in fields):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or duplicate selected field")
    if any(item.field not in allowed for item in request.order):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown ordering field")
    where = conditions(spec, request, current_user, allowed)
    table = spec.table_model
    # Never run against the bare public search_path: the tenant schema must have been set by authentication.
    if require_tenant_schema() != current_user.tenant_schema:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context mismatch")

    async with get_session_context() as session:
        if request.aggregate is not None:
            expression = aggregate_column(spec, request.aggregate, allowed)
            if request.group_by:
                columns = [getattr(table, field) for field in request.group_by]
                statement = select(*columns, expression.label("value")).select_from(table).where(*where)
                statement = statement.group_by(*columns).order_by(*columns).limit(request.limit + 1).offset(request.offset)
                groups = [dict(row) for row in (await session.execute(statement)).mappings().all()]
                more = len(groups) > request.limit
                return {"resource": request.resource, "aggregate": request.aggregate.model_dump(),
                        "group_by": request.group_by, "groups": [
                            {key: model_scalar(value) for key, value in jsonable_encoder(row).items()}
                            for row in groups[:request.limit]], "limit": request.limit, "offset": request.offset,
                        "truncated": more, "next_offset": request.offset + request.limit if more else None}
            statement = select(expression).select_from(table).where(*where)
            value = (await session.execute(statement)).scalar_one()
            return {"resource": request.resource, "aggregate": request.aggregate.model_dump(),
                    "value": model_scalar(jsonable_encoder(value))}

        statement = select(*(_column(spec, field) for field in fields)).where(*where)
        for item in request.order:
            column = _column(spec, item.field)
            statement = statement.order_by(column.desc() if item.direction == "desc" else column.asc())
        if not request.order:
            statement = statement.order_by(table.id.asc())
        statement = statement.limit(request.limit).offset(request.offset)
        rows = [{field: model_scalar(value) for field, value in jsonable_encoder(dict(row)).items()}
                for row in (await session.execute(statement)).mappings().all()]
        result: dict[str, Any] = {"resource": request.resource, "rows": rows, "limit": request.limit, "offset": request.offset}
        if request.include_count:
            count_statement = select(func.count()).select_from(table).where(*where)
            result["total"] = (await session.execute(count_statement)).scalar_one()
    return result
