"""关联字段拍平配置，供 ``GET /api/{module}/export`` 使用。

与 :class:`app.framework.crud.repository.SqlModelCrudRepository` / :class:`OrmRelationshipCrudRepository` 配套：

- **无** ``export_relation_paths``：仅主表标量列（外键列在导出前会被去掉）。
- **有** ``export_relation_paths``：从 ``export_row_model`` / ``list_item_model`` 的嵌套 ``model_dump`` 中取关联属性，
  追加为宽表列；需保证导出查询已 ``selectinload``（见仓储 ``list_load_options`` 或 ``export_load_options``）。

- ``nav_path``：嵌套 dict 路径片段，如 ``("organization",)``、`("room", "building")`。
- ``columns``：末端对象上 ``source_key → export_key``，支持多列。
- ``label_table``：表头取该表列 ``comment``。

单字段糖：:meth:`ExportRelationPath.single`。

示例：``app.business.bed.repository.BedRepository``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExportRelationColumn:
    """从 nav_path 末端关联对象的 dict 上取 ``source_key``，映射到导出行的 ``export_key``。"""

    source_key: str
    export_key: str


@dataclass(frozen=True, slots=True)
class ExportRelationPath:
    nav_path: tuple[str, ...]
    """从行根字典走到目标关联对象的路径片段。"""

    label_table: type[Any]
    """取列 comment 的 SQLModel 表类（与各 source_key 对应列在同一逻辑表上）。"""

    columns: tuple[ExportRelationColumn, ...]
    """同一关联节点上要展开的若干字段。"""

    @classmethod
    def single(
        cls,
        *,
        export_key: str,
        nav_path: tuple[str, ...],
        label_table: type[Any],
        source_key: str,
    ) -> ExportRelationPath:
        """常用写法：每条路径只导出关联表的一个字段（等价于原先的 label_column）。"""
        return cls(
            nav_path=nav_path,
            label_table=label_table,
            columns=(ExportRelationColumn(source_key=source_key, export_key=export_key),),
        )


def navigate_json_dict(row: dict[str, Any], nav_path: tuple[str, ...]) -> dict[str, Any] | None:
    cur: Any = row
    for segment in nav_path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(segment)
        if cur is None:
            return None
    return cur if isinstance(cur, dict) else None


def flatten_relation_export_values(row: dict[str, Any], paths: tuple[ExportRelationPath, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in paths:
        target = navigate_json_dict(row, spec.nav_path)
        if target is None:
            continue
        for col in spec.columns:
            val = target.get(col.source_key)
            if val is not None:
                out[col.export_key] = val
    return out


def labels_from_relation_paths(paths: tuple[ExportRelationPath, ...]) -> dict[str, str]:
    """根据关联表的列注释生成导出表头。"""
    out: dict[str, str] = {}
    for spec in paths:
        for col in spec.columns:
            tbl_col = spec.label_table.__table__.columns.get(col.source_key)
            cmt = getattr(tbl_col, "comment", None) if tbl_col is not None else None
            if isinstance(cmt, str) and cmt.strip():
                out[col.export_key] = cmt.strip()
            else:
                out[col.export_key] = col.export_key
    return out
