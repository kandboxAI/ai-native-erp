"""文件与附件服务（L1）：所有模块的上传、绑定、下载都经过这里。

- 业务模块用 register_file_scene 登记上传场景（允许的类别、大小上限、数量上限），
  用 register_file_access 登记“谁能看这个业务单据的文件”。
- 上传：申请上传（签发直传 URL）→ 客户端直传 → 完成上传（核对存储中的对象）→ pending。
- 业务提交单据时在自己的事务里 bind / replace；读取单据时 items_for_business 返回带临时签名链接的附件。
- 下载权限跟随业务单据；接口任何时候都不返回上传人。
设计见 docs/foundation-platform/file-attachment-design.md。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.framework.db.ids import uuid7
from app.framework.db.session import get_session_context
from app.framework.files.storage import get_storage

from .models import STATUS_BOUND, STATUS_PENDING, STATUS_UPLOADING, FileAttachment
from . import repository

MB = 1024 * 1024
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
DOCUMENT_TYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}
VIDEO_TYPES = {"video/mp4": "mp4", "video/webm": "webm"}
# 压缩包、设计源文件等：教务侧的作品资料、迎检材料允许上传，统一归入 other 类（dict file_kind）；
# application/octet-stream 兜底，浏览器对未知类型多以此声明。
ARCHIVE_TYPES = {
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/x-rar-compressed": "rar",
    "application/vnd.rar": "rar",
    "application/x-7z-compressed": "7z",
    "application/gzip": "gz",
    "application/x-tar": "tar",
    "image/vnd.adobe.photoshop": "psd",
    "application/postscript": "ai",
    "application/illustrator": "ai",
    "application/octet-stream": "bin",
}
KIND_TYPES = {"image": IMAGE_TYPES, "document": DOCUMENT_TYPES, "video": VIDEO_TYPES, "other": ARCHIVE_TYPES}

# 统一的大小上限（2026-10-11 决定）：照片 2 MB、文档 20 MB、课件 100 MB；场景登记时使用
PHOTO_MAX_BYTES = 2 * MB
DOCUMENT_MAX_BYTES = 20 * MB
COURSEWARE_MAX_BYTES = 100 * MB


@dataclass(frozen=True)
class FileScene:
    code: str
    kinds: frozenset[str]
    max_bytes: int
    max_count: int = 1
    extra_content_types: dict[str, str] = field(default_factory=dict)

    def content_types(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for kind in self.kinds:
            result.update(KIND_TYPES[kind])
        result.update(self.extra_content_types)
        return result


AccessChecker = Callable[[AsyncSession, AuthenticatedUser, UUID], Awaitable[bool]]
_scenes: dict[str, FileScene] = {}
_access: dict[str, AccessChecker] = {}


def register_file_scene(code: str, *, kinds: set[str] | frozenset[str], max_bytes: int, max_count: int = 1,
                        extra_content_types: dict[str, str] | None = None) -> FileScene:
    unknown = set(kinds) - set(KIND_TYPES)
    if unknown:
        raise ValueError(f"未知的文件类别：{sorted(unknown)}")
    scene = FileScene(code=code, kinds=frozenset(kinds), max_bytes=max_bytes, max_count=max_count,
                      extra_content_types=dict(extra_content_types or {}))
    _scenes[code] = scene
    return scene


def register_file_access(business_type_code: str, checker: AccessChecker) -> None:
    _access[business_type_code] = checker


def scene(code: str) -> FileScene:
    found = _scenes.get(code)
    if found is None:
        raise AppException("不支持的上传场景", status_code=422)
    return found


def _kind_of(content_type: str) -> str:
    return next((kind for kind, types in KIND_TYPES.items() if content_type in types), "other")


def _expires_at():
    return local_now() + timedelta(hours=get_settings().attachment_pending_hours)


def file_item(row: FileAttachment) -> dict[str, Any]:
    """对外的附件信息：含临时签名链接，不含上传人与存储键。"""
    settings = get_settings()
    url = get_storage(row.storage_backend).download_url(
        row.storage_key, file_name=row.original_file_name, content_type=row.content_type,
        expires=settings.file_download_url_expires_seconds, image=row.file_kind_code == "image",
    )
    return {
        "id": str(row.id), "file_name": row.original_file_name, "name": row.original_file_name,
        "content_type": row.content_type, "file_kind": row.file_kind_code,
        "file_size": row.file_size, "width": row.width, "height": row.height, "url": url,
    }


class FileService:
    async def read_content(self, session, file_id, *, user):
        """供业务适配器读取已授权原件；复用绑定业务访问检查，不暴露存储键。"""
        row = await repository.file_for_read(session, file_id)
        if row is None or not await self.can_read(session, row, user):
            raise AppException("文件不存在或无权访问", status_code=404)
        content = await get_storage(row.storage_backend).read(row.storage_key, max_bytes=scene(row.scene_code).max_bytes)
        return row, content

    async def processing_url(self, session, file_id, *, org_id, scene_code, business_type_code, business_id):
        """所属模块鉴权后，为外部处理任务签发两小时原件链接；不接收任意 URL。"""
        row = await repository.upload_for_ingest(session, file_id)
        if (row is None or row.status_code != STATUS_BOUND or row.org_id != org_id
                or row.scene_code != scene_code or row.business_type_code != business_type_code
                or row.business_id != business_id):
            raise AppException("文件不属于当前业务对象", status_code=409)
        if row.storage_backend == "local":
            raise AppException("云转写需要配置 OSS，当前录音已保存到本地", status_code=503)
        return get_storage(row.storage_backend).download_url(
            row.storage_key, file_name=row.original_file_name, content_type=row.content_type,
            expires=7200, image=False,
        )

    async def latest_for_business(self, session, business_type_code, business_id, *, scene_code):
        """所属模块完成对象鉴权后，读取指定场景最近一次提交的绑定版本。"""
        return await repository.latest_bound_for_business(session, business_type_code, business_id, scene_code)

    async def latest_for_businesses(self, session, business_type_code, business_ids, *, scene_code):
        """批量读取调用方已授权的业务对象各自最新的绑定文件。"""
        return await repository.latest_bound_for_businesses(session, business_type_code, business_ids, scene_code)

    async def read_bound_for_ingest(self, session, file_id, *, org_id, scene_code, business_type_code, business_id):
        """业务后台只可读取已绑定到该业务对象的原件，不提供任意存储路径读取。"""
        row = await repository.upload_for_ingest(session, file_id)
        if (row is None or row.status_code != STATUS_BOUND or row.org_id != org_id or row.scene_code != scene_code
                or row.business_type_code != business_type_code or row.business_id != business_id):
            raise AppException("原件绑定与当前业务版本不一致", status_code=409)
        return row, await self._ingest_content(row, scene_code)

    async def _ingest_content(self, row, scene_code):
        target_scene = scene(scene_code)
        if row.content_type not in target_scene.content_types() or not 0 < row.file_size <= target_scene.max_bytes:
            raise AppException("文件类型或大小不符合当前场景", status_code=422)
        content = await get_storage(row.storage_backend).read(row.storage_key, max_bytes=target_scene.max_bytes)
        if len(content) != row.file_size or base64.b64encode(hashlib.md5(content).digest()).decode() != row.content_md5:
            raise AppException("原件已变化，请重新上传", status_code=409)
        return content

    async def read_pending_for_ingest(self, session, file_id, *, user, org_id, scene_code):
        """仅在所属业务的事务中读取当前用户、组织及场景内已核验的待绑定原件。"""
        row = await repository.upload_for_ingest(session, file_id)
        if (row is None or row.status_code != STATUS_PENDING or row.uploader_user_id != user.user_id
                or row.org_id != org_id or row.scene_code != scene_code or row.expires_at < local_now()):
            raise AppException("文件未就绪、已使用或不属于当前用户和组织", status_code=422)
        return row, await self._ingest_content(row, scene_code)

    # ───────── 上传 ─────────
    async def create_upload_ticket(
        self, *, scene_code: str, file_name: str, content_type: str, file_size: int, content_md5: str, user: AuthenticatedUser,
    ) -> dict[str, Any]:
        if user.org_id is None:
            raise AppException("当前账号未关联组织", status_code=403)
        target_scene = scene(scene_code)
        allowed = target_scene.content_types()
        if content_type not in allowed:
            raise AppException("不支持的文件类型", status_code=422)
        if file_size <= 0 or file_size > target_scene.max_bytes:
            raise AppException(f"文件不能超过 {target_scene.max_bytes // MB} MB", status_code=413)
        try:
            if len(base64.b64decode(content_md5, validate=True)) != 16:
                raise ValueError
        except (binascii.Error, ValueError):
            raise AppException("Content-MD5 无效", status_code=422) from None
        await self.cleanup_expired()
        storage = get_storage()
        now = local_now()
        file_id = uuid7()
        extension = allowed[content_type]
        safe_name = Path(file_name or f"file.{extension}").name[:255]
        key = f"{user.tenant_schema}/{scene_code}/{now:%Y/%m}/{file_id}.{extension}"
        row = FileAttachment(
            id=file_id, org_id=user.org_id, uploader_user_id=user.user_id, storage_backend=storage.name, storage_key=key,
            original_file_name=safe_name, extension=extension, content_type=content_type, file_kind_code=_kind_of(content_type),
            file_size=file_size, content_md5=content_md5, status_code=STATUS_UPLOADING, scene_code=scene_code,
            expires_at=_expires_at(), created_by=user.user_id, updated_by=user.user_id,
        )
        async with get_session_context() as session:
            session.add(row)
            await session.commit()
        expires = get_settings().file_upload_url_expires_seconds
        target = storage.upload_target(key, content_type=content_type, content_md5=content_md5, expires=expires)
        return {"id": str(file_id), "upload": {"method": target.method, "url": target.url, "headers": target.headers}, "expires_in": expires}

    async def upload_bytes(
        self, *, scene_code: str, file_name: str, content_type: str, content: bytes, user: AuthenticatedUser,
    ) -> dict[str, Any]:
        """服务端上传（演示数据、种子脚本、测试用）：与客户端直传走同一流程（申请 → 写入存储 → 完成）。"""
        content_md5 = base64.b64encode(hashlib.md5(content).digest()).decode()
        ticket = await self.create_upload_ticket(scene_code=scene_code, file_name=file_name, content_type=content_type,
                                                 file_size=len(content), content_md5=content_md5, user=user)
        async with get_session_context() as session:
            row = await session.get(FileAttachment, UUID(ticket["id"]))
            backend, key = row.storage_backend, row.storage_key
        await get_storage(backend).put(key, content, content_type=content_type, content_md5=content_md5)
        return await self.complete_upload(UUID(ticket["id"]), user)

    async def complete_upload(self, file_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await session.get(FileAttachment, file_id, with_for_update=True)
            if row is None or row.uploader_user_id != user.user_id:
                raise AppException("文件不存在", status_code=404)
            if row.status_code != STATUS_UPLOADING:
                return file_item(row)
            storage = get_storage(row.storage_backend)
            is_image = row.file_kind_code == "image"
            info = await storage.stat(row.storage_key, image=is_image)
            problem = None
            if info is None:
                problem = "文件尚未上传完成"
            elif info.size != row.file_size or info.size > scene(row.scene_code).max_bytes:
                problem = "文件大小与申请不符"
            elif info.content_type and info.content_type != row.content_type:
                problem = "文件类型与申请不符"
            elif is_image and (info.width is None or info.height is None):
                problem = info.image_error or "不是有效的图片"
            if problem is not None:
                if info is not None:
                    await storage.delete(row.storage_key)
                await session.delete(row)
                await session.commit()
                raise AppException(problem, status_code=422)
            row.width, row.height = (info.width, info.height) if is_image else (None, None)
            row.status_code = STATUS_PENDING
            row.updated_by = user.user_id
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return file_item(row)

    async def discard(self, file_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await session.get(FileAttachment, file_id, with_for_update=True)
            if row is None:
                return {"id": str(file_id), "deleted": True}
            if row.uploader_user_id != user.user_id or row.status_code == STATUS_BOUND:
                raise AppException("文件已被使用或无权删除", status_code=409)
            backend, key = row.storage_backend, row.storage_key
            await session.delete(row)
            await session.commit()
        await get_storage(backend).delete(key)
        return {"id": str(file_id), "deleted": True}

    async def cleanup_expired(self) -> int:
        async with get_session_context() as session:
            rows = (await session.exec(select(FileAttachment).where(
                FileAttachment.status_code.in_([STATUS_UPLOADING, STATUS_PENDING]), FileAttachment.expires_at < local_now(),
            ).limit(100))).all()
            targets = [(row.storage_backend, row.storage_key) for row in rows]
            for row in rows:
                await session.delete(row)
            if rows:
                await session.commit()
        for backend, key in targets:
            await get_storage(backend).delete(key)
        return len(targets)

    # ───────── 下载 ─────────
    async def download_url(self, file_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await session.get(FileAttachment, file_id)
            if row is None or not await self.can_read(session, row, user):
                raise AppException("文件不存在或无权访问", status_code=404)
            return file_item(row)

    async def can_read(self, session: AsyncSession, row: FileAttachment, user: AuthenticatedUser) -> bool:
        if row.status_code != STATUS_BOUND:
            return row.uploader_user_id == user.user_id
        checker = _access.get(row.business_type_code or "")
        return checker is not None and row.business_id is not None and bool(await checker(session, user, row.business_id))

    # ───────── 业务绑定（在业务事务中调用，不提交） ─────────
    async def bind(
        self, session: AsyncSession, file_ids: list[UUID], *, user: AuthenticatedUser, org_id: UUID, scene_code: str,
        business_type_code: str, business_id: UUID, business_sub_id: UUID | None = None, start_sort: int = 0,
    ) -> list[FileAttachment]:
        unique_ids = list(dict.fromkeys(file_ids))
        if len(unique_ids) != len(file_ids):
            raise AppException("文件不能重复提交", status_code=422)
        if not unique_ids:
            return []
        if start_sort + len(unique_ids) > scene(scene_code).max_count:
            raise AppException(f"最多上传 {scene(scene_code).max_count} 个文件", status_code=422)
        rows = (await session.exec(select(FileAttachment).where(FileAttachment.id.in_(unique_ids)).with_for_update())).all()
        by_id = {row.id: row for row in rows}
        now = local_now()
        ordered: list[FileAttachment] = []
        for offset, file_id in enumerate(unique_ids):
            row = by_id.get(file_id)
            if (row is None or row.status_code != STATUS_PENDING or row.uploader_user_id != user.user_id
                    or row.scene_code != scene_code or row.expires_at < now):
                raise AppException("文件不存在、未上传完成、已过期、已被使用或不属于当前用户", status_code=422)
            row.org_id = org_id
            row.status_code = STATUS_BOUND
            row.business_type_code = business_type_code
            row.business_id = business_id
            row.business_sub_id = business_sub_id
            row.sort_no = start_sort + offset
            row.bound_at = now
            row.updated_by = user.user_id
            session.add(row)
            ordered.append(row)
        return ordered

    async def replace(
        self, session: AsyncSession, file_ids: list[UUID], *, user: AuthenticatedUser, org_id: UUID, scene_code: str,
        business_type_code: str, business_id: UUID, business_sub_id: UUID | None = None,
    ) -> list[FileAttachment]:
        """编辑单据时替换附件：已绑定的保留，新上传的绑定，被移除的删除。"""
        current = await self.list_for_business(session, business_type_code, [business_id], scene_code=scene_code)
        current_ids = {row.id for row in current}
        wanted = list(dict.fromkeys(file_ids))
        if len(wanted) > scene(scene_code).max_count:
            raise AppException(f"最多上传 {scene(scene_code).max_count} 个文件", status_code=422)
        removed = [row for row in current if row.id not in set(wanted)]
        for row in removed:
            await self.delete_row(session, row)
        new_ids = [file_id for file_id in wanted if file_id not in current_ids]
        await self.bind(session, new_ids, user=user, org_id=org_id, scene_code=scene_code, business_type_code=business_type_code,
                        business_id=business_id, business_sub_id=business_sub_id, start_sort=0) if new_ids else None
        position = {file_id: index for index, file_id in enumerate(wanted)}
        rows = await self.list_for_business(session, business_type_code, [business_id], scene_code=scene_code)
        for row in rows:
            row.sort_no = position.get(row.id, row.sort_no)
            session.add(row)
        return sorted(rows, key=lambda row: row.sort_no)

    async def list_for_business(
        self, session: AsyncSession, business_type_code: str, business_ids: list[UUID], *, scene_code: str | None = None,
    ) -> list[FileAttachment]:
        if not business_ids:
            return []
        statement = select(FileAttachment).where(
            FileAttachment.business_type_code == business_type_code, FileAttachment.business_id.in_(business_ids),
            FileAttachment.status_code == STATUS_BOUND,
        )
        if scene_code is not None:
            statement = statement.where(FileAttachment.scene_code == scene_code)
        return list((await session.exec(statement.order_by(FileAttachment.sort_no, FileAttachment.created_at))).all())

    async def items_for_business(
        self, session: AsyncSession, business_type_code: str, business_ids: list[UUID], *, scene_code: str | None = None,
    ) -> dict[UUID, list[dict[str, Any]]]:
        """按业务单据分组的附件信息（含临时签名链接）；调用方已确认用户能看这些单据。"""
        grouped: dict[UUID, list[dict[str, Any]]] = {business_id: [] for business_id in business_ids}
        for row in await self.list_for_business(session, business_type_code, business_ids, scene_code=scene_code):
            grouped.setdefault(row.business_id, []).append(file_item(row))
        return grouped

    async def count_for_business(self, session: AsyncSession, business_type_code: str, business_ids: list[UUID]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {business_id: 0 for business_id in business_ids}
        for row in await self.list_for_business(session, business_type_code, business_ids):
            counts[row.business_id] = counts.get(row.business_id, 0) + 1
        return counts

    async def delete_for_business(self, session: AsyncSession, business_type_code: str, business_id: UUID) -> None:
        for row in await self.list_for_business(session, business_type_code, [business_id]):
            await self.delete_row(session, row)

    async def delete_row(self, session: AsyncSession, row: FileAttachment) -> None:
        await get_storage(row.storage_backend).delete(row.storage_key)
        await session.delete(row)


service = FileService()

__all__ = [
    "COURSEWARE_MAX_BYTES", "DOCUMENT_MAX_BYTES", "FileScene", "FileService", "PHOTO_MAX_BYTES",
    "file_item", "register_file_access", "register_file_scene", "scene", "service",
]
