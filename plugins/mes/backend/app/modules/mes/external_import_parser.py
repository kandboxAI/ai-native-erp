"""跟单宝四表只读解析；严格匹配、按来源顺序保留，不执行 Excel 内容。"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

FILES = {"route_step": "工艺路线__*.xlsx", "production_order": "生产工单__*.xlsx",
         "work_order": "生产工单货品__*.xlsx", "stock_balance": "实时库存__*.xlsx"}
REQUIRED = {
    "route_step": {"工艺路线名称", "工艺", "加工类型", "标准工时", "标准工时单位"},
    "production_order": {"工单号", "项目名称", "货品款数", "工单状态"},
    "work_order": {"工单号", "货品编码", "货品名称", "数量", "单位", "货品状态", "工艺路线"},
    "stock_balance": {"货品编码", "货品名称", "规格型号", "单位", "实际库存", "占用数", "可用数"},
}
UNITS = {"pcs": "piece", "piece": "piece", "件": "piece", "支": "branch"}
PROCESSING_TYPES = {"自制": "in_house", "委外": "outsourced", "采购": "purchased"}
TASK_STATES = {"待生产": "pending", "生产中": "in_progress", "已完工": "completed", "已暂停": "paused"}


def text(value):
    return "" if value is None else str(value).strip()


def number(value, *, default=None):
    if value in (None, ""):
        return default
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise ValueError(f"不是有效数值：{value!r}") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"数值须为非负有限值：{value!r}")
    return result


def timestamp(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    else:
        result = datetime.fromisoformat(str(value).strip())
    return result.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if result.tzinfo is None else result


def standard_minutes(row):
    value = number(row.get("标准工时"))
    if not value:
        return None
    factor = {"分": Decimal(1), "分钟": Decimal(1), "小时": Decimal(60), "天": Decimal(1440)}.get(text(row.get("标准工时单位")))
    if factor is None:
        raise ValueError("不支持的标准工时单位")
    minutes = (value * factor).quantize(Decimal("0.001"))
    if minutes <= 0 or minutes > 5256000:
        raise ValueError("单件工时精度或范围超出当前配置上限")
    return minutes


def route_steps(value):
    if not text(value):
        return []
    result = []
    for segment in str(value).split(">>"):
        match = re.fullmatch(r"\s*(.+?)【([^】]+)】\s*", segment)
        if not match or match[2] not in TASK_STATES:
            raise ValueError(f"工序状态格式不明确：{segment}")
        result.append((match[1].strip(), TASK_STATES[match[2]]))
    return result


def digest(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class SourceRow:
    kind: str
    key: str
    file_name: str
    file_hash: str
    sheet: str
    line: int
    values: dict

    @property
    def row_hash(self):
        return digest(self.values)


@dataclass
class Dataset:
    rows: dict[str, list[SourceRow]]

    def summary(self):
        routes = {row.values["工艺路线名称"] for row in self.rows["route_step"]}
        goods = Counter(row.values["工单号"] for row in self.rows["work_order"])
        partial = sum(goods[row.values["工单号"]] != int(number(row.values["货品款数"]))
                      for row in self.rows["production_order"])
        balance = defaultdict(Decimal)
        for row in self.rows["stock_balance"]:
            balance[text(row.values["单位"])] += number(row.values["实际库存"])
        return {"source_rows": {kind: len(rows) for kind, rows in self.rows.items()}, "routes": len(routes),
                "incomplete_projects": partial, "stock_quantities_by_source_unit": {unit: str(value) for unit, value in balance.items()}}


def read_dataset(directory):
    collected = {}
    for kind, pattern in FILES.items():
        paths = list(Path(directory).glob(pattern))
        if len(paths) != 1:
            raise ValueError(f"{pattern} 必须且只能提供一份文件，实际 {len(paths)} 份")
        path = paths[0]
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        book = load_workbook(path, data_only=True, read_only=True)
        try:
            if len(book.worksheets) != 1:
                raise ValueError(f"{path.name} 仅支持已核对的单表导出")
            sheet = book.worksheets[0]
            iterator = sheet.iter_rows(values_only=True)
            headers = [text(value) for value in next(iterator)]
            if not REQUIRED[kind] <= set(headers) or len(set(headers)) != len(headers):
                raise ValueError(f"{path.name} 表头缺失或重复")
            rows, keys, sequence = [], set(), Counter()
            for line, cells in enumerate(iterator, 2):
                if not any(value is not None for value in cells):
                    continue
                if text(cells[0]) in {"合计", "总计"}:
                    continue
                values = {key: (value.isoformat() if isinstance(value, (date, datetime)) else value)
                          for key, value in zip(headers, cells)}
                if kind == "route_step":
                    name = text(values["工艺路线名称"])
                    sequence[name] += 1
                    key = f"{name}::{sequence[name]}"
                    if not name or not text(values["工艺"]) or text(values.get("加工类型")) not in {"自制", "委外", "品检"}:
                        raise ValueError(f"{path.name}:{line} 工艺名称或类型无效")
                    standard_minutes(values)
                elif kind == "production_order":
                    key = text(values["工单号"])
                    count = number(values["货品款数"])
                    if count is None or count != int(count) or text(values["工单状态"]) not in {"待下单", "已下单", "已暂停", "已完工"}:
                        raise ValueError(f"{path.name}:{line} 款数或状态无效")
                elif kind == "work_order":
                    key = text(values["货品编码"])
                    if number(values["数量"]) is None or number(values["数量"]) <= 0 or text(values["单位"]) not in UNITS:
                        raise ValueError(f"{path.name}:{line} 数量或单位无效")
                    if text(values.get("货品类型")) not in PROCESSING_TYPES or text(values["货品状态"]) not in {"待配置", "待下单", "已下单", "已暂停", "已完工"}:
                        raise ValueError(f"{path.name}:{line} 货品类型或状态无效")
                    route_steps(values["工艺路线"])
                else:
                    if text(values["单位"]) not in UNITS:
                        raise ValueError(f"{path.name}:{line} 库存单位未定义")
                    key = digest([text(values.get(key)) for key in ("货品编码", "规格型号", "单位")])
                    actual, occupied, available = [number(values.get(key), default=Decimal(0)) for key in ("实际库存", "占用数", "可用数")]
                    if occupied != 0 or actual - occupied != available:
                        raise ValueError(f"{path.name}:{line} 存在占用或库存口径不一致，不能伪造占用来源")
                if not key or len(key) > 256 or key in keys:
                    raise ValueError(f"{path.name}:{line} 来源编号为空、过长或重复")
                keys.add(key)
                rows.append(SourceRow(kind, key, path.name, file_hash, sheet.title, line, values))
            collected[kind] = rows
        finally:
            book.close()
    orders = {row.key for row in collected["production_order"]}
    missing = {text(row.values["工单号"]) for row in collected["work_order"]} - orders
    if missing:
        raise ValueError("货品引用的工单未导出：" + "、".join(sorted(missing)))
    return Dataset(collected)
