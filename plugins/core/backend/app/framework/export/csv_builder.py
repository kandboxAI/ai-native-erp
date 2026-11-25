"""将 JSON 友好的行数据序列化为 CSV（Excel 可识别 UTF-8 BOM）。"""

import csv
import io
from pathlib import PurePath
from typing import Any
from urllib.parse import quote

from app.framework.export.value_format import export_cell_display

CSV_FILENAME_EXTENSION = ".csv"

def build_csv_attachment(rows: list[dict[str, Any]]) -> bytes:
    """表头为第一行中出现的全部键的稳定排序；若无数据则为空 BOM 文件。"""
    if not rows:
        return "\ufeff".encode("utf-8")

    fieldnames = sorted({key for row in rows for key in row.keys()})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({name: export_cell_display(row.get(name)) for name in fieldnames})
    raw = buffer.getvalue()
    return ("\ufeff" + raw).encode("utf-8")


def _ascii_fallback_filename(part: str) -> str:
    safe = "".join(c if c.isascii() and c not in '\\/:*?"<>|' else "_" for c in part) or "export"
    return f"{safe}{CSV_FILENAME_EXTENSION}"


def csv_content_disposition(download_name: str) -> str:
    """RFC 5987：同时给出 ASCII fallback 与 UTF-8 filename*。"""
    path = PurePath(download_name)
    suffix = path.suffix or CSV_FILENAME_EXTENSION
    stem = path.stem if path.suffix else str(path)

    ascii_name = _ascii_fallback_filename(stem)
    quoted = quote(f"{stem}{suffix}", safe="")

    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
