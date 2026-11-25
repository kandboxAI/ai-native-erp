"""ERP-independent metadata discovery. Business adapters own authorization and execution."""

from .engine import DiscoveryEngine
from .models import DiscoveryError, DiscoveryRequest, DiscoverySettings

__all__ = ["DiscoveryEngine", "DiscoveryError", "DiscoveryRequest", "DiscoverySettings"]
