"""导出前裁剪行数据：去掉主键 id、外键 *_id；按配置扁平化嵌套关联为独立列（见 relation_paths）。"""

from __future__ import annotations

from typing import Any

from app.framework.export.relation_paths import ExportRelationPath, flatten_relation_export_values


def prepare_export_row(
    row: dict[str, Any],
    relation_paths: tuple[ExportRelationPath, ...] | None = None,
) -> dict[str, Any]:
    paths = relation_paths or ()
    related_cols = flatten_relation_export_values(row, paths) if paths else {}

    out: dict[str, Any] = {}
    for key, value in row.items():
        if key == "id" or key.endswith("_id"):
            continue
        if isinstance(value, dict):
            continue
        if isinstance(value, list) and value and isinstance(value[0], dict):
            continue
        out[key] = value

    out.update(related_cols)
    return out


def prepare_export_rows(
    rows: list[dict[str, Any]],
    relation_paths: tuple[ExportRelationPath, ...] | None = None,
) -> list[dict[str, Any]]:
    return [prepare_export_row(r, relation_paths) for r in rows]


# 兼容旧名
def sanitize_export_rows(
    rows: list[dict[str, Any]],
    relation_paths: tuple[ExportRelationPath, ...] | None = None,
) -> list[dict[str, Any]]:
    return prepare_export_rows(rows, relation_paths)
