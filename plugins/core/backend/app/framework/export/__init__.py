"""通用导出工具（CSV / Excel 等），供路由与仓储复用"""

from app.framework.export.attachment_headers import binary_attachment_disposition
from app.framework.export.limits import DEFAULT_EXPORT_ROWS, MAX_EXPORT_ROWS
from app.framework.export.csv_builder import (
    CSV_FILENAME_EXTENSION,
    build_csv_attachment,
    csv_content_disposition,
)
from app.framework.export.xlsx_builder import (
    WORKBOOK_FILENAME_EXTENSION,
    XLSX_MEDIA_TYPE,
    build_xlsx_bytes,
)

__all__ = [
    "CSV_FILENAME_EXTENSION",
    "DEFAULT_EXPORT_ROWS",
    "MAX_EXPORT_ROWS",
    "WORKBOOK_FILENAME_EXTENSION",
    "XLSX_MEDIA_TYPE",
    "binary_attachment_disposition",
    "build_csv_attachment",
    "build_xlsx_bytes",
    "csv_content_disposition",
]
