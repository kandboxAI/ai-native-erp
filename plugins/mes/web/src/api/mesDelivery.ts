import { http } from "@/utils/http";
import type { ApiResponse, MesPage } from "./mes";

export type DeliveryKind = "shipments" | "reconciliations";
export type DeliveryLine = {
  id?: string;
  work_order_id: string;
  work_order_no_snapshot?: string;
  product_item_name_snapshot?: string;
  unit_code?: string;
  quantity: string;
  unit_price: string;
  order_unit_price?: string | null;
  order_currency?: string | null;
  order_currency_snapshot?: string | null;
  amount?: string;
  shipment_line_id?: string;
  shipment_no?: string;
  business_date?: string;
  adjustment_amount?: string;
  adjustment_reason?: string;
};
export type DeliveryDocument = {
  id: string;
  org_id: string;
  shipment_no?: string;
  reconciliation_no?: string;
  customer_no_snapshot: string;
  customer_name_snapshot: string;
  business_date?: string;
  period_start?: string;
  period_end?: string;
  status_code: string;
  fulfillment_mode_code?: "direct" | "stock";
  warehouse_id?: string;
  stock_orders?: {
    id: string;
    order_no: string;
    stock_order_id: string;
    status_code: string;
  }[];
  version_no: number;
  total_amount: string;
  order_currency_snapshot?: string | null;
  note?: string;
  cancellation_reason?: string;
  lines: DeliveryLine[];
};
export type DeliverySource = {
  id?: string;
  org_id: string;
  work_order_id: string;
  work_order_no?: string;
  work_order_no_snapshot?: string;
  product_item_name?: string;
  product_item_name_snapshot?: string;
  unit_code: string;
  available_quantity?: string;
  quantity?: string;
  unit_price?: string;
  amount?: string;
  shipment_no?: string;
  business_date?: string;
  customer_no_snapshot?: string;
  customer_name_snapshot?: string;
  customer_id?: string | null;
  sales_order_no?: string | null;
  has_order_source?: boolean;
  order_unit_price?: string | null;
  order_currency?: string | null;
  order_currency_snapshot?: string | null;
};
export type ShipmentCustomer = {
  id: string;
  org_id: string;
  customer_no: string;
  customer_name: string;
  sales_order_no?: string | null;
};
export const deliveryParams = (query: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(query).filter(
      ([, value]) =>
        value != null && (typeof value !== "string" || value.trim() !== "")
    )
  );
export const getDeliveries = (
  kind: DeliveryKind,
  query: Record<string, unknown>
) =>
  http.request<ApiResponse<MesPage<DeliveryDocument>>>(
    "get",
    `/api/mes/${kind}`,
    { params: deliveryParams(query) }
  );
export const getDelivery = (kind: DeliveryKind, id: string) =>
  http.request<ApiResponse<DeliveryDocument>>("get", `/api/mes/${kind}/${id}`);
export const getDeliverySources = (
  kind: DeliveryKind,
  query: Record<string, unknown>
) =>
  http.request<ApiResponse<MesPage<DeliverySource>>>(
    "get",
    `/api/mes/${kind}/sources`,
    { params: deliveryParams(query) }
  );
export const getShipmentCustomerOptions = (keyword = "", salesOrderId?: string) =>
  http.request<ApiResponse<ShipmentCustomer[]>>("get", "/api/mes/shipments/customer-options", {
    params: deliveryParams({ keyword, sales_order_id: salesOrderId }),
  });
export const getShipmentSalesOrderOptions = (customerId: string, keyword = "") =>
  http.request<ApiResponse<{ id: string; order_no: string; customer_po_no: string }[]>>(
    "get",
    "/api/mes/shipments/sales-order-options",
    { params: deliveryParams({ customer_id: customerId, keyword }) },
  );
export const saveDelivery = (kind: DeliveryKind, body: unknown, id?: string) =>
  http.request<ApiResponse<DeliveryDocument>>(
    id ? "put" : "post",
    `/api/mes/${kind}${id ? `/${id}` : ""}`,
    { data: body }
  );
export const actDelivery = (
  kind: DeliveryKind,
  id: string,
  action: string,
  body: { version_no: number; reason?: string }
) =>
  http.request<ApiResponse<DeliveryDocument>>(
    "post",
    `/api/mes/${kind}/${id}/${action}`,
    { data: body }
  );

export const shipmentDocumentNames = {
  packing_list: "装箱单",
  customs_draft: "报关资料草稿",
  invoice_request: "开票申请单",
  commercial_invoice: "商业发票",
  domestic_invoice: "发票",
  domestic_contract: "合同",
} as const;
export type ShipmentDocumentKind = keyof typeof shipmentDocumentNames;

export const shipmentMaterialNames = {
  aluminum: "铝材料",
  steel: "钢材料",
  engineering_plastic: "工程塑料",
} as const;
export type ShipmentMaterial = keyof typeof shipmentMaterialNames;
export type ShipmentMaterialChoice = ShipmentMaterial | "individual";

export type CustomsDetails = {
  declared_name: string;
  hs_code: string | null;
  origin_country: string | null;
  declaration_elements: string;
  customer_tariff_no: string | null;
};
export type ShipmentCustomsLine = CustomsDetails & {
  shipment_line_id: string;
  material_group: ShipmentMaterialChoice | null;
  material_name: string;
};
export type ShipmentCustomsProfile = CustomsDetails & {
  material_group: ShipmentMaterial;
};
export type ShipmentExportDetails = {
  invoice_no: string;
  contract_no: string;
  contract_date: string | null;
  seller_name_en: string;
  seller_address_en: string;
  seller_contact: string;
  seller_phone: string;
  buyer_contact: string;
  buyer_phone: string;
  buyer_eori_vat: string;
  payment_terms: string;
  payment_instructions: string;
  marks: string;
  package_type: string;
  shipping_method: string;
  transport_vehicle: string;
  loading_port: string;
  destination_port: string;
  destination_name_zh: string;
  trade_country: string | null;
  domestic_source: string;
  seller_credit_no: string;
  producer_name: string;
  producer_credit_no: string;
  customs_office: string;
  supervision_mode: string;
  exemption_nature: string;
  exemption_method: string;
  declaration_date: string | null;
  customs_record_no: string;
  licence_no: string;
  edi_list_no: string;
  freight: string;
  insurance: string;
  other_fees: string;
  related_party_confirmation: string;
  price_influence_confirmation: string;
  royalty_confirmation: string;
  self_payment_confirmation: string;
  declarant_contact: string;
  signed_at: string;
  contract_terms: string;
  customs_note: string;
};
export type ShipmentDomesticDetails = Pick<ShipmentExportDetails,
  "invoice_no" | "contract_no" | "contract_date" | "signed_at" | "seller_phone" | "buyer_phone" | "payment_terms" | "contract_terms"
>;
type BoxDetails = {
  box_no: string;
  gross_weight_kg: string;
  length_cm: string;
  width_cm: string;
  height_cm: string;
};
type PackedDetails = { quantity: string; net_weight_kg: string };
export type ShipmentPackedLine = PackedDetails & { shipment_line_id: string };
export type ShipmentBoxInput = BoxDetails & {
  lines: ShipmentPackedLine[];
};
export type ShipmentDocumentHeader = {
  trade_mode: "domestic" | "export";
  seller_name: string;
  seller_address: string;
  buyer_name: string;
  buyer_address: string;
  buyer_tax_no: string;
  destination_country: string | null;
  trade_term: string;
  transport_no: string;
  include_commercial_invoice: boolean;
};
export type ShipmentDocumentInput = ShipmentDocumentHeader & {
  version_no: number;
  boxes: ShipmentBoxInput[];
  customs: ShipmentCustomsLine[];
  customs_profiles: ShipmentCustomsProfile[];
  export_details: ShipmentExportDetails | null;
  domestic_details: ShipmentDomesticDetails | null;
};
export type ShipmentDocumentSnapshot = {
  kinds: ShipmentDocumentKind[];
  header: ShipmentDocumentHeader & {
    export_details?: ShipmentExportDetails;
    domestic_details?: ShipmentDomesticDetails;
  };
  goods: {
    line_no: number;
    work_order_no: string;
    item_no: string;
    item_name: string;
    sales_order_no: string;
    quantity: string;
    unit: string;
    currency: string;
    price: string;
    amount: string;
    price_basis: string;
    customs: Partial<CustomsDetails>;
    customs_input?: Partial<Omit<ShipmentCustomsLine, "shipment_line_id">>;
  }[];
  boxes: (BoxDetails & { items: (PackedDetails & { line_no: number })[] })[];
  customs_profiles?: ShipmentCustomsProfile[];
  customs_groups?: {
    group_no: number;
    category: string;
    name: string;
    unit: string;
    currency: string;
    quantity: string;
    net_weight_kg: string;
    amount: string;
    unit_price: string;
    customs: Partial<CustomsDetails>;
  }[];
  customs_issues?: string[];
};
export type ShipmentDocumentVersion = {
  id: string;
  revision_no: number;
  created_at: string;
  template_key: string;
  kinds: ShipmentDocumentKind[];
  is_preview: boolean;
  is_superseded: boolean;
};
export type ShipmentInvoice = {
  id: string;
  invoice_no: string;
  issued_date: string;
  attachment_id: string;
};
export type ShipmentDocumentSet = {
  versions: ShipmentDocumentVersion[];
  latest_snapshot: ShipmentDocumentSnapshot | null;
  invoices: ShipmentInvoice[];
  source_goods: {
    shipment_line_id: string;
    drawing_no: string;
    material: string;
    order_description: string;
    sales_order_no: string;
    customer_po_no: string;
    material_source: "sales_order" | "work_order" | "quotation" | "product" | null;
    suggested_material_group: ShipmentMaterial | null;
    unit_net_weight_kg: string | null;
  }[];
};
const documentsPath = (id: string) => `/api/mes/shipments/${id}/documents`;
export const getShipmentDocuments = (id: string) =>
  http.request<ApiResponse<ShipmentDocumentSet>>("get", documentsPath(id));
export const previewShipmentDocuments = (id: string, data: ShipmentDocumentInput) =>
  http.request<ApiResponse<ShipmentDocumentSnapshot>>("post", documentsPath(id) + "/preview", { data });
export const generateShipmentDocuments = (id: string, data: ShipmentDocumentInput) =>
  http.request<ApiResponse<ShipmentDocumentVersion>>("post", documentsPath(id), { data });
export const shipmentDocumentDownloadPath = (id: string, revision: string, kind: ShipmentDocumentKind) =>
  `${documentsPath(id)}/${revision}/${kind}`;
export const registerShipmentInvoice = (id: string, data: Omit<ShipmentInvoice, "id">) =>
  http.request<ApiResponse<ShipmentInvoice>>("post", `/api/mes/shipments/${id}/invoices`, { data });
