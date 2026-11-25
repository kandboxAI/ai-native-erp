"""列表排序请求上下文；目录由各模块声明，底座不包含行业路由。"""
from functools import lru_cache

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import AppException
from app.framework.catalog import iter_module_attr
from app.framework.db.list_sorting import (
    ListSortContext, list_sort_context, resolve_sort_policy, validate_sort,
)


@lru_cache(maxsize=1)
def collect_list_sort_policies():
    return tuple(policy for module in iter_module_attr("list_sorting")
                 for policy in getattr(module, "LIST_SORT_POLICIES", ()))


class ListSortingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        policy = resolve_sort_policy(request.method, request.url.path, collect_list_sort_policies())
        if policy is None:
            return await call_next(request)
        sort_by = request.headers.get("x-list-sort-by") or request.query_params.get("sort_by")
        sort_order = request.headers.get("x-list-sort-order") or request.query_params.get("sort_order", "asc")
        try:
            validate_sort(sort_by, sort_order, policy)
        except AppException as error:
            return JSONResponse({"code": 422, "message": str(error), "data": None}, status_code=422)
        context = ListSortContext(policy, sort_by, sort_order)
        token = list_sort_context.set(context)
        try:
            response = await call_next(request)
            if response.status_code < 300:
                if sort_by and not context.applied:
                    return JSONResponse({"code": 422, "message": "当前列表不支持此字段排序，请选择其他列", "data": None}, status_code=422)
                response.headers["X-List-Sort-Fields"] = ",".join(sorted(context.available_fields))
            return response
        finally:
            list_sort_context.reset(token)
