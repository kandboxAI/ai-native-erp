from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from .delivery_schemas import DeliveryCommand, DeliveryQuery, ReconciliationBody, ShipmentBody, ShipmentUpdate
from .delivery_service import delivery_service as service
from . import shipment_document_service as documents
from .shipment_document_exports import RENDERERS, TITLES
from .shipment_document_schemas import DocumentKind, ShipmentDocumentBody, ShipmentInvoiceBody

router = APIRouter(tags=["mes-delivery"])


async def save(operation):
    try:
        return success_response(await operation)
    except IntegrityError as exc:
        raise AppException("单号、幂等键重复或出货明细已被对账占用，请刷新后重试", 409) from exc


@router.get("/shipments/sources")
async def shipment_sources(query: DeliveryQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return paginated_response(**await service.sources("shipments", query, user))


@router.get("/shipments/customer-options")
async def shipment_customer_options(sales_order_id: UUID | None = None, keyword: str = Query("", max_length=128),
        limit: int = Query(50, ge=1, le=50), user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return success_response(await service.customer_options(user, keyword, limit, sales_order_id))


@router.get("/shipments/sales-order-options")
async def shipment_sales_order_options(customer_id: UUID, keyword: str = Query("", max_length=128),
        limit: int = Query(50, ge=1, le=50), user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return success_response(await service.sales_order_options(user, customer_id, keyword, limit))


@router.get("/shipments")
async def shipments(query: DeliveryQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:list"]))):
    return paginated_response(**await service.documents("shipments", query, user))


@router.get("/shipments/{document_id}")
async def shipment(document_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:list"]))):
    return success_response(await service.detail("shipments", document_id, user))


@router.post("/shipments")
async def create_shipment(body: ShipmentBody, user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return await save(service.save_shipment(body, user))


@router.put("/shipments/{document_id}")
async def update_shipment(document_id: UUID, body: ShipmentUpdate, user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return await save(service.save_shipment(body, user, document_id))


@router.get("/shipments/{document_id}/documents")
async def shipment_documents(document_id: UUID,
        user: AuthenticatedUser = Depends(require_permissions([documents.LIST, documents.DOCUMENTS]))):
    return success_response(await documents.document_set(document_id, user))


@router.post("/shipments/{document_id}/documents/preview")
async def preview_shipment_documents(document_id: UUID, body: ShipmentDocumentBody,
        user: AuthenticatedUser = Depends(require_permissions([documents.LIST, documents.DOCUMENTS, documents.MANAGE]))):
    return success_response(await documents.make_documents(document_id, body, user, preview=True))


@router.post("/shipments/{document_id}/documents")
async def create_shipment_documents(document_id: UUID, body: ShipmentDocumentBody,
        user: AuthenticatedUser = Depends(require_permissions([documents.LIST, documents.DOCUMENTS, documents.MANAGE]))):
    return await save(documents.make_documents(document_id, body, user))


@router.get("/shipments/{document_id}/documents/{revision_id}/{kind}")
async def download_shipment_document(document_id: UUID, revision_id: UUID, kind: DocumentKind,
        user: AuthenticatedUser = Depends(require_permissions([documents.LIST, documents.DOCUMENTS]))):
    snapshot, metadata, status = await documents.export_data(document_id, revision_id, kind, user)
    render = RENDERERS.get(metadata["template_key"])
    if render is None:
        raise AppException("该历史单据的模板版本不可用", 409)
    filename = f"{snapshot['shipment_no']}-{TITLES[kind]}-V{metadata['revision_no']}.xlsx"
    return Response(render(snapshot, kind, metadata, status),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}", "Cache-Control": "no-store"})


@router.post("/shipments/{document_id}/invoices")
async def register_shipment_invoice(document_id: UUID, body: ShipmentInvoiceBody,
        user: AuthenticatedUser = Depends(require_permissions([documents.LIST, documents.DOCUMENTS, documents.INVOICE]))):
    return await save(documents.register_invoice(document_id, body, user))


@router.post("/shipments/{document_id}/{action}")
async def shipment_action(document_id: UUID, action: str, body: DeliveryCommand, user: AuthenticatedUser = Depends(require_permissions(["mes:shipment:manage"]))):
    return await save(service.shipment_action(document_id, action, body, user))


@router.get("/reconciliations/sources")
async def reconciliation_sources(query: DeliveryQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:reconciliation:manage"]))):
    return paginated_response(**await service.sources("reconciliations", query, user))


@router.get("/reconciliations")
async def reconciliations(query: DeliveryQuery = Depends(), user: AuthenticatedUser = Depends(require_permissions(["mes:reconciliation:list"]))):
    return paginated_response(**await service.documents("reconciliations", query, user))


@router.get("/reconciliations/{document_id}")
async def reconciliation(document_id: UUID, user: AuthenticatedUser = Depends(require_permissions(["mes:reconciliation:list"]))):
    return success_response(await service.detail("reconciliations", document_id, user))


@router.post("/reconciliations")
async def create_reconciliation(body: ReconciliationBody, user: AuthenticatedUser = Depends(require_permissions(["mes:reconciliation:manage"]))):
    return await save(service.save_reconciliation(body, user))


@router.post("/reconciliations/{document_id}/{action}")
async def reconciliation_action(document_id: UUID, action: str, body: DeliveryCommand, user: AuthenticatedUser = Depends(require_permissions(["mes:reconciliation:manage"]))):
    return await save(service.reconciliation_action(document_id, action, body, user))
