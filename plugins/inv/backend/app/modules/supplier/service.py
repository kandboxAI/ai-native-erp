from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import repository
from .schemas import SupplierBankAccountItem, SupplierBankAccountWrite, SupplierOption


class SupplierService(CrudService):
    async def options(self, *, keyword: str | None, active_only: bool) -> list[SupplierOption]:
        async with get_session_context() as session:
            return await repository.options(session, keyword=keyword, active_only=active_only)

    async def _require_supplier(self, session, supplier_id: UUID, current_user: AuthenticatedUser) -> None:
        from fastapi import status

        from app.core.exceptions import AppException

        if await repository.detail(session, str(supplier_id), current_user) is None:
            raise AppException("供应商不存在", status_code=status.HTTP_404_NOT_FOUND)

    async def list_bank_accounts(self, supplier_id: UUID, current_user: AuthenticatedUser) -> list[SupplierBankAccountItem]:
        async with get_session_context() as session:
            await self._require_supplier(session, supplier_id, current_user)
            return await repository.list_bank_accounts(session, supplier_id)

    async def save_bank_account(
        self,
        supplier_id: UUID,
        payload: SupplierBankAccountWrite,
        current_user: AuthenticatedUser,
        account_id: UUID | None = None,
    ) -> SupplierBankAccountItem:
        async with get_session_context() as session:
            await self._require_supplier(session, supplier_id, current_user)
            return await repository.save_bank_account(session, supplier_id, payload.model_dump(), current_user.user_id, account_id)

    async def delete_bank_account(self, supplier_id: UUID, account_id: UUID, current_user: AuthenticatedUser) -> bool:
        async with get_session_context() as session:
            return await repository.delete_bank_account(session, supplier_id, account_id, current_user.user_id)


service = SupplierService(repository=repository, session_getter=get_session_context)
