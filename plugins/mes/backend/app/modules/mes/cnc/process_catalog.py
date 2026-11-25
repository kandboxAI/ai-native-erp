"""核算表工序字典：完整名称用于展示，缩写仅用于匹配。费率单位为元/小时。"""

import re
from typing import Literal

ProcessType = Literal[
    "cutting",
    "turning",
    "milling",
    "nc",
    "cnc",
    "drilling",
    "grinding",
    "surface_grinding",
    "cylindrical_grinding",
    "wire_fast",
    "wire_slow",
    "edm_imported",
    "edm_domestic",
    "fitting",
    "inspection",
]

# 专用工序在通用工序之前，避免圆磨命中磨削、CNC 命中 NC。
PROCESS_CATALOG = (
    ("cutting", "下料", ("下料", "锯切"), 35),
    ("turning", "车削", ("车削", "精车", "粗车", "车"), 60),
    ("milling", "铣削", ("铣削", "精铣", "粗铣", "铣"), 60),
    ("nc", "普通数控加工", ("普通数控加工", "NC"), 80),
    ("cnc", "加工中心加工", ("加工中心加工", "加工中心", "CNC"), 100),
    ("drilling", "钻孔加工", ("钻孔加工", "钻孔", "打孔", "沉孔", "锪孔"), 45),
    ("surface_grinding", "大水磨加工", ("大水磨加工", "大水磨"), 80),
    ("cylindrical_grinding", "圆磨加工", ("圆磨加工", "圆磨"), 60),
    ("grinding", "磨削加工", ("磨削加工", "磨削", "磨"), 60),
    ("wire_fast", "快走丝线切割加工", ("快走丝线切割加工", "快走丝", "快W/C"), 35),
    ("wire_slow", "慢走丝线切割加工", ("慢走丝线切割加工", "慢走丝", "慢W/C"), 120),
    ("edm_imported", "进口电火花加工", ("进口电火花", "EDM进"), 100),
    ("edm_domestic", "国产电火花加工", ("国产电火花", "EDM国"), 35),
    ("fitting", "钳工加工与装配", ("钳工加工与装配", "钳工", "钳", "去毛刺", "锐边处理"), 35),
    ("inspection", "检验", ("检验", "检测", "测量"), 35),
)


def process_catalog() -> list[dict]:
    return [
        {"process_type_code": key, "name": name, "aliases": list(aliases), "hourly_rate": rate}
        for key, name, aliases, rate in PROCESS_CATALOG
    ]


def infer_process_type(name: str) -> str | None:
    value = "".join(name.casefold().split())
    aliases = sorted(
        ((alias, key) for key, label, words, rate in PROCESS_CATALOG for alias in (label, *words)),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, key in aliases:
        alias = "".join(alias.casefold().split())
        if alias.isascii():
            if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", value):
                return key
        elif alias in value:
            return key
    return None
