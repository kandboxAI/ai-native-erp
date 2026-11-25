import { http } from "@/utils/http";

type ApiResponse<T> = { code: number; message: string; data: T };
export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type RequisitionLine = {
  id: string;
  item_id: string;
  item_no_snapshot: string;
  item_name_snapshot: string;
  specification_snapshot: string | null;
  unit_code_snapshot: string;
  unit_name: string;
  quantity: string;
  issued_quantity?: string | null;
  requires_asset_selection?: boolean;
};

export type RequisitionEvent = {
  id: string;
  event_type_code: string;
  from_status_code: string | null;
  to_status_code: string;
  note: string | null;
  operator_name_snapshot: string;
  created_at: string;
  photos: RequisitionPhoto[];
  receipt_lines: ReceiptLine[];
};

export type RequisitionWarehouseOption = {
  requisition_approval_department_id?: string | null;
  requisition_approval_department_name?: string | null;
  requisition_approval_label?: string;
  id: string;
  warehouse_no: string;
  warehouse_name: string;
};

export type MaterialOption = {
  id: string;
  warehouse_id: string;
  warehouse_no: string;
  warehouse_name: string;
  item_no: string;
  item_name: string;
  category_name: string | null;
  specification: string | null;
  unit_code: string;
  unit_name: string;
  available_quantity: string;
};

export type MaterialRequisition = {
  requisition_approval_department_id?: string | null;
  requisition_approval_department_name?: string | null;
  requisition_approval_label?: string;
  extension_fields?: Array<{ label: string; value: string }>;
  custody_location_note?: string | null;
  personal_custody_assets?: Array<{ asset_no: string | null; item_id: string; quantity: string }>;
  org_id: string;
  id: string;
  request_no: string;
  submission_batch_no: string;
  warehouse_id: string;
  warehouse_no: string | null;
  warehouse_name: string | null;
  applicant_name_snapshot: string;
  applicant_org_id?: string | null;
  applicant_org_name_snapshot?: string | null;
  department_id: string | null;
  department_name_snapshot: string | null;
  purpose: string;
  status_code:
    | "submitted"
    | "approved"
    | "rejected"
    | "issued"
    | "withdrawn"
    | "pending_receipt"
    | "receipt_exception"
    | "received";
  approval_note: string | null;
  approved_by_name_snapshot: string | null;
  approved_at: string | null;
  issued_by_name_snapshot: string | null;
  issued_at: string | null;
  stock_order_id: string | null;
  stock_order_no: string | null;
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
};

export const getMaterialRequisitionOptions = () =>
  http.request<
    ApiResponse<{
      statuses: Array<{ value: string; label: string }>;
      warehouses: RequisitionWarehouseOption[];
    }>
  >("get", "/api/inventory_requisition/options");

export const listAvailableMaterials = (params: {
  keyword?: string;
  warehouse_id: string;
}) =>
  http.request<ApiResponse<{ items: MaterialOption[] }>>(
    "get",
    "/api/inventory_requisition/materials",
    { params },
  );

export const createMaterialRequisition = (data: {
  custody_location_note?: string;
  warehouse_id: string;
  purpose: string;
  photo_file_ids?: string[];
  lines: Array<{
    item_id: string;
    warehouse_id: string;
    quantity: number;
  }>;
}) =>
  http.request<
    ApiResponse<{
      submission_batch_no: string;
      requests: MaterialRequisition[];
    }>
  >("post", "/api/inventory_requisition/create", { data });

export const listMaterialRequisitions = (params: Record<string, any>) =>
  http.request<ApiResponse<PageResult<MaterialRequisition>>>(
    "get",
    "/api/inventory_requisition/list",
    { params },
  );

export const getMaterialRequisition = (id: string) =>
  http.request<ApiResponse<MaterialRequisition>>(
    "get",
    `/api/inventory_requisition/detail/${id}`,
  );

const action = (name: string, id: string, data: Record<string, any>) =>
  http.request<ApiResponse<MaterialRequisition>>(
    "post",
    `/api/inventory_requisition/${name}/${id}`,
    { data },
  );

export const approveMaterialRequisition = (
  id: string,
  version_no: number,
  note?: string,
) => action("approve", id, { version_no, note: note || null });
export const rejectMaterialRequisition = (
  id: string,
  version_no: number,
  note: string,
) => action("reject", id, { version_no, note });
export const issueMaterialRequisition = (
  id: string,
  version_no: number,
  note?: string,
  photo_file_ids: string[] = [],
  lines?: Array<{ line_id: string; quantity: number; tracking?: Record<string, unknown> }>,
) =>
  action("issue", id, {
    version_no,
    note: note || null,
    photo_file_ids,
    lines,
  });

export const exportMaterialRequisitions = (params: Record<string, any>) =>
  http.request<Blob>("get", "/api/inventory_requisition/export", {
    params,
    responseType: "blob",
  });

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
) => action(exception ? "receipt-exception" : "receive", id, data);
export const resolveMaterialRequisitionException = (
  id: string,
  data: { version_no: number; note: string; photo_file_ids?: string[] },
) => action("resolve-exception", id, data);

export const listMyMaterialRequisitions = (params: Record<string, unknown>) =>
  http.request<ApiResponse<PageResult<MaterialRequisition>>>(
    "get",
    "/api/inventory_requisition/my",
    { params },
  );
