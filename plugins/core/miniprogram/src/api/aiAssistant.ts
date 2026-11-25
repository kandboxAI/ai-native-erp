import { requestApi as request } from "./client";
import { requestEventStream } from "./eventStream";

export interface AssistantRun {
  run_id: string;
  session_id: string;
  status: "running" | "completed" | "failed" | "interrupted";
  answer: string;
  message: string;
}

export interface AssistantWriteApproval {
  approval_id: string;
  session_id: string;
  run_id: string;
  preview: string;
  expires_at: number;
}

export const listAssistantWriteApprovals = () =>
  request<AssistantWriteApproval[]>({ path: "/api/ai/write-approvals", data: { surface: "miniapp" } });

export const decideAssistantWriteApproval = (approvalId: string, approved: boolean) =>
  request<{ accepted: boolean }>({
    method: "POST",
    path: `/api/ai/write-approvals/${encodeURIComponent(approvalId)}/decision`,
    data: { approved },
  });

export interface AssistantSessionItem {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface AssistantHistory {
  session_id: string;
  title: string;
  messages: {
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string | null;
  }[];
  active_run: AssistantRun | null;
}
export const listAssistantSessions = (offset = 0) =>
  request<{
    items: AssistantSessionItem[];
    has_more: boolean;
    next_offset: number;
  }>({
    path: "/api/ai/sessions",
    data: { offset, limit: 20 },
  });
export const getAssistantHistory = (sessionId: string) =>
  request<AssistantHistory>({
    path: `/api/ai/sessions/${encodeURIComponent(sessionId)}/messages`,
  });
export const deleteAssistantSession = (sessionId: string) =>
  request<{ deleted: boolean }>({
    method: "DELETE",
    path: `/api/ai/sessions/${encodeURIComponent(sessionId)}`,
  });
export const createAssistantSession = () =>
  request<{ session_id: string }>({ method: "POST", path: "/api/ai/sessions" });
export const sendAssistantMessage = (sessionId: string, content: string) =>
  request<AssistantRun>({
    method: "POST",
    path: `/api/ai/sessions/${sessionId}/messages`,
    data: { content },
  });
export const getAssistantRun = (sessionId: string, runId: string) =>
  request<AssistantRun>({
    path: `/api/ai/sessions/${sessionId}/runs/${runId}`,
  });

export const streamAssistantRun = (
  sessionId: string,
  runId: string,
  onAnswer: (answer: string) => void,
) =>
  requestEventStream(
    `/api/ai/sessions/${sessionId}/runs/${runId}/events`,
    (event) => {
      if (event.event === "snapshot" && typeof event.data.answer === "string")
        onAnswer(event.data.answer);
    },
  );
