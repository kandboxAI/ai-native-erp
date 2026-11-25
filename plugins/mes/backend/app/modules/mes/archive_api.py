from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_any_permissions
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from app.framework.db.session import get_session_context
from app.modules.organization.public import list_writable_org_options
from .archive_schemas import ArchiveQuery
from .archive_service import archive_service as service, ARCHIVES, permission, require

ArchiveKind = Literal["customers", "project-stages", "processes", "equipment", "requirements"]
LIST = [permission(kind, "list") for kind in ARCHIVES]
MANAGE = [permission(kind, "manage") for kind in ARCHIVES]
OPTIONS = MANAGE + ["mes:work_order:create", "mes:work_order:manage", "mes:process_template:manage", "mes:schedule:list", "mes:schedule:manage"]
router = APIRouter(tags=["mes-archives"])


@router.get("/archives/{kind}")
async def page(kind: ArchiveKind, query: ArchiveQuery = Depends(), user=Depends(require_any_permissions(LIST))):
    return paginated_response(**await service.page(kind, query, user))


@router.get("/archive-options/{kind}")
async def options(kind: ArchiveKind, query: ArchiveQuery = Depends(), user=Depends(require_any_permissions(OPTIONS))):
    return paginated_response(**await service.options(kind, query, user))


@router.get("/archives/{kind}/organizations")
async def organizations(kind: ArchiveKind, keyword: str = "", user=Depends(require_any_permissions(MANAGE))):
    key = permission(kind, "manage")
    require(user, key)
    async with get_session_context() as session:
        return success_response(await list_writable_org_options(session, user, key, keyword))


async def save(kind, body, user, identifier=None):
    try: return success_response(await service.save(kind, body, user, identifier))
    except IntegrityError as error: raise AppException("档案编号重复或关联项已变化，请刷新后重试", 409) from error


@router.post("/archives/{kind}")
async def create(kind: ArchiveKind, body: dict, user=Depends(require_any_permissions(MANAGE))):
    return await save(kind, body, user)


@router.put("/archives/{kind}/{identifier}")
async def update(kind: ArchiveKind, identifier: UUID, body: dict, user=Depends(require_any_permissions(MANAGE))):
    return await save(kind, body, user, identifier)
