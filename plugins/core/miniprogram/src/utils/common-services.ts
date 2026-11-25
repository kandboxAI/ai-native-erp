import type { RoleServiceItem } from "@/config/roleServices";

export type ServiceUsage = Record<string, { count: number; last_used_at: number }>;

export function normalizeServiceUsage(value: unknown): ServiceUsage {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter(([path, entry]) =>
    path.startsWith("/pages/") && entry &&
    Number.isSafeInteger(entry.count) && entry.count > 0 &&
    Number.isFinite(entry.last_used_at) && entry.last_used_at >= 0,
  ));
}

export function commonServices(services: RoleServiceItem[], usage: ServiceUsage): RoleServiceItem[] {
  // 仅排序当前授权目录，无使用记录时保留服务端顺序。
  return services.map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const first = a.item.url ? usage[a.item.url] : undefined;
      const second = b.item.url ? usage[b.item.url] : undefined;
      return (second?.count || 0) - (first?.count || 0) ||
        (second?.last_used_at || 0) - (first?.last_used_at || 0) || a.index - b.index;
    })
    .map(({ item }) => item);
}
