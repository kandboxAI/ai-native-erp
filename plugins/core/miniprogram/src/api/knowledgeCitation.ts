import { requestApi } from "./client";
import type { KnowledgeSource } from "@/utils/assistantMarkdown";

export interface KnowledgeContent {
  document_name: string;
  page: number;
  page_size: number;
  total_chunks: number;
  chunks: {
    chunk_no: string | null;
    chunk_index: number | null;
    content: string;
    truncated: boolean;
  }[];
}

export function readKnowledgeCitation(source: KnowledgeSource, page?: number) {
  const { chunk_no, ...document } = source;
  return requestApi<KnowledgeContent>({
    method: "POST",
    path: "/api/knowledge/read",
    timeout: 30000,
    data: {
      ...document,
      ...(page === undefined ? { chunk_no } : { page, page_size: 10 }),
    },
  });
}
