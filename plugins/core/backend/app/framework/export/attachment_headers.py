"""下载附件的 RFC 5987 Content-Disposition 头构造。"""

from pathlib import PurePath
from urllib.parse import quote


def ascii_fallback_attachment_filename(download_stem: str, extension_with_dot: str) -> str:
    safe = (
        "".join(c if c.isascii() and c not in '\\/:*?"<>|' else "_" for c in download_stem) or "export"
    )
    return f"{safe}{extension_with_dot}"


def binary_attachment_disposition(download_name: str, default_extension_with_dot: str) -> str:
    """给定完整文件名（可含路径分隔符仅存 stem）；同时给出 ASCII fallback 与 UTF-8 filename*。"""
    path = PurePath(download_name)
    suffix = path.suffix or default_extension_with_dot
    stem = path.stem if path.suffix else str(path)
    ascii_name = ascii_fallback_attachment_filename(stem, suffix)
    full_name = f"{stem}{suffix}"
    quoted = quote(full_name, safe="")

    # Starlette 要求非 ASCII 使用 filename*=UTF-8''…
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
