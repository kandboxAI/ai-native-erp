<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import QuotationImports from "./QuotationImports.vue";
import CncAdoptionPanel from "./CncAdoptionPanel.vue";
import QuantityTiers from "./QuantityTiers.vue";
import HistoricalPrices from "./HistoricalPrices.vue";
import {
  approvalBody,
  hasApprovalPriceChanges,
  originalLine,
} from "./approval";
import { matchesDrawing, pageItems, fillHistoricalPrices } from "./lines";
import ActionButton from "@/components/ActionButton/index.vue";
import ListPagination from "@/components/ListPagination/index.vue";
import {
  computed,
  nextTick,
  ref,
  watch,
  onActivated,
  onDeactivated,
  onMounted,
  onBeforeUnmount,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type TableInstance } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { useUserStoreHook } from "@/store/modules/user";
import { notifyTodosChanged } from "@/utils/todoRefresh";
import { createCncProgressPoller, hasPendingCnc } from "./progress";
import {
  validateRequirements,
  validateEngineering,
  validateApproval,
} from "./validation";
import {
  request,
  download,
  normalize,
  requirements,
  engineering,
  newLine,
  type Quote,
  type QuoteLine,
  type QuoteFile,
  type CncProgress,
} from "./api";

const route = useRoute(),
  router = useRouter();
const principal = useUserStoreHook();
const importer = ref<InstanceType<typeof QuotationImports>>(),
  importBusy = ref(false),
  adoptionBusy = ref(false);
let active = true;
const rows = ref<Quote[]>([]),
  draft = ref<Quote>();
const reviewOriginal = ref<Quote>();
const priceAdjustmentReason = ref("");
const reviewPriceChanged = computed(
  () =>
    !!draft.value && hasApprovalPriceChanges(draft.value, reviewOriginal.value),
);
const customers = ref<{ id: string; name: string }[]>([]);
const keyword = ref(""),
  status = ref(""),
  error = ref(""),
  busy = ref(false);
const page = ref(1),
  pageSize = ref(20),
  total = ref(0),
  selected = ref<QuoteLine[]>([]);
const mode = ref("view");
const progressMessage = ref("");
const detailTable = ref<TableInstance>();
const history = ref<InstanceType<typeof HistoricalPrices>>();
function createCustomerOrder(row: Quote) {
  router.push({
    path: "/mes/sales-orders",
    query: { new: "1", quote_id: row.id },
  });
}
const lineKeyword = ref(""),
  linePage = ref(1),
  linePageSize = ref(20);
const filteredLines = computed(() =>
  (draft.value?.lines || []).filter((line) =>
    matchesDrawing(line, lineKeyword.value),
  ),
);
const visibleLines = computed(() =>
  pageItems(filteredLines.value, linePage.value, linePageSize.value),
);
const temporaryKeys = new WeakMap<QuoteLine, string>();
let nextLineKey = 0;
function detailRowKey(line: QuoteLine) {
  if (line.id) return line.id;
  if (!temporaryKeys.has(line)) temporaryKeys.set(line, `new-${++nextLineKey}`);
  return temporaryKeys.get(line)!;
}
async function addGoods() {
  if (!draft.value) return;
  lineKeyword.value = "";
  draft.value.lines.push(newLine());
  await nextTick();
  linePage.value = Math.ceil(draft.value.lines.length / linePageSize.value);
}
function selectAllDetail() {
  detailTable.value?.clearSelection();
  for (const line of filteredLines.value)
    detailTable.value?.toggleRowSelection(line, true);
}
function removeGoods(line: QuoteLine) {
  const index = draft.value?.lines.indexOf(line) ?? -1;
  if (index >= 0) draft.value!.lines.splice(index, 1);
}
watch([lineKeyword, linePageSize], () => {
  linePage.value = 1;
});
watch(
  () => filteredLines.value.length,
  (count) => {
    linePage.value = Math.min(
      linePage.value,
      Math.max(1, Math.ceil(count / linePageSize.value)),
    );
  },
);
watch(
  () => draft.value?.id,
  () => {
    lineKeyword.value = "";
    linePage.value = 1;
  },
);
const labels: Record<string, string> = {
  draft: "业务录入",
  pending: "待工程报价",
  pricing: "工程报价中",
  review: "待初审",
  final_review: "待复审",
  quoted: "审核通过",
  voided: "已作废",
};
const statusTypes: Record<string, "info" | "warning" | "primary" | "success"> =
  {
    draft: "info",
    pending: "warning",
    pricing: "primary",
    review: "info",
    final_review: "warning",
    quoted: "success",
  };
const actionLabels: Record<string, string> = {
  save: "保存需求",
  engineering: "工程报价",
  submit: "提交工程",
  finish: "提交初审",
  return: "退回业务",
  reject: "退回工程",
  approve: "初审通过",
  approval_price: "初审改价",
  final_approve: "复审通过",
  final_reject: "复审退回初审",
  delete: "删除询价草稿",
  void: "作废询价",
  revise: "新建修订",
  adopt: "采用核价",
};
const business = computed(
  () =>
    mode.value === "sales" &&
    draft.value?.status_code === "draft" &&
    hasPerms("mes:quotation:manage"),
);
const price = computed(
  () =>
    mode.value === "engineering" &&
    ["pending", "pricing"].includes(draft.value?.status_code || "") &&
    hasPerms("mes:quotation:price"),
);
const review = computed(
  () =>
    mode.value === "review" &&
    draft.value?.status_code === "review" &&
    hasPerms("mes:quotation:approve"),
);
const finalReview = computed(
  () =>
    mode.value === "final_review" &&
    draft.value?.status_code === "final_review" &&
    hasPerms("mes:quotation:approve"),
);
const canCnc = computed(
  () =>
    price.value &&
    ["mes:quote:list", "mes:quote:manage", "mes:quote:analyze"].every((key) =>
      hasPerms(key),
    ),
);
let generation = 0;
async function run(action: () => Promise<void>) {
  if (busy.value || importBusy.value || adoptionBusy.value) return;
  busy.value = true;
  try {
    await action();
  } catch (cause) {
    if (cause !== "cancel" && cause !== "close") {
      actionMessage((cause as Error)?.message || "操作失败，请检查网络或权限");
    }
  } finally {
    busy.value = false;
  }
}
async function listing() {
  const token = generation;
  const data = await request<{ items: Quote[]; total: number }>(
    `?page=${page.value}&page_size=${pageSize.value}&keyword=${encodeURIComponent(keyword.value)}&status=${encodeURIComponent(status.value)}`,
  );
  if (!active || token !== generation) return;
  rows.value = data.items;
  total.value = data.total;
}
async function loadCustomers(orgId?: string) {
  const token = generation;
  const data = await request<{
    org_id: string;
    customers: typeof customers.value;
  }>(`/customers${orgId ? `?org_id=${orgId}` : ""}`);
  if (active && token === generation) customers.value = data.customers;
  return data.org_id;
}
async function search() {
  page.value = 1;
  await listing();
}
async function resetFilters() {
  keyword.value = "";
  status.value = "";
  await search();
}
async function loadPage() {
  if (!active || route.path !== "/mes/quotations") return;
  const token = ++generation;
  error.value = "";
  draft.value = undefined;
  reviewOriginal.value = undefined;
  priceAdjustmentReason.value = "";
  selected.value = [];
  try {
    if (route.query.new === "1") {
      if (!hasPerms("mes:quotation:manage")) throw Error("缺少业务录入权限");
      const orgId = await loadCustomers();
      if (token !== generation) return;
      draft.value = {
        quote_no: "保存后自动编号",
        revision: 1,
        version_no: 1,
        title: "",
        org_id: orgId,
        customer_id: "",
        currency: "EUR",
        deadline: null,
        status_code: "draft",
        note: "",
        lines: [newLine()],
      };
      mode.value = "sales";
    } else if (typeof route.query.quote_id === "string") {
      const result = normalize(
        await request<Quote>(`/${route.query.quote_id}`),
      );
      if (token !== generation) return;
      draft.value = result;
      reviewOriginal.value = JSON.parse(JSON.stringify(result));
      mode.value = String(route.query.mode || "view");
      if (mode.value === "engineering" && hasPerms("mes:quotation:price"))
        fillHistoricalPrices(result);
      if (mode.value === "sales" && hasPerms("mes:quotation:manage"))
        await loadCustomers(result.org_id);
    } else {
      mode.value = "view";
      await listing();
    }
  } catch (cause) {
    if (token === generation)
      error.value = (cause as Error).message || "加载询价失败";
  }
}
watch(() => route.fullPath, loadPage, { immediate: true });
onActivated(() => {
  active = true;
  void loadPage();
});
onDeactivated(() => {
  active = false;
  generation++;
  rows.value = [];
  draft.value = undefined;
  customers.value = [];
  progress.sync();
});
watch(
  () => principal.username,
  () => {
    generation++;
    rows.value = [];
    draft.value = undefined;
    customers.value = [];
    if (principal.username && active) void loadPage();
  },
);
const progress = createCncProgressPoller({
  target: () =>
    active &&
    document.visibilityState !== "hidden" &&
    route.path === "/mes/quotations" &&
    draft.value?.id &&
    ["mes:quotation:list", "mes:quotation:price", "mes:quote:list"].every(
      hasPerms,
    )
      ? { key: `${generation}:${draft.value.id}`, quote: draft.value }
      : undefined,
  paused: () => busy.value || importBusy.value || adoptionBusy.value,
  fetch: (id) => request<CncProgress>(`/${id}/cnc-records`),
  notify: (message) => {
    progressMessage.value = message;
  },
});
watch(
  () => [
    draft.value,
    busy.value,
    importBusy.value,
    adoptionBusy.value,
    principal.permissions.join("|"),
    draft.value && hasPendingCnc(draft.value),
  ],
  () => progress.sync(),
);
watch(draft, () => {
  progressMessage.value = "";
});
const syncProgress = () => progress.sync();
onMounted(() => document.addEventListener("visibilitychange", syncProgress));
onBeforeUnmount(() => {
  active = false;
  generation++;
  progress.dispose();
  document.removeEventListener("visibilitychange", syncProgress);
});
async function openCnc(partId: string) {
  if (price.value) await savePrice(false);
  await router.push({ path: "/mes/quoting", query: { part_id: partId } });
}
const show = (row: Quote, actor = "view") =>
  router.push({
    path: "/mes/quotations",
    query: { quote_id: row.id, mode: actor },
  });
async function back() {
  if (business.value || price.value)
    await ElMessageBox.confirm(
      "离开页面前请确认已保存，需要返回列表吗？",
      "返回列表",
      { type: "warning" },
    );
  await router.push("/mes/quotations");
}
function canDelete(row: Quote) {
  return !!row.id && row.status_code === "draft" && hasPerms("mes:quotation:manage");
}
async function deleteQuote(row: Quote) {
  if (!canDelete(row)) return;
  await ElMessageBox.confirm(
    `确认删除询价草稿 ${row.quote_no} · R${row.revision}？`,
    "删除询价",
    { type: "warning", confirmButtonText: "删除" },
  );
  await request(`/${row.id}?version_no=${row.version_no}`, "delete");
  notifyTodosChanged();
  actionMessage("询价草稿已删除", "success");
  if (draft.value?.id === row.id) {
    await router.replace("/mes/quotations");
  } else {
    if (rows.value.length === 1 && page.value > 1) page.value--;
    await listing();
  }
}
function canVoid(row: Quote) {
  return (
    !!row.id &&
    hasPerms("mes:quotation:manage") &&
    ["pending", "pricing", "review", "final_review", "quoted"].includes(row.status_code) &&
    (row.customer_order_count ?? 0) === 0
  );
}
async function voidQuote(row: Quote) {
  if (!canVoid(row)) return;
  const { value } = await ElMessageBox.prompt(
    `作废后会保留询价记录，本版报价不可用于生成客户订单。请填写 ${row.quote_no} · R${row.revision} 的作废原因。`,
    "作废询价",
    {
      type: "warning",
      confirmButtonText: "作废",
      inputValidator: (reason) => {
        const length = reason?.trim().length ?? 0;
        if (!length || length > 1000) return "请填写作废原因（1–1000 字）";
        return true;
      },
    },
  );
  const result = await request<Quote>(`/${row.id}/actions/void`, "post", {
    version_no: row.version_no,
    note: value.trim(),
  });
  notifyTodosChanged();
  actionMessage("询价已作废", "success");
  if (draft.value?.id === row.id) {
    draft.value = normalize(result);
    mode.value = "view";
  } else {
    if (status.value && rows.value.length === 1 && page.value > 1) page.value--;
    await listing();
  }
}
async function save() {
  if (!draft.value) return;
  validateRequirements(draft.value);
  const old = draft.value;
  const result = normalize(
    await request<Quote>(
      old.id ? `/${old.id}` : "",
      old.id ? "put" : "post",
      requirements(old),
    ),
  );
  draft.value = result;
  if (!old.id)
    await router.replace({
      path: "/mes/quotations",
      query: { quote_id: result.id, mode: "sales" },
    });
  ElMessage.success("保存成功");
}
async function savePrice(notify = true) {
  const token = generation,
    old = draft.value!;
  const result = normalize(
    await request<Quote>(`/${old.id}/engineering`, "put", engineering(old)),
  );
  if (!active || generation !== token || draft.value?.id !== old.id)
    throw Error("页面已变化，请返回询价后核对保存结果");
  draft.value = result;
  if (notify) ElMessage.success("保存成功");
}
async function persistForAdoption(): Promise<Quote> {
  await savePrice(false);
  return draft.value!;
}
async function action(key: string) {
  if (
    key === "approve" &&
    reviewPriceChanged.value &&
    !priceAdjustmentReason.value.trim()
  )
    throw Error("调整报价时请填写改价说明");
  if (key === "submit") validateRequirements(draft.value!, true);
  if (key === "finish") validateEngineering(draft.value!);
  if (key === "approve") validateApproval(draft.value!);
  let note = "";
  if (["return", "reject", "final_reject"].includes(key)) {
    const result = await ElMessageBox.prompt("请填写具体退回原因", "退回", {
      inputValidator: (value) => !!value?.trim() || "请填写原因",
    });
    note = result.value.trim();
  } else {
    const confirmation = {
      finish: "提交本版报价，进入初审？",
      approve: "确认本版材料、价格及交期无误，提交复审？",
      final_approve: "确认复审通过？通过后本版报价可用于生成客户订单。",
    }[key];
    if (confirmation)
      await ElMessageBox.confirm(confirmation, "确认报价", { type: "warning" });
  }
  const old = draft.value!;
  const path =
    key === "submit"
      ? `${old.id ? `/${old.id}` : ""}/submit`
      : key === "finish"
        ? `/${old.id}/engineering/submit`
        : key === "approve"
          ? `/${old.id}/approve`
          : `/${old.id}/actions/${key}`;
  const body =
    key === "submit"
      ? requirements(old)
      : key === "finish"
        ? engineering(old)
        : key === "approve"
          ? approvalBody(old, priceAdjustmentReason.value, note)
          : { version_no: old.version_no, note };
  draft.value = normalize(await request<Quote>(path, "post", body));
  notifyTodosChanged();
  if (route.query.new === "1") {
    await router.replace({
      path: "/mes/quotations",
      query: { quote_id: draft.value.id, mode: "view" },
    });
  }
  mode.value = "view";
  ElMessage.success(
    {
      submit: "已提交工程报价",
      finish: "已提交报价初审",
      approve: "初审通过，待复审",
      final_approve: "复审通过",
      final_reject: "已退回初审",
      return: "已退回业务补充",
      reject: "已退回工程",
    }[key] || "操作成功",
  );
}
async function revise() {
  await ElMessageBox.confirm("保留原版，创建新的业务录入修订？", "新建修订");
  const result = await request<Quote>(`/${draft.value!.id}/revisions`, "post", {
    version_no: draft.value!.version_no,
  });
  await show(result, "sales");
}
async function viewFile(file: QuoteFile) {
  // L1 checks the owning quotation on every download URL request; no token in URL.
  const { http } = await import("@/utils/http");
  const result = await http.request<{ data: { url: string } }>(
    "get",
    `/api/files/${file.attachment_id}/url`,
  );
  window.open(result.data.url, "_blank", "noopener,noreferrer");
}
async function analyze() {
  await ElMessageBox.confirm(
    "将本次选择货品的图纸和必要制造要求提交给已配置的解析、模型服务，继续吗？",
    "批量 AI 报价",
    { type: "warning" },
  );
  const ids = selected.value.map((line) => line.id!);
  await savePrice(false);
  const failures: string[] = [];
  let success = 0;
  // Persistent CNC jobs run in the existing backend worker, not a browser timer.
  for (const id of ids) {
    try {
      await request(`/${draft.value!.id}/lines/${id}/cnc`, "post", {
        version_no: draft.value!.version_no,
        cloud_allowed: true,
      });
      success++;
    } catch (cause) {
      failures.push(
        `${draft.value!.lines.find((line) => line.id === id)?.drawing_no}: ${(cause as Error).message}`,
      );
    }
  }
  draft.value = normalize(await request<Quote>(`/${draft.value!.id}`));
  if (failures.length) {
    actionMessage(
      [`已创建 ${success} 项核价任务，${failures.length} 项失败。`, ...failures].join("\n"),
      "warning",
    );
  } else {
    actionMessage(`已创建 ${success} 项核价任务`, "success");
  }
}
async function exportQuote(zip = false) {
  await download(
    `/api/mes/quotations/${draft.value!.id}/export?with_drawings=${zip}`,
    `${draft.value!.quote_no}_R${draft.value!.revision}.${zip ? "zip" : "xlsx"}`,
  );
}
</script>

<template>
  <main v-loading="busy || importBusy" class="quotation-page">
    <header class="quotation-toolbar">
      <div class="quotation-heading">
        <h2>
          {{ draft ? `${draft.quote_no} · R${draft.revision}` : "询价报价" }}
        </h2>
        <p class="quotation-muted">
          业务整理客户需求，工程核价，初审及复审通过后输出报价。
        </p>
      </div>
      <div class="quotation-page-actions">
        <el-button
          v-if="!draft && hasPerms('mes:sales_order:list')"
          @click="router.push('/mes/sales-orders')"
          >客户订单</el-button
        >
        <el-button
          v-if="
            draft?.status_code === 'quoted' &&
            hasPerms('mes:sales_order:list') &&
            hasPerms('mes:sales_order:manage')
          "
          type="primary"
          @click="createCustomerOrder(draft)"
          >生成客户订单</el-button
        >
        <el-button v-if="draft" @click="run(back)">返回列表</el-button>
        <el-button
          v-else-if="hasPerms('mes:quotation:manage')"
          type="primary"
          @click="router.push({ path: '/mes/quotations', query: { new: '1' } })"
          >新建询价</el-button
        >
        <el-button
          v-if="
            draft?.status_code === 'review' &&
            !review &&
            hasPerms('mes:quotation:approve')
          "
          type="primary"
          @click="draft && show(draft, 'review')"
          >初审报价</el-button
        >
        <el-button
          v-if="draft?.status_code === 'final_review' && !finalReview && hasPerms('mes:quotation:approve')"
          type="primary"
          @click="draft && show(draft, 'final_review')"
          >复审报价</el-button
        >
        <el-button
          v-if="draft && canDelete(draft)"
          type="danger"
          @click="run(() => deleteQuote(draft!))"
          >删除</el-button
        >
        <el-button
          v-if="draft && canVoid(draft)"
          type="danger"
          @click="run(() => voidQuote(draft!))"
          >作废</el-button
        >
      </div>
    </header>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <template v-if="!draft && route.query.new !== '1' && !route.query.quote_id">
      <el-form inline class="quotation-panel" @submit.prevent="run(search)"
        ><el-form-item label="搜索"
          ><el-input
            v-model="keyword"
            placeholder="单号、客户或询价名称"
            clearable /></el-form-item
        ><el-form-item label="状态"
          ><el-select
            v-model="status"
            placeholder="全部状态"
            clearable
            style="width: 180px"
            ><el-option
              v-for="(label, key) in labels"
              :key="key"
              :label="label"
              :value="key" /></el-select></el-form-item
        ><el-form-item class="quotation-filter-actions"
          ><el-button type="primary" native-type="submit">查询</el-button
          ><el-button @click="run(resetFilters)">重置</el-button
          ><el-button @click="run(listing)">刷新</el-button></el-form-item
        ></el-form
      >
      <section class="erp-list-panel" aria-label="询价报价列表">
        <el-table :data="rows" border
          ><el-table-column label="报价单 / 修订" min-width="220"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="show(row as Quote)"
                >{{ row.quote_no }} · R{{ row.revision }}</el-button
              ></template
            ></el-table-column
          ><el-table-column
            prop="title"
            label="询价名称"
            min-width="180"
          /><el-table-column
            prop="customer_name_snapshot"
            label="客户"
            min-width="160"
          /><el-table-column label="状态" width="130"
            ><template #default="{ row }"
              ><el-tag
                :type="statusTypes[row.status_code] || 'info'"
                :class="{ 'quotation-review': row.status_code === 'review' }"
                >{{ labels[row.status_code] }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column
            v-if="hasPerms('mes:sales_order:list')"
            label="成交记录"
            width="130"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="
                  router.push({
                    path: '/mes/sales-orders',
                    query: { quotation_id: row.id },
                  })
                "
                >{{ row.customer_order_count || 0 }} 张订单</el-button
              ></template
            ></el-table-column
          ><el-table-column label="操作" min-width="260"
            ><template #default="{ row }"
              ><el-button link @click="show(row as Quote)">查看</el-button
              ><el-button
                v-if="
                  row.status_code === 'draft' &&
                  hasPerms('mes:quotation:manage')
                "
                link
                type="primary"
                @click="show(row as Quote, 'sales')"
                >编辑需求</el-button
              ><el-button
                v-if="
                  ['pending', 'pricing'].includes(row.status_code) &&
                  hasPerms('mes:quotation:price')
                "
                link
                type="primary"
                @click="show(row as Quote, 'engineering')"
                >工程报价</el-button
              ><el-button
                v-if="
                  row.status_code === 'review' &&
                  hasPerms('mes:quotation:approve')
                "
                link
                type="primary"
                @click="show(row as Quote, 'review')"
                >初审报价</el-button
              ><el-button
                v-if="row.status_code === 'final_review' && hasPerms('mes:quotation:approve')"
                link
                type="primary"
                @click="show(row as Quote, 'final_review')"
                >复审报价</el-button
              ><el-button
                v-if="
                  row.status_code === 'quoted' &&
                  hasPerms('mes:sales_order:list') &&
                  hasPerms('mes:sales_order:manage')
                "
                link
                type="primary"
                @click="createCustomerOrder(row as Quote)"
                >生成客户订单</el-button
              ><el-button
                v-if="canDelete(row as Quote)"
                link
                type="danger"
                @click="run(() => deleteQuote(row as Quote))"
                >删除</el-button
              ><el-button
                v-if="canVoid(row as Quote)"
                link
                type="danger"
                @click="run(() => voidQuote(row as Quote))"
                >作废</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <ListPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :disabled="busy"
          @current-change="run(listing)"
          @size-change="run(search)"
        />
      </section>
    </template>
    <template v-if="draft">
      <div class="quotation-toolbar quotation-status">
        <el-tag
          :type="statusTypes[draft.status_code] || 'info'"
          :class="{ 'quotation-review': draft.status_code === 'review' }"
          >{{ labels[draft.status_code] }}</el-tag
        >
        <span v-if="draft.return_reason"
          >退回原因：{{ draft.return_reason }}</span
        >
      </div>
      <el-form
        label-position="top"
        class="quotation-panel"
        :disabled="!business"
        ><div class="quotation-fields">
          <el-form-item label="询价名称" required
            ><el-input v-model="draft.title" maxlength="128" /></el-form-item
          ><el-form-item label="客户" required
            ><el-select v-if="business" v-model="draft.customer_id"
              ><el-option
                v-for="customer in customers"
                :key="customer.id"
                :value="customer.id"
                :label="customer.name" /></el-select
            ><el-input
              v-else
              :model-value="draft.customer_name_snapshot" /></el-form-item
          ><el-form-item label="币种"
            ><el-select v-model="draft.currency"
              ><el-option
                v-for="currency in ['EUR', 'CNY', 'USD']"
                :key="currency"
                :value="currency"
                :label="currency" /></el-select></el-form-item
          ><el-form-item label="报价截止日期"
            ><el-date-picker
              v-model="draft.deadline"
              type="date"
              value-format="YYYY-MM-DD"
          /></el-form-item>
        </div>
        <el-form-item label="询价说明"
          ><el-input v-model="draft.note" maxlength="1000" /></el-form-item
      ></el-form>
      <section class="quotation-panel erp-list-panel">
        <div class="quotation-toolbar">
          <h3>
            {{
              review
                ? "报价初审明细"
                : finalReview
                  ? "报价复审明细"
                : price
                  ? "工程报价明细"
                  : "货品与客户要求"
            }}
          </h3>
          <QuotationImports
            v-if="business"
            ref="importer"
            :lines="draft.lines"
            @apply="(value) => draft && (draft.lines = value)"
            @busy="(value) => (importBusy = value)"
          >
            <ActionButton intent="create" @click="addGoods"
              >添加货品</ActionButton
            >
          </QuotationImports>
          <el-button
            v-if="canCnc"
            type="primary"
            :disabled="!selected.length"
            @click="run(analyze)"
            >AI 报价（{{ selected.length }}）</el-button
          >
        </div>
        <p v-if="business" class="quotation-muted">
          可一次上传二维图纸和三维模型，按同名图号配对。每项最多一份
          PDF 和一份模型。
        </p>
        <p v-if="price" class="quotation-muted">
          工程确认采用并完善单价，提交后进入报价初审。
        </p>
        <p v-if="review" class="quotation-muted">
          初审可调整对客单价和交期。改价须填写说明，确认后提交复审。
        </p>
        <p v-if="finalReview" class="quotation-muted">
          请核对初审确认的材料、单价和交期。需要调整时填写原因并退回初审。
        </p>
        <el-form
          inline
          class="quotation-line-search"
          @submit.prevent="linePage = 1"
        >
          <el-form-item label="图号"
            ><el-input
              v-model="lineKeyword"
              aria-label="工程明细图号"
              placeholder="按图号搜索"
              clearable
          /></el-form-item>
          <el-form-item
            ><el-button type="primary" native-type="submit">查询</el-button
            ><el-button
              @click="
                lineKeyword = '';
                linePage = 1;
              "
              >重置</el-button
            ></el-form-item
          >
          <el-form-item
            ><span class="quotation-muted"
              >共 {{ draft.lines.length }} 项，匹配
              {{ filteredLines.length }} 项<span
                v-if="canCnc && selected.length"
                >；已选 {{ selected.length }} 项（跨页保留）</span
              ></span
            ></el-form-item
          >
        </el-form>
        <div v-if="canCnc" class="quotation-detail-selection">
          <el-button link type="primary" @click="selectAllDetail"
            >选择全部匹配项（{{ filteredLines.length }}）</el-button
          >
          <el-button
            link
            :disabled="!selected.length"
            @click="detailTable?.clearSelection()"
            >清空选择</el-button
          >
        </div>
        <el-table
          ref="detailTable"
          :data="visibleLines"
          :row-key="detailRowKey"
          max-height="580"
          border
          @selection-change="(value) => (selected = value)"
        >
          <el-table-column
            v-if="canCnc"
            type="selection"
            width="48"
            reserve-selection
          />
          <el-table-column label="图号 / 版本" min-width="210" fixed
            ><template #default="{ row }"
              ><el-input
                v-model="row.drawing_no"
                :disabled="!business"
                placeholder="图号"
                maxlength="64"
              /><el-input
                v-model="row.drawing_revision"
                :disabled="!business"
                placeholder="版本"
                maxlength="32"
              /><el-button
                v-if="price"
                link
                type="primary"
                @click="history?.open(row as QuoteLine)"
                >历史报价</el-button
              ></template
            ></el-table-column
          >
          <el-table-column
            v-if="!business && hasPerms('mes:quotation:price')"
            label="历史报价参考"
            min-width="225"
          >
            <template #default="{ row }">
              <template v-if="row.historical_reference">
                <div>
                  {{ row.historical_reference.unit_price }}
                  {{ row.historical_reference.currency }} /
                  {{ row.historical_reference.quantity }}
                  {{ row.historical_reference.unit_name }}
                </div>
                <div class="quotation-muted">
                  {{ row.historical_reference.quote_no }} · R{{
                    row.historical_reference.revision
                  }}
                </div>
                <el-tag
                  size="small"
                  :type="
                    row.historical_reference.is_compatible ? 'info' : 'warning'
                  "
                  >{{
                    row.historical_reference.is_compatible
                      ? "相同条件报价"
                      : "条件有差异，请核对"
                  }}</el-tag
                >
              </template>
              <span v-else>暂无历史报价</span>
            </template>
          </el-table-column>
          <el-table-column label="数量档报价" min-width="150"
            ><template #default="{ row }"
              ><QuantityTiers
                :line="row as QuoteLine"
                :business="business"
                :price="price"
                :review="review"
                :original="originalLine(reviewOriginal, row as QuoteLine)"
                :currency="draft.currency"
                @update="(value) => (row.quantity_tiers = value)" /></template
          ></el-table-column>
          <el-table-column label="客户要求材料" min-width="160"
            ><template #default="{ row }"
              ><el-input
                v-model="row.customer_material"
                :disabled="!business"
                maxlength="128" /></template
          ></el-table-column>
          <el-table-column v-if="!business" label="报价采用材料" min-width="160"
            ><template #default="{ row }"
              ><el-input
                v-model="row.quoted_material"
                :disabled="!price"
                maxlength="128" /></template
          ></el-table-column>
          <el-table-column
            v-if="!business"
            :label="`单价（${draft.currency}，未税）`"
            min-width="175"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.unit_price"
                :disabled="!(price || review)"
                :min="0"
                :max="100000000"
                :precision="2"
                controls-position="right"
              /><small v-if="review">
                工程原价：{{
                  originalLine(reviewOriginal, row as QuoteLine)?.unit_price ??
                  "未报价"
                }}
                {{ draft.currency }} </small
              ><small v-if="row.adopted_cnc_quote_id"
                >已采用核价依据</small
              ></template
            ></el-table-column
          >
          <el-table-column
            v-if="!business"
            label="最终交期（自然日）"
            min-width="150"
            ><template #default="{ row }"
              ><el-input-number
                v-if="review"
                v-model="row.lead_days"
                :min="1"
                :max="3650"
                :precision="0"
                controls-position="right"
              />
              <span v-else>{{
                row.lead_days == null ? "待审批确认" : `${row.lead_days} 天`
              }}</span></template
            ></el-table-column
          >
          <el-table-column label="图纸 / 模型" min-width="210"
            ><template #default="{ row }"
              ><div v-for="file in row.files" :key="file.attachment_id">
                <el-button
                  link
                  type="primary"
                  @click="run(() => viewFile(file))"
                  >{{ file.name }}</el-button
                >
              </div>
              <el-button
                v-if="business"
                link
                @click="importer?.pick(row as QuoteLine)"
                >上传 / 替换</el-button
              ></template
            ></el-table-column
          >
          <el-table-column label="描述" min-width="180"
            ><template #default="{ row }"
              ><el-input
                v-model="row.description"
                :disabled="!business"
                maxlength="128" /></template
          ></el-table-column>
          <el-table-column label="数量 / 单位" min-width="170"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.quantity"
                :disabled="!business"
                :min="0.001"
                :max="1000000"
                :precision="3"
                controls-position="right" /><el-input
                v-model="row.unit_name"
                :disabled="!business"
                maxlength="16" /></template
          ></el-table-column>
          <el-table-column
            v-if="draft.status_code !== 'draft'"
            label="单件净重（kg）"
            min-width="160"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.weight_kg"
                :disabled="!price"
                :min="0"
                :precision="6"
                controls-position="right" /></template
          ></el-table-column>
          <el-table-column label="表面处理 / 客户备注" min-width="200"
            ><template #default="{ row }"
              ><el-input
                v-model="row.surface_treatment"
                :disabled="!business"
                placeholder="表面处理"
                maxlength="500" /><el-input
                v-model="row.note"
                :disabled="!business"
                placeholder="客户备注"
                maxlength="1000" /></template
          ></el-table-column>
          <el-table-column
            v-if="!business && hasPerms('mes:quotation:price')"
            label="工程内部说明（不导出）"
            min-width="220"
            ><template #default="{ row }"
              ><el-input
                v-model="row.engineering_note"
                :disabled="!price"
                maxlength="1000" /></template
          ></el-table-column>
          <el-table-column v-if="business" label="操作" width="80"
            ><template #default="{ row }"
              ><el-button
                link
                type="danger"
                @click="removeGoods(row as QuoteLine)"
                >移除</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <ListPagination
          v-model:current-page="linePage"
          v-model:page-size="linePageSize"
          :total="filteredLines.length"
          :disabled="busy || importBusy || adoptionBusy"
          @size-change="linePage = 1"
        />
      </section>
      <HistoricalPrices
        v-if="draft && price"
        ref="history"
        :currency="draft.currency"
        :customer-id="draft.customer_id"
        :editable="price"
      />
      <CncAdoptionPanel
        v-if="hasPerms('mes:quotation:price')"
        :quote="draft"
        :editable="price"
        :disabled="busy || importBusy"
        :progress-message="progressMessage"
        :persist="persistForAdoption"
        @busy="(value) => (adoptionBusy = value)"
        @update="(value) => (draft = value)"
        @open="(partId) => run(() => openCnc(partId))"
      />
      <section v-if="review" class="quotation-panel">
        <el-form label-position="top">
          <el-form-item label="改价说明" :required="reviewPriceChanged">
            <el-input
              v-model="priceAdjustmentReason"
              type="textarea"
              :rows="2"
              maxlength="1000"
              show-word-limit
              placeholder="调整任意对客单价时必填，说明将随审核记录保存"
            />
          </el-form-item>
        </el-form>
      </section>
      <section v-if="draft.events?.length" class="quotation-panel">
        <h3>操作记录</h3>
        <el-table :data="draft.events" size="small" max-height="360"
          ><el-table-column
            prop="created_at"
            label="时间"
            min-width="200" /><el-table-column
            prop="action_key"
            label="动作"
            width="140"
            ><template #default="{ row }">{{
              actionLabels[row.action_key] || row.action_key
            }}</template></el-table-column
          ><el-table-column prop="note" label="说明" show-overflow-tooltip
        /></el-table>
      </section>
      <footer class="erp-form-actions quotation-panel">
        <div
          v-if="draft.id && hasPerms('mes:quotation:export')"
          class="erp-form-actions__secondary"
        >
          <ActionButton intent="download" @click="run(() => exportQuote())">
            导出 Excel
          </ActionButton>
          <ActionButton intent="download" @click="run(() => exportQuote(true))">
            打包图纸与报价
          </ActionButton>
        </div>
        <div class="erp-form-actions__primary">
          <el-button v-if="business" @click="run(save)">保存录入</el-button
          ><el-button
            v-if="business"
            type="primary"
            @click="run(() => action('submit'))"
            >提交工程报价</el-button
          ><el-button v-if="price" type="success" @click="run(savePrice)"
            >保存报价进度</el-button
          ><el-button v-if="price" type="warning" @click="run(() => action('return'))"
            >退回业务补充</el-button
          ><el-button
            v-if="price"
            type="primary"
            @click="run(() => action('finish'))"
            >提交报价初审</el-button
          ><template v-if="review"
            ><el-button type="warning" @click="run(() => action('reject'))"
              >退回工程</el-button
            ><el-button type="success" @click="run(() => action('approve'))"
              >初审通过并提交复审</el-button
            ></template
          ><template v-if="finalReview">
            <el-button type="warning" @click="run(() => action('final_reject'))">退回初审</el-button>
            <el-button type="success" @click="run(() => action('final_approve'))">复审通过</el-button>
          </template
          ><el-button
            v-if="
              draft.status_code === 'quoted' && hasPerms('mes:quotation:manage')
            "
            @click="run(revise)"
            >新建修订</el-button
          >
        </div>
      </footer>
    </template>
  </main>
</template>

<style scoped>
.quotation-page {
  padding: 20px;
}

.quotation-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 12px 0;
}

.quotation-heading {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.quotation-page-actions {
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  margin-left: auto;
}

.quotation-page-actions > .el-button + .el-button {
  margin-left: 0;
}

.quotation-status {
  justify-content: flex-start;
}

.quotation-review.el-tag {
  --el-tag-text-color: #6750a4;
  --el-tag-bg-color: color-mix(in srgb, #6750a4 10%, var(--el-bg-color));
  --el-tag-border-color: color-mix(in srgb, #6750a4 25%, var(--el-bg-color));
}

:global(html.dark .quotation-review.el-tag) {
  --el-tag-text-color: #c4b5ed;
}

.quotation-panel {
  padding: 20px;
  margin: 16px 0;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.quotation-line-search {
  margin: 16px 0;
}

.quotation-detail-selection {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.quotation-line-search .el-input {
  width: 250px;
}

.quotation-fields {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.quotation-muted {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}

small {
  display: block;
  color: var(--el-color-success);
}

@media (width <= 900px) {
  .quotation-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .quotation-toolbar {
    flex-wrap: wrap;
  }
}
</style>
