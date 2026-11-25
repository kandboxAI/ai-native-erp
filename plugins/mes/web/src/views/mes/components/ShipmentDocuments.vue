<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { actionMessage, message } from "@/utils/message";
import { getFileUrl, uploadFile } from "@/api/systemFile";
import {
  generateShipmentDocuments,
  getShipmentDocuments,
  previewShipmentDocuments,
  registerShipmentInvoice,
  shipmentDocumentDownloadPath,
  shipmentDocumentNames,
  shipmentMaterialNames,
  type CustomsDetails,
  type DeliveryDocument,
  type ShipmentBoxInput,
  type ShipmentDocumentInput,
  type ShipmentDocumentKind,
  type ShipmentDomesticDetails,
  type ShipmentDocumentSet,
  type ShipmentDocumentSnapshot,
  type ShipmentDocumentVersion,
  type ShipmentExportDetails,
  type ShipmentMaterial,
  type ShipmentPackedLine,
} from "@plugins/mes/web/src/api/mesDelivery";
import { download } from "../quotations/api";
import { formatMesDate } from "../shared";

const props = defineProps<{ shipment: DeliveryDocument }>();
const emit = defineEmits<{ busyChange: [busy: boolean] }>();
const records = ref<ShipmentDocumentSet>();
const preview = ref<ShipmentDocumentSnapshot>();
const previewHeading = ref<HTMLElement>();
const historyHeading = ref<HTMLElement>();
const busy = ref(false);
const error = ref("");
const invoiceFile = ref<File>();
const invoiceFileId = ref("");
const invoiceInputKey = ref(0);
const invoice = reactive({ invoice_no: "", issued_date: "" });
const materialGroups = Object.keys(shipmentMaterialNames) as ShipmentMaterial[];
const exportFieldGroups = [
  {
    name: "commercial",
    title: "商业单据与收款信息",
    fields: [
      ["invoice_no", "商业发票编号", 80], ["contract_no", "合同号", 80],
      ["seller_name_en", "发货方英文名", 180], ["seller_address_en", "发货方英文地址", 400],
      ["seller_contact", "发货方联系人", 80], ["seller_phone", "发货方电话", 64],
      ["buyer_contact", "收货方联系人", 80], ["buyer_phone", "收货方电话", 64],
      ["buyer_eori_vat", "购方 EORI / VAT", 64], ["payment_terms", "付款条件", 180],
      ["signed_at", "签约地点", 80], ["payment_instructions", "收款说明", 1200],
      ["contract_terms", "补充合同条款", 1000],
    ],
  },
  {
    name: "declaration",
    title: "运输及报关抬头",
    fields: [
      ["shipping_method", "运输方式", 64], ["transport_vehicle", "运输工具名称", 80],
      ["package_type", "包装种类", 64], ["destination_name_zh", "运抵国中文名", 80],
      ["loading_port", "装运口岸", 80], ["destination_port", "指运港", 80],
      ["trade_country", "贸易国代码", 2], ["domestic_source", "境内货源地", 120],
      ["seller_credit_no", "经营单位信用代码", 32], ["producer_name", "生产销售单位", 180],
      ["producer_credit_no", "生产销售单位信用代码", 32], ["customs_office", "出境关别", 80],
      ["supervision_mode", "监管方式", 80], ["exemption_nature", "征免性质", 80],
      ["exemption_method", "征免方式", 80],
      ["customs_record_no", "备案号", 80], ["licence_no", "许可证号", 80], ["edi_list_no", "EDI 清单编号", 80],
      ["freight", "运费", 80], ["insurance", "保费", 80], ["other_fees", "杂费", 80],
      ["related_party_confirmation", "特殊关系确认", 16], ["price_influence_confirmation", "价格影响确认", 16],
      ["royalty_confirmation", "支付特许权使用费确认", 16], ["self_payment_confirmation", "自报自缴", 16],
      ["declarant_contact", "报关员及联系方式", 120], ["marks", "包装唛头", 400], ["customs_note", "报关备注", 1000],
    ],
  },
] as const satisfies readonly {
  name: string;
  title: string;
  fields: readonly (readonly [keyof ShipmentExportDetails, string, number])[];
}[];
const exportDetails = reactive<ShipmentExportDetails>({
  invoice_no: "", contract_no: "", contract_date: null, seller_name_en: "", seller_address_en: "",
  seller_contact: "", seller_phone: "", buyer_contact: "", buyer_phone: "",
  buyer_eori_vat: "", payment_terms: "", payment_instructions: "", marks: "",
  package_type: "", shipping_method: "", transport_vehicle: "", loading_port: "", destination_port: "", destination_name_zh: "",
  trade_country: null, domestic_source: "", seller_credit_no: "", producer_name: "",
  producer_credit_no: "", customs_office: "", supervision_mode: "",
  exemption_nature: "", exemption_method: "", declaration_date: null, signed_at: "",
  customs_record_no: "", licence_no: "", edi_list_no: "", freight: "", insurance: "", other_fees: "",
  related_party_confirmation: "", price_influence_confirmation: "", royalty_confirmation: "",
  self_payment_confirmation: "", declarant_contact: "",
  contract_terms: "", customs_note: "",
});
const domesticDetails = reactive<ShipmentDomesticDetails>({
  invoice_no: "", contract_no: "", contract_date: null, signed_at: "",
  seller_phone: "", buyer_phone: "", payment_terms: "", contract_terms: "",
});
const domesticFields = [
  ["invoice_no", "发票编号", 80, "留空用出货单号"],
  ["contract_no", "合同号", 80, "留空时尝试带入唯一客户采购单号"],
  ["signed_at", "签约地点", 80], ["payment_terms", "付款条件", 180],
  ["seller_phone", "销售方电话", 64], ["buyer_phone", "购方电话", 64],
] as const;

function emptyDeclaration(): CustomsDetails {
  return {
    declared_name: "", hs_code: null, origin_country: null,
    declaration_elements: "", customer_tariff_no: null,
  };
}

const profiles = reactive({
  aluminum: emptyDeclaration(), steel: emptyDeclaration(), engineering_plastic: emptyDeclaration(),
});
const form = reactive<
  Omit<ShipmentDocumentInput, "trade_mode" | "export_details" | "domestic_details" | "customs_profiles"> & {
    trade_mode: ShipmentDocumentInput["trade_mode"] | "";
  }
>({
  version_no: props.shipment.version_no,
  trade_mode: "",
  seller_name: "",
  seller_address: "",
  buyer_name: props.shipment.customer_name_snapshot,
  buyer_address: "",
  buyer_tax_no: "",
  destination_country: null,
  trade_term: "",
  transport_no: "",
  include_commercial_invoice: false,
  boxes: [],
  customs: [],
});
const lines = computed(
  () => new Map(props.shipment.lines.map((line) => [line.id, line])),
);
const sourceGoods = computed(
  () => new Map((records.value?.source_goods ?? []).map((row) => [row.shipment_line_id, row])),
);
const materialSources = {
  sales_order: "订单",
  work_order: "工单",
  quotation: "关联报价",
  product: "货品规格",
};
function syncCustomsLines() {
  const existing = new Map(form.customs.map((row) => [row.shipment_line_id, row]));
  form.customs = props.shipment.lines.flatMap(({ id }) =>
    id ? [existing.get(id) ?? { ...emptyDeclaration(), shipment_line_id: id, material_group: null, material_name: "" }] : [],
  );
}
function effectiveMaterial(id: string) {
  return form.customs.find((line) => line.shipment_line_id === id)?.material_group
    ?? sourceGoods.value.get(id)?.suggested_material_group
    ?? null;
}
function suggestedMaterialLabel(id: string, entered: string) {
  const suggested = sourceGoods.value.get(id)?.suggested_material_group;
  if (suggested) return `按材料建议 · ${shipmentMaterialNames[suggested]}`;
  return entered.trim() ? "按补录材料归类" : "材料待确认";
}
function materialLabel(id: string) {
  const source = sourceGoods.value.get(id)?.material_source;
  return source ? materialSources[source] : "";
}
const activeGroups = computed(() => {
  const used = new Set(form.customs.map((row) => effectiveMaterial(row.shipment_line_id)));
  return materialGroups.filter((key) => used.has(key));
});
const declarationForms = computed(() => [
  ...activeGroups.value.map((key) => ({ key, label: shipmentMaterialNames[key], fields: profiles[key] })),
  ...form.customs.filter((row) => {
    const category = effectiveMaterial(row.shipment_line_id);
    return !category || category === "individual";
  }).map((row) => ({
    key: row.shipment_line_id,
    label: sourceGoods.value.get(row.shipment_line_id)?.drawing_no || lineLabel(row.shipment_line_id),
    fields: row,
  })),
]);
const canEdit = computed(
  () =>
    !!records.value &&
    props.shipment.status_code !== "cancelled" &&
    hasPerms("mes:shipment:manage"),
);
const canRegister = computed(() => {
  const current = records.value?.versions[0];
  return (
    props.shipment.status_code === "posted" &&
    hasPerms("mes:shipment:invoice") &&
    current &&
    !current.is_preview &&
    !current.is_superseded &&
    (current.kinds.includes("domestic_invoice") || current.kinds.includes("invoice_request"))
  );
});
const documentKinds = computed<ShipmentDocumentKind[]>(() =>
  !form.trade_mode
    ? []
    : form.trade_mode === "domestic"
      ? ["domestic_invoice", "domestic_contract"]
      : ["commercial_invoice", "packing_list", "customs_draft"],
);

watch(form, () => {
  preview.value = undefined;
});
watch([exportDetails, domesticDetails, profiles], () => {
  preview.value = undefined;
});
watch(busy, (value) => emit("busyChange", value));
onBeforeUnmount(() => emit("busyChange", false));
watch(
  () => props.shipment.version_no,
  () => {
    form.version_no = props.shipment.version_no;
    syncCustomsLines();
    run(() => load(), true);
  },
);

function populate(snapshot: ShipmentDocumentSnapshot) {
  const { export_details: savedExportDetails, domestic_details: savedDomesticDetails, ...header } = snapshot.header;
  Object.assign(form, header);
  if (savedExportDetails) Object.assign(exportDetails, savedExportDetails);
  if (savedDomesticDetails) Object.assign(domesticDetails, savedDomesticDetails);
  for (const { material_group, ...profile } of snapshot.customs_profiles ?? []) {
    Object.assign(profiles[material_group], profile);
  }
  const sourceByOrder = new Map(
    props.shipment.lines.map((line) => [line.work_order_no_snapshot, line.id]),
  );
  const goods = new Map(snapshot.goods.map((line) => [line.line_no, line]));
  const linkedId = (lineNo: number) =>
    sourceByOrder.get(goods.get(lineNo)?.work_order_no);
  form.boxes = snapshot.boxes.map(({ items, ...box }) => ({
    ...box,
    lines: items.flatMap(({ line_no, ...entry }) => {
      const id = linkedId(line_no);
      return id ? [{ ...entry, shipment_line_id: id }] : [];
    }),
  }));
  for (const row of snapshot.goods) {
    const current = form.customs.find(
      (line) => line.shipment_line_id === linkedId(row.line_no),
    );
    if (!current) continue;
    if (row.customs_input) Object.assign(current, row.customs_input);
    else if (Object.values(row.customs).some(Boolean)) {
      Object.assign(current, row.customs, { material_group: "individual" });
    }
  }
}
async function load(prefill = false) {
  error.value = "";
  records.value = (await getShipmentDocuments(props.shipment.id)).data;
  syncCustomsLines();
  if (prefill && records.value.latest_snapshot)
    populate(records.value.latest_snapshot);
}
async function run(fn: () => Promise<void>, loading = false) {
  if (busy.value) return;
  busy.value = true;
  try {
    await fn();
  } catch (cause) {
    const text = getHttpErrorMessage(cause, "出货单据操作失败");
    if (loading) error.value = text;
    else actionMessage(text);
  } finally {
    busy.value = false;
  }
}
function addPackedLine(box: ShipmentBoxInput) {
  box.lines.push({ shipment_line_id: "", quantity: "", net_weight_kg: "" });
}
const autoNetWeights = new WeakSet<ShipmentPackedLine>();

function scaledDecimal(value: string, places: number) {
  const text = value.trim();
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) return 0n;
  const [whole, fraction = ""] = text.split(".");
  return fraction.length > places
    ? 0n
    : BigInt((whole || "0") + fraction.padEnd(places, "0"));
}
function formatScaled(value: bigint, places: number) {
  const digits = value.toString().padStart(places + 1, "0");
  const whole = digits.slice(0, -places);
  const fraction = digits.slice(-places).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}
const packedQuantities = computed(() => {
  const totals = new Map<string, bigint>();
  for (const box of form.boxes) {
    for (const row of box.lines) {
      const id = row.shipment_line_id;
      if (id) totals.set(id, (totals.get(id) ?? 0n) + scaledDecimal(row.quantity, 3));
    }
  }
  return totals;
});
function unpackedQuantity(id: string) {
  return scaledDecimal(lines.value.get(id)?.quantity ?? "", 3) - (packedQuantities.value.get(id) ?? 0n);
}
function estimatePackedWeight(row: ShipmentPackedLine) {
  const unitWeight = scaledDecimal(sourceGoods.value.get(row.shipment_line_id)?.unit_net_weight_kg ?? "", 6);
  // 数量保留三位，单件及箱内净重保留六位。用整数计算，避免拆箱时引入浮点尾差。
  const weight = (unitWeight * scaledDecimal(row.quantity, 3) + 500n) / 1000n;
  row.net_weight_kg = weight > 0n ? formatScaled(weight, 6) : "";
  autoNetWeights.add(row);
}
function selectPackedGood(row: ShipmentPackedLine, id: string) {
  if (row.shipment_line_id === id) return;
  const available = unpackedQuantity(id);
  row.shipment_line_id = id;
  row.quantity = available > 0n ? formatScaled(available, 3) : "";
  estimatePackedWeight(row);
}
function setPackedQuantity(row: ShipmentPackedLine, quantity: string) {
  row.quantity = quantity;
  if (autoNetWeights.has(row) || !row.net_weight_kg) estimatePackedWeight(row);
}
function setPackedWeight(row: ShipmentPackedLine, weight: string) {
  row.net_weight_kg = weight;
  autoNetWeights.delete(row);
}
function addBox() {
  const box: ShipmentBoxInput = {
    box_no: "",
    gross_weight_kg: "",
    length_cm: "",
    width_cm: "",
    height_cm: "",
    lines: [],
  };
  addPackedLine(box);
  form.boxes.push(box);
}
function lineLabel(id: string) {
  const row = lines.value.get(id);
  return row
    ? `${row.work_order_no_snapshot} · ${row.product_item_name_snapshot} · 本批 ${row.quantity}`
    : "";
}
function normalizedDeclaration(row: CustomsDetails): CustomsDetails {
  return {
    declared_name: row.declared_name,
    declaration_elements: row.declaration_elements,
    hs_code: row.hs_code?.trim() || null,
    origin_country: row.origin_country?.trim().toUpperCase() || null,
    customer_tariff_no: row.customer_tariff_no?.trim() || null,
  };
}
function payload(): ShipmentDocumentInput {
  const tradeMode = form.trade_mode;
  if (!tradeMode) throw Error("请选择本次出货类型");
  const overseas = tradeMode === "export";
  return {
    ...form,
    version_no: props.shipment.version_no,
    trade_mode: tradeMode,
    destination_country: overseas
      ? form.destination_country?.trim().toUpperCase() || null
      : null,
    buyer_tax_no: overseas ? "" : form.buyer_tax_no,
    trade_term: overseas ? form.trade_term : "",
    transport_no: overseas ? form.transport_no : "",
    include_commercial_invoice: overseas,
    boxes: overseas ? form.boxes : [],
    customs: overseas
      ? form.customs.map((row) => {
          const category = effectiveMaterial(row.shipment_line_id);
          return {
            ...(!category || category === "individual" ? normalizedDeclaration(row) : emptyDeclaration()),
            shipment_line_id: row.shipment_line_id,
            material_group: row.material_group,
            material_name: sourceGoods.value.get(row.shipment_line_id)?.material ? "" : row.material_name,
          };
        })
      : [],
    customs_profiles: overseas ? activeGroups.value.map((material_group) => ({
      ...normalizedDeclaration(profiles[material_group]), material_group,
    })) : [],
    export_details: overseas ? {
      ...exportDetails,
      trade_country: exportDetails.trade_country?.trim().toUpperCase() || null,
      contract_date: exportDetails.contract_date || null,
      declaration_date: exportDetails.declaration_date || null,
    } : null,
    domestic_details: overseas ? null : { ...domesticDetails, contract_date: domesticDetails.contract_date || null },
  };
}
async function showPreview() {
  preview.value = (
    await previewShipmentDocuments(props.shipment.id, payload())
  ).data;
  await nextTick();
  previewHeading.value?.focus({ preventScroll: true });
  previewHeading.value?.scrollIntoView({ block: "nearest" });
}
async function generate() {
  await generateShipmentDocuments(props.shipment.id, payload());
  await load();
  message("出货单据已生成", { type: "success" });
  await nextTick();
  historyHeading.value?.focus({ preventScroll: true });
  historyHeading.value?.scrollIntoView({ block: "nearest" });
}
async function downloadVersion(
  row: ShipmentDocumentVersion,
  kind: ShipmentDocumentKind,
) {
  await download(
    shipmentDocumentDownloadPath(props.shipment.id, row.id, kind),
    `${props.shipment.shipment_no}-${documentName(kind, row.template_key)}-V${row.revision_no}.xlsx`,
  );
}
function documentName(kind: ShipmentDocumentKind, template = "shipment_xlsx_v5") {
  if (["shipment_xlsx_v2", "shipment_xlsx_v3", "shipment_xlsx_v4", "shipment_xlsx_v5"].includes(template)) {
    if (kind === "packing_list") return "英文装箱单";
    if (kind === "commercial_invoice") return "英文商业发票";
  }
  return shipmentDocumentNames[kind];
}
function selectInvoiceFile(event: Event) {
  invoiceFile.value = (event.target as HTMLInputElement).files?.[0];
  invoiceFileId.value = "";
}
async function saveInvoice() {
  if (
    !invoice.invoice_no.trim() ||
    !invoice.issued_date ||
    !invoiceFile.value
  ) {
    throw Error("请填写发票号码、开票日期并选择正式发票 PDF");
  }
  if (invoiceFile.value.type !== "application/pdf")
    throw Error("请选择 PDF 文件");
  if (!invoiceFileId.value)
    invoiceFileId.value = (
      await uploadFile(invoiceFile.value, "mes_shipment_invoice")
    ).id;
  await registerShipmentInvoice(props.shipment.id, {
    ...invoice,
    attachment_id: invoiceFileId.value,
  });
  invoice.invoice_no = invoice.issued_date = invoiceFileId.value = "";
  invoiceFile.value = undefined;
  invoiceInputKey.value++;
  await load();
  message("正式发票已登记", { type: "success" });
}
async function openInvoice(id: string) {
  const { data } = await getFileUrl(id);
  const link = document.createElement("a");
  link.href = data.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.click();
}
function versionStatus(row: ShipmentDocumentVersion) {
  if (props.shipment.status_code === "cancelled") return "出货已取消";
  if (row.is_superseded) return "历史版本";
  return row.is_preview ? "出货预览" : "已生成";
}
onMounted(() => run(() => load(true), true));
</script>

<template>
  <div v-loading="busy" class="shipment-documents">
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    >
      <el-button link type="primary" @click="run(() => load(!records), true)"
        >重新加载</el-button
      >
    </el-alert>
    <el-alert
      v-else-if="shipment.status_code === 'cancelled'"
      title="出货单已取消，保留原单据及正式发票登记供追溯。"
      type="warning"
      :closable="false"
    />
    <el-skeleton v-if="busy && !records" animated :rows="4" />
    <div
      v-if="records"
      class="documents-grid"
      :class="{ 'documents-grid--readonly': !canEdit }"
    >
      <section v-if="canEdit" class="documents-main">
        <h3 class="documents-title">出货资料</h3>
        <el-form label-position="top" @submit.prevent>
          <div class="trade-options">
            <el-form-item label="出货类型" required>
              <el-radio-group v-model="form.trade_mode">
                <el-radio value="domestic">国内</el-radio>
                <el-radio value="export" :disabled="!!records.invoices.length"
                  >出口</el-radio
                >
              </el-radio-group>
            </el-form-item>
          </div>
          <p v-if="documentKinds.length" class="document-kinds">
            本次生成：<strong>{{
              documentKinds
                .map((kind) => documentName(kind))
                .join("、")
            }}</strong>
          </p>
          <div class="document-fields">
            <el-form-item label="销售方 / 发货方名称" required
              ><el-input
                v-model="form.seller_name"
                maxlength="180"
                placeholder="填写发货或开票全称"
            /></el-form-item>
            <el-form-item label="购方 / 收货方名称" required
              ><el-input
                v-model="form.buyer_name"
                maxlength="180"
                placeholder="填写收货或开票全称"
            /></el-form-item>
            <el-form-item
              label="发货方地址"
              :required="form.trade_mode === 'export'"
              ><el-input v-model="form.seller_address" maxlength="400"
            /></el-form-item>
            <el-form-item
              label="收货方地址"
              :required="form.trade_mode === 'export'"
              ><el-input v-model="form.buyer_address" maxlength="400"
            /></el-form-item>
            <template v-if="form.trade_mode === 'export'">
              <el-form-item label="目的国家或地区代码" required
                ><el-input
                  v-model="form.destination_country"
                  maxlength="2"
                  placeholder="例如 DE"
              /></el-form-item>
              <el-form-item label="贸易术语 / 运输单号"
                ><div class="document-fields">
                  <el-input
                    v-model="form.trade_term"
                    maxlength="32"
                    aria-label="贸易术语"
                    placeholder="贸易术语"
                  />
                  <el-input
                    v-model="form.transport_no"
                    maxlength="80"
                    aria-label="运输单号"
                    placeholder="运输单号"
                  /></div
              ></el-form-item>
            </template>
            <el-form-item
              v-else-if="form.trade_mode === 'domestic'"
              label="购方税号"
              ><el-input v-model="form.buyer_tax_no" maxlength="64"
            /></el-form-item>
          </div>
          <el-collapse v-if="form.trade_mode === 'domestic'" class="document-sections">
            <el-collapse-item name="domestic" title="发票与合同资料">
              <div class="document-fields">
                <el-form-item v-for="[key, label, limit, placeholder] in domesticFields" :key="key" :label="label">
                  <el-input v-model="domesticDetails[key]" :maxlength="limit" :placeholder="placeholder" />
                </el-form-item>
                <el-form-item label="签约日期">
                  <el-date-picker v-model="domesticDetails.contract_date" type="date" value-format="YYYY-MM-DD" />
                </el-form-item>
                <el-form-item label="合同条款" class="document-field-full">
                  <el-input v-model="domesticDetails.contract_terms" type="textarea" :rows="2" maxlength="1000" />
                </el-form-item>
              </div>
            </el-collapse-item>
          </el-collapse>
          <template v-if="form.trade_mode === 'export'">
            <el-collapse class="document-sections">
              <el-collapse-item
                v-for="group in exportFieldGroups"
                :key="group.name"
                :name="group.name"
                :title="group.title"
              >
                <div class="document-fields">
                  <el-form-item v-for="[key, label, limit] in group.fields" :key="key" :label="label">
                    <el-input
                      v-model="exportDetails[key]"
                      :maxlength="limit"
                      :type="limit >= 400 ? 'textarea' : 'text'"
                      :rows="2"
                      :placeholder="key === 'invoice_no' ? '留空用出货单号' : key === 'contract_no' ? '留空时尝试带入唯一客户采购单号' : undefined"
                    />
                  </el-form-item>
                  <el-form-item v-if="group.name === 'declaration'" label="申报日期">
                    <el-date-picker v-model="exportDetails.declaration_date" type="date" value-format="YYYY-MM-DD" />
                  </el-form-item>
                  <el-form-item v-else label="签约日期">
                    <el-date-picker v-model="exportDetails.contract_date" type="date" value-format="YYYY-MM-DD" />
                  </el-form-item>
                </div>
              </el-collapse-item>
            </el-collapse>
            <h3>实际装箱</h3>
            <p class="document-note">
              选择货品后带入尚未装箱的数量。有单件净重时自动估算本箱净重，称重后可以修正。
            </p>
            <section
              v-for="(box, boxIndex) in form.boxes"
              :key="boxIndex"
              class="document-box"
            >
              <div class="box-fields">
                <el-form-item label="箱号" required
                  ><el-input v-model="box.box_no" maxlength="40"
                /></el-form-item>
                <el-form-item label="毛重 kg" required
                  ><el-input v-model="box.gross_weight_kg" inputmode="decimal"
                /></el-form-item>
                <el-form-item label="长 cm" required
                  ><el-input v-model="box.length_cm" inputmode="decimal"
                /></el-form-item>
                <el-form-item label="宽 cm" required
                  ><el-input v-model="box.width_cm" inputmode="decimal"
                /></el-form-item>
                <el-form-item label="高 cm" required
                  ><el-input v-model="box.height_cm" inputmode="decimal"
                /></el-form-item>
              </div>
              <el-table :data="box.lines" border>
                <el-table-column label="箱内货品" min-width="240">
                  <template #default="{ row, $index }">
                    <el-select
                      :model-value="row.shipment_line_id"
                      filterable
                      aria-label="箱内货品"
                      @update:model-value="selectPackedGood(box.lines[$index], $event)"
                    >
                      <el-option
                        v-for="line in shipment.lines"
                        :key="line.id"
                        :value="line.id || ''"
                        :label="lineLabel(line.id || '')"
                        :disabled="!line.id || (line.id !== row.shipment_line_id && (
                          unpackedQuantity(line.id) <= 0n || box.lines.some((entry) => entry.shipment_line_id === line.id)
                        ))"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="实装数量" min-width="110"
                  ><template #default="{ row, $index }"
                    ><el-input
                      :model-value="row.quantity"
                      inputmode="decimal"
                      aria-label="实装数量"
                      @update:model-value="setPackedQuantity(box.lines[$index], $event)" /></template
                ></el-table-column>
                <el-table-column label="净重 kg" min-width="110"
                  ><template #default="{ row, $index }"
                    ><el-input
                      :model-value="row.net_weight_kg"
                      inputmode="decimal"
                      aria-label="箱内货品净重"
                      :placeholder="row.shipment_line_id && !sourceGoods.get(row.shipment_line_id)?.unit_net_weight_kg ? '填写称重净重' : undefined"
                      @update:model-value="setPackedWeight(box.lines[$index], $event)" /></template
                ></el-table-column>
                <el-table-column label="操作" width="86"
                  ><template #default="{ $index }"
                    ><el-button
                      link
                      type="danger"
                      @click="box.lines.splice($index, 1)"
                      >移除</el-button
                    ></template
                  ></el-table-column
                >
              </el-table>
              <div class="erp-form-actions">
                <el-button
                  type="danger"
                  plain
                  @click="form.boxes.splice(boxIndex, 1)"
                  >移除箱</el-button
                >
                <el-button
                  :disabled="box.lines.length >= 100"
                  @click="addPackedLine(box)"
                  >添加箱内货品</el-button
                >
              </div>
            </section>
            <el-button
              type="primary"
              plain
              :disabled="form.boxes.length >= 100"
              @click="addBox"
              >添加箱</el-button
            >
            <h3 class="document-group-heading">报关归类</h3>
            <p class="document-note">
              系统按订单、工单、关联报价和货品规格查找材料并建议类别。申报口径一致的货品自动汇总，需要拆开时选「逐项申报」。
            </p>
            <el-table :data="form.customs" border max-height="320">
              <el-table-column label="图号 / 出货货品" min-width="220">
                <template #default="{ row }">
                  <div v-if="sourceGoods.get(row.shipment_line_id)?.drawing_no">
                    <strong>{{ sourceGoods.get(row.shipment_line_id)?.drawing_no }}</strong>
                  </div>
                  <div class="document-note">{{ lineLabel(row.shipment_line_id) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="材料 / 来源" min-width="200">
                <template #default="{ row }">
                  <template v-if="sourceGoods.get(row.shipment_line_id)?.material">
                    <div>{{ sourceGoods.get(row.shipment_line_id)?.material }}</div>
                    <small class="document-note">{{ materialLabel(row.shipment_line_id) }}</small>
                  </template>
                  <el-input
                    v-else
                    v-model="row.material_name"
                    aria-label="补录材料"
                    maxlength="256"
                    placeholder="补录实际材料或牌号"
                  />
                </template>
              </el-table-column>
              <el-table-column label="申报类别" min-width="185">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.material_group ?? 'auto'"
                    aria-label="申报类别"
                    @update:model-value="row.material_group = $event === 'auto' ? null : $event"
                  >
                    <el-option value="auto" :label="suggestedMaterialLabel(row.shipment_line_id, row.material_name)" />
                    <el-option v-for="key in materialGroups" :key="key" :value="key" :label="shipmentMaterialNames[key]" />
                    <el-option value="individual" label="逐项申报" />
                  </el-select>
                </template>
              </el-table-column>
            </el-table>
            <el-collapse class="document-sections">
              <el-collapse-item v-for="entry in declarationForms" :key="entry.key" :name="entry.key" :title="entry.label">
                <div class="document-fields">
                  <el-form-item label="申报品名">
                    <el-input v-model="entry.fields.declared_name" maxlength="160" />
                  </el-form-item>
                  <el-form-item label="中国申报 HS 编码">
                    <el-input v-model="entry.fields.hs_code" inputmode="numeric" maxlength="10" />
                  </el-form-item>
                  <el-form-item label="原产国代码">
                    <el-input v-model="entry.fields.origin_country" placeholder="例如 CN" maxlength="2" />
                  </el-form-item>
                  <el-form-item label="客户发票税则号">
                    <el-input v-model="entry.fields.customer_tariff_no" inputmode="numeric" maxlength="12" />
                  </el-form-item>
                  <el-form-item label="申报要素" class="document-field-full">
                    <el-input v-model="entry.fields.declaration_elements" type="textarea" :rows="2" maxlength="1500" />
                  </el-form-item>
                </div>
              </el-collapse-item>
            </el-collapse>
            <p class="document-note">报关人员核对申报品名、商品编号、原产国和申报要素。缺项会在草稿中列出。</p>
          </template>
        </el-form>
        <div class="erp-form-actions documents-actions">
          <el-button
            :disabled="busy || !form.trade_mode"
            @click="run(showPreview)"
            >预览</el-button
          >
          <el-button
            type="primary"
            :disabled="busy || !form.trade_mode"
            @click="run(generate)"
            >{{
              shipment.status_code === "posted" ? "生成单据" : "生成出货预览"
            }}</el-button
          >
        </div>
        <template v-if="preview">
          <h3 ref="previewHeading" class="documents-title" tabindex="-1">
            本次预览
          </h3>
          <p>
            {{
              preview.kinds
                .map((kind) => documentName(kind))
                .join("、")
            }}<span v-if="preview.boxes.length">
              · {{ preview.boxes.length }} 箱</span
            >
          </p>
          <el-table
            class="preview-table"
            :data="preview.goods"
            border
            max-height="260"
          >
            <el-table-column prop="item_name" label="货品" min-width="180" />
            <el-table-column
              prop="sales_order_no"
              label="客户订单"
              min-width="180"
            />
            <el-table-column prop="quantity" label="本批数量" width="105" />
            <el-table-column prop="currency" label="币种" width="85" />
            <el-table-column prop="price_basis" label="价格口径" width="120" />
            <el-table-column prop="amount" label="本批金额" min-width="115" />
          </el-table>
          <ul class="preview-list">
            <li v-for="row in preview.goods" :key="row.line_no">
              <strong>{{ row.item_name }}</strong>
              <div v-if="row.sales_order_no" class="document-note">
                {{ row.sales_order_no }}
              </div>
              <dl class="preview-figures">
                <div>
                  <dt>本批数量</dt>
                  <dd>{{ row.quantity }} {{ row.unit }}</dd>
                </div>
                <div>
                  <dt>本批金额</dt>
                  <dd>{{ row.amount }} {{ row.currency }}</dd>
                </div>
              </dl>
              <small class="document-note">{{ row.price_basis }}</small>
            </li>
          </ul>
          <template v-if="preview.customs_groups?.length">
            <h4 class="document-group-heading">报关汇总</h4>
            <el-table :data="preview.customs_groups" border max-height="320">
              <el-table-column prop="category" label="材料类别" min-width="105" />
              <el-table-column prop="name" label="申报品名" min-width="125" />
              <el-table-column prop="customs.hs_code" label="HS 编码" min-width="114" />
              <el-table-column label="汇总数量" min-width="100">
                <template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template>
              </el-table-column>
              <el-table-column prop="net_weight_kg" label="净重 kg" min-width="90" align="right" />
              <el-table-column prop="unit_price" label="汇总单价" min-width="100" align="right" />
              <el-table-column label="汇总金额" min-width="125" align="right">
                <template #default="{ row }">{{ row.amount }} {{ row.currency }}</template>
              </el-table-column>
            </el-table>
            <ul v-if="preview.customs_issues?.length" class="customs-issues">
              <li v-for="issue in preview.customs_issues" :key="issue">{{ issue }}</li>
            </ul>
          </template>
        </template>
      </section>
      <aside class="documents-rail" aria-label="单据与发票记录">
        <section class="documents-history">
          <h3 ref="historyHeading" class="documents-title" tabindex="-1">
            单据历史
          </h3>
          <p v-if="!records.versions.length" class="document-note">
            暂无已生成单据
          </p>
          <ul v-else class="history-list">
            <li
              v-for="row in records.versions"
              :key="row.id"
              class="history-item"
            >
              <div>
                <div class="history-version">
                  <strong>版本 V{{ row.revision_no }}</strong>
                  <el-tag
                    size="small"
                    :type="
                      shipment.status_code === 'cancelled' || row.is_superseded
                        ? 'info'
                        : row.is_preview
                          ? 'primary'
                          : 'success'
                    "
                    >{{ versionStatus(row) }}</el-tag
                  >
                </div>
                <div class="document-note">
                  {{ formatMesDate(row.created_at) }}
                </div>
              </div>
              <div class="download-links">
                <el-button
                  v-for="kind in row.kinds"
                  :key="kind"
                  link
                  type="primary"
                  @click="run(() => downloadVersion(row, kind))"
                  >下载{{ documentName(kind, row.template_key) }}</el-button
                >
              </div>
            </li>
          </ul>
        </section>
        <section
          v-if="canRegister || records.invoices.length"
          class="documents-invoices"
        >
          <h3 class="documents-title">正式发票</h3>
          <ul v-if="records.invoices.length" class="history-list">
            <li
              v-for="row in records.invoices"
              :key="row.id"
              class="history-item"
            >
              <div>
                <strong>{{ row.invoice_no }}</strong>
                <div class="document-note">{{ row.issued_date }}</div>
              </div>
              <el-button
                link
                type="primary"
                @click="run(() => openInvoice(row.attachment_id))"
                >查看 PDF</el-button
              >
            </li>
          </ul>
          <el-form
            v-if="canRegister"
            label-position="top"
            class="invoice-form"
            @submit.prevent="run(saveInvoice)"
          >
            <el-form-item label="发票号码" required>
              <el-input v-model="invoice.invoice_no" maxlength="80" />
            </el-form-item>
            <el-form-item label="开票日期" required>
              <el-date-picker
                v-model="invoice.issued_date"
                type="date"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item label="正式发票 PDF" required>
              <input
                :key="invoiceInputKey"
                type="file"
                accept="application/pdf"
                aria-label="正式发票 PDF"
                @change="selectInvoiceFile"
              />
            </el-form-item>
            <div class="erp-form-actions">
              <el-button type="primary" native-type="submit" :disabled="busy"
                >登记发票</el-button
              >
            </div>
          </el-form>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.shipment-documents {
  min-height: 184px;
  padding: 18px;
}

.shipment-documents > :deep(.el-alert) {
  margin-bottom: 16px;
}

.documents-grid {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(0, 3fr);
  gap: 16px;
  align-items: start;
}

.documents-grid--readonly {
  grid-template-columns: minmax(0, 1fr);
}

.documents-rail {
  display: grid;
  min-width: 0;
  gap: 12px;
}

.documents-main,
.documents-history,
.documents-invoices {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.documents-title {
  margin: 0 0 16px;
  padding-left: 10px;
  border-left: 3px solid var(--el-color-primary);
  font-size: 17px;
  line-height: 1.4;
}

.trade-options .el-form-item {
  margin-bottom: 12px;
}

.document-kinds {
  padding: 10px 12px;
  margin: 0 0 16px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}

.document-kinds strong {
  color: var(--el-color-primary);
}

.document-fields,
.box-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.box-fields {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 120px), 1fr));
}

.document-sections {
  margin: 16px 0;
}

.document-group-heading {
  margin-top: 20px;
}

.document-field-full {
  grid-column: 1 / -1;
}

.customs-issues {
  padding-left: 20px;
  margin: 12px 0 0;
  color: var(--el-color-warning-dark-2);
}

.document-box {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.document-note {
  color: var(--el-text-color-secondary);
}

.documents-actions {
  padding: 10px 12px;
  margin-bottom: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}

.history-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.preview-list {
  display: none;
  padding: 0;
  margin: 0;
  list-style: none;
}

.preview-list > li {
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.preview-list > li + li {
  margin-top: 8px;
}

.preview-figures {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 8px 0 4px;
}

.preview-figures dt {
  color: var(--el-text-color-secondary);
}

.preview-figures dd {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
}

.history-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 12px;
  padding: 11px 0;
  overflow-wrap: anywhere;
}

.history-item + .history-item {
  border-top: 1px solid var(--el-border-color-lighter);
}

.history-version {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
}

.download-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.download-links .el-button {
  margin-left: 0;
}

.invoice-form {
  margin-top: 16px;
}

.invoice-form input[type="file"] {
  width: 100%;
}

@media (max-width: 1024px) {
  .documents-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .shipment-documents,
  .documents-main,
  .documents-history,
  .documents-invoices {
    padding: 12px;
  }

  .document-fields {
    grid-template-columns: minmax(0, 1fr);
  }

  .preview-table {
    display: none;
  }

  .preview-list {
    display: block;
  }
}
</style>
