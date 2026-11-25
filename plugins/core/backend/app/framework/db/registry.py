"""只扫描当前部署组合的模型目录，映射前注册其表到 SQLModel.metadata。"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from app.framework.deployment import is_module_enabled
import app.modules as modules_pkg

APP_DIR = Path(__file__).resolve().parents[2]


def _is_model_file(path: Path) -> bool:
    if path.suffix != ".py" or "__pycache__" in path.parts:
        return False
    if not (path.name == "models.py" or path.name.endswith("_models.py")):
        return False
    return "table=True" in path.read_text(encoding="utf-8")


def _enabled_model_files():
    for entry in sorted(APP_DIR.iterdir()):
        if entry.name == "modules":
            for directory in modules_pkg.__path__:
                for module_dir in sorted(Path(directory).iterdir()):
                    if module_dir.is_dir() and is_module_enabled(module_dir.name):
                        for path in sorted(module_dir.rglob("*.py")):
                            yield path, "app.modules." + ".".join(path.relative_to(Path(directory)).with_suffix("").parts)
        elif entry.is_dir():
            for path in sorted(entry.rglob("*.py")):
                yield path, ".".join(path.relative_to(APP_DIR.parent).with_suffix("").parts)
        elif entry.suffix == ".py":
            yield entry, "app." + entry.stem


def import_all_models() -> None:
    for path, import_path in _enabled_model_files():
        if _is_model_file(path):
            import_module(import_path)
