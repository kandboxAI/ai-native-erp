from app.auth.schemas import AuthenticatedUser
from app.framework.db.session import get_session_context

from .repository import repository
from .schemas import LoginLogListQuery


class LoginLogService:
    async def list(self, params: LoginLogListQuery, current_user: AuthenticatedUser) -> dict:
        async with get_session_context() as session:
            return await repository.list(session, params, current_user.tenant_id)


service = LoginLogService()
