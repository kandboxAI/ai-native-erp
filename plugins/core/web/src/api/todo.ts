import { http } from "@/utils/http";

export type TodoAction = {
  key: string;
  label: string;
  input?: boolean;
  confirm?: boolean;
};
export type TodoRow = {
  is_projection?: boolean;
  targets?: { web?: string; miniapp?: string };
  web_unavailable_reason?: string;
  id: string;
  todo_type_key: string;
  type_label: string;
  source_id: string;
  title: string;
  avatar_url?: string | null;
  summary: string;
  status_code: string;
  assignee_status_code: string;
  priority_code: string;
  arrived_at: string;
  due_at: string | null;
  is_overdue: boolean;
  path: string;
  actions: TodoAction[];
  ai_analysis?: string;
  ai_priority_reason?: string;
  ai_analysis_status_code?: string;
};
type Result<T> = { code: number; data: T };
export function recommendTodoPriority() {
  return http.request<Result<{ items: TodoRow[]; total: number }>>(
    "post",
    "/api/todo/priority-recommendations",
    { timeout: 180000 }
  );
}
export function listTodos(
  params: {
    page?: number;
    page_size?: number;
    keyword?: string;
    status_code?: string;
    include_overdue?: boolean;
  } = {}
) {
  return http.request<Result<{ items: TodoRow[]; total: number }>>(
    "get",
    "/api/todo/mine",
    { params }
  );
}
export function getTodo(id: string) {
  return http.request<Result<TodoRow>>("get", `/api/todo/detail/${id}`);
}
export function actOnTodo(id: string, action: string, comment = "") {
  return http.request<Result<Record<string, unknown>>>(
    "post",
    `/api/todo/${id}/actions/${action}`,
    { data: { comment } }
  );
}
export function createTodo(data: {
  todo_type_key: string;
  source_id: string;
  round_key: string;
  user_ids: string[];
  role_ids: string[];
  notify_assignees: boolean;
}) {
  return http.request<Result<{ id: string }>>("post", "/api/todo", { data });
}
export function todoAssignmentOptions(org_id: string, keyword = "") {
  return http.request<
    Result<{
      users: { value: string; label: string }[];
      roles: { value: string; label: string }[];
    }>
  >("get", "/api/todo/assignment-options", { params: { org_id, keyword } });
}
