from app.framework.crud.router import build_crud_router

from .schemas import DictionaryItemCreate, DictionaryItemListQuery, DictionaryItemUpdate
from .service import service

router = build_crud_router(
    module_name="dictionary_item",
    service=service,
    create_model=DictionaryItemCreate,
    update_model=DictionaryItemUpdate,
    tags=["dictionary_item"],
    list_model=DictionaryItemListQuery,
)
