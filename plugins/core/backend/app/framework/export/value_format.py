"""列表/导出共用的单元格展示格式（CSV 与 Excel 文本列一致）。"""

import json
from typing import Any


def export_cell_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)
