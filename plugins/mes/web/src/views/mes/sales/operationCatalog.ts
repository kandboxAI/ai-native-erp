import type { OperationCatalog } from "../work-orders/operationCatalog";
import type { MesProcessTemplate } from "@plugins/mes/web/src/api/mes";
import type { ArchiveOption } from "@plugins/mes/web/src/api/mesArchives";
import { routeOperations } from "../work-orders/routeDefinitions";

export const previewOrgId = "preview-sales-org";
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));

/** 仅供未接入后端的订单流程使用；所有标识为临时值，绝不调用 HTTP。 */
export function createSalesOperationCatalog(): OperationCatalog & {
  reset: () => void;
} {
  const processes: ArchiveOption[] = [
    {
      value: "preview-cut",
      label: "演示 · 下料",
      record_no: "DEMO-CUT",
      record_name: "下料",
    },
    {
      value: "preview-cnc",
      label: "演示 · CNC 加工",
      record_no: "DEMO-CNC",
      record_name: "CNC 加工",
      previous_process_ids: ["preview-cut"],
      previous_process_names: "下料",
    },
    {
      value: "preview-qa",
      label: "演示 · 检验",
      record_no: "DEMO-QA",
      record_name: "检验",
      is_quality_required: true,
    },
  ];
  const equipment: ArchiveOption[] = [
    {
      value: "preview-cnc-01",
      label: "演示 · CNC-01",
      record_no: "CNC-01",
      record_name: "演示数控加工中心",
      process_id: "preview-cnc",
      work_center_name: "演示机加工车间",
    },
  ];
  let routes: MesProcessTemplate[] = [],
    serial = 0;
  function reset() {
    serial = 0;
    routes = [
      {
        id: "preview-route-cnc",
        org_id: previewOrgId,
        template_no: "DEMO-CNC",
        template_name: "演示 · 下料—加工—检验",
        version_no: 1,
        is_active: true,
        operations: processes.map((process, index) => ({
          operation_no: String((index + 1) * 10),
          operation_name: process.record_name,
          process_id: process.value,
          is_quality_required: !!process.is_quality_required,
          standard_minutes_per_unit: [3, 30, 5][index],
        })),
      },
    ];
  }
  reset();
  const matches = (record: unknown, keyword = "") =>
    JSON.stringify(record).toLowerCase().includes(keyword.trim().toLowerCase());
  return {
    reset,
    async loadTemplates(params) {
      if (params.org_id !== previewOrgId) return [];
      return copy(
        routes.filter(
          (route) =>
            route.org_id === params.org_id &&
            route.is_active &&
            (!route.product_item_id ||
              route.product_item_id === params.product_item_id) &&
            matches([route.template_no, route.template_name], params.keyword),
        ),
      );
    },
    async saveTemplate(template) {
      if (template.org_id !== previewOrgId)
        throw Error("只能保存当前演示组织的路线");
      if (!template.template_no.trim() || !template.template_name.trim())
        throw Error("请填写路线编号和名称");
      if (
        routes.some(
          (route) => route.template_no === template.template_no.trim(),
        )
      )
        throw Error("路线编号已存在");
      const id = `preview-route-${++serial}`;
      routes.push(
        copy({
          ...template,
          id,
          template_no: template.template_no.trim(),
          template_name: template.template_name.trim(),
          version_no: 1,
          operations: routeOperations(template.operations),
        }),
      );
      return { id, version_no: 1 };
    },
    async loadArchives(kind, org, keyword = "") {
      if (org !== previewOrgId) return [];
      const records =
        kind === "processes"
          ? processes
          : kind === "equipment"
            ? equipment
            : kind === "requirements"
              ? [
                  {
                    value: "preview-finish",
                    label: "演示 · 去毛刺要求",
                    record_no: "DEMO-FINISH",
                    record_name: "去毛刺要求",
                    description: "去除锐边毛刺，按图纸要求检查。",
                  },
                ]
              : [];
      return copy(
        records.filter((row) =>
          matches([row.record_no, row.record_name], keyword),
        ),
      );
    },
    async loadAssignees(keyword = "", org) {
      return org === previewOrgId && matches("演示技术员", keyword)
        ? [{ value: "preview-worker", label: "演示技术员" }]
        : [];
    },
  };
}
