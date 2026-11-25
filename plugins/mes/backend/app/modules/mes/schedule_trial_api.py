from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permissions
from app.core.response import success_response
from .schedule_trial_schemas import TrialScope, TrialSolve
from .schedule_trial_service import service

router = APIRouter(prefix="/schedule-trials")


@router.post("/prepare", summary="读取完整工单及资源资料，准备只读试排")
async def prepare(body: TrialScope, user=Depends(require_permissions(["mes:schedule:manage"]))):
    return success_response(await service.prepare(body, user))


@router.post("/solve", summary="CP-SAT只读条件试排，不写入生产计划")
async def solve(body: TrialSolve, user=Depends(require_permissions(["mes:schedule:manage"]))):
    return success_response(await service.solve(body, user))
