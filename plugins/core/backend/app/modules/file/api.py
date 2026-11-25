"""文件接口：申请上传、完成上传、删除未使用的文件、获取下载链接；本地存储的签名上传与下载（仅开发环境）。

下载权限跟随业务单据（file service 的访问登记）；响应中不含上传人。
"""

from __future__ import annotations

import base64
import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.framework.files.storage import LocalStorage, get_storage, verify_local_token

from .service import service

router = APIRouter(prefix="/api/files", tags=["files"])


class UploadTicketRequest(BaseModel):
    scene: str = Field(..., min_length=1, max_length=64)
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=128)
    file_size: int = Field(..., gt=0)
    content_md5: str = Field(..., min_length=22, max_length=32, description="文件内容 MD5 的 Base64 编码，上传时作为 Content-MD5 请求头")


@router.post("/upload-tickets")
async def create_upload_ticket(payload: UploadTicketRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.create_upload_ticket(
        scene_code=payload.scene, file_name=payload.file_name, content_type=payload.content_type,
        file_size=payload.file_size, content_md5=payload.content_md5, user=user,
    ))


@router.post("/{file_id}/complete")
async def complete_upload(file_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.complete_upload(file_id, user))


@router.delete("/{file_id}")
async def discard(file_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.discard(file_id, user))


@router.get("/{file_id}/url")
async def download_url(file_id: UUID, user: AuthenticatedUser = Depends(get_current_user)):
    return success_response(await service.download_url(file_id, user))


def _local() -> LocalStorage:
    storage = get_storage("local")
    if not isinstance(storage, LocalStorage):
        raise AppException("本地存储不可用", status_code=404)
    return storage


@router.put("/local/{token}")
async def local_upload(token: str, request: Request):
    """本地存储的直传地址（与 OSS 签名 PUT 等价）：校验签名、内容类型与 Content-MD5 后写入。"""
    claims = verify_local_token(token, action="put")
    content = await request.body()
    if request.headers.get("content-type", "").split(";")[0].strip() != claims["ct"]:
        raise AppException("内容类型与签名不符", status_code=403)
    if base64.b64encode(hashlib.md5(content).digest()).decode() != claims["md5"] or request.headers.get("content-md5") != claims["md5"]:
        raise AppException("Content-MD5 校验失败", status_code=400)
    _local().write(claims["key"], content)
    return Response(status_code=200)


@router.get("/local/{token}")
async def local_download(token: str):
    """本地存储的签名下载地址（与 OSS 签名 GET 等价）。"""
    claims = verify_local_token(token, action="get")
    path = _local().path(claims["key"])
    if not path.is_file():
        raise AppException("文件不存在", status_code=404)
    return FileResponse(path, media_type=claims["ct"], filename=claims["name"], content_disposition_type="inline")
