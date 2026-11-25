from fastapi import APIRouter

from .definition.api import router as definition_router
from .runtime.api import router as runtime_router
from .task.api import router as task_router

router = APIRouter()
router.include_router(definition_router)
router.include_router(runtime_router)
router.include_router(task_router)
