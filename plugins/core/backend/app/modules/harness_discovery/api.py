from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response

from .models import DiscoveryRequest
from .service import discover

router = APIRouter(prefix="/api/harness/discovery", tags=["harness-discovery"])


@router.post("", include_in_schema=False)
async def discover_erp_resources(request: DiscoveryRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await discover(request, current_user))
