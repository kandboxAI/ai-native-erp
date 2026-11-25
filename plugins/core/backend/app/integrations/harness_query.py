"""Harness-only, read-only database query API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response

from .harness_query_repository import RESOURCES, QueryResource, canonical_resource_name, read_query, readable_fields, resource_authorized
from .harness_query_schemas import QueryRequest
from .harness_schema_catalog import resource_descriptions

router = APIRouter(prefix="/api/harness/query", tags=["harness-query"])


def _authorized(current_user: AuthenticatedUser, resource: QueryResource) -> bool:
    # Only permissions decide; the built-in administrator role is granted every permission.
    return resource_authorized(resource, current_user)


def _resource(request: QueryRequest, current_user: AuthenticatedUser) -> QueryResource:
    resource = RESOURCES.get(canonical_resource_name(request.resource) or "")
    if resource is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown query resource")
    if not _authorized(current_user, resource):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing resource list permission")
    return resource


@router.post("", include_in_schema=False)
async def query_erp_data(
    request: QueryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    x_harness_read_only: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return registered resources or a read scoped to the authenticated ERP user."""
    if request.operation == "catalog":
        if x_harness_read_only == "1":
            raise HTTPException(400, "请按问题检索资源并 describe，不支持向网页智能体返回全量表结构")
        resources = [
            {"name": name, "fields": readable_fields(spec), **resource_descriptions(spec)}
            for name, spec in RESOURCES.items() if _authorized(current_user, spec)
        ]
        return success_response({"policy_version": 1, "resources": resources})

    if request.operation == "plan":
        from .harness_plan_service import run_plan
        return success_response({"policy_version": 1, **await run_plan(request, current_user)})
    if request.plan is not None:
        raise HTTPException(400, "plan 只能用于关联查询操作")
    request = request.model_copy(update={"resource": canonical_resource_name(request.resource)})
    spec = _resource(request, current_user)
    if request.catalog_revision:
        from app.modules.harness_discovery.service import check_revision
        check_revision(request.catalog_revision, current_user)
    return success_response({"policy_version": 1, **await read_query(spec, request, current_user)})
