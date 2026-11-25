from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_any_permissions, require_permissions
from app.core.exceptions import AppException
from app.core.response import success_response, paginated_response
from .schedule_resource_service import LIST, MANAGE, service
from .schedule_resource_schemas import (ResourceQuery, PersonBody, QualificationBody, CalendarBody,
    CalendarBatchBody, CalendarExceptionBody)
from app.framework.db.session import get_session_context
from app.modules.organization.public import list_writable_org_options
from .schedule_resource_service import require
from .schedule_resource_repository import repository

router = APIRouter(prefix="/schedule-resources", tags=["MES排程资源"])
reader = require_any_permissions([LIST, MANAGE])
writer = require_permissions([MANAGE])


async def save(action):
    try: return success_response(await action)
    except IntegrityError as error: raise AppException("资源编号重复或关联资料已变化，请重新读取核对", 409) from error


@router.get("/organizations")
async def organizations(keyword: str = "", user=Depends(reader)):
    permission = require(user)
    async with get_session_context() as session:
        return success_response(await list_writable_org_options(session, user, permission, keyword))


@router.get("/processes")
async def processes(org_id: UUID, keyword: str = "", user=Depends(reader)):
    permission = require(user)
    async with get_session_context() as session:
        rows = await repository.process_options(session, org_id, keyword[:100], user, permission)
        return success_response([dict(value=r.id, label=f"{r.process_no} · {r.process_name}") for r in rows])


@router.get("/options")
async def options(org_id: UUID, user=Depends(reader)):
    return success_response(await service.options(org_id, user))


@router.get("/{kind}")
async def page(kind: Literal["people", "calendars"], query: ResourceQuery = Depends(), user=Depends(reader)):
    return paginated_response(**await service.page(kind, query, user))


@router.get("/{kind}/{identifier}")
async def detail(kind: Literal["people", "calendars"], identifier: UUID, user=Depends(reader)):
    return success_response(await service.detail(kind, identifier, user))


@router.post("/people")
async def create_person(body: PersonBody, user=Depends(writer)):
    return await save(service.save_person(body, user))


@router.put("/people/{identifier}")
async def update_person(identifier: UUID, body: PersonBody, user=Depends(writer)):
    return await save(service.save_person(body, user, identifier))


@router.post("/people/{identifier}/qualifications")
async def create_skill(identifier: UUID, body: QualificationBody, user=Depends(writer)):
    return await save(service.save_qualification(identifier, body, user))


@router.put("/people/{identifier}/qualifications/{qualification_id}")
async def update_skill(identifier: UUID, qualification_id: UUID, body: QualificationBody, user=Depends(writer)):
    return await save(service.save_qualification(identifier, body, user, qualification_id))


@router.post("/calendars")
async def create_calendar(body: CalendarBody, user=Depends(writer)):
    return await save(service.save_calendar(body, user))


@router.post("/calendar-batch")
async def batch_calendars(body: CalendarBatchBody, user=Depends(writer)):
    return await save(service.batch_calendars(body, user))


@router.put("/calendars/{identifier}")
async def update_calendar(identifier: UUID, body: CalendarBody, user=Depends(writer)):
    return await save(service.save_calendar(body, user, identifier))


@router.post("/calendars/{identifier}/exceptions")
async def create_exception(identifier: UUID, body: CalendarExceptionBody, user=Depends(writer)):
    return await save(service.save_exception(identifier, body, user))


@router.put("/calendars/{identifier}/exceptions/{exception_id}")
async def update_exception(identifier: UUID, exception_id: UUID, body: CalendarExceptionBody, user=Depends(writer)):
    return await save(service.save_exception(identifier, body, user, exception_id))
