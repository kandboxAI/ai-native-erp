import { requestApi } from "./client";

export interface TodoItem {
  id: string;
  is_projection?: boolean;
  title: string;
  avatar_url?: string | null;
  summary: string;
  type_label: string;
  status_code: string;
  assignee_status_code: string;
  arrived_at: string;
  due_at: string | null;
  is_overdue: boolean;
  targets: { web?: string; miniapp?: string };
  open_miniapp_directly?: boolean;
  ai_analysis?: string;
  ai_priority_reason?: string;
  actions: { key: string; label: string; input?: boolean }[];
}

export function listUnifiedTodos(page = 1, pageSize = 20) {
  return requestApi<{
    items: TodoItem[];
    total: number;
    page: number;
    page_size: number;
  }>({
    path: "/api/todo/mine",
    data: { page, page_size: pageSize, sort_by: "arrived_at" },
  });
}

export function getTodo(id: string) {
  return requestApi<TodoItem>({
    path: `/api/todo/detail/${encodeURIComponent(id)}`,
  });
}

export function recommendTodoPriority() {
  return requestApi<{ items: TodoItem[]; total: number }>({
    path: "/api/todo/priority-recommendations",
    method: "POST",
    timeout: 180000,
  });
}

export function actOnTodo(id: string, action: string, comment = "") {
  return requestApi({
    path: `/api/todo/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`,
    method: "POST",
    data: { comment },
  });
}
