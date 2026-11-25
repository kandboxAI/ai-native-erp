"""Plugin-only public UI dependencies must survive a pure-core export."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_core.py"
spec = importlib.util.spec_from_file_location("export_core_shared_web", SCRIPT)
export_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_core)

SHARED = (
    "web/src/components/ActionButton/index.vue",
    "web/src/components/ListPagination/index.vue",
    "web/src/utils/quantity.ts",
)


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    policy = {"format_version": 1, **{group: [] for group in (
        "backend_tests", "web_tests", "web_support", "web_shared_entries",
        "web_assets", "web_styles", "miniapp_support",
    )}}
    policy["web_shared_entries"] = list(SHARED)
    files = {
        "backend/scripts/core_source_allowlist.json": json.dumps(policy),
        SHARED[0]: "<template><button /></template>\n",
        SHARED[1]: "<template><nav /></template>\n",
        SHARED[2]: 'export { formatQuantity } from "./quantityFormat";\n',
        "web/src/utils/quantityFormat.ts": "export const formatQuantity = String;\n",
        "web/src/views/mes/index.vue": "<template>industry page</template>\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(export_core, "ROOT", root)
    return root


def test_exports_shared_entries_and_their_dependencies_without_core_page_imports(source, tmp_path):
    destination = tmp_path / "export"
    export_core.copy_shared_web(destination)
    expected = {*SHARED, "web/src/utils/quantityFormat.ts"}
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    assert actual == expected
    for name in expected:
        assert (destination / name).read_bytes() == (source / name).read_bytes()


@pytest.mark.parametrize("missing", SHARED)
def test_rejects_missing_public_dependency_instead_of_silently_omitting_it(source, tmp_path, missing):
    (source / missing).unlink()
    with pytest.raises(ValueError, match="公共前端入口缺失"):
        export_core.copy_shared_web(tmp_path / "export")
