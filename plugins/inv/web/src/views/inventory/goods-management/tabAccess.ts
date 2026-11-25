/** 页签依赖各自查询权限，菜单授权不代替业务操作授权。 */
const TAB_PERMISSIONS = {
  items: "inventory_product:list",
  categories: "inventory_product_category:list",
  warehouses: "inventory_warehouse:list",
  locations: "inventory_location:list",
  suppliers: "supplier:list",
  supplierCategories: "supplier_category:list"
} as const;

export function accessibleMaterialTabs(
  hasPermission: (permission: string) => boolean
): string[] {
  return Object.entries(TAB_PERMISSIONS)
    .filter(([, permission]) => hasPermission(permission))
    .map(([tab]) => tab);
}

export function selectMaterialTab(
  current: string,
  available: readonly string[]
): string {
  return available.includes(current) ? current : (available[0] ?? "");
}
