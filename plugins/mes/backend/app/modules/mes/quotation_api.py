from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import quote as url_quote
from uuid import UUID
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import APIRouter, Depends, File, UploadFile, Query
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions, require_plugin_enabled
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from app.framework.db.session import get_session_context
from app.modules.file.service import service as files
from .quotation_schemas import QuotationBody, EngineeringBody, QuotationCommand, QuotationCncBody, QuotationAdoptBody, QuotationApprovalBody, QuotationAdoptionPreview, QuotationBatchAdopt
from .quotation_service import service
from .quotation_repository import repository
from .quotation_exports import workbook
from .quotation_imports import import_template, inspect_import, MAX_BYTES

router = APIRouter(prefix="/quotations", dependencies=[Depends(require_plugin_enabled("mes"))])
LIST = "mes:quotation:list"


@router.get("/historical-prices")
async def historical_prices(drawing_no: str = Query(min_length=1, max_length=64), customer_id: UUID | None = None,
        page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(require_permissions([LIST, "mes:quotation:price"]))):
    return paginated_response(**await service.historical_prices(user, drawing_no, customer_id, page, page_size))


@router.get("/import-template")
async def template(user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return Response(import_template(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote('询价货品导入模板.xlsx')}"})


@router.post("/import-preview")
async def preview(file: UploadFile = File(...), user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise AppException("请上传系统模板格式的 .xlsx 文件", 422)
    return success_response(inspect_import(await file.read(MAX_BYTES+1)))


@router.get("")
async def listing(keyword: str = Query("", max_length=128), status: str = Query("", max_length=32),
        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), user=Depends(require_permissions([LIST]))):
    return paginated_response(**await service.page(user, keyword, status, page, page_size))


@router.get("/customers")
async def customers(org_id: UUID | None = None, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.customers(org_id, user))


@router.post("/files")
async def upload(file: UploadFile = File(...), user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.upload(file, user))


@router.post("")
async def create(body: QuotationBody, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.save(None, body, user))


@router.post("/submit")
async def create_and_submit(body: QuotationBody, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.save(None, body, user, submit=True))


@router.get("/{identifier}")
async def detail(identifier: UUID, user=Depends(require_permissions([LIST]))):
    return success_response(await service.detail(identifier, user))


@router.get("/{identifier}/cnc-records")
async def cnc_progress(identifier: UUID,
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list"]))):
    return success_response(await service.cnc_progress(identifier, user))


@router.get("/{identifier}/exchange-rate")
async def exchange_rate(identifier: UUID, quote_currency: Literal["CNY", "EUR", "USD"],
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list"]))):
    return success_response(await service.exchange_rate(identifier, quote_currency, user))


@router.put("/{identifier}")
async def save(identifier: UUID, body: QuotationBody, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.save(identifier, body, user))


@router.delete("/{identifier}")
async def delete_draft(identifier: UUID, version_no: int = Query(ge=1),
        user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.delete_draft(identifier, version_no, user))


@router.post("/{identifier}/submit")
async def save_and_submit(identifier: UUID, body: QuotationBody, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    return success_response(await service.save(identifier, body, user, submit=True))


@router.put("/{identifier}/engineering")
async def engineering(identifier: UUID, body: EngineeringBody, user=Depends(require_permissions([LIST, "mes:quotation:price"]))):
    return success_response(await service.engineering(identifier, body, user))


@router.post("/{identifier}/engineering/submit")
async def engineering_and_submit(identifier: UUID, body: EngineeringBody, user=Depends(require_permissions([LIST, "mes:quotation:price"]))):
    return success_response(await service.engineering(identifier, body, user, submit=True))


@router.post("/{identifier}/revisions")
async def revision(identifier: UUID, body: QuotationCommand, user=Depends(require_permissions([LIST, "mes:quotation:manage"]))):
    try:
        result = await service.revise(identifier, body, user)
    except IntegrityError as error:
        raise AppException("报价已产生新修订，请刷新后重试", 409) from error
    return success_response(result)


@router.post("/{identifier}/actions/{action}")
async def command(identifier: UUID, action: str, body: QuotationCommand, user=Depends(require_permissions([LIST]))):
    return success_response(await service.command(identifier, action, body, user))


@router.post("/{identifier}/approve")
async def approve(identifier: UUID, body: QuotationApprovalBody, user=Depends(require_permissions([LIST, "mes:quotation:approve"]))):
    return success_response(await service.approve(identifier, body, user))


@router.post("/{identifier}/lines/{line_id}/cnc")
async def prepare_cnc(identifier: UUID, line_id: UUID, body: QuotationCncBody,
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list", "mes:quote:manage", "mes:quote:analyze"]))):
    return success_response(await service.prepare_cnc(identifier, line_id, body, user))


@router.post("/{identifier}/lines/{line_id}/adopt")
async def adopt(identifier: UUID, line_id: UUID, body: QuotationAdoptBody,
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list"]))):
    return success_response(await service.adopt(identifier, line_id, body, user))


@router.post("/{identifier}/adoption-preview")
async def adoption_preview(identifier: UUID, body: QuotationAdoptionPreview,
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list"]))):
    return success_response(await service.adoption_preview(identifier, body, user))


@router.post("/{identifier}/adopt-batch")
async def adopt_batch(identifier: UUID, body: QuotationBatchAdopt,
        user=Depends(require_permissions([LIST, "mes:quotation:price", "mes:quote:list"]))):
    return success_response(await service.adopt_batch(identifier, body, user))


@router.get("/{identifier}/export")
async def export(identifier: UUID, with_drawings: bool = False, user=Depends(require_permissions([LIST, "mes:quotation:export"]))):
    async with get_session_context() as session:
        quote = await repository.get(session, identifier, user, "mes:quotation:export")
        data = await service.data(session, quote, user)
        content = workbook(data)
        name = f"{quote.quote_no}_R{quote.revision}"
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        suffix = ".xlsx"
        if with_drawings:
            output = BytesIO()
            total = 0
            with ZipFile(output, "w", ZIP_DEFLATED) as archive:
                archive.writestr(name+".xlsx", content)
                for index, line in enumerate(await repository.lines(session, quote), 1):
                    for binding in await repository.files(session, line.id):
                        original, raw = await files.read_content(session, binding.attachment_id, user=user)
                        total += len(raw)
                        if total > 200*1024*1024:
                            raise AppException("打包原件超过 200MB，请分批下载", 413)
                        safe_name = Path(original.original_file_name.replace("\\", "/")).name
                        archive.writestr(f"drawings/{index}/{safe_name}", raw)
            content, media, suffix = output.getvalue(), "application/zip", ".zip"
    return Response(content, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(name+suffix)}"})
