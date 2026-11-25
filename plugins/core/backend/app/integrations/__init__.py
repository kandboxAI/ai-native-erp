"""Core integrations plus explicitly packaged plugin integration modules."""
from app.framework.plugin_sources import module_namespace_paths

__path__ = module_namespace_paths(__path__, "integrations")
