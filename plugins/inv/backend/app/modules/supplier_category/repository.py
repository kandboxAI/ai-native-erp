from fastapi import status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import SqlModelCrudRepository

from .models import MdSupplierCategory
from .schemas import SupplierCategoryItem


class SupplierCategoryRepository(SqlModelCrudRepository):
    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        from app.modules.supplier.models import MdSupplier

        used = (
            await session.exec(
                select(MdSupplier.id)
                .where(MdSupplier.category_id == self._normalize_id(item_id), MdSupplier.deleted_at.is_(None))
                .limit(1)
            )
        ).first()
        if used is not None:
            raise AppException("该分类下仍有供应商，不能删除", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)


repository = SupplierCategoryRepository(
    table_model=MdSupplierCategory,
    item_model=SupplierCategoryItem,
    writable_columns=["category_name", "is_active"],
    searchable_columns=["category_name"],
    filterable_columns=["is_active"],
    scope_resource="supplier_category",
)
