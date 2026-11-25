from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from . import service
from .schemas import TodoQuery, TodoCreate, TodoAction

router = APIRouter(prefix="/api/todo", tags=["通用待办"])


@router.get("/assignment-options")
async def assignment_options(org_id: UUID, keyword: str = Query(default="", max_length=100),
                             user: AuthenticatedUser = Depends(require_permissions(["todo:create"]))):
    return success_response(await service.assignment_options(org_id, keyword, user))


@router.get("/mine")
async def mine(query: TodoQuery = Query(), user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.mine(query, user))


@router.post("/priority-recommendations")
async def priority_recommendations(user: AuthenticatedUser = Depends(get_current_user)):
    from .priority import recommend
    return success_response(await recommend(user))


@router.get("/detail/{todo_id}")
async def detail(todo_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.detail(todo_id, user))


@router.post("")
async def create(body: TodoCreate, user: AuthenticatedUser = Depends(require_permissions(["todo:create"]))):
    return success_response(await service.create(body, user))


@router.post("/{todo_id}/actions/{action_key}")
async def act(todo_id: UUID, action_key: str, body: TodoAction,
              user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.act(todo_id, action_key, body, user))
