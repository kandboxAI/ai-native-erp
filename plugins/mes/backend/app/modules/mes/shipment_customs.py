"""材料建议和报关草稿归并。成交金额和实装重量沿用出货版本。"""
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from unicodedata import normalize


MATERIAL_LABELS = {"aluminum": "铝材料", "steel": "钢材料", "engineering_plastic": "工程塑料"}
MATERIAL_PATTERNS = {
    "aluminum": (
        r"铝|ALUMIN(?:UM|IUM)|DURALUMIN|"
        r"(?<![A-Z0-9])(?:EN\s*[- ]?AW\s*[- ]?\d{4}|AL\s*[- ]?\d{4}|ALSI\d+\w*|"
        r"2A\d{2}|A(?:DC|C)\d{1,2}|(?:1050|1060|1100|2011|2014|2017|2024|3003|"
        r"5052|5083|5754|6060|6061|6063|6082|7075)(?:[- ]?T\d{1,3})?)(?![A-Z0-9])"
    ),
    "steel": (
        r"(?<!赛)钢|STEEL|(?<![A-Z0-9])(?:SUS\s*\d{3}[A-Z]*|AISI\s*\d{3,4}[A-Z]*|"
        r"S(?:S)?\s*(?:201|304L?|316L?|410|416|420|430|440[ABC])|"
        r"201|304L?|316L?|410|416|420|430|440[ABC]|17[- ]?4\s*PH|"
        r"42CRMO4?|40CR|45#|Q(?:235|345|355)[A-Z]?|S(?:235|355)[A-Z]*|"
        r"S(?:45|50)C|SKD(?:11|61)|(?:1\.\d{4}))(?![A-Z0-9])"
    ),
    "engineering_plastic": (
        r"工程塑料|尼龙|赛钢|聚甲醛|聚碳酸酯|聚四氟乙烯|聚醚醚酮|电木|特氟龙|"
        r"(?<![A-Z0-9])(?:POM(?:[- ]?[CH])?|DELRIN|ACETAL|NYLON|PA(?:6|66|12)?|"
        r"PEEK|PTFE|TEFLON|UHMW[- ]?PE|PPS|PET|PBT|ABS|PMMA|PC)(?![A-Z0-9])"
    ),
}
MATERIAL_SEARCH = {key: re.compile(pattern) for key, pattern in MATERIAL_PATTERNS.items()}
DECLARATION_KEYS = ("declared_name", "hs_code", "origin_country", "declaration_elements", "customer_tariff_no")


def suggest_material_group(material: str) -> str | None:
    text = normalize("NFKC", material).upper()
    matches = [group for group, pattern in MATERIAL_SEARCH.items() if pattern.search(text)]
    return matches[0] if len(matches) == 1 else None


def declaration_fields(declaration, profile) -> dict:
    return {
        key: getattr(declaration, key, None) or getattr(profile, key, None)
        for key in DECLARATION_KEYS
    }


def unit_price(amount: Decimal, quantity: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return (amount / quantity).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def declaration_groups(goods: list[dict]) -> list[dict]:
    groups = {}
    for row in goods:
        family = row["material_group"]
        details = row["customs"]
        unit = row["unit_code"] or row["unit"]
        # 编码、品名、原产国、要素与计量单位不同的项目保留各自的申报行。
        key = (
            family, unit, row["currency"],
            *(details.get(field) for field in DECLARATION_KEYS if field != "customer_tariff_no"),
        ) if family in MATERIAL_LABELS else (row["line_no"],)
        group = groups.setdefault(key, {
            "material_group": family,
            "category": MATERIAL_LABELS.get(family) or ("逐项申报" if family == "individual" else "材料待确认"),
            "customs": details,
            "goods_line_nos": [],
            "name": details.get("declared_name") or MATERIAL_LABELS.get(family) or row["item_name"],
            "unit": "个" if unit == "piece" else row["unit"],
            "unit_code": unit,
            "currency": row["currency"],
            "quantity": Decimal(0),
            "net_weight_kg": Decimal(0),
            "amount": Decimal(0),
        })
        group["goods_line_nos"].append(row["line_no"])
        for field in ("quantity", "net_weight_kg", "amount"):
            group[field] += Decimal(row[field])
    ordered = sorted(
        groups.values(), key=lambda group: (
            list(MATERIAL_LABELS).index(group["material_group"]) if group["material_group"] in MATERIAL_LABELS else len(MATERIAL_LABELS),
            group["goods_line_nos"][0],
        )
    )
    for group_no, group in enumerate(ordered, 1):
        group["group_no"] = group_no
        group["unit_price"] = str(unit_price(group["amount"], group["quantity"]))
        for field in ("quantity", "net_weight_kg", "amount"):
            group[field] = str(group[field])
    return ordered
