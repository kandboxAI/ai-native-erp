"""导入接口，沿用原路由前缀：
/api/inventory_product_category/import、/api/inventory_product/import、/api/inventory_item/import。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.export.attachment_headers import binary_attachment_disposition

from .excel import MAX_IMPORT_BYTES, XLSX_MEDIA_TYPE
from ..products.schemas import ItemListQuery
from app.core.exceptions import AppException
from .schemas import InventoryImportOptions
from .service import service

CATEGORY_PERMISSION = "inventory_product_category:import"
ITEM_PERMISSION = "inventory_product:import"
STOCK_PERMISSION = "inventory_item:import"


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": binary_attachment_disposition(filename, ".xlsx")},
    )


async def _read_upload(file: UploadFile) -> bytes:
    try:
        content = await file.read(MAX_IMPORT_BYTES + 1)
        if len(content) > MAX_IMPORT_BYTES:
            raise AppException("Excel文件过大（上限5MB）")
        return content
    finally:
        await file.close()


def _build(prefix: str, tag: str, kind: str, permission: str, template_name: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("/template")
    async def download_template(current_user: AuthenticatedUser = Depends(require_permissions([permission]))) -> Response:
        if kind == "category":
            content = await service.category_template()
        elif kind == "item":
            content = await service.item_template()
        else:
            content = await service.stock_template(current_user)
        return _xlsx(content, template_name)

    @router.post("/validate")
    async def validate_import(
        file: UploadFile = File(...),
        allow_update_existing: bool = Form(False),
        current_user: AuthenticatedUser = Depends(require_permissions([permission])),
    ) -> dict[str, Any]:
        result = await service.run(
            kind, await _read_upload(file), file.filename or "import.xlsx", InventoryImportOptions(allow_update_existing=allow_update_existing), current_user, write=False
        )
        return success_response(result.model_dump(mode="json"))

    @router.post("")
    async def run_import(
        file: UploadFile = File(...),
        allow_update_existing: bool = Form(False),
        current_user: AuthenticatedUser = Depends(require_permissions([permission])),
    ) -> dict[str, Any]:
        result = await service.run(
            kind, await _read_upload(file), file.filename or "import.xlsx", InventoryImportOptions(allow_update_existing=allow_update_existing), current_user, write=True
        )
        return success_response(result.model_dump(mode="json"))

    return router


category_import_router = _build("/api/inventory_product_category/import", "inventory_product_category", "category", CATEGORY_PERMISSION, "物料分类导入模板.xlsx")
item_import_router = _build("/api/inventory_product/import", "inventory_product", "item", ITEM_PERMISSION, "物料档案导入模板.xlsx")
stock_import_router = _build("/api/inventory_item/import", "inventory_item", "stock", STOCK_PERMISSION, "库存盘点导入模板.xlsx")


@item_import_router.get("/export")
async def export_item_template_data(
    query: ItemListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["inventory_product:list", "inventory_product:export"])),
) -> Response:
    return _xlsx(await service.item_export(query, user), "物料档案.xlsx")
