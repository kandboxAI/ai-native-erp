"""文件存储适配层：客户端直传对象存储，后端签发 URL、核对结果并按限额读取业务导入原件。

业务模块与 file_attachment 不感知具体存储。两种实现使用同一套协议：
- OssStorage：阿里云 OSS 私有 bucket，签名 PUT 上传、签名 GET 下载、HEAD 与图片信息接口核对；
- LocalStorage：仅开发环境；签发指向后端 /api/files/local/{token} 的一次性签名地址，文件写在本地目录。
file_storage_backend = auto 时，配好 OSS 用 OSS，否则用本地存储。
设计见 docs/foundation-platform/file-attachment-design.md §2.5。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.core.config import get_settings
from app.core.exceptions import AppException

# 图片下载时由 OSS 重新编码输出，确保返回给查看者的图片不带原始 EXIF（含拍摄位置）
OSS_IMAGE_PROCESS = "image/auto-orient,1/format,jpg/quality,q_90"
LOCAL_UPLOAD_PATH = "/api/files/local"


@dataclass(frozen=True)
class UploadTarget:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str | None
    width: int | None = None
    height: int | None = None
    image_error: str | None = None


class StorageBackend(Protocol):
    name: str

    def upload_target(self, key: str, *, content_type: str, content_md5: str, expires: int) -> UploadTarget: ...

    async def stat(self, key: str, *, image: bool) -> ObjectInfo | None: ...

    def download_url(self, key: str, *, file_name: str, content_type: str, expires: int, image: bool) -> str: ...

    async def delete(self, key: str) -> None: ...

    async def put(self, key: str, content: bytes, *, content_type: str, content_md5: str) -> None: ...

    async def read(self, key: str, *, max_bytes: int) -> bytes: ...


@dataclass(frozen=True)
class ImageInspection:
    width: int | None = None
    height: int | None = None
    error: str | None = None


def _inspect_image(content: bytes) -> ImageInspection:
    """区分像素、真实格式、帧数及编码错误，避免都误报为无效图片。"""
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        with Image.open(BytesIO(content)) as probe:
            actual_format = (probe.format or "").upper()
            # 相机 JPG 可用 MPF 封装主 JPEG 与辅助图；浏览器按主图展示。
            # MPO 不是 GIF/APNG 一类的播放动画，不应因辅助帧而拒绝合法 JPG。
            if actual_format not in {"JPEG", "PNG", "WEBP", "MPO"}:
                return ImageInspection(error=f"图片实际格式为 {actual_format or '未知'}，请重新导出为 JPG、PNG 或 WebP 后上传")
            if actual_format != "MPO" and getattr(probe, "n_frames", 1) != 1:
                return ImageInspection(error="当前仅支持单帧静态图片，请导出为普通 JPG、PNG 或 WebP 后上传")
            if actual_format == "MPO":
                probe.seek(0)
            probe.verify()
        with Image.open(BytesIO(content)) as source:
            source.seek(0)
            return ImageInspection(width=source.width, height=source.height)
    except Image.DecompressionBombError:
        return ImageInspection(error="图片像素超过服务端上限（8000万像素），请缩小分辨率后上传")
    except UnidentifiedImageError:
        return ImageInspection(error="无法识别图片内容，请重新导出为 JPG、PNG 或 WebP 后上传")
    except (OSError, SyntaxError, ValueError):
        return ImageInspection(error="图片文件不完整或编码异常，请重新导出后上传")


def _image_size(content: bytes) -> tuple[int, int] | None:
    info = _inspect_image(content)
    return (info.width, info.height) if info.width is not None and info.height is not None else None


# ───────── 本地存储（开发环境） ─────────

def _sign(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
    digest = hmac.new(get_settings().jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{digest}"


def verify_local_token(token: str, *, action: str) -> dict:
    try:
        raw, digest = token.rsplit(".", 1)
        expected = hmac.new(get_settings().jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(digest, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, json.JSONDecodeError):
        raise AppException("签名无效", status_code=403) from None
    if payload.get("act") != action or payload.get("exp", 0) < time.time():
        raise AppException("签名已过期或用途不符", status_code=403)
    return payload


class LocalStorage:
    name = "local"

    def root(self) -> Path:
        configured = Path(get_settings().attachment_storage_dir)
        root = configured if configured.is_absolute() else Path(__file__).resolve().parents[3] / configured
        return root.resolve()

    def path(self, key: str) -> Path:
        root = self.root()
        target = (root / key).resolve()
        if target == root or root not in target.parents:
            raise AppException("非法存储路径", status_code=500)
        return target

    def upload_target(self, key: str, *, content_type: str, content_md5: str, expires: int) -> UploadTarget:
        token = _sign({"act": "put", "key": key, "ct": content_type, "md5": content_md5, "exp": int(time.time()) + expires})
        return UploadTarget("PUT", f"{LOCAL_UPLOAD_PATH}/{token}", {"Content-Type": content_type, "Content-MD5": content_md5})

    def write(self, key: str, content: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".uploading")
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    async def stat(self, key: str, *, image: bool) -> ObjectInfo | None:
        target = self.path(key)
        if not target.is_file():
            return None
        size = target.stat().st_size
        if not image:
            return ObjectInfo(size=size, content_type=None)
        info = await asyncio.to_thread(_inspect_image, target.read_bytes())
        return ObjectInfo(size=size, content_type=None, width=info.width, height=info.height, image_error=info.error)

    def download_url(self, key: str, *, file_name: str, content_type: str, expires: int, image: bool) -> str:
        token = _sign({"act": "get", "key": key, "ct": content_type, "name": file_name, "exp": int(time.time()) + expires})
        return f"{LOCAL_UPLOAD_PATH}/{token}"

    async def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    async def put(self, key: str, content: bytes, *, content_type: str, content_md5: str) -> None:
        self.write(key, content)

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        target = self.path(key)
        if not target.is_file():
            raise AppException("文件不存在", status_code=404)

        def read_bounded():
            with target.open("rb") as source:
                content = source.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise AppException("文件超过允许的处理大小", status_code=413)
            return content

        return await asyncio.to_thread(read_bounded)


# ───────── 阿里云 OSS ─────────

class OssStorage:
    name = "oss"

    def __init__(self) -> None:
        import oss2

        settings = get_settings()
        endpoint = settings.oss_endpoint or f"https://oss-{settings.oss_region}.aliyuncs.com"
        self._bucket = oss2.Bucket(oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret), endpoint, settings.oss_bucket_files)

    def upload_target(self, key: str, *, content_type: str, content_md5: str, expires: int) -> UploadTarget:
        headers = {"Content-Type": content_type, "Content-MD5": content_md5}
        url = self._bucket.sign_url("PUT", key, expires, headers=headers, slash_safe=True)
        return UploadTarget("PUT", url, headers)

    async def stat(self, key: str, *, image: bool) -> ObjectInfo | None:
        import oss2

        try:
            head = await asyncio.to_thread(self._bucket.head_object, key)
        except oss2.exceptions.NotFound:
            return None
        width = height = None
        if image:
            try:
                result = await asyncio.to_thread(self._bucket.get_object, key, process="image/info")
                info = json.loads(result.read())
                width, height = int(info["ImageWidth"]["value"]), int(info["ImageHeight"]["value"])
            except (oss2.exceptions.OssError, KeyError, ValueError):
                pass
        return ObjectInfo(size=head.content_length, content_type=head.content_type, width=width, height=height)

    def download_url(self, key: str, *, file_name: str, content_type: str, expires: int, image: bool) -> str:
        params = {"response-content-disposition": f"inline; filename*=UTF-8''{quote(file_name)}"}
        if image:
            params["x-oss-process"] = OSS_IMAGE_PROCESS
        return self._bucket.sign_url("GET", key, expires, params=params, slash_safe=True)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._bucket.delete_object, key)

    async def put(self, key: str, content: bytes, *, content_type: str, content_md5: str) -> None:
        await asyncio.to_thread(self._bucket.put_object, key, content, headers={"Content-Type": content_type, "Content-MD5": content_md5})

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        import oss2

        def read_bounded():
            try:
                source = self._bucket.get_object(key)
            except oss2.exceptions.NoSuchKey:
                raise AppException("文件不存在", status_code=404) from None
            try:
                content = source.read(max_bytes + 1)
            finally:
                source.close()
            if len(content) > max_bytes:
                raise AppException("文件超过允许的处理大小", status_code=413)
            return content

        return await asyncio.to_thread(read_bounded)


def oss_configured() -> bool:
    settings = get_settings()
    return bool(settings.oss_access_key_id and settings.oss_access_key_secret and (settings.oss_endpoint or settings.oss_region))


@lru_cache
def _backends() -> dict[str, StorageBackend]:
    return {}


def get_storage(name: str | None = None) -> StorageBackend:
    """name 为附件记录上的 storage_backend；不传时按配置选择新文件使用的存储。"""
    if name is None:
        configured = get_settings().file_storage_backend
        name = ("oss" if oss_configured() else "local") if configured == "auto" else configured
    backends = _backends()
    if name not in backends:
        if name == "oss":
            if not oss_configured():
                raise AppException("对象存储未配置", status_code=500)
            backends[name] = OssStorage()
        elif name == "local":
            backends[name] = LocalStorage()
        else:
            raise AppException("不支持的存储类型", status_code=500)
    return backends[name]


__all__ = [
    "LocalStorage", "ObjectInfo", "OssStorage", "StorageBackend", "UploadTarget", "get_storage", "oss_configured", "verify_local_token",
]
