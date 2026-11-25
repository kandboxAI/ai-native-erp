from app.core.exceptions import AppException
from .models import CncDrawingFile


async def drawing_file(session, identifier):
    row = await session.get(CncDrawingFile, identifier)
    if row is None:
        raise AppException("图纸不存在", 404)
    return row
