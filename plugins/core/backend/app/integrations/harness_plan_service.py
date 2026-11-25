"""Validate catalog freshness before the scoped relational executor runs."""
from fastapi import HTTPException

from .harness_plan_repository import execute_erp_plan


async def run_plan(request, user):
    if not request.catalog_revision:
        raise HTTPException(400, "关联查询需要检索返回的 catalog_revision")
    from app.modules.harness_discovery.service import check_revision
    check_revision(request.catalog_revision, user)
    return await execute_erp_plan(request.plan, user)
