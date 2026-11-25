from app.framework.crud.router import build_crud_router

from .schemas import DepartmentCreate, DepartmentListQuery, DepartmentUpdate
from .service import service

router = build_crud_router(
    module_name="department",
    service=service,
    create_model=DepartmentCreate,
    update_model=DepartmentUpdate,
    tags=["department"],
    list_model=DepartmentListQuery,
)
