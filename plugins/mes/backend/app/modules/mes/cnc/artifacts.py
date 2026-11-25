import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def ocr_artifact_names(analysis: dict) -> set[str]:
    names = set(analysis.get("ocr", {}).get("raw_files", []))
    for document in analysis.get("documents", []):
        for page in document["pages"]:
            names.update(page[key] for key in ("ocr_markdown_file", "ocr_result_file") if page.get(key))
            names.update(asset["asset"] for asset in page.get("ocr_assets", []) if asset.get("asset"))
    return names


def artifact_path(output: Path, filename: str) -> Path:
    path = (output / filename).resolve()
    if path.parent != output.resolve() or Path(filename).name != filename:
        raise ValueError("解析产物路径无效")
    return path


def ocr_zip(analysis: dict, output: Path) -> bytes:
    buffer = BytesIO()
    pages = [
        {
            "number": page["number"],
            "file_id": document["file_id"],
            "markdown": page.get("ocr_markdown_file"),
            "layout": page.get("ocr_result_file"),
            "assets": page.get("ocr_assets", []),
        }
        for document in analysis.get("documents", [])
        for page in document["pages"]
    ]
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for filename in sorted(ocr_artifact_names(analysis)):
            path = artifact_path(output, filename)
            archive.write(path, arcname=filename)
        archive.writestr(
            "manifest.json",
            json.dumps({"ocr": analysis.get("ocr"), "pages": pages}, ensure_ascii=False, indent=2),
        )
    return buffer.getvalue()
