"""从 SQLModel/SQLAlchemy 表的列 ``comment`` 生成导出 Excel 列头；可被路由传入的覆盖字典覆盖。"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.framework.export.relation_paths import ExportRelationPath


def labels_from_sqlmodel_table(table_model: type[Any] | None) -> dict[str, str]:
    if table_model is None:
        return {}
    table = getattr(table_model, "__table__", None)
    if table is None:
        return {}

    labels: dict[str, str] = {}
    for col in table.columns:
        key = str(col.key)
        cmt = getattr(col, "comment", None)
        if isinstance(cmt, str) and cmt.strip():
            labels[key] = cmt.strip()
    return labels


def build_export_header_map(
    *,
    table_model: type[Any] | None,
    overrides: dict[str, str] | None = None,
    relation_paths: "tuple[ExportRelationPath, ...] | None" = None,
) -> dict[str, str]:
    from app.framework.export.relation_paths import labels_from_relation_paths

    merged = labels_from_sqlmodel_table(table_model)
    if relation_paths:
        merged.update(labels_from_relation_paths(relation_paths))
    if overrides:
        merged.update(overrides)
    return merged


def export_column_header(field_key: str, header_lookup: dict[str, str] | None) -> str:
    if header_lookup:
        lab = header_lookup.get(field_key)
        if isinstance(lab, str) and lab.strip():
            return lab.strip()
    return field_key
