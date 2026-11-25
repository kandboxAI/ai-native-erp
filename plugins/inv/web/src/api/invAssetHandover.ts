import { http } from "@/utils/http";

type ApiResponse<T> = { code: number; message: string; data: T };
type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type AssetHandoverLine = {
  id: string;
  asset_register_id: string | null;
  location_item_id: string | null;
  asset_no_snapshot: string | null;
  asset_name_snapshot: string;
  specification_snapshot: string | null;
  quantity: string;
  unit_code_snapshot: string;
  disposition_code: "transfer_teacher" | "return_logistics";
  from_location_id: string | null;
  from_location_name: string;
  from_department_id: string | null;
  from_department_name: string | null;
  from_custodian_user_id: string | null;
  from_custodian_name: string | null;
  to_location_id: string;
  to_location_name: string;
  to_department_id: string;
  to_department_name: string;
  to_custodian_user_id: string | null;
  to_custodian_name: string | null;
  status_code: "pending" | "rejected" | "received";
  rejection_reason: string | null;
  confirmed_at: string | null;
  confirmed_by_name: string | null;
  can_receive: boolean;
};

export type AssetHandover = {
  org_name?: string;
  id: string;
  org_id: string;
  handover_no: string;
  source_type_code: "manual" | "teacher_offboarding";
  source_id: string | null;
  transferor_user_id: string | null;
  transferor_name_snapshot: string;
  status_code: "draft" | "awaiting_receipt" | "completed" | "voided";
  version_no: number;
  remark: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  voided_at: string | null;
  voided_by: string | null;
  void_reason: string | null;
  created_at: string;
  line_count: number;
  received_count: number;
  pending_count: number;
  rejected_count: number;
  lines: AssetHandoverLine[];
  source_context?: { label: string; document_no: string; path: string } | null;
};

export type AssetHandoverLineCreate = {
  asset_register_id: string | null;
  location_item_id: string | null;
  quantity: number;
  disposition_code: "transfer_teacher" | "return_logistics";
  to_location_id: string;
  to_department_id: string;
  to_custodian_user_id: string | null;
};

export const createAssetHandover = (data: {
  org_id: string;
  source_type_code: "manual";
  transferor_user_id: string;
  transferor_name_snapshot: string;
  remark: string | null;
  lines: AssetHandoverLineCreate[];
}) =>
  http.request<ApiResponse<AssetHandover>>("post", "/api/asset-handovers", {
    data
  });

export const listAssetHandovers = (params: Record<string, unknown>) =>
  http.request<ApiResponse<PageResult<AssetHandover>>>(
    "get",
    "/api/asset-handovers",
    { params }
  );

export const listMyAssetHandovers = (params: Record<string, unknown>) =>
  http.request<ApiResponse<PageResult<AssetHandover>>>(
    "get",
    "/api/asset-handovers/mine",
    { params }
  );

export const getAssetHandover = (id: string) =>
  http.request<ApiResponse<AssetHandover>>("get", `/api/asset-handovers/${id}`);

export const updateAssetHandover = (
  id: string,
  data: Record<string, unknown>
) =>
  http.request<ApiResponse<AssetHandover>>(
    "put",
    `/api/asset-handovers/${id}`,
    { data }
  );

export const submitAssetHandover = (id: string, expected_version: number) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/submit`,
    { data: { expected_version } }
  );

export const withdrawAssetHandover = (id: string, expected_version: number) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/withdraw`,
    { data: { expected_version } }
  );

export const voidAssetHandover = (
  id: string,
  expected_version: number,
  reason: string
) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/void`,
    {
      data: { expected_version, reason }
    }
  );

export const receiveAssetHandoverLine = (id: string, lineId: string) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/lines/${lineId}/receive`
  );

export const rejectAssetHandoverLine = (
  id: string,
  lineId: string,
  reason: string
) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/lines/${lineId}/reject`,
    { data: { reason } }
  );

export const resubmitAssetHandoverLine = (
  id: string,
  lineId: string,
  data: {
    expected_version: number;
    quantity: string;
    disposition_code: "transfer_teacher" | "return_logistics";
    to_location_id: string;
    to_department_id: string;
    to_custodian_user_id: string | null;
  }
) =>
  http.request<ApiResponse<AssetHandover>>(
    "post",
    `/api/asset-handovers/${id}/lines/${lineId}/resubmit`,
    { data }
  );
