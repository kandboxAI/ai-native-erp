"""按当前账号的真实菜单授权解析导航目标，不维护行业页面副本。"""

import math
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.modules.menu.service import service as menu_service

router = APIRouter(prefix="/api/harness/navigation", tags=["harness-navigation"])


class NavigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menu_key: str | None = Field(default=None, min_length=1, max_length=128)
    path: str | None = Field(default=None, min_length=1, max_length=2048)
    query: dict[str, StrictStr | StrictInt | StrictFloat | StrictBool | None] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def validate_target(self):
        if (self.menu_key is None) == (self.path is None):
            raise ValueError("menu_key 和 path 必须且只能提供一个")
        for key, value in self.query.items():
            if len(key) > 64 or (isinstance(value, str) and len(value) > 512) or (isinstance(value, float) and not math.isfinite(value)):
                raise ValueError("页面查询参数无效")
        return self


def resolve_target(nodes: list[dict], payload: NavigationRequest, user: AuthenticatedUser) -> dict:
    for node in nodes:
        matches = node.get("menu_key") == payload.menu_key if payload.menu_key is not None else node.get("path") == payload.path
        path = node.get("path")
        if matches and node.get("menu_type_code") == "menu" and not node.get("is_external"):
            permission = node.get("permission_key")
            if permission and permission not in user.permissions:
                continue
            decoded = unquote(path) if isinstance(path, str) else ""
            if not decoded.startswith("/") or decoded.startswith("//") or any(c in decoded for c in "\\?#") or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
                continue
            return {"menu_key": node["menu_key"], "path": path, "query": payload.query}
        try:
            return resolve_target(node.get("children", []), payload, user)
        except HTTPException as error:
            if error.status_code != 404:
                raise
    raise HTTPException(404, "页面不存在或当前账号无权访问")


@router.post("", include_in_schema=False)
async def resolve_navigation(payload: NavigationRequest, user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    return success_response(resolve_target(await menu_service.tree_for_user(user), payload, user))
