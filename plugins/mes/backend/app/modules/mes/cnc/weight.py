"""复用选材密度及模型几何计算重量；不向模型请求或猜测材料密度。"""

from decimal import Decimal, InvalidOperation, localcontext
from math import prod

from .schemas import Specs

KG_SCALE = Decimal("1000000")  # mm³ → cm³，以及 g → kg。
WEIGHT_PRECISION = Decimal("0.000001")


def positive_decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def estimate_weight(specs: Specs, quantity: int, geometry: dict | None = None) -> dict:
    """均匀材质的单件/整批重量；净体积优先，外接尺寸仅作实心外形估重。"""
    geometry = geometry or {}
    density = specs.density
    stock_dimensions = (specs.stock_length, specs.stock_width, specs.stock_height)
    stock_volume = prod(stock_dimensions) if all(value is not None for value in stock_dimensions) else None
    metric = geometry.get("units", "mm") == "mm"
    net_volume = positive_decimal(geometry.get("volume_mm3")) if metric else None
    bounds = geometry.get("bounds")
    dimensions = [positive_decimal(value) for value in bounds] if metric and isinstance(bounds, (list, tuple)) and len(bounds) == 3 else []
    envelope_volume = prod(dimensions) if dimensions and all(value is not None for value in dimensions) else None
    volume = net_volume if net_volume is not None else envelope_volume

    if density is None:
        method_key, basis = "unavailable", "请填写或选择材料密度后计算重量。"
    elif net_volume is not None:
        method_key, basis = "cad_volume", "按 STEP 净体积 × 材料密度计算，已按模型扣除孔槽，按均匀材质估算。"
    elif envelope_volume is not None:
        method_key, basis = "model_bounds", "按模型长 × 宽 × 高 × 材料密度估算，尚未扣除孔槽和型腔，不作为净重。"
    else:
        method_key, basis = "unavailable", "缺少模型净体积或有效模型尺寸，暂不能估算零件重量；毛坯重量按已填写尺寸计算。"

    def mass(volume_mm3, count=1):
        if volume_mm3 is None or density is None:
            return None
        with localcontext() as context:
            context.prec = 50
            value = volume_mm3 * density * count / KG_SCALE
            return str(value.quantize(WEIGHT_PRECISION))

    return {
        "quantity": quantity,
        "density_g_cm3": str(density) if density is not None else None,
        "volume_mm3": str(volume) if volume is not None else None,
        "method_key": method_key,
        "basis": basis,
        "estimated_weight_kg": mass(volume),
        "estimated_total_weight_kg": mass(volume, quantity),
        "net_weight_kg": mass(net_volume),
        "net_total_weight_kg": mass(net_volume, quantity),
        "stock_weight_kg": mass(stock_volume),
        "stock_total_weight_kg": mass(stock_volume, quantity),
    }
