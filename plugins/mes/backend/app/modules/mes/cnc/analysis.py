"""独立解析进程：避免 CAD 原生库崩溃影响 API 和队列消费者。"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


def parse_pdf(source: Path, output: Path, file_id: str) -> dict:
    import pdfplumber
    import pypdfium2 as pdfium

    pages = []
    with pdfplumber.open(source) as document, pdfium.PdfDocument(source) as renderer:
        if len(document.pages) > 20:
            raise ValueError("MVP 单份 PDF 最多支持 20 页，请拆分后上传")
        for number, page in enumerate(document.pages, start=1):
            image_name = f"{file_id}-page-{number}.png"
            # 整页用于定位，局部视图避免视觉模型整页缩放后丢失小字和旋转标注。
            scale = min(3.2, 4000 / max(page.width, page.height))
            image = renderer[number - 1].render(scale=scale).to_pil()
            image.save(output / image_name)
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            tokens = []
            for index, word in enumerate(words):
                text = word["text"]
                tokens.append(
                    {
                        "id": f"{file_id}-p{number}-t{index}",
                        "text": text,
                        "bbox": [
                            word["x0"] / page.width,
                            word["top"] / page.height,
                            word["x1"] / page.width,
                            word["bottom"] / page.height,
                        ],
                        "dimension_candidate": bool(re.search(r"\d", text)) and len(text) <= 30,
                    }
                )
            pages.append(
                {
                    "number": number,
                    "width": float(page.width),
                    "height": float(page.height),
                    "image": image_name,
                    "text": (page.extract_text() or "")[:40000],
                    "tokens": tokens,
                    "detail_views": create_detail_views(
                        image, words, page.width, page.height, output, f"{file_id}-p{number}"
                    ),
                }
            )
    return {"file_id": file_id, "pages": pages}


def create_detail_views(
    image, words: list[dict], width: float, height: float, output: Path, prefix: str
) -> list[dict]:
    regions = [
        ("分区放大", box, 0)
        for box in (
            [0, 0, 0.55, 0.55],
            [0.45, 0, 1, 0.55],
            [0, 0.45, 0.55, 1],
            [0.45, 0.45, 1, 1],
        )
    ]
    groups = []
    # 用文字层定位旋转区域，但不采信其中的字符内容；实际识别仍看原图。
    for word in words:
        if word.get("upright", True) or word["top"] > height * 0.7:
            continue
        box = [word["x0"], word["top"], word["x1"], word["bottom"]]
        near = [
            group
            for group in groups
            if box[0] <= group[2] + 40
            and box[2] >= group[0] - 40
            and box[1] <= group[3] + 80
            and box[3] >= group[1] - 80
        ]
        for group in near:
            box = [min(box[0], group[0]), min(box[1], group[1]), max(box[2], group[2]), max(box[3], group[3])]
            groups.remove(group)
        groups.append(box)
    for box in sorted(groups, key=lambda item: item[1])[:4]:
        bbox = [
            max(0, box[0] - 12) / width,
            max(0, box[1] - 12) / height,
            min(width, box[2] + 12) / width,
            min(height, box[3] + 12) / height,
        ]
        regions.append(("旋转标注放大，顺时针 90°", bbox, -90))
    details = []
    for index, (label, bbox, angle) in enumerate(regions):
        pixels = (
            round(bbox[0] * image.width),
            round(bbox[1] * image.height),
            round(bbox[2] * image.width),
            round(bbox[3] * image.height),
        )
        cropped = image.crop(pixels)
        if angle:
            cropped = cropped.rotate(angle, expand=True, fillcolor="white")
        name = f"{prefix}-detail-{index}.png"
        cropped.save(output / name)
        details.append(
            {
                "id": f"{prefix}-detail-{index}",
                "image": name,
                "label": label,
                "bbox": bbox,
                "rotation_degrees": angle,
            }
        )
    return details


def parse_step(source: Path, output: Path, file_id: str) -> dict:
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    reader = STEPControl_Reader()
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        raise ValueError("STEP 文件无法读取")
    if not reader.TransferRoots():
        raise ValueError("STEP 没有可转换的几何")
    shape = reader.OneShape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError("STEP 拓扑无效，未进行静默修复，请人工检查模型")
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    solid_count = 0
    while solids.More():
        solid_count += 1
        solids.Next()
    if solid_count != 1:
        raise ValueError(f"MVP 只分析单实体零件，当前实体数量：{solid_count}")
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box)
    lower, upper = box.CornerMin(), box.CornerMax()
    xmin, ymin, zmin = lower.X(), lower.Y(), lower.Z()
    xmax, ymax, zmax = upper.X(), upper.Y(), upper.Z()
    volume_props, area_props = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, volume_props)
    BRepGProp.SurfaceProperties_s(shape, area_props)
    volume = abs(volume_props.Mass())
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("STEP 实体体积无效")
    BRepMesh_IncrementalMesh(shape, 0.25, False, 0.5, False).Perform()
    positions, face_ids, features = [], [], []
    surface_counts = Counter()
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0
    while faces.More():
        face_id += 1
        if face_id > 10000:
            raise ValueError("模型超过 MVP 10000 面限制")
        face = TopoDS.Face(faces.Current())
        surface = BRepAdaptor_Surface(face)
        surface_counts[str(surface.GetType()).split(".")[-1]] += 1
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            features.append(
                {
                    "id": f"face-{face_id}",
                    "type": "cylinder_candidate",
                    "face_ids": [face_id],
                    "label": f"圆柱面候选 Ø{cylinder.Radius() * 2:.3f}",
                    "diameter": round(cylinder.Radius() * 2, 6),
                    "axis_direction": [
                        round(v, 6)
                        for v in (
                            cylinder.Axis().Direction().X(),
                            cylinder.Axis().Direction().Y(),
                            cylinder.Axis().Direction().Z(),
                        )
                    ],
                    "note": "尚未区分孔、外圆或圆角；不能直接作为孔数或加工工序。",
                }
            )
        elif surface.GetType() == GeomAbs_Plane:
            features.append(
                {"id": f"face-{face_id}", "type": "plane", "face_ids": [face_id], "label": f"平面 {face_id}"}
            )
        elif surface.GetType() == GeomAbs_Cone:
            cone = surface.Cone()
            features.append(
                {
                    "id": f"face-{face_id}",
                    "type": "cone_candidate",
                    "face_ids": [face_id],
                    "label": f"圆锥面候选 {math.degrees(abs(cone.SemiAngle())):.3f}° 半角",
                    "semi_angle_degrees": round(math.degrees(abs(cone.SemiAngle())), 6),
                    "note": "几何半角，不是图纸角度要求；不能直接据此确认螺纹或工艺。",
                }
            )
        elif surface.GetType() == GeomAbs_Torus:
            torus = surface.Torus()
            features.append(
                {
                    "id": f"face-{face_id}",
                    "type": "torus_candidate",
                    "face_ids": [face_id],
                    "label": f"圆环曲面候选 R{torus.MinorRadius():.3f}",
                    "major_radius": round(torus.MajorRadius(), 6),
                    "minor_radius": round(torus.MinorRadius(), 6),
                }
            )
        else:
            features.append(
                {
                    "id": f"face-{face_id}",
                    "type": "other_surface",
                    "face_ids": [face_id],
                    "label": f"其他曲面 {face_id}",
                    "note": "仅提供面定位，尚未分类制造特征。",
                }
            )
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None:
            transform = location.Transformation()
            for index in range(1, triangulation.NbTriangles() + 1):
                nodes = list(triangulation.Triangle(index).Get())
                if face.Orientation() == TopAbs_REVERSED:
                    nodes.reverse()
                for node in nodes:
                    point = triangulation.Node(node).Transformed(transform)
                    positions.extend(round(value, 5) for value in (point.X(), point.Y(), point.Z()))
                face_ids.append(face_id)
                if len(face_ids) > 500000:
                    raise ValueError("模型网格超过 MVP 限制")
        faces.Next()
    mesh_name = f"{file_id}-mesh.json"
    (output / mesh_name).write_text(
        json.dumps({"positions": positions, "face_ids": face_ids}), encoding="utf-8"
    )
    return {
        "file_id": file_id,
        "units": "mm",
        "solid_count": solid_count,
        "bounds": [round(xmax - xmin, 6), round(ymax - ymin, 6), round(zmax - zmin, 6)],
        "volume_mm3": round(volume, 6),
        "area_mm2": round(area_props.Mass(), 6),
        "face_count": face_id,
        "mesh": mesh_name,
        "features": features,
        "surface_counts": dict(surface_counts),
        "pmi_extracted": False,
        "note": "尺寸为模型坐标轴包围盒；曲面只作工艺建议依据，未执行孔槽分组、刀具可达性或 PMI 提取，不能从形状推断材料及制造要求。",
    }


def run(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output = Path(manifest["output"])
    output.mkdir(parents=True, exist_ok=True)
    result = {"documents": [], "geometry": None, "warnings": []}
    for item in manifest["files"]:
        source = Path(item["path"])
        try:
            if item["kind"] == "pdf":
                document = parse_pdf(source, output, item["id"])
                result["documents"].append(document)
                if not any(page["tokens"] for page in document["pages"]):
                    result["warnings"].append(
                        "PDF 没有可提取文字，请启用视觉模型或人工录入；未运行本地 OCR。"
                    )
            else:
                result["geometry"] = parse_step(source, output, item["id"])
        except (ImportError, ValueError, RuntimeError) as error:
            result["warnings"].append(f"{item['name']}：{error}")
    if not result["documents"] and result["geometry"] is None:
        raise ValueError("；".join(result["warnings"]) or "没有可解析文件")
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]))
