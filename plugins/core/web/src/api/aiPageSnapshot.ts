import { http } from "@/utils/http";

export interface ResolvedPageSnapshot {
  page_key: string;
  sections: Array<{
    key: string;
    title: string;
    data_source: "live" | "demo";
    updated_at: string;
    state: "loaded" | "empty";
    scope: string;
    metrics: Array<{
      key: string;
      label: string;
      value: string | number | null;
      unit: string;
      state?: "withheld_or_unavailable";
    }>;
  }>;
  notice: string;
}

export const resolveAiPageSnapshot = (pageKey: string, receipts: string[]) =>
  http.request<{ data: ResolvedPageSnapshot }>(
    "post",
    "/api/ai/context/page-snapshot",
    {
      data: { page_key: pageKey, receipts }
    }
  );
