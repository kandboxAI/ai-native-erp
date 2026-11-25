from app.framework.catalog import PermissionDef

PERMISSIONS = [PermissionDef("inventory_supplier_price:list", "查询采购价格表", "inventory"),
    PermissionDef("inventory_supplier_price:manage", "维护采购价格表", "inventory")]
