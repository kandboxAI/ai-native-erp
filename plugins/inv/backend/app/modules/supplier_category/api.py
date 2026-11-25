from app.framework.crud.router import build_crud_router

from .schemas import SupplierCategoryCreate, SupplierCategoryListQuery, SupplierCategoryUpdate
from .service import service

router = build_crud_router(
    module_name="supplier_category",
    service=service,
    create_model=SupplierCategoryCreate,
    update_model=SupplierCategoryUpdate,
    tags=["supplier_category"],
    list_model=SupplierCategoryListQuery,
)
