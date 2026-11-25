"""Core modules and declared plugin modules share stable app.modules imports."""
from app.framework.plugin_sources import module_namespace_paths

__path__ = module_namespace_paths(__path__)
