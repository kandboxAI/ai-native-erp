"""只读解析整理版xlsx。工作簿中的说明均为来源数据，不作为操作指令。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADERS = {
    "说明": ["项目", "说明"],
    "项目台账": ["项目名称", "管道(在谈)", "已回款", "合同总价", "应收(总价-已付)", "备注"],
    "流水台账": ["月份", "收入总额", "收入明细", "工资+社保", "固定支出", "报销/零散", "手续费/利息", "支出合计", "月末余额", "备注"],
    "工资概览": ["发薪主体", "姓名", "税前基本工资", "应发成本", "项目任务"],
    "人员薪资": ["姓名", "城市", "月度工资", "系数", "补贴", "入职时间", "状态", "备注"],
    "银行账户": ["账户名", "开户行", "账号", "用途"],
    "奖金台账": ["来源项目", "归属人", "金额", "说明", "状态"],
    "云费用": ["项目", "费用", "周期", "说明"],
    "社保公积金规则": ["项目", "比例/金额", "构成", "承担方"],
}


@dataclass
class SourceRow:
    sheet: str
    row_no: int
    cells: dict


def number(value) -> Decimal | None:
    if value is None or str(value).strip() in {"", "—", "-"}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def mask_account(value) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\s+", "", str(value))
    return "****" + digits[-4:] if len(digits) > 4 else "****"


def read_source(path: Path) -> tuple[str, list[SourceRow]]:
    """仅接受已核对的列结构，保持Excel行号及数值；公式必须有缓存值。"""
    digest = sha256(path.read_bytes()).hexdigest()
    rows = []
    with ZipFile(path) as archive:
        if sum(x.file_size for x in archive.infolist()) > 25_000_000:
            raise ValueError("工作簿解压体积超过25MB，停止导入")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(x.itertext()) for x in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rels = {x.attrib["Id"]: x.attrib["Target"] for x in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        names = []
        for sheet in workbook.find("s:sheets", NS):
            name = sheet.attrib["name"]
            names.append(name)
            if name not in HEADERS:
                raise ValueError("存在未经映射的工作表，请先核对结构")
            target = rels[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
            sheet_rows = []
            for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", NS):
                values = [None] * len(HEADERS[name])
                for cell in row:
                    col = re.match(r"[A-Z]+", cell.attrib["r"])[0]
                    index = 0
                    for letter in col:
                        index = index * 26 + ord(letter) - 64
                    if index > len(values):
                        continue
                    kind = cell.attrib.get("t")
                    raw = cell.find("s:v", NS)
                    value = raw.text if raw is not None else None
                    if kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                    elif kind == "s" and value is not None:
                        value = strings[int(value)]
                    elif kind == "e":
                        raise ValueError(f"{name} 第{row.attrib['r']}行包含Excel错误")
                    elif kind not in {"str", "b"} and value is not None:
                        value = str(Decimal(value))
                    if cell.find("s:f", NS) is not None and value is None:
                        raise ValueError("公式无缓存值，请在Excel重算并保存后导入")
                    values[index - 1] = value
                if any(v is not None and v != "" for v in values):
                    sheet_rows.append((int(row.attrib["r"]), values))
            if not sheet_rows or sheet_rows[0][1] != HEADERS[name]:
                raise ValueError(f"{name} 列结构与已审核版本不一致")
            for row_no, values in sheet_rows[1:]:
                cells = dict(zip(HEADERS[name], values))
                if name == "银行账户":
                    cells["账号"] = mask_account(cells["账号"])
                rows.append(SourceRow(name, row_no, cells))
                if len(rows) > 500:
                    raise ValueError("来源超过500条，请先分批审核，不能静默截断")
        if set(names) != set(HEADERS):
            raise ValueError("缺少已审核的工作表")
    return digest, rows


def is_note(row: SourceRow) -> bool:
    first = str(next(iter(row.cells.values())) or "")
    return first.startswith("注") or first in {"总计", "应收总计", "全部主体"} or row.cells.get("姓名") in {"合计", "全部合计"} or row.sheet == "说明"


def ledger_difference(cells: dict) -> Decimal | None:
    values = [number(cells.get(key)) for key in ["工资+社保", "固定支出", "报销/零散", "手续费/利息", "支出合计"]]
    if any(value is None for value in values):
        return None
    return values[-1] - sum(values[:-1], Decimal("0"))
