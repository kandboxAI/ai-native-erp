"""物资与库存、供应商的全部接口（由 app/framework/router.py 挂载）。"""

from fastapi import APIRouter

from app.modules.supplier.api import router as supplier_router
from app.modules.supplier_category.api import router as supplier_category_router

from .imports.api import category_import_router, item_import_router, stock_import_router
from .meta_api import router as meta_router
from .products.api import category_router, item_router
from .stock.api import alert_router, movement_router, setting_router, stock_router
from .stock_order.api import router as stock_order_router
from .stock_order.api import type_router
from .warehouse.api import warehouse_router
from app.modules.inventory_pricing.api import router as price_router

# 导入路由（/import/...）先于 CRUD 路由注册，避免被 /detail/{id} 等路径吞掉
routers: list[APIRouter] = [
    category_import_router,
    item_import_router,
    stock_import_router,
    meta_router,
    category_router,
    item_router,
    warehouse_router,
    stock_router,
    alert_router,
    setting_router,
    movement_router,
    type_router,
    stock_order_router,
    supplier_category_router,
    supplier_router,
    price_router,
]

router = APIRouter()
for child_router in routers:
    router.include_router(child_router)
