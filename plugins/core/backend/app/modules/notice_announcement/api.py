"""公告接口：管理端增删改查，本人可见列表、详情、已读，阅读情况。"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user, require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import NoticeCreate, NoticeListQuery, NoticeReaderListQuery, NoticeUpdate
from .service import service

router = APIRouter(prefix="/api/notice_announcement", tags=["notice_announcement"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")


@router.get("/list")
async def list_notices(
    params: NoticeListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user, mine=False))


@router.get("/detail/{notice_id}")
async def notice_detail(
    notice_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:detail"])),
) -> dict[str, Any]:
    item = await service.detail(notice_id, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/create")
async def create_notice(
    payload: NoticeCreate,
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:create"])),
) -> dict[str, Any]:
    item = await service.create(payload, current_user)
    return success_response(item.model_dump(mode="json"))


@router.put("/update/{notice_id}")
async def update_notice(
    notice_id: UUID,
    payload: NoticeUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:update"])),
) -> dict[str, Any]:
    item = await service.update(notice_id, payload, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.delete("/delete/{notice_id}")
async def delete_notice(
    notice_id: UUID,
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:delete"])),
) -> dict[str, Any]:
    if not await service.delete(notice_id, current_user):
        raise _not_found()
    return success_response({"deleted": True})


@router.get("/readers/{notice_id}")
async def list_notice_readers(
    notice_id: UUID,
    params: NoticeReaderListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["notice_announcement:list"])),
) -> dict[str, Any]:
    result = await service.list_readers(notice_id, params, current_user)
    if result is None:
        raise _not_found()
    return paginated_response(**result)


@router.get("/target-options")
async def notice_target_options(
    keyword: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_any_permissions(["notice_announcement:create", "notice_announcement:update"])),
) -> dict[str, Any]:
    """接收范围可选的角色与用户（按显示名搜索）。"""
    return success_response(await service.target_options(keyword, limit))


# ───────── 本人（登录即可，只看已发布且在接收范围内的） ─────────
@router.get("/mine/list")
async def list_my_notices(
    params: NoticeListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return paginated_response(**await service.list(params, current_user, mine=True))


@router.get("/mine/detail/{notice_id}")
async def my_notice_detail(notice_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    item = await service.detail(notice_id, current_user, mine=True)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/read/{notice_id}")
async def mark_notice_read(notice_id: UUID, current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    item = await service.mark_read(notice_id, current_user)
    if item is None:
        raise _not_found()
    return success_response(item.model_dump(mode="json"))


@router.post("/read-all")
async def mark_all_notices_read(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return success_response({"marked_count": await service.mark_all_read(current_user)})
