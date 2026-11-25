from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.core.rate_limit import enforce_fixed_window_rate_limit
from app.core.response import paginated_response, success_response
from app.db.pagination import PageParams
from app.framework.crud.service import CrudService
from app.framework.export.attachment_headers import binary_attachment_disposition
from app.framework.export.limits import DEFAULT_EXPORT_ROWS, MAX_EXPORT_ROWS
from app.framework.export.column_comments import build_export_header_map
from app.framework.export.xlsx_builder import (
    WORKBOOK_FILENAME_EXTENSION,
    XLSX_MEDIA_TYPE,
    build_xlsx_bytes,
)


def build_crud_router(
    *,
    module_name: str,
    service: CrudService,
    create_model,
    update_model,
    tags: list[str],
    list_model=PageParams,
    # 与 list_model 不同时：仅用于 `/export` 的筛选参数模型（分页仍无效，由 export_limit 决定行数）
    export_list_model: Any | None = None,
    # 导出列头特例覆盖（优先级最高）；默认用 repository.table_model 的列 comment
    export_header_zh: dict[str, str] | None = None,
    enable_create: bool = True,
    enable_update: bool = True,
    enable_delete: bool = True,
) -> APIRouter:
    router = APIRouter(prefix=f"/api/{module_name}", tags=tags)
    repo = getattr(service, "repository", None)
    if repo is not None and getattr(repo, "scope_resource", None) is None:
        repo.scope_resource = module_name

    @router.get("/list")
    async def list_items(
        params: list_model = Depends(),
        current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:list"])),
    ) -> dict[str, Any]:
        result = await service.list(params, current_user)
        return paginated_response(**result)

    _ExportParams = export_list_model or list_model

    @router.get("/export")
    async def export_items_excel(
        request: Request,
        params: _ExportParams = Depends(),
        export_limit: int = Query(DEFAULT_EXPORT_ROWS, ge=1, le=MAX_EXPORT_ROWS, description="单次导出行上限"),
        current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:export"])),
    ) -> Response:
        """与 `/list` 相同筛选条件的 Excel 导出（.xlsx）。需 `{module}:export`。分页参数对导出无效。"""
        settings = get_settings()
        client_ip = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if not client_ip and request.client:
            client_ip = request.client.host
        await enforce_fixed_window_rate_limit(
            namespace=f"export_{module_name}",
            key_parts=[str(current_user.user_id), client_ip or "unknown"],
            limit=settings.api_export_rate_limit_per_minute,
            window_seconds=60,
        )
        rows = await service.export_rows(params, current_user, limit=export_limit)
        repo = getattr(service, "repository", None)
        tm = getattr(repo, "table_model", None)
        rel_paths = getattr(repo, "export_relation_paths", None) or ()
        header_lookup = build_export_header_map(
            table_model=tm,
            overrides=export_header_zh,
            relation_paths=rel_paths if rel_paths else None,
        )
        body = build_xlsx_bytes(
            rows,
            header_lookup=header_lookup,
            relation_paths=rel_paths if rel_paths else None,
        )
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        filename = f"{module_name}_export_{ts}{WORKBOOK_FILENAME_EXTENSION}"
        headers = {"Content-Disposition": binary_attachment_disposition(filename, WORKBOOK_FILENAME_EXTENSION)}
        return Response(content=body, media_type=XLSX_MEDIA_TYPE, headers=headers)

    @router.get("/detail/{item_id}")
    async def detail_item(
        item_id: str,
        current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:detail"])),
    ) -> dict[str, Any]:
        item = await service.detail(item_id, current_user)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
        return success_response(item.model_dump(mode="json"))

    if enable_create:
        @router.post("/create")
        async def create_item(
            payload: create_model,
            current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:create"])),
        ) -> dict[str, Any]:
            item = await service.create(payload.model_dump(exclude_none=True), current_user)
            return success_response(item.model_dump(mode="json"))

    if enable_update:
        @router.put("/update/{item_id}")
        async def update_item(
            item_id: str,
            request: Request,
            payload: update_model,
            current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:update"])),
        ) -> dict[str, Any]:
            # 使用 exclude_unset：仅提交请求体里出现的字段；显式传 null 可清空可空字段（exclude_none 会丢掉 null）
            update_payload = payload.model_dump(exclude_unset=True)
            try:
                raw_body = await request.json()
            except Exception:
                raw_body = {}
            if isinstance(raw_body, dict) and "updated_at" in raw_body:
                update_payload["__expected_updated_at"] = raw_body.get("updated_at")
            item = await service.update(item_id, update_payload, current_user)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
            return success_response(item.model_dump(mode="json"))

    if enable_delete:
        @router.delete("/delete/{item_id}")
        async def delete_item(
            item_id: str,
            current_user: AuthenticatedUser = Depends(require_permissions([f"{module_name}:delete"])),
        ) -> dict[str, Any]:
            deleted = await service.delete(item_id, current_user)
            if not deleted:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
            return success_response({"deleted": True})

    @router.get("/permissions")
    async def module_permissions(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
        allowed = current_user.permissions or []
        return success_response(
            {
                "module": module_name,
                "permissions": [item for item in allowed if item.startswith(f"{module_name}:")],
            }
        )

    # Describe standard CRUD contracts once for all modules. Exposure is still
    # decided by centralized module policy and the approved resource fields.
    tm = getattr(repo, "table_model", None)
    if tm is not None:
        table = tm.__table__
        resource = table.name if table.schema is None else f"{table.schema}.{table.name}"
        for route in router.routes:
            suffix = route.path.removeprefix(f"/api/{module_name}/").split("/")[0]
            if suffix in {"list", "detail", "create", "update", "delete"}:
                route.endpoint.__harness_crud__ = {"module": module_name, "resource": resource, "action": suffix}
    return router
