/** 物资页面共用：组织选项、字典、单据状态显示、按表单的权限判断。 */
import { ref } from "vue";
import { hasPerms } from "@/utils/auth";
import { useBasicDataStoreHook } from "@/store/modules/basicData";
import {
  FORM_PERMISSION_RESOURCE,
  STOCK_ORDER_STATUS_LABELS,
  loadInventoryMeta,
  dictLabel,
  type InventoryMetaOptions,
  type StockOrderForm,
  type StockOrderStatus
} from "@plugins/inv/web/src/api/inventoryManagement";

export type OptionItem = { label: string; value: string };

export function useOrgOptions() {
  const orgOptions = ref<OptionItem[]>([]);
  async function loadOrgOptions() {
    try {
      const items = await useBasicDataStoreHook().loadOrganizations();
      orgOptions.value = items
        .filter(o => o.is_active !== false)
        .map(o => ({ label: o.org_name, value: o.id }));
    } catch {
      orgOptions.value = [];
    }
  }
  return { orgOptions, loadOrgOptions };
}

export function useInventoryMeta() {
  const meta = ref<InventoryMetaOptions>({});
  async function loadMeta() {
    meta.value = await loadInventoryMeta();
  }
  const label = (dictCode: string, value?: string | null) =>
    dictLabel(meta.value, dictCode, value);
  const unitLabel = (code?: string | null) => label("md_unit", code);
  return { meta, loadMeta, label, unitLabel };
}

export function statusLabel(status?: string | null): string {
  return STOCK_ORDER_STATUS_LABELS[status as StockOrderStatus] ?? status ?? "";
}

export function statusTagType(
  status?: string | null
): "success" | "warning" | "info" | "danger" | "primary" {
  switch (status) {
    case "confirmed":
      return "success";
    case "submitted":
      return "warning";
    case "approved":
      return "primary";
    case "voided":
      return "danger";
    default:
      return "info";
  }
}

export function formPermission(form: StockOrderForm, action: string): string {
  return `${FORM_PERMISSION_RESOURCE[form]}:${action}`;
}

export function canForm(form: StockOrderForm, action: string): boolean {
  return (
    hasPerms(formPermission(form, action)) ||
    (form === "inbound" && hasPerms("inventory_inbound:list"))
  );
}

export const dash = (v: unknown) =>
  v === null || v === undefined || v === "" ? "—" : String(v);

/** 各表单的文案 */
export const FORM_TEXT: Record<
  StockOrderForm,
  { noun: string; dateLabel: string; counterparty: string }
> = {
  inbound: {
    noun: "入库单",
    dateLabel: "入库日期",
    counterparty: "供应商 / 来源"
  },
  outbound: { noun: "出库单", dateLabel: "出库日期", counterparty: "领用人" },
  transfer: { noun: "调拨单", dateLabel: "调拨日期", counterparty: "经办人" },
  lend: { noun: "借出单", dateLabel: "借出日期", counterparty: "借用人" },
  return: { noun: "归还单", dateLabel: "归还日期", counterparty: "归还人" },
  damage: { noun: "报损单", dateLabel: "报损日期", counterparty: "责任人" },
  adjust: { noun: "盘点调整单", dateLabel: "盘点日期", counterparty: "盘点人" }
};
