from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import repository

service = CrudService(repository=repository, session_getter=get_session_context)
