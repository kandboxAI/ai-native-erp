"""产品新建时绑定图纸，复用 L1 文件生命周期及现有工单下载鉴权。"""
from pathlib import Path

from app.core.exceptions import AppException
from app.modules.file.service import DOCUMENT_MAX_BYTES, register_file_scene, service as files
from .drawing_models import MesWorkOrderDrawingRevision, MesWorkOrderDrawingFile
from .drawing_repository import drawing_repository

DRAWING_TYPE = "mes_work_order_drawing"
DRAWING_SCENE = "mes_work_order_drawing"
register_file_scene(
    DRAWING_SCENE, kinds={"image", "document", "other"}, max_bytes=DOCUMENT_MAX_BYTES, max_count=20,
    extra_content_types={
        "image/vnd.dwg": "dwg", "image/vnd.dxf": "dxf", "application/dxf": "dxf", "application/step": "step",
    },
)


def drawing_kind(name):
    extension = Path(name).suffix.lower()
    return "pdf" if extension == ".pdf" else "model" if extension in {".stp", ".step"} else None


def validate_product_files(rows):
    kinds = []
    for row in rows:
        kind = drawing_kind(row.original_file_name)
        allowed = {"application/pdf"} if kind == "pdf" else {"application/step", "application/octet-stream"}
        if kind is None or row.content_type not in allowed:
            raise AppException("二维图纸须为 PDF，三维模型须为 STP/STEP", 422)
        kinds.append(kind)
    if len(set(kinds)) != len(kinds):
        raise AppException("每个货品最多一份 PDF 和一份 STP/STEP；请替换对应文件", 422)


async def append_revision(session, order, ids, number, label, note, user):
    revision = MesWorkOrderDrawingRevision(org_id=order.org_id, work_order_id=order.id,
        revision_no=number, revision_label=label, change_note=note, created_by=user.user_id)
    drawing_repository.add(session, revision)
    await session.flush()
    for index, identifier in enumerate(ids):
        drawing_repository.add(session, MesWorkOrderDrawingFile(org_id=order.org_id, revision_id=revision.id,
            attachment_id=identifier, sort_no=index, created_by=user.user_id))
    return revision


async def bind_product_drawings(session, order, body, user):
    ids = body.drawing_attachment_ids
    if not ids:
        return
    # Bind uses the caller's transaction and checks upload ownership, scene and expiry.
    rows = await files.bind(
        session, ids, user=user, org_id=order.org_id, scene_code=DRAWING_SCENE,
        business_type_code=DRAWING_TYPE, business_id=order.id,
    )
    validate_product_files(rows)
    order.drawing_revision_label = (body.drawing_revision_label or "").strip() or None
    await append_revision(session, order, ids, 1, order.drawing_revision_label, "创建货品时上传图纸", user)
