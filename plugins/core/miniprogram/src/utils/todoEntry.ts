import type { TodoItem } from "@/api/todo";

export function todoMiniappTarget(todo: TodoItem) {
  const target = todo.targets.miniapp;
  const page = target?.split("?")[0];
  if (page && page !== "/pages/todo-handle/index" &&
      __DEPLOYED_MINIAPP_PAGES__.includes(page)) return target;
}

export function todoEntryTarget(todo: TodoItem) {
  const target = todoMiniappTarget(todo);
  if (todo.is_projection || !isTodoRecordId(todo.id)) return target;
  if (target && todo.open_miniapp_directly && !todo.actions.length) return target;
  return `/pages/todo-handle/index?id=${encodeURIComponent(todo.id)}`;
}

export function isTodoRecordId(id: string) {
  return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id);
}

export function openTodoEntry(target: string | undefined, title: string, summary: string) {
  if (target) {
    uni.navigateTo({ url: target });
    return;
  }
  uni.showModal({
    title: "待办详情",
    content: [title, summary, "请登录 ERP 管理端，在工作台打开此待办办理。"]
      .filter(Boolean).join("\n"),
    showCancel: false,
    confirmText: "知道了",
  });
}

const STORAGE_KEY = "erp_pending_todo_entry";
const ROUTES = new Set(["pages/todo-handle/index", "pages/todo-detail/index"]);

/** 仅保留待办页面和编号，登录后仍由详情接口校验当前账号权限。 */
export function rememberTodoEntry(path: string, id: string) {
  const route = path.replace(/^\//, "");
  if (ROUTES.has(route) && isTodoRecordId(id)) {
    uni.setStorageSync(STORAGE_KEY, { route, id });
  }
}

export function takeTodoEntry(): string | undefined {
  const entry = uni.getStorageSync(STORAGE_KEY);
  uni.removeStorageSync(STORAGE_KEY);
  if (
    entry &&
    ROUTES.has(entry.route) &&
    typeof entry.id === "string" &&
    isTodoRecordId(entry.id)
  ) {
    return `/${entry.route}?id=${encodeURIComponent(entry.id)}`;
  }
}
