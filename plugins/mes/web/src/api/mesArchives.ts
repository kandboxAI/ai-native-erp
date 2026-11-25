import { http } from "@/utils/http";
import type { ApiResponse, MesPage, MesOption } from "./mes";
import { deliveryParams } from "./mesDelivery";

export type ArchiveKind =
  "customers" | "project-stages" | "processes" | "equipment" | "requirements";
export type ArchiveRecord = {
  id: string;
  org_id: string;
  record_no: string;
  record_name: string;
  version_no: number;
  sort_no: number;
  is_active: boolean;
  description?: string;
  reconciliation_mode_code?: string;
  pricing_description?: string;
  processing_type_code?: string;
  project_stage_id?: string;
  project_stage_label?: string;
  requirement_id?: string;
  requirement_label?: string;
  process_id?: string;
  process_label?: string;
  process_ids?: string[];
  process_labels?: Record<string, string>;
  work_center_name?: string;
  is_piecework?: boolean;
  is_quality_required?: boolean;
  is_equipment_required?: boolean | null;
  execution_kind_code?: string | null;
  previous_process_ids?: string[];
  previous_process_labels?: Record<string, string>;
};
export type ArchiveOption = MesOption & {
  record_no: string;
  record_name: string;
  description?: string;
  process_id?: string;
  process_ids?: string[];
  project_stage_id?: string;
  requirement_id?: string;
  work_center_name?: string;
  is_quality_required?: boolean;
  previous_process_ids?: string[];
  previous_process_names?: string;
};
export const archivePermission = (kind: ArchiveKind) =>
  `mes:archive:${{ customers: "customer", "project-stages": "stage", processes: "process", equipment: "equipment", requirements: "requirement" }[kind]}:manage`;
export const getArchives = (
  kind: ArchiveKind,
  params: Record<string, unknown>,
) =>
  http.request<ApiResponse<MesPage<ArchiveRecord>>>(
    "get",
    `/api/mes/archives/${kind}`,
    { params: deliveryParams(params) },
  );
export const saveArchive = (
  kind: ArchiveKind,
  id: string | undefined,
  data: unknown,
) =>
  http.request<ApiResponse<ArchiveRecord>>(
    id ? "put" : "post",
    `/api/mes/archives/${kind}${id ? `/${id}` : ""}`,
    { data },
  );
export const archiveOrganizations = async (kind: ArchiveKind, keyword = "") => {
  const result = await http.request<
    ApiResponse<{ id: string; org_name: string }[]>
  >("get", `/api/mes/archives/${kind}/organizations`, { params: { keyword } });
  return result.data.map((row) => ({ value: row.id, label: row.org_name }));
};
export async function archiveOptions(
  kind: ArchiveKind,
  org_id: string,
  keyword = "",
  equipmentFilter: {
    applicable_process_id?: string;
    generic_equipment_only?: boolean;
  } = {},
): Promise<ArchiveOption[]> {
  if (!org_id) return [];
  const result = await http.request<
    ApiResponse<MesPage<Omit<ArchiveOption, "value"> & { id: string }>>
  >("get", `/api/mes/archive-options/${kind}`, {
    params: { org_id, keyword, page_size: 50, ...equipmentFilter },
  });
  return result.data.items.map((row) => ({ ...row, value: row.id }));
}

export type SupplierPrice = {
  id: string;
  org_id: string;
  supplier_id: string;
  item_id: string;
  currency_code: string;
  unit_code: string;
  unit_price: string | number;
  valid_from: string;
  valid_to?: string;
  is_active: boolean;
  version_no: number;
  note?: string;
  supplier_no?: string;
  supplier_name?: string;
  item_no?: string;
  item_name?: string;
};
export const getSupplierPrices = (params: Record<string, unknown>) =>
  http.request<ApiResponse<MesPage<SupplierPrice>>>(
    "get",
    "/api/inventory_supplier_price",
    { params: deliveryParams(params) },
  );
export const saveSupplierPrice = (id: string | undefined, data: unknown) =>
  http.request<ApiResponse<SupplierPrice>>(
    id ? "put" : "post",
    `/api/inventory_supplier_price${id ? `/${id}` : ""}`,
    { data },
  );
export async function priceOrganizations(keyword = "") {
  const result = await http.request<
    ApiResponse<{ id: string; org_name: string }[]>
  >("get", "/api/inventory_supplier_price/organizations", {
    params: { keyword },
  });
  return result.data.map((row) => ({ value: row.id, label: row.org_name }));
}
export async function priceOptions(kind: "items" | "suppliers", keyword = "") {
  const result = await http.request<
    ApiResponse<{ id: string; label: string }[]>
  >("get", `/api/inventory_supplier_price/options/${kind}`, {
    params: { keyword },
  });
  return result.data.map((row) => ({ value: row.id, label: row.label }));
}
