import { requestApi } from "@/api/client";

export type RequisitionStatus =
  | "submitted"
  | "approved"
  | "rejected"
  | "issued"
  | "withdrawn"
  | "pending_receipt"
  | "receipt_exception"
  | "received";

export interface MaterialOption {
  id: string;
  warehouse_id: string;
  warehouse_no: string;
  warehouse_name: string;
  item_no: string;
  item_name: string;
  category_name?: string;
  specification?: string;
  unit_code: string;
  unit_name: string;
  available_quantity: string;
}

export interface RequisitionApprovalContext {
  requisition_approval_department_id?: string | null;
  requisition_approval_department_name?: string | null;
  requisition_approval_label?: string;
}

export interface RequisitionWarehouseOption extends RequisitionApprovalContext {
  id: string;
  warehouse_no: string;
  warehouse_name: string;
}

export interface RequisitionLine {
  id: string;
  item_id: string;
  item_no_snapshot: string;
  item_name_snapshot: string;
  specification_snapshot?: string;
  unit_code_snapshot: string;
  unit_name: string;
  quantity: string;
  issued_quantity?: string | null;
  requires_asset_selection?: boolean;
}

export interface RequisitionEvent {
  id: string;
  event_type_code: string;
  from_status_code?: string;
  to_status_code: RequisitionStatus;
  note?: string;
  operator_name_snapshot: string;
  created_at: string;
  photos: RequisitionPhoto[];
  receipt_lines: ReceiptLine[];
}

export interface MaterialRequisition extends RequisitionApprovalContext {
  custody_location_note?: string | null;
  personal_custody_assets?: Array<{ asset_no: string | null; item_id: string; quantity: string }>;
  id: string;
  request_no: string;
  submission_batch_no: string;
  warehouse_id: string;
  warehouse_no?: string;
  warehouse_name?: string;
  applicant_name_snapshot: string;
  applicant_org_id?: string | null;
  applicant_org_name_snapshot?: string | null;
  department_name_snapshot?: string;
  purpose: string;
  status_code: RequisitionStatus;
  approval_note?: string;
  approved_by_name_snapshot?: string;
  approved_at?: string;
  issued_by_name_snapshot?: string;
  issued_at?: string;
  stock_order_no?: string;
  can_receive?: boolean;
  can_issue?: boolean;
  can_withdraw?: boolean;
  received_by_name_snapshot?: string | null;
  received_at?: string | null;
  version_no: number;
  created_at: string;
  updated_at: string;
  lines: RequisitionLine[];
  events: RequisitionEvent[];
}

interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const getMaterialRequisitionOptions = (data: { mine?: boolean } = {}) =>
  requestApi<{
    statuses: Array<{ value: string; label: string }>;
    warehouses: RequisitionWarehouseOption[];
  }>({ path: "/api/inventory_requisition/options", data });

export const listAvailableMaterials = (keyword = "", warehouseId?: string) =>
  requestApi<{ items: MaterialOption[] }>({
    path: "/api/inventory_requisition/materials",
    data: {
      keyword: keyword || undefined,
      warehouse_id: warehouseId || undefined,
    },
  });

export const createMaterialRequisition = (data: {
  custody_location_note?: string;
  warehouse_id?: string;
  purpose: string;
  photo_file_ids?: string[];
  lines: Array<{ item_id: string; warehouse_id: string; quantity: number }>;
}) =>
  requestApi<{
    submission_batch_no: string;
    requests: MaterialRequisition[];
  }>({
    method: "POST",
    path: "/api/inventory_requisition/create",
    data,
  });

export const listMyMaterialRequisitions = (data: Record<string, any> = {}) =>
  requestApi<PageResult<MaterialRequisition>>({
    path: "/api/inventory_requisition/my",
    data,
  });

export const listManagedMaterialRequisitions = (
  data: Record<string, any> = {},
) =>
  requestApi<PageResult<MaterialRequisition>>({
    path: "/api/inventory_requisition/list",
    data,
  });

export const getMaterialRequisition = (id: string) =>
  requestApi<MaterialRequisition>({
    path: `/api/inventory_requisition/detail/${id}`,
  });

export const approveMaterialRequisition = (
  id: string,
  version_no: number,
  note?: string,
) =>
  requestApi<MaterialRequisition>({
    method: "POST",
    path: `/api/inventory_requisition/approve/${id}`,
    data: { version_no, note: note || null },
  });

export const rejectMaterialRequisition = (
  id: string,
  version_no: number,
  note: string,
) =>
  requestApi<MaterialRequisition>({
    method: "POST",
    path: `/api/inventory_requisition/reject/${id}`,
    data: { version_no, note },
  });

export const withdrawMaterialRequisition = (id: string, version_no: number) =>
  requestApi<MaterialRequisition>({
    method: "POST",
    path: `/api/inventory_requisition/withdraw/${id}`,
    data: { version_no },
  });

export interface RequisitionAssetBinding {
  id: string;
  quantity: string;
  asset_no: string | null;
  serial_no?: string | null;
  management_mode: "individual" | "batch";
  stock_status_code: string;
  registration_status_code: string;
  status_code: string;
}

export const listRequisitionAssetBindings = (data: {
  item_id: string;
  warehouse_id: string;
  keyword?: string;
  page: number;
  page_size: number;
}) => requestApi<PageResult<RequisitionAssetBinding>>({ path: "/api/asset/stock-bindings", data });

export interface RequisitionIssuePayload {
  version_no: number;
  note?: string;
  photo_file_ids: string[];
  lines: Array<{
    line_id: string;
    quantity: string;
    tracking?: { asset: { selections: Array<{ binding_id: string; quantity: string }> } };
  }>;
}

export const issueMaterialRequisition = (id: string, data: RequisitionIssuePayload) =>
  requestApi<MaterialRequisition>({ method: "POST", path: `/api/inventory_requisition/issue/${id}`, data });

export type RequisitionPhoto = { id: string; url: string; file_name?: string };
export type ReceiptLine = {
  line_id: string;
  received_quantity: number | string;
  exception_quantity: number | string;
  exception_type_code:
    "shortage" | "wrong_item" | "damaged" | "not_received" | null;
};
export type ReceiptPayload = {
  version_no: number;
  note?: string;
  photo_file_ids?: string[];
  lines: ReceiptLine[];
};
export const requisitionStatusLabels: Record<string, string> = {
  submitted: "待审批",
  approved: "待发放",
  rejected: "已驳回",
  withdrawn: "已撤回",
  issued: "已发放（未记录签收）",
  pending_receipt: "待签收",
  receipt_exception: "收货异常",
  received: "已签收",
};
export const requisitionEventLabels: Record<string, string> = {
  submit: "提交申请",
  approve: "审批通过",
  reject: "驳回申请",
  withdraw: "撤回申请",
  issue: "发放出库",
  receive: "确认收货",
  receipt_exception: "反馈收货异常",
  resolve_exception: "登记异常处理",
};
export const receiptExceptionLabels: Record<string, string> = {
  shortage: "少发",
  wrong_item: "错发",
  damaged: "破损",
  not_received: "未收到",
};
export const receiveMaterialRequisition = (
  id: string,
  data: ReceiptPayload,
  exception = false,
) =>
  requestApi<MaterialRequisition>({
    method: "POST",
    path: `/api/inventory_requisition/${exception ? "receipt-exception" : "receive"}/${id}`,
    data,
  });
