"""Last-resort value checks after the explicit field policy."""

from __future__ import annotations

from typing import Any
from app.framework.model_data_protection import safe_scalar


def model_scalar(value: Any) -> Any:
    return safe_scalar(value)
