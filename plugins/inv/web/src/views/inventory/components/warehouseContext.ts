import { getToken } from "@/utils/auth";

function contextKey(): string | undefined {
  if (typeof window === "undefined") return;
  const identity = getToken();
  if (!identity?.userId) return;
  return `inv-current-warehouse:${identity.userId}:${identity.sessionExpires ?? "session"}`;
}

export function rememberWarehouse(id: string): void {
  try {
    const key = contextKey();
    if (!key) return;
    if (id) window.sessionStorage.setItem(key, id);
    else window.sessionStorage.removeItem(key);
  } catch { /* 存储不可用时仍按服务端授权选项操作。 */ }
}

export function preferredWarehouseId(options: readonly { id: string }[]): string {
  try {
    const key = contextKey();
    const current = key ? window.sessionStorage.getItem(key) : null;
    if (current && options.some(option => option.id === current)) return current;
    if (current && key) window.sessionStorage.removeItem(key);
  } catch { /* 会话上下文只用于默认选择，不参与权限判断。 */ }
  return options.length === 1 ? options[0].id : "";
}
