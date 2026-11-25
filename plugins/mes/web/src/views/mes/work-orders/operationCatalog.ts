import {
  getMesProcessTemplateOptions,
  saveMesProcessTemplate,
  getMesAssigneeOptions,
  type MesProcessTemplate,
} from "@plugins/mes/web/src/api/mes";
import { archiveOptions } from "@plugins/mes/web/src/api/mesArchives";

/** 编辑器只依赖档案读写契约；保存工单由调用页面负责。 */
export type OperationCatalog = {
  loadTemplates: (
    params: Parameters<typeof getMesProcessTemplateOptions>[0],
  ) => Promise<MesProcessTemplate[]>;
  saveTemplate: (
    template: MesProcessTemplate,
  ) => Promise<{ id: string; version_no: number }>;
  loadArchives: typeof archiveOptions;
  loadAssignees: typeof getMesAssigneeOptions;
};

export const systemOperationCatalog: OperationCatalog = {
  loadTemplates: async (params) =>
    (await getMesProcessTemplateOptions(params)).data.items,
  saveTemplate: async (template) =>
    (await saveMesProcessTemplate(template)).data,
  loadArchives: archiveOptions,
  loadAssignees: getMesAssigneeOptions,
};
