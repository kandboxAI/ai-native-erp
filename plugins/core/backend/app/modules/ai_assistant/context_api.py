"""个人偏好仅本人可写，租户统一模板要求全部范围的系统参数管理权限。"""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from .page_snapshot import SnapshotResolveRequest, resolve_page_snapshot
from . import context_service as service
from .context_schemas import PersonalInstructions, PersonalTemplatePreference, PromptTemplateInput

router = APIRouter(prefix="/api/ai/context", tags=["AI 角色与偏好"])


@router.get("/mine")
async def mine(user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.current_context(user))


@router.get("/prompt")
async def prompt(user: AuthenticatedUser = Depends(get_current_user)):
    # DSH 只获得当前用户的组合提示词，不返回设置页的完整配置。
    context = await service.current_context(user)
    return success_response({"prompt": context["prompt"],
        "position_memory_enabled": any(item["can_contribute"] for item in context["position_knowledge"])})


@router.put("/mine")
async def save_mine(body: PersonalInstructions, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.save_personal(user, body))


@router.get("/templates")
async def templates(user: AuthenticatedUser = Depends(require_permissions(["system_setting:update"]))):
    return success_response(await service.configuration(user))


@router.put("/mine/templates/{template_id}")
async def save_my_template(template_id: UUID, body: PersonalTemplatePreference,
                           user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.save_personal_template(user, template_id, body))


@router.post("/templates")
async def create_template(body: PromptTemplateInput,
                          user: AuthenticatedUser = Depends(require_permissions(["system_setting:update"]))):
    return success_response(await service.save_template(user, body))


@router.put("/templates/{template_id}")
async def update_template(template_id: UUID, body: PromptTemplateInput,
                          user: AuthenticatedUser = Depends(require_permissions(["system_setting:update"]))):
    return success_response(await service.save_template(user, body, template_id))


@router.post("/page-snapshot", summary="复核当前用户的已加载页面快照，不接收任意页面明细")
async def page_snapshot(body: SnapshotResolveRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(resolve_page_snapshot(body, user))
