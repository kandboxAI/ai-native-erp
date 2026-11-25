from decimal import ROUND_HALF_UP, Decimal

from .schemas import Operation, Specs

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


class IncompleteQuote(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("请补充：" + "、".join(missing))


def calculate_quote(
    specs: Specs, operations: list[Operation], quantity: int, *, net_volume_mm3=None, surface_area_mm2=None
) -> dict:
    required = {
        "材料": specs.material.strip() or None,
        "毛坯长": specs.stock_length,
        "毛坯宽": specs.stock_width,
        "毛坯高": specs.stock_height,
        "材料单价": specs.material_price,
    }
    if specs.material_price_unit_code == "kg":
        required["材料密度"] = specs.density
    else:
        required["材料计费长度（mm/件）"] = specs.material_billing_length
    missing = [name for name, value in required.items() if value is None]
    if not operations:
        missing.append("加工工序")
    for index, operation in enumerate(operations, start=1):
        if operation.pricing_mode_code == "external":
            if operation.external_rate is None:
                missing.append(
                    f"工序{index} {operation.name} 外协单价（元/{operation.external_price_unit_code}）"
                )
            if operation.external_price_unit_code == "m2":
                if operation.external_area_mm2 is None and surface_area_mm2 is None:
                    missing.append(f"工序{index} {operation.name} 计费表面积（mm²）")
                continue
            if specs.density is None:
                missing.append(f"工序{index} {operation.name} 计费重量所需材料密度")
            if operation.external_weight_basis_code == "net" and net_volume_mm3 is None:
                missing.append(f"工序{index} {operation.name} CAD 净体积")
            continue
        for label, value in (
            ("预估工时（小时/件）", operation.unit_hours),
            ("小时费率", operation.hourly_rate),
        ):
            if value is None:
                missing.append(f"工序{index} {label}")
    if missing:
        raise IncompleteQuote(missing)

    # 内部全程保留 Decimal 精度，仅在展示/导出时按分舍入。
    stock_volume = specs.stock_length * specs.stock_width * specs.stock_height
    weight = stock_volume * specs.density / Decimal("1000000") if specs.density is not None else None
    material_unit = (
        weight if specs.material_price_unit_code == "kg" else specs.material_billing_length
    ) * specs.material_price
    machining_unit = Decimal("0")
    external_unit = specs.external_unit_cost
    breakdown = []
    for operation in operations:
        if operation.pricing_mode_code == "external":
            if operation.external_price_unit_code == "m2":
                charged = Decimal(str(operation.external_area_mm2 or surface_area_mm2)) / Decimal("1000000")
            else:
                charged = (
                    weight
                    if operation.external_weight_basis_code == "stock"
                    else Decimal(str(net_volume_mm3)) * specs.density / Decimal("1000000")
                )
            external = max(charged * operation.external_rate, operation.external_minimum_unit)
            external_unit += external
            breakdown.append(
                {
                    "name": operation.name,
                    "machine": operation.machine,
                    "pricing_mode_code": "external",
                    "external_rate": str(operation.external_rate),
                    "external_unit": money(external),
                    "weight_basis_code": operation.external_weight_basis_code,
                    "price_unit_code": operation.external_price_unit_code,
                    "charged_area_m2"
                    if operation.external_price_unit_code == "m2"
                    else "charged_weight_kg": str(charged),
                    "minimum_unit": str(operation.external_minimum_unit),
                }
            )
            continue
        machining = operation.unit_hours * operation.hourly_rate
        machining_unit += machining
        breakdown.append(
            {
                "name": operation.name,
                "machine": operation.machine,
                "pricing_mode_code": "hourly",
                "unit_hours": str(operation.unit_hours),
                "hourly_rate": str(operation.hourly_rate),
                "machining_unit": money(machining),
            }
        )
    batch_cost = (material_unit + machining_unit + external_unit) * quantity
    batch_cost += specs.other_batch_cost
    unit_cost = batch_cost / quantity
    unit_price = unit_cost.quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "currency": "CNY",
        "quantity": quantity,
        "stock_weight_kg": str(weight.quantize(Decimal("0.000001"))) if weight is not None else None,
        "material_price_unit_code": specs.material_price_unit_code,
        "material_unit": money(material_unit),
        "machining_unit": money(machining_unit),
        "external_unit": money(external_unit),
        "other_batch": money(specs.other_batch_cost),
        "batch_cost": money(batch_cost),
        "unit_cost": money(unit_cost),
        "unit_price": str(unit_price),
        "total_price": money(unit_price * quantity),
        "operations": breakdown,
        "basis": "人民币、不含税；按核算成本直接计价，无毛利加价。工序费用=预估工时（小时/件）×费率（元/小时），暂不单列准备费。运费等仅计入已填写费用。",
    }
