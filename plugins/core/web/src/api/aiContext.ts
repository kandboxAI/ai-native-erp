import { http } from "@/utils/http";

type Response<T> = { code: number; message: string; data: T };
export type AiContext = {
  instructions: string;
  facts: string[];
  role_names: string[];
  applied_templates: { id: string; template_name: string }[];
  available_templates: PersonalRoleTemplate[];
  position_knowledge: PositionKnowledge[];
  prompt: string;
};
export type PositionKnowledge = {
  position_id: string;
  position_name: string;
  knowledge_base_id: string;
  knowledge_base_name: string;
  overview_document_id: string | null;
  version_no: number | null;
  summary: string;
  can_contribute: boolean;
};
export type PersonalRoleTemplate = {
  id: string;
  template_name: string;
  instructions: string;
  is_active: boolean;
};
export type PromptTemplate = {
  id?: string;
  template_name: string;
  role_id: string;
  instructions: string;
  is_active: boolean;
};
export type TemplateConfiguration = {
  templates: PromptTemplate[];
  roles: { id: string; name: string }[];
  variables: string[];
};
const base = "/api/ai/context";
export const getAiContext = () =>
  http.request<Response<AiContext>>("get", `${base}/mine`);
export const saveAiInstructions = (instructions: string) =>
  http.request<Response<AiContext>>("put", `${base}/mine`, {
    data: { instructions }
  });
export const getAiTemplates = () =>
  http.request<Response<TemplateConfiguration>>("get", `${base}/templates`);
export const saveMyAiTemplate = (templateId: string, isActive: boolean) =>
  http.request<Response<AiContext>>(
    "put",
    `${base}/mine/templates/${templateId}`,
    {
      data: { is_active: isActive }
    }
  );
export const saveAiTemplate = (template: PromptTemplate) => {
  const { id, ...data } = template;
  return http.request<Response<PromptTemplate>>(
    id ? "put" : "post",
    `${base}/templates${id ? `/${id}` : ""}`,
    { data }
  );
};
