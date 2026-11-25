from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user, require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .excel import build_requisition_workbook
from .schemas import RequisitionCreate, RequisitionDecision, RequisitionListQuery, RequisitionReject, RequisitionVersion, RequisitionIssue, RequisitionReceipt, RequisitionEvidence, STATUS_OPTIONS
from .service import service

router = APIRouter(prefix="/api/inventory_requisition", tags=["inventory_requisition"])
READ_PERMISSIONS = ["inventory_requisition:create", "inventory_requisition:list", "inventory_requisition:approve", "inventory_requisition:issue"]


@router.get("/options")
async def options(mine: bool = True, user: AuthenticatedUser = Depends(require_any_permissions(READ_PERMISSIONS))) -> dict[str, Any]:
    return success_response(
        {
            "statuses": STATUS_OPTIONS,
            "warehouses": await service.warehouse_options(user, mine=mine),
        }
    )


@router.get("/materials")
async def materials(
    keyword: str | None = Query(default=None, max_length=128),
    warehouse_id: UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_any_permissions(READ_PERMISSIONS)),
) -> dict[str, Any]:
    return success_response({"items": await service.material_options(keyword, warehouse_id, user)})


@router.get("/my")
async def my_requests(
    query: RequisitionListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:create"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(query, user, mine=True))


@router.get("/list")
async def list_requests(
    query: RequisitionListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(query, user, mine=False))


@router.get("/detail/{request_id}")
async def detail(request_id: UUID, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response(await service.detail(request_id, user))


@router.post("/create")
async def create(
    payload: RequisitionCreate,
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:create"])),
) -> dict[str, Any]:
    return success_response(await service.create(payload, user))


@router.post("/approve/{request_id}")
async def approve(
    request_id: UUID,
    payload: RequisitionDecision,
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:approve"])),
) -> dict[str, Any]:
    return success_response(await service.approve(request_id, payload, user))


@router.post("/reject/{request_id}")
async def reject(
    request_id: UUID,
    payload: RequisitionReject,
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:approve"])),
) -> dict[str, Any]:
    return success_response(await service.reject(request_id, payload, user))


@router.post("/withdraw/{request_id}")
async def withdraw(
    request_id: UUID,
    payload: RequisitionVersion,
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:create"])),
) -> dict[str, Any]:
    return success_response(await service.withdraw(request_id, payload, user))


@router.post("/issue/{request_id}")
async def issue(
    request_id: UUID,
    payload: RequisitionIssue,
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:issue"])),
) -> dict[str, Any]:
    return success_response(await service.issue(request_id, payload, user))


@router.post("/receive/{request_id}")
async def receive(request_id: UUID, payload: RequisitionReceipt,
                  user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:create"]))):
    return success_response(await service.receive(request_id, payload, user))


@router.post("/receipt-exception/{request_id}")
async def receipt_exception(request_id: UUID, payload: RequisitionReceipt,
                            user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:create"]))):
    return success_response(await service.receive(request_id, payload, user, exception=True))


@router.post("/resolve-exception/{request_id}")
async def resolve_exception(request_id: UUID, payload: RequisitionEvidence,
                            user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:issue"]))):
    return success_response(await service.resolve_exception(request_id, payload, user))


@router.get("/export")
async def export(
    query: RequisitionListQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["inventory_requisition:export"])),
) -> StreamingResponse:
    query.page = 1
    query.page_size = 100
    rows: list[dict] = []
    while True:
        result = await service.list(query, user, mine=False)
        rows.extend(result["items"])
        if len(rows) >= result["total"]:
            break
        query.page += 1
    content = build_requisition_workbook(rows)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=material-requisition-ledger.xlsx"},
    )

