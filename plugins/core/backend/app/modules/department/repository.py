from app.framework.crud.repository import SqlModelCrudRepository

from .models import SysDepartment
from .schemas import DepartmentItem

repository = SqlModelCrudRepository(
    table_model=SysDepartment,
    item_model=DepartmentItem,
    writable_columns=[
        "org_id",
        "department_no",
        "department_name",
        "parent_id",
        "manager_user_id",
        "sort_no",
        "is_active",
        "remark",
    ],
    searchable_columns=["department_no", "department_name", "remark"],
    filterable_columns=["org_id", "is_active"],
    scope_resource="department",
    organization_write_kind="any",
)
