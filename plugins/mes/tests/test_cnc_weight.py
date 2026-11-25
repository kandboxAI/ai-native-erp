"""重量单位、净体积/外形体积区分及无完整报价时的重量展示；不访问数据库或模型。"""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.mes.cnc.schemas import Specs
from app.modules.mes.cnc.weight import estimate_weight


def specs(**overrides):
    return Specs(stock_length=110, stock_width=60, stock_height=30, **{"density": "2.7", **overrides})


def test_real_net_volume_takes_priority_over_bounding_dimensions_and_keeps_stock_separate():
    result = estimate_weight(specs(), 10, {"units": "mm", "volume_mm3": 60000, "bounds": [100, 50, 20]})
    assert result["method_key"] == "cad_volume"
    assert result["net_weight_kg"] == result["estimated_weight_kg"] == "0.162000"
    assert result["net_total_weight_kg"] == "1.620000"
    assert result["stock_weight_kg"] == "0.534600"
    assert result["stock_total_weight_kg"] == "5.346000"


def test_dimensions_alone_are_an_envelope_estimate_never_a_net_weight():
    result = estimate_weight(specs(), 3, {"bounds": [100, 50, 20]})
    assert result["method_key"] == "model_bounds" and "未扣除孔槽" in result["basis"]
    assert result["estimated_weight_kg"] == "0.270000"
    assert result["estimated_total_weight_kg"] == "0.810000"
    assert result["net_weight_kg"] is None and result["net_total_weight_kg"] is None


def test_density_is_never_guessed_from_material_name():
    result = estimate_weight(specs(material="AL6061", density=None), 2, {"volume_mm3": 100000})
    assert result["method_key"] == "unavailable" and "密度" in result["basis"]
    assert result["estimated_weight_kg"] is None and result["stock_weight_kg"] is None


def test_stock_dimensions_alone_cannot_be_misrepresented_as_part_net_weight():
    result = estimate_weight(specs(), 2)
    assert result["method_key"] == "unavailable" and result["net_weight_kg"] is None
    assert result["estimated_weight_kg"] is None and result["stock_weight_kg"] == "0.534600"


def test_net_weight_does_not_require_price_or_stock_dimensions():
    result = estimate_weight(Specs(density="7.85", material_price_unit_code="mm"), 2, {"volume_mm3": 100000})
    assert result["net_weight_kg"] == "0.785000" and result["net_total_weight_kg"] == "1.570000"
    assert result["stock_weight_kg"] is None


def test_batch_weight_is_computed_before_rounding_single_piece_weight():
    result = estimate_weight(specs(), 1000000, {"volume_mm3": "0.1"})
    assert result["net_weight_kg"] == "0.000000"
    assert result["net_total_weight_kg"] == "0.270000"


@pytest.mark.parametrize("volume", [None, 0, -10, "NaN", "Infinity", "unknown"])
def test_invalid_net_volume_falls_back_to_explicitly_labelled_envelope(volume):
    result = estimate_weight(specs(), 1, {"volume_mm3": volume, "bounds": [100, 50, 20]})
    assert result["net_weight_kg"] is None and result["method_key"] == "model_bounds"


@pytest.mark.parametrize("geometry", [
    {"bounds": [100, 50]}, {"bounds": [100, 0, 20]}, {"bounds": [100, -50, 20]},
    {"units": "cm", "volume_mm3": 100000, "bounds": [100, 50, 20]},
])
def test_incomplete_dimensions_or_unknown_units_do_not_generate_false_net_weight(geometry):
    result = estimate_weight(specs(), 1, geometry)
    assert result["method_key"] == "unavailable" and result["estimated_weight_kg"] is None


def test_part_detail_exposes_weight_without_operations_or_a_successful_quote(monkeypatch):
    from app.modules.mes.cnc import service as module
    from app.modules.mes.cnc.models import CncPart

    part = CncPart(name="零件", org_id=uuid4(), quantity=10, density="2.7",
                   analysis={"geometry": {"volume_mm3": 60000, "bounds": [100, 50, 20]}})
    monkeypatch.setattr(module, "repo", NS(jobs=AsyncMock(return_value=None), operations=AsyncMock(return_value=[]),
        files=AsyncMock(return_value=[]), quotes=AsyncMock(return_value=[])))
    monkeypatch.setattr(module, "files", NS(list_for_business=AsyncMock(return_value=[])))
    data = asyncio.run(module.service.part_data(NS(), part))
    assert data["quote"] is None and data["operations"] == []
    assert data["weight_estimate"]["net_weight_kg"] == "0.162000"
    assert data["weight_estimate"]["net_total_weight_kg"] == "1.620000"
