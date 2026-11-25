"""统一响应、动作权限和租户启用守卫；计算及持久化由 Service 处理。"""

import importlib.util
from urllib.parse import quote as url_quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.auth.dependencies import require_permissions, require_plugin_enabled
from app.core.response import success_response
from app.core.exceptions import AppException
from .config import settings
from .pricing import IncompleteQuote
from .repository import LIST, MANAGE, ANALYZE, APPROVE, RULES
from .rules import ApplyRules, RulesEdit
from .schemas import PartEdit, AnalysisRequest, AdoptDraft, Approval, MaterialSelectionRequest
from .service import service

router = APIRouter(prefix="/cnc", dependencies=[Depends(require_plugin_enabled("mes"))])


@router.get("/health")
async def health(user=Depends(require_permissions([LIST]))):
    config = settings()
    return success_response(
        {
            "ai_configured": bool(config.ai_api_key.get_secret_value()),
            "ai_model": config.ai_model,
            "ocr_configured": bool(config.paddleocr_access_token.get_secret_value()),
            "ocr": config.paddleocr_model,
            "cad_available": importlib.util.find_spec("OCP") is not None,
        }
    )


@router.get("/parts")
async def listing(
    deleted: bool = False,
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=200),
    user=Depends(require_permissions([LIST])),
):
    return success_response(await service.listing(user, deleted, search, page, page_size))


@router.post("/parts")
async def create(
    files: list[UploadFile] = File(...),
    name: str = Form("", max_length=200),
    quantity: int = Form(1),
    user=Depends(require_permissions([LIST, MANAGE])),
):
    return success_response(await service.create(files, name, quantity, user))


@router.get("/parts/{part_id}")
async def detail(part_id: UUID, user=Depends(require_permissions([LIST]))):
    return success_response(await service.detail(part_id, user))


@router.get("/parts/{part_id}/status")
async def status(part_id: UUID, user=Depends(require_permissions([LIST]))):
    return success_response(await service.detail(part_id, user, status_only=True))


@router.get("/parts/{part_id}/processes")
async def process_options(part_id:UUID,user=Depends(require_permissions([LIST]))):
    return success_response(await service.process_options(part_id,user))


@router.put("/parts/{part_id}")
async def edit(part_id: UUID, body: PartEdit, user=Depends(require_permissions([LIST, MANAGE]))):
    return success_response(await service.edit(part_id, body, user))


@router.delete("/parts/{part_id}")
async def remove(
    part_id: UUID, version_no: int = Query(ge=1), user=Depends(require_permissions([LIST, MANAGE]))
):
    return success_response(await service.delete_or_restore(part_id, user, version=version_no))


@router.post("/parts/{part_id}/restore")
async def restore(part_id: UUID, user=Depends(require_permissions([LIST, MANAGE]))):
    return success_response(await service.delete_or_restore(part_id, user, restore=True))


@router.get("/quote-rules")
async def rules(org_id: UUID | None = None, user=Depends(require_permissions([LIST]))):
    return success_response(await service.rules(user, org_id=org_id))


@router.put("/quote-rules")
async def save_rules(
    body: RulesEdit, org_id: UUID | None = None, user=Depends(require_permissions([LIST, RULES]))
):
    return success_response(await service.rules(user, body, org_id))


@router.post("/parts/{part_id}/apply-rules")
async def fill(part_id: UUID, body: ApplyRules, user=Depends(require_permissions([LIST, MANAGE]))):
    return success_response(await service.fill_rules(part_id, body, user))


@router.post("/parts/{part_id}/adopt-draft")
async def adopt(part_id: UUID, body: AdoptDraft, user=Depends(require_permissions([LIST, MANAGE]))):
    return success_response(await service.fill_rules(part_id, body, user, adopt=True))


@router.post("/parts/{part_id}/analyze")
async def analyze(
    part_id: UUID, body: AnalysisRequest, user=Depends(require_permissions([LIST, MANAGE, ANALYZE]))
):
    return success_response(await service.queue(part_id, body, user))


@router.post("/parts/{part_id}/select-material")
async def select_material(
    part_id: UUID,
    body: MaterialSelectionRequest,
    user=Depends(require_permissions([LIST, MANAGE, ANALYZE])),
):
    return success_response(await service.select_material(part_id, body, user))


@router.post("/jobs/{job_id}/reconcile")
async def reconcile(job_id: UUID, user=Depends(require_permissions([LIST, ANALYZE]))):
    return success_response(await service.reconcile(job_id, user))


@router.get("/files/{file_id}")
async def original(file_id: UUID, user=Depends(require_permissions([LIST]))):
    content, media, name = await service.file_content(file_id, user)
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{url_quote(name)}"},
    )


@router.get("/parts/{part_id}/assets/{filename}")
async def asset(part_id: UUID, filename: str, user=Depends(require_permissions([LIST]))):
    return FileResponse(await service.artifact(part_id, filename, user))


@router.get("/parts/{part_id}/ocr-export")
async def ocr_export(part_id: UUID, user=Depends(require_permissions([LIST]))):
    return Response(
        await service.ocr_export(part_id, user),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="document-{part_id}.zip"'},
    )


@router.post("/parts/{part_id}/quote")
async def evaluate(part_id: UUID, user=Depends(require_permissions([LIST, MANAGE]))):
    try:
        return success_response(await service.evaluate(part_id, user))
    except IncompleteQuote as error:
        return JSONResponse(
            status_code=422, content={"code": 422, "message": str(error), "data": {"missing": error.missing}}
        )


@router.post("/quotes/{quote_id}/approve")
async def approve(quote_id: UUID, body: Approval, user=Depends(require_permissions([LIST, APPROVE]))):
    return success_response(await service.approve(quote_id, user))


@router.get("/quotes/{quote_id}/export/{format}")
async def export(quote_id: UUID, format: str, user=Depends(require_permissions([LIST]))):
    quote = await service.export_context(quote_id, user)
    if format == "xlsx":
        from .exports import xlsx_bytes

        data, media = xlsx_bytes(quote), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        from .exports import pdf_bytes

        data, media = pdf_bytes(quote), "application/pdf"
    else:
        raise AppException("不支持的导出格式", 404)
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="quote-{quote_id}.{format}"'},
    )
