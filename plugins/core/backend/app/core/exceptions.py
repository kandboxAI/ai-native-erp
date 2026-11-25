from typing import Any
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _json_safe_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 Pydantic 错误中的 bytes、UUID、ValueError 等递归转为 JSON 安全值。"""

    def normalize(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace")[:500]
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [normalize(item) for item in value]
        return str(value)

    return [normalize(item) for item in errors]


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/json; charset=utf-8",
        content={
            "code": exc.status_code,
            "message": exc.message,
            "data": {},
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = _json_safe_validation_errors(exc.errors())
    from app.core.validation import format_validation_errors
    message = format_validation_errors(errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "message": message,
            "data": errors,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception path=%s method=%s", request.url.path, request.method)
    settings = get_settings()
    if settings.debug or settings.app_env == "development":
        message = _friendly_unhandled_message(exc)
    else:
        message = "服务器内部错误"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": message,
            "data": {},
        },
    )


def _friendly_unhandled_message(exc: Exception) -> str:
    """开发环境也避免把整段 SQLAlchemy 堆栈直接甩给前端。"""
    text = str(exc).strip() or exc.__class__.__name__
    lower = text.lower()
    if (
        "uniqueviolation" in lower
        or "duplicate key" in lower
        or "unique constraint" in lower
    ):
        if "email" in lower or "users_email" in lower:
            return "该手机号对应的登录账号已存在，无法重复生成"
        return "数据已存在，无法重复创建"
    if "asyncpg" in lower or "sqlalchemy" in lower or "[sql:" in lower:
        # 只保留首行，避免整段 SQL 刷屏
        first = next((line.strip() for line in text.splitlines() if line.strip()), text)
        if len(first) > 180:
            return f"{first[:180]}…"
        return first
    if len(text) > 300:
        return f"{text[:300]}…"
    return text


# 数据库约束 → 业务提示（约束名按规范命名：uk_ 唯一、fk_ 外键、ex_ 排除、ck_ 检查）
_SQLSTATE_MESSAGES = {
    "23505": (status.HTTP_409_CONFLICT, "数据重复：{detail}"),
    "23503": (status.HTTP_400_BAD_REQUEST, "引用的数据不存在或仍被引用：{detail}"),
    "23P01": (status.HTTP_409_CONFLICT, "有效期与已有记录重叠：{detail}"),
    "23514": (status.HTTP_400_BAD_REQUEST, "数据不符合规则：{detail}"),
    "23502": (status.HTTP_400_BAD_REQUEST, "缺少必填字段：{detail}"),
}


async def integrity_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(getattr(original, "__cause__", None), "sqlstate", None)
    cause = getattr(original, "__cause__", None) or original
    detail = getattr(cause, "constraint_name", None) or getattr(cause, "column_name", None) or ""
    status_code, template = _SQLSTATE_MESSAGES.get(sqlstate, (status.HTTP_400_BAD_REQUEST, "数据不符合约束：{detail}"))
    return JSONResponse(
        status_code=status_code,
        media_type="application/json; charset=utf-8",
        content={"code": status_code, "message": template.format(detail=detail).rstrip("："), "data": {}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    from sqlalchemy.exc import IntegrityError

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
