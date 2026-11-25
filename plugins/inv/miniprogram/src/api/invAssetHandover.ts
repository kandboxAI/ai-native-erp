import { requestApi } from "@/api/client";

export type AssetHandoverStatus =
  | "draft"
  | "awaiting_receipt"
  | "completed"
  | "voided";

export interface AssetHandoverLine {
  id: string;
  asset_no_snapshot?: string;
  asset_name_snapshot: string;
  specification_snapshot?: string;
  quantity: string;
  unit_code_snapshot: string;
  disposition_code: "transfer_teacher" | "return_logistics";
  from_location_name: string;
  from_department_name?: string;
  from_custodian_name?: string;
  to_location_name: string;
  to_department_name: string;
  to_custodian_name?: string;
  status_code: "pending" | "rejected" | "received";
  rejection_reason?: string;
  confirmed_at?: string;
  confirmed_by_name?: string;
  can_receive: boolean;
}

export interface AssetHandover {
  id: string;
  handover_no: string;
  source_type_code: "manual" | "teacher_offboarding";
  transferor_name_snapshot: string;
  status_code: AssetHandoverStatus;
  remark?: string;
  submitted_at?: string;
  completed_at?: string;
  created_at: string;
  line_count: number;
  received_count: number;
  pending_count: number;
  rejected_count: number;
  lines: AssetHandoverLine[];
}

interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const listMyAssetHandovers = (data: Record<string, unknown> = {}) =>
  requestApi<PageResult<AssetHandover>>({
    path: "/api/asset-handovers/mine",
    data,
  });

export const getAssetHandover = (id: string) =>
  requestApi<AssetHandover>({ path: `/api/asset-handovers/${id}` });

export const receiveAssetHandoverLine = (id: string, lineId: string) =>
  requestApi<AssetHandover>({
    method: "POST",
    path: `/api/asset-handovers/${id}/lines/${lineId}/receive`,
  });

export const rejectAssetHandoverLine = (
  id: string,
  lineId: string,
  reason: string,
) =>
  requestApi<AssetHandover>({
    method: "POST",
    path: `/api/asset-handovers/${id}/lines/${lineId}/reject`,
    data: { reason },
  });
