import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.response import success_response
from app.auth.tenants import (
    TenantDirectoryNotInitializedError,
    ensure_tenant_directory_initialized,
    list_active_tenant_schemas,
)
from app.integrations.redis_client import get_redis, shutdown_redis, startup_redis
from app.db.connection import shutdown_database, startup_database
from app.framework.db.session import shutdown_sqlmodel_database, startup_sqlmodel_database
from app.framework.jobs import start_jobs, stop_jobs
from app.modules.ai_assistant.service import shutdown as shutdown_assistant
from app.framework.router import framework_router
from app.framework.deployment import get_deployment_profile, profile_description
from app.middleware.operation_log import OperationLogMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.list_sorting import ListSortingMiddleware

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)

logging.getLogger("app.framework").setLevel(logging.INFO)
app.add_middleware(OperationLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ListSortingMiddleware)
_cors_kwargs: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["X-List-Sort-Fields"],
    "allow_origins": [str(origin) for origin in settings.cors_origins],
}
if settings.app_env == "development" or settings.debug:
    _cors_kwargs["allow_origin_regex"] = (
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    )
app.add_middleware(CORSMiddleware, **_cors_kwargs)
register_exception_handlers(app)
app.include_router(framework_router)


@app.on_event("startup")
async def on_startup() -> None:
    await startup_database()
    try:
        await ensure_tenant_directory_initialized()
        await startup_sqlmodel_database()
        await startup_redis()
        # 插件化后台任务（master 侧）
        start_jobs(list_active_tenant_schemas)
    except BaseException:
        try:
            await on_shutdown()
        except Exception as error:
            logging.getLogger(__name__).warning("startup cleanup failed: %s", type(error).__name__)
        raise


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await shutdown_assistant()
    await stop_jobs()
    await shutdown_redis()
    await shutdown_sqlmodel_database()
    await shutdown_database()


@app.get("/healthz")
async def health_check() -> dict:
    return success_response(
        {
            "status": "ok",
            "service": settings.app_name,
            "deployment_profile": get_deployment_profile(),
            "deployment": profile_description(),
        }
    )


@app.get("/readyz", response_model=None)
async def readiness_check():
    checks: dict[str, str] = {}
    ok = True
    try:
        await ensure_tenant_directory_initialized()
        checks["database"] = "ok"
    except TenantDirectoryNotInitializedError:
        ok = False
        checks["database"] = "uninitialized"
    except Exception:
        ok = False
        checks["database"] = "error"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        ok = False
        checks["redis"] = "error"

    payload = success_response({"status": "ok" if ok else "error", "checks": checks})
    if ok:
        return payload
    return JSONResponse(status_code=503, content=payload)
