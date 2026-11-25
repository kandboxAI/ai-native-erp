import type { InjectionKey } from "vue";

/** 页面显式启用；通用外壳不按行业路径或菜单名称猜测样式。 */
export const listPresentationKey: InjectionKey<{
  pageKey: string;
  title: string;
}> = Symbol("list-presentation");

/** 桌面上下文标识使用小写程序键，不直接使用路由的 PascalCase 名称。 */
export function listPageKey(name: unknown): string {
  return `page.${String(name)
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9_.-]/g, "_")
    .slice(0, 90)}`;
}
