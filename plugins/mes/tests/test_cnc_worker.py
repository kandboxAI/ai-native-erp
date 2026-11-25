"""本地解析进程的宿主目录与失败传播；不访问数据库或云服务。"""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.core.config import BASE_DIR
from app.modules.mes.cnc import worker


def test_parser_uses_host_backend_directory_after_plugin_relocation(tmp_path, monkeypatch):
    output = tmp_path / "解析产物 with spaces"
    output.mkdir()
    manifest = output / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    expected = {"documents": [], "geometry": None, "warnings": []}
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert Path(kwargs["cwd"]) == BASE_DIR
        assert Path(kwargs["cwd"]).is_dir()
        kwargs["stdout"].write("local parser started\n")
        (output / "result.json").write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.setattr(worker.subprocess, "run", run)
    monkeypatch.setattr(worker, "settings", lambda: SimpleNamespace(analysis_timeout_seconds=37))
    monkeypatch.chdir(tmp_path)

    assert worker.parse_local(manifest, output) == expected
    command, kwargs = calls[0]
    assert command == [sys.executable, "-m", "app.modules.mes.cnc.analysis", str(manifest)]
    assert kwargs["timeout"] == 37 and kwargs["check"] is True
    assert kwargs["stderr"] == subprocess.STDOUT
    assert "local parser started" in (output / "parser.log").read_text(encoding="utf-8")


def test_parser_failure_keeps_subprocess_error_and_log(tmp_path, monkeypatch):
    def fail(command, **kwargs):
        kwargs["stdout"].write("parser failure details\n")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(worker.subprocess, "run", fail)
    monkeypatch.setattr(worker, "settings", lambda: SimpleNamespace(analysis_timeout_seconds=30))
    with pytest.raises(subprocess.CalledProcessError):
        worker.parse_local(tmp_path / "manifest.json", tmp_path)
    assert "parser failure details" in (tmp_path / "parser.log").read_text(encoding="utf-8")


def test_real_parser_handles_pdf_and_step_from_an_unrelated_working_directory(tmp_path, monkeypatch):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pytest.importorskip("OCP")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    output = tmp_path / "图纸解析 with spaces"
    output.mkdir()
    pdf = output / "drawing.pdf"
    document = canvas.Canvas(str(pdf), pagesize=(200, 200))
    document.drawString(20, 100, "Parser regression 10 x 20 x 30")
    document.save()
    step = output / "model.step"
    writer = STEPControl_Writer()
    assert writer.Transfer(BRepPrimAPI_MakeBox(10, 20, 30).Shape(), STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(str(step)) == IFSelect_RetDone
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps({
        "output": str(output),
        "files": [
            {"id": "pdf-fixture", "name": pdf.name, "kind": "pdf", "path": str(pdf)},
            {"id": "step-fixture", "name": step.name, "kind": "step", "path": str(step)},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(worker, "settings", lambda: SimpleNamespace(analysis_timeout_seconds=60))
    monkeypatch.chdir(tmp_path)

    result = worker.parse_local(manifest, output)

    assert len(result["documents"]) == 1
    page = result["documents"][0]["pages"][0]
    assert "Parser regression" in page["text"]
    assert (output / page["image"]).is_file()
    assert result["geometry"]["bounds"] == pytest.approx([10, 20, 30])
    assert result["geometry"]["volume_mm3"] == pytest.approx(6000)
    assert (output / result["geometry"]["mesh"]).is_file()
    assert result["warnings"] == []
