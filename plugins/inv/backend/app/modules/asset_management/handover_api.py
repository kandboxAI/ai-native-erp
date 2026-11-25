"""资产交接 HTTP 接口。"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .handover_schemas import (
    AssetHandoverCreate,
    AssetHandoverQuery,
    AssetHandoverReject,
    AssetHandoverLineResubmit,
    AssetHandoverUpdate,
    AssetHandoverVersion,
    AssetHandoverVoid,
)
from .handover_service import handover_service

router = APIRouter(prefix="/api/asset-handovers", tags=["asset-handover"])


@router.get("")
async def list_handovers(
    query: AssetHandoverQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:list"])),
) -> dict[str, Any]:
    return paginated_response(**await handover_service.list(query, user))


@router.get("/mine")
async def list_my_handovers(
    query: AssetHandoverQuery = Depends(),
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:mine"])),
) -> dict[str, Any]:
    return paginated_response(**await handover_service.list_mine(query, user))


@router.get("/{handover_id}")
async def handover_detail(
    handover_id: UUID,
    user: AuthenticatedUser = Depends(
        require_any_permissions(
            [
                "asset_handover:list",
                "asset_handover:mine",
                "education:offboarding:view",
            ]
        )
    ),
) -> dict[str, Any]:
    return success_response(await handover_service.detail(handover_id, user))


@router.post("")
async def create_handover(
    body: AssetHandoverCreate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:create"])),
) -> dict[str, Any]:
    return success_response(await handover_service.create(body, user))


@router.put("/{handover_id}")
async def update_handover(
    handover_id: UUID,
    body: AssetHandoverUpdate,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:manage"])),
) -> dict[str, Any]:
    return success_response(await handover_service.update(handover_id, body, user))


@router.post("/{handover_id}/submit")
async def submit_handover(
    handover_id: UUID,
    body: AssetHandoverVersion,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:manage"])),
) -> dict[str, Any]:
    return success_response(await handover_service.submit(handover_id, body.expected_version, user))


@router.post("/{handover_id}/withdraw")
async def withdraw_handover(
    handover_id: UUID,
    body: AssetHandoverVersion,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:manage"])),
) -> dict[str, Any]:
    return success_response(await handover_service.withdraw(handover_id, body.expected_version, user))


@router.post("/{handover_id}/void")
async def void_handover(
    handover_id: UUID,
    body: AssetHandoverVoid,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:manage"])),
) -> dict[str, Any]:
    return success_response(await handover_service.void(handover_id, body.expected_version, body.reason, user))


@router.post("/{handover_id}/lines/{line_id}/receive")
async def receive_handover_line(
    handover_id: UUID,
    line_id: UUID,
    user: AuthenticatedUser = Depends(
        require_any_permissions(["asset_handover:mine", "asset_handover:receive"])
    ),
) -> dict[str, Any]:
    return success_response(await handover_service.receive_line(handover_id, line_id, user))


@router.post("/{handover_id}/lines/{line_id}/reject")
async def reject_handover_line(
    handover_id: UUID,
    line_id: UUID,
    body: AssetHandoverReject,
    user: AuthenticatedUser = Depends(
        require_any_permissions(["asset_handover:mine", "asset_handover:receive"])
    ),
) -> dict[str, Any]:
    return success_response(await handover_service.reject_line(handover_id, line_id, body.reason, user))


@router.post("/{handover_id}/lines/{line_id}/resubmit")
async def resubmit_handover_line(
    handover_id: UUID,
    line_id: UUID,
    body: AssetHandoverLineResubmit,
    user: AuthenticatedUser = Depends(require_permissions(["asset_handover:manage"])),
) -> dict[str, Any]:
    return success_response(
        await handover_service.resubmit_line(handover_id, line_id, body, user)
    )
