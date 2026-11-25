"""统一文件服务的受控原件读取查询。"""

from sqlalchemy import select

from .models import FileAttachment, STATUS_BOUND


async def upload_for_ingest(session, file_id):
    return await session.get(FileAttachment, file_id, with_for_update=True)


async def file_for_read(session, file_id):
    return await session.get(FileAttachment, file_id)

async def latest_bound_for_business(session, business_type_code, business_id, scene_code):
    statement = select(FileAttachment).where(
        FileAttachment.business_type_code == business_type_code,
        FileAttachment.business_id == business_id,
        FileAttachment.scene_code == scene_code,
        FileAttachment.status_code == STATUS_BOUND,
    ).order_by(FileAttachment.bound_at.desc(), FileAttachment.id.desc()).limit(1)
    return (await session.exec(statement)).scalars().first()


async def latest_bound_for_businesses(session, business_type_code, business_ids, scene_code):
    statement = select(FileAttachment).where(
        FileAttachment.business_type_code == business_type_code,
        FileAttachment.business_id.in_(business_ids),
        FileAttachment.scene_code == scene_code,
        FileAttachment.status_code == STATUS_BOUND,
    ).distinct(FileAttachment.business_id).order_by(
        FileAttachment.business_id, FileAttachment.bound_at.desc(), FileAttachment.id.desc()
    )
    return (await session.exec(statement)).scalars().all()
