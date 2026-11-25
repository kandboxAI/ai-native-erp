<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import dayjs from "dayjs";
import {
  ApiError,
  assetUrl,
  loadEvidenceAssets,
  downloadLink,
  releaseAssets,
  jsonOptions,
  request,
  useWorkbench,
  type RecordData
} from "./api";
import DrawingView from "./components/DrawingView.vue";
import ModelView from "./components/ModelView.vue";
import OcrDocument from "./components/OcrDocument.vue";
import QuoteRules from "./components/QuoteRules.vue";
import { hasPerms } from "@/utils/auth";
import { actionMessage } from "@/utils/message";

const store = useWorkbench();
const route = useRoute();
const router = useRouter();
const form = ref<RecordData | null>(null);
const health = ref<RecordData | null>(null);
const checkingServices = ref(true);
const servicesError = ref("");
const busy = ref(false);
const selectingMaterial = ref(false);
const dirty = ref(false);
const pricingMissing = ref<string[]>([]);
const externalChange = ref(false);
const createOpen = ref(false);
// 每次进入页面默认收起，将空间留给图纸和报价。
const tasksExpanded = ref(false);
const deletedOpen = ref(false);
const deletedParts = ref<RecordData[]>([]);
const deletingId = ref("");
const rulesEditor = ref<InstanceType<typeof QuoteRules> | null>(null);
const quoteRules = ref<RecordData | null>(null);
const uploadFiles = ref<File[]>([]);
const newName = ref("");
const newQuantity = ref(1);
const search = ref("");
let searchTimer: ReturnType<typeof setTimeout>;
watch(search, value => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => act(() => store.refreshList(value)), 250);
});
const view = ref("drawing");
const editorTab = ref("requirements");
const detailPanels = ref<string[]>(["details"]);
const pageIndex = ref(0);
const selectedEvidence = ref<RecordData | null>(null);
const highlightedFaces = ref<number[]>([]);
let pollTimer: ReturnType<typeof setInterval> | null = null;
let polling = false;
let disposed = false;
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}
let applyingForm = false;

const part = computed(() => store.current);
const manufacturingProcesses = ref<RecordData[]>([]);
const processOptionsError = ref("");
const processOptionsLoading = ref(false);
let processOptionsRequest = 0;
async function refreshManufacturingProcesses() {
  const current = ++processOptionsRequest;
  const id = part.value?.id;
  manufacturingProcesses.value = [];
  processOptionsError.value = "";
  if (!id || disposed) return;
  processOptionsLoading.value = true;
  try {
    const rows = await request(`/parts/${id}/processes`);
    if (!Array.isArray(rows)) throw new Error("工艺选项响应格式不正确");
    if (current === processOptionsRequest && part.value?.id === id && !disposed)
      manufacturingProcesses.value = rows;
  } catch {
    if (current === processOptionsRequest && !disposed)
      processOptionsError.value = "正式工艺档案读取失败，请刷新后重试";
  } finally {
    if (current === processOptionsRequest && !disposed)
      processOptionsLoading.value = false;
  }
}
watch(
  () => part.value?.id,
  () => {
    void refreshManufacturingProcesses();
  },
  { immediate: true }
);
function processOptions(operation: RecordData) {
  return manufacturingProcesses.value.filter(
    p =>
      p.processing_type_code ===
      (operation.pricing_mode_code === "external" ? "outsourced" : "in_house")
  );
}
function clearArchiveBinding(operation: RecordData) {
  operation.process_id = null;
  operation.process_no_snapshot = null;
}
function selectManufacturingProcess(operation: RecordData, id: string) {
  const selected = processOptions(operation).find(p => p.id === id);
  if (!selected) {
    clearArchiveBinding(operation);
    return;
  }
  operation.process_id = selected.id;
  operation.process_no_snapshot = selected.process_no;
  operation.name = selected.process_name;
}
const analysis = computed(() => part.value?.analysis || {});
const pages = computed(() =>
  (analysis.value.documents || []).flatMap((document: RecordData) =>
    document.pages.map((page: RecordData) => ({
      ...page,
      fileId: document.file_id
    }))
  )
);
const page = computed(() => pages.value[pageIndex.value]);
watch(
  [() => part.value?.id, () => analysis.value.artifact_job, editorTab, page],
  () => {
    if (editorTab.value === "evidence" && part.value && page.value)
      void loadEvidenceAssets(part.value, page.value);
  }
);
const geometry = computed(() => analysis.value.geometry);
const weightEstimate = computed(() => part.value?.weight_estimate);
const weightInputsChanged = computed(() => {
  if (!form.value || !part.value) return false;
  return (
    Number(form.value.quantity) !== Number(part.value.quantity) ||
    ["density", "stock_length", "stock_width", "stock_height"].some(
      key =>
        Number(form.value!.specs[key] ?? 0) !==
        Number(part.value!.specs[key] ?? 0)
    )
  );
});
const hasPdf = computed(() =>
  part.value?.files.some((file: RecordData) => file.kind === "pdf")
);
const missingAnalysisConfig = computed(() => {
  if (!health.value) return [];
  const missing: string[] = [];
  if (!health.value.ai_configured) missing.push("工艺分析服务");
  if (hasPdf.value && !health.value.ocr_configured)
    missing.push("图纸识别服务");
  return missing;
});
const cloudReady = computed(
  () =>
    !checkingServices.value &&
    !!health.value &&
    !servicesError.value &&
    !missingAnalysisConfig.value.length
);
const quote = computed(() => part.value?.quote);
const materialNeedsAttention = computed(() => {
  const selection = analysis.value.material_selection;
  return (
    !running.value &&
    !quote.value &&
    !form.value?.specs.material_rule_no &&
    selection &&
    selection.status !== "selected" &&
    (form.value?.specs.material_price == null ||
      form.value?.specs.density == null)
  );
});
const materialReferencePlaceholder = computed(() => {
  const specs = form.value?.specs;
  const source = specs?.parameter_sources?.material_price;
  return source?.rule_name
    ? `${source.kind === "ai_material" ? "AI 选材" : "参数来源"}：${source.rule_name} · ${specs.material_price}元/${specs.material_price_unit_code || "kg"}`
    : "由 AI 选材，或手动选择材料规则";
});
const materialSelectionStale = computed(() => {
  const selection = analysis.value.material_selection;
  const specs = form.value?.specs;
  if (!selection || !specs) return false;
  const basis = selection.basis || {};
  return (
    basis.material !== (specs.material || "").trim() ||
    basis.hardness !== (specs.hardness || "").trim() ||
    ["stock_length", "stock_width", "stock_height"].some(
      key =>
        (basis[key] == null) !== (specs[key] == null) ||
        (basis[key] != null && Number(basis[key]) !== Number(specs[key]))
    ) ||
    (quoteRules.value &&
      selection.rules_version_no !== quoteRules.value.version_no)
  );
});
const materialRuleSelection = computed((): string => {
  const manual = form.value?.specs.material_rule_no;
  if (manual) return manual;
  const selection = analysis.value.material_selection;
  // 选择事件先核对后台版本，再写入人工绑定，避免旧表单阻止自动回填。
  return selection?.status === "selected" && !materialSelectionStale.value
    ? selection.rule_no
    : "";
});
const materialSelectionFeedback = computed(() => {
  if (running.value) return "";
  const selection = analysis.value.material_selection;
  if (!selection || form.value?.specs.material_rule_no) return "";
  if (materialSelectionStale.value)
    return "材料或毛坯已变化，请重新匹配参考材料。";
  return selection.status === "selected"
    ? ""
    : "暂未匹配到合适的参考材料，可重新匹配或手动选择。";
});
const running = computed(() =>
  ["queued", "running"].includes(part.value?.job?.status_code)
);
const analysisStateLabels: Record<string, string> = {
  completed: "完成",
  partial: "部分完成",
  failed: "失败",
  skipped: "未执行",
  pending: "待执行"
};
const analysisIssue = computed(() => {
  const job = part.value?.job;
  if (!job || running.value) return "";
  if (job.status_code === "failed")
    return "本次解析任务已中断，请查看解析结果后重新生成。";
  if (job.status_code !== "completed") return "";
  const ai = analysis.value.ai;
  if (!ai) return "本次任务未生成制造要求与工艺，请查看解析结果后重新生成。";
  if (ai.planning_status === "failed")
    return "工艺生成未完成，当前尚不能自动报价。请查看解析结果中的提示。";
  if (ai.planning_status === "partial")
    return "部分加工要求待补充，已匹配工序和估时已保留，请逐项核对提示。";
  if (["failed", "partial"].includes(ai.status))
    return "图纸制造要求未完整识别，材料或加工工序可能缺失。请查看解析结果中的提示。";
  if (ai.planning_status === "skipped")
    return "本次尚未执行完整工艺生成，请查看解析结果后重新生成。";
  if (!form.value?.operations.length)
    return ai.operations?.length
      ? "已有工艺建议尚未填入当前工序，请在解析结果中复核并采用本次工艺。"
      : "本次分析未生成可用加工工序，请查看解析结果中的工序评估与提示。";
  if (!form.value?.specs.material?.trim())
    return "尚未识别或填入材料牌号，请核对解析结果及原图，并补充材料。";
  return "";
});
const taskStage = computed(() => {
  const job = part.value?.job;
  if (!job) return "图纸已上传，等待生成报价";
  if (job.status_code === "queued") return "等待生成报价";
  if (job.status_code === "failed") return "报价生成中断，可重试";
  if (job.status_code === "running") {
    if (/选择材料|选材|材料参考/.test(job.stage)) return "正在匹配材料参考价";
    if (/文件|几何|计算/.test(job.stage)) return "正在读取图纸与模型";
    if (/文档|OCR|版面|Markdown|云端/.test(job.stage)) return "正在识别图纸";
    if (/制造要求|视觉/.test(job.stage)) return "正在提取制造要求与工艺";
    return "正在解析，请稍候";
  }
  if (quote.value) return "报价已生成，可修改和完善";
  if (analysisIssue.value) return "解析结果待处理，请查看解析提示";
  if (pricingMissing.value.length) return "请补充缺失信息后更新报价";
  return ["ocr", "ai"].some(key =>
    ["partial", "failed"].includes(analysis.value[key]?.status)
  )
    ? "解析部分完成，请核对提示"
    : "解析完成，请复核制造要求与工艺";
});
const parts = computed(() =>
  store.parts.filter(p =>
    p.name.toLowerCase().includes(search.value.toLowerCase())
  )
);

const displayMoney = (value: unknown) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      });

const displayWeight = (value: unknown) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: 3,
        maximumFractionDigits: 6
      });

const formatTaskTime = (value?: string) =>
  value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";

function openQuoteDetails() {
  editorTab.value =
    materialNeedsAttention.value ||
    pricingMissing.value.some(item => /材料/.test(item))
      ? "material"
      : pricingMissing.value.some(item => /毛坯/.test(item))
        ? "requirements"
        : "cost";
  detailPanels.value = ["details"];
}

function openAnalysisDetails() {
  editorTab.value = "evidence";
  detailPanels.value = ["details"];
}

function operationSummary(operation: RecordData) {
  if (operation.pricing_mode_code === "external") {
    const byArea = operation.external_price_unit_code === "m2";
    const basis = byArea
      ? "按表面积"
      : operation.external_weight_method_key === "net"
        ? "按净重"
        : "按毛坯重量";
    return `外协 · ${basis} · ${operation.external_rate == null ? "待补单价" : `¥${operation.external_rate}/${byArea ? "m²" : "kg"}`}`;
  }
  return `按工时 · ${operation.unit_hours ?? "待补"} 小时/件 × ${operation.hourly_rate == null ? "待补费率" : `¥${operation.hourly_rate}/小时`}`;
}

function operationResult(index: number) {
  // 修改过程中不重算金额，工序费用只展示服务端本次核价的结果。
  return dirty.value ? null : quote.value?.result.operations?.[index];
}

function operationAmount(index: number) {
  if (dirty.value) return "待更新";
  const result = operationResult(index);
  return result
    ? `¥ ${displayMoney(result.external_unit ?? result.machining_unit)} / 件`
    : "待核价";
}
const numericSpecs = [
  "stock_length",
  "stock_width",
  "stock_height",
  "density",
  "material_price",
  "material_billing_length",
  "external_unit_cost",
  "other_batch_cost"
];
const numericOperations = [
  "unit_hours",
  "hourly_rate",
  "external_rate",
  "external_minimum_unit",
  "external_area_mm2"
];

watch(
  form,
  () => {
    if (!applyingForm) dirty.value = true;
  },
  { deep: true, flush: "sync" }
);
watch(
  () => {
    if (!form.value) return "";
    const { is_requirements_confirmed: _confirmed, ...specs } =
      form.value.specs;
    return JSON.stringify({
      name: form.value.name,
      quantity: form.value.quantity,
      specs,
      operations: form.value.operations
    });
  },
  () => {
    // 计价依据改变后重新要求确认，避免沿用上一版的审核勾选。
    if (!applyingForm && form.value)
      form.value.specs.is_requirements_confirmed = false;
  },
  { flush: "sync" }
);

function applyForm() {
  const data = JSON.parse(JSON.stringify(store.current));
  if (!data) return;
  for (const key of numericSpecs)
    data.specs[key] =
      data.specs[key] == null ? undefined : Number(data.specs[key]);
  for (const operation of data.operations)
    for (const key of numericOperations)
      operation[key] =
        operation[key] == null ? undefined : Number(operation[key]);
  applyingForm = true;
  form.value = data;
  applyingForm = false;
  dirty.value = false;
  externalChange.value = false;
  pricingMissing.value =
    !data.quote && data.analysis?.pricing?.version_no === data.version_no
      ? data.analysis.pricing.missing || []
      : [];
}

async function act(action: () => Promise<void>) {
  const previousBusy = busy.value;
  busy.value = true;
  try {
    await action();
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      /数据已更新|重新加载/.test(error.message)
    ) {
      externalChange.value = true;
      ElMessage.warning(
        "后台数据已更新，未保存的输入仍保留。请点击“重新加载最新结果”，核对后再操作。"
      );
    } else ElMessage.error(businessMessage((error as Error).message));
  } finally {
    busy.value = previousBusy;
  }
}

function useLatestPart(data: RecordData) {
  if (disposed) return;
  if (store.current?.analysis?.artifact_job !== data.analysis?.artifact_job)
    releaseAssets();
  store.current = data;
  applyForm();
}

async function readPartSnapshot(id: string) {
  const latest = await request(`/parts/${id}`);
  // 材料规则与零件一起回填，避免先显示新报价、仍使用旧下拉选项。
  const rules = await request(
    "/quote-rules" + (latest.org_id ? "?org_id=" + latest.org_id : "")
  );
  return { latest, rules };
}

/** 轮询和选材共用版本核对；详情请求期间开始编辑时，不覆盖本地输入。 */
async function syncPart(id: string, forAction = false) {
  const expected = store.current;
  if (disposed || !expected || expected.id !== id) return false;
  const state = await request(`/parts/${id}/status`);
  if (
    disposed ||
    store.current !== expected ||
    deletingId.value === id ||
    (!forAction && busy.value)
  )
    return false;
  const changed =
    state.version_no !== expected.version_no ||
    // 共享报价可能已被其他实例更新，仍须核对本页独立的编辑表单。
    form.value?.id !== id ||
    state.version_no !== form.value?.version_no ||
    (state.job?.status_code === "completed" &&
      form.value?.job?.status_code !== "completed");
  if (changed) {
    if (dirty.value) {
      expected.job = state.job;
      externalChange.value = true;
      if (forAction)
        ElMessage.warning(
          "后台结果已更新，当前输入仍保留，请先重新加载最新结果再选择材料。"
        );
      return false;
    }
    const { latest, rules } = await readPartSnapshot(id);
    if (
      disposed ||
      store.current !== expected ||
      deletingId.value === id ||
      (!forAction && busy.value)
    )
      return false;
    if (dirty.value) {
      expected.job = state.job;
      externalChange.value = true;
      if (forAction)
        ElMessage.warning(
          "后台结果已更新，当前输入仍保留，请先重新加载最新结果再选择材料。"
        );
      return false;
    }
    quoteRules.value = rules;
    useLatestPart(latest);
    if (latest.analysis?.draft?.added_operations) editorTab.value = "cost";
  } else expected.job = state.job;
  if (store.current?.id !== id) return false;
  const rulesVersion =
    store.current.analysis?.material_selection?.rules_version_no;
  if (
    rulesVersion &&
    (!quoteRules.value?.version_no ||
      rulesVersion > quoteRules.value.version_no)
  )
    await refreshRules();
  if (store.current?.id !== id) return false;
  if (forAction && running.value) {
    ElMessage.info("正在解析并匹配材料，完成后会自动更新，请稍后再选材。");
    return false;
  }
  return !externalChange.value;
}

async function reloadLatestPart() {
  if (busy.value || !part.value) return;
  if (dirty.value) {
    try {
      await ElMessageBox.confirm(
        "当前未保存的输入仍在页面中。重新加载将放弃这些输入，使用后台最新的材料、工艺和报价结果，是否继续？",
        "加载最新结果",
        {
          confirmButtonText: "放弃修改并加载",
          cancelButtonText: "保留当前输入"
        }
      );
    } catch {
      return;
    }
  }
  const id = part.value.id;
  await act(async () => {
    const { latest, rules } = await readPartSnapshot(id);
    if (store.current?.id !== id) return;
    quoteRules.value = rules;
    useLatestPart(latest);
    ElMessage.success("已加载最新结果，请核对材料及报价后再修改");
  });
}

async function selectPart(id: string) {
  if (disposed) return;
  if (dirty.value) {
    try {
      await ElMessageBox.confirm(
        "当前修改尚未保存，切换后将放弃这些修改。",
        "切换零件",
        { confirmButtonText: "切换", cancelButtonText: "继续编辑" }
      );
    } catch {
      return;
    }
  }
  stopPolling();
  await act(async () => {
    const latest = await request(`/parts/${id}`);
    if (disposed) return;
    useLatestPart(latest);
    selectedEvidence.value = null;
    highlightedFaces.value = [];
    pageIndex.value = 0;
    view.value = pages.value.length ? "drawing" : "model";
    editorTab.value = store.current!.operations.length
      ? "cost"
      : "requirements";
    detailPanels.value = ["details"];
    await refreshRules();
    if (disposed) return;
    await router.replace({ path: "/mes/quoting", query: { part_id: id } });
    // fullPath 是页面 key；修改 part_id 后旧实例可能已被销毁。
    if (disposed) return;
    let pollErrorReported = false;
    pollTimer = setInterval(async () => {
      if (disposed || polling || busy.value || store.current?.id !== id) return;
      polling = true;
      try {
        await syncPart(id);
        if (disposed) return;
        await store.refreshList(search.value);
        pollErrorReported = false;
      } catch (error) {
        // 断网、请求超时或列表刷新失败后继续轮询，避免后台已完成却一直不回填。
        // 无权访问或零件已删除时才停止，连续失败只提示一次。
        if (error instanceof ApiError && [403, 404].includes(error.status))
          stopPolling();
        if (!pollErrorReported) {
          ElMessage.error(businessMessage((error as Error).message));
          pollErrorReported = true;
        }
      } finally {
        polling = false;
      }
    }, 4000);
  });
}

async function removePart(item: RecordData) {
  try {
    await ElMessageBox.confirm(
      `确定删除“${item.name}”吗？删除后可在“已删除”中恢复。` +
        (part.value?.id === item.id && dirty.value
          ? " 当前未保存的修改将被放弃。"
          : ""),
      "删除询价零件",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger"
      }
    );
  } catch {
    return;
  }
  deletingId.value = item.id;
  try {
    await act(async () => {
      await request(`/parts/${item.id}?version_no=${item.version_no}`, {
        method: "DELETE"
      });
      const currentDeleted = part.value?.id === item.id;
      const index = store.parts.findIndex(row => row.id === item.id);
      if (currentDeleted) {
        stopPolling();
        store.current = null;
        applyingForm = true;
        form.value = null;
        applyingForm = false;
        dirty.value = false;
        await router.replace("/mes/quoting");
      }
      await store.refreshList();
      if (currentDeleted && store.parts.length)
        await selectPart(
          store.parts[Math.max(0, Math.min(index, store.parts.length - 1))].id
        );
      ElMessage.success("零件已删除，可在“已删除”中恢复");
    });
  } finally {
    deletingId.value = "";
  }
}

async function showDeleted() {
  await act(async () => {
    deletedParts.value = await request("/parts?deleted=true");
    deletedOpen.value = true;
  });
}

async function restorePart(item: RecordData) {
  await act(async () => {
    await request(`/parts/${item.id}/restore`, jsonOptions({}));
    deletedParts.value = await request("/parts?deleted=true");
    await store.refreshList();
    ElMessage.success("零件已恢复到询价列表");
  });
}

async function save() {
  if (!form.value) return;
  if (externalChange.value)
    throw new Error(
      "后台数据已更新，当前输入已保留，请先重新加载最新结果再修改。"
    );
  const data = JSON.parse(JSON.stringify(form.value));
  // input-number 清空后的 undefined 显式转为 null，避免沿用旧参数。
  for (const key of numericSpecs)
    if (data.specs[key] == null) data.specs[key] = null;
  for (const operation of data.operations)
    for (const key of numericOperations)
      if (operation[key] == null)
        operation[key] = key === "external_minimum_unit" ? 0 : null;
  store.current = await request(
    "/parts/" + data.id,
    jsonOptions(
      {
        name: data.name,
        quantity: data.quantity,
        version_no: data.version_no,
        specs: data.specs,
        operations: data.operations
      },
      "PUT"
    )
  );
  applyForm();
  await store.refreshList();
}

async function refreshAnalysisServices() {
  checkingServices.value = true;
  servicesError.value = "";
  try {
    health.value = await request("/health");
  } catch (error) {
    health.value = null;
    servicesError.value = (error as Error).message;
  } finally {
    checkingServices.value = false;
  }
}

async function analyze() {
  if (!cloudReady.value) return;
  await act(async () => {
    if (dirty.value) await save();
    await startAnalysis(part.value!.id);
  });
}

async function startAnalysis(id: string) {
  await request(
    `/parts/${id}/analyze`,
    jsonOptions({ mode: "auto", cloud_allowed: true })
  );
  const latest = await request(`/parts/${id}`);
  if (disposed || store.current?.id !== id) return;
  useLatestPart(latest);
  ElMessage.success("正在生成报价，完成后会自动更新");
}

async function adoptLatestDraft() {
  try {
    await ElMessageBox.confirm(
      "将用本次工艺与估时替换当前工序。已有报价快照仍保留，当前未保存修改会先保存。",
      "采用本次工艺",
      {
        confirmButtonText: "采用并核价",
        cancelButtonText: "保留当前工序"
      }
    );
  } catch {
    return;
  }
  await act(async () => {
    if (dirty.value) await save();
    store.current = await request(
      `/parts/${part.value!.id}/adopt-draft`,
      jsonOptions({ version_no: part.value!.version_no })
    );
    applyForm();
    await store.refreshList();
    ElMessage.success("已采用本次工艺，并按当前规则核价");
  });
}

async function createPart() {
  if (!uploadFiles.value.length) {
    ElMessage.warning("请选择 PDF 和/或 STEP 文件");
    return;
  }
  await act(async () => {
    const body = new FormData();
    body.append("name", newName.value);
    body.append("quantity", String(newQuantity.value));
    for (const file of uploadFiles.value) body.append("files", file);
    const created = await request("/parts", { method: "POST", body });
    createOpen.value = false;
    uploadFiles.value = [];
    newName.value = "";
    newQuantity.value = 1;
    await store.refreshList();
    dirty.value = false;
    await nextTick();
    await selectPart(created.id);
    // “上传并生成报价”同时确认本次在线分析，上传后直接衔接解析及核价。
    try {
      await startAnalysis(created.id);
    } catch (error) {
      ElMessage.warning(
        "图纸已上传，暂未开始生成报价。" +
          businessMessage((error as Error).message) +
          "可点击“生成报价”重试。"
      );
    }
  });
}

async function refreshRules() {
  const current = part.value;
  const expectedRules = quoteRules.value;
  const rules = await request(
    "/quote-rules" + (current?.org_id ? "?org_id=" + current.org_id : "")
  );
  if (
    part.value?.id === current?.id &&
    (quoteRules.value === expectedRules ||
      rules.version_no >= quoteRules.value?.version_no)
  )
    quoteRules.value = rules;
}

async function fillFromRules(isStockOnly = false, selectedMaterial?: string) {
  if (busy.value || running.value || externalChange.value || !part.value)
    return;
  await act(async () => {
    if (!(await syncPart(part.value!.id, true))) return;
    if (selectedMaterial !== undefined) {
      form.value!.specs.material_rule_no = selectedMaterial || null;
      form.value!.specs.material_price = undefined;
      form.value!.specs.density = undefined;
    }
    if (dirty.value) await save();
    await refreshRules();
    const result = await request(
      "/parts/" + part.value!.id + "/apply-rules",
      jsonOptions({
        version_no: part.value!.version_no,
        rules_version_no: quoteRules.value!.version_no,
        is_stock_only: isStockOnly
      })
    );
    store.current = result.part;
    applyForm();
    await store.refreshList();
    if (isStockOnly && !result.summary.filled.length) {
      ElMessage.info(
        part.value?.model_dimensions
          ? "毛坯尺寸已有数值，已保留；清空需要重算的尺寸后可再次补齐"
          : "暂无模型净尺寸，请先上传并解析 STEP/STP 模型"
      );
      return;
    }
    const { filled, unmatched_operations, skipped, material_match } = result.summary;
    const feedback = [`已补齐 ${filled.length} 项参数。`];
    if (unmatched_operations.length)
      feedback.push(`未匹配工序：${unmatched_operations.join("、")}。`);
    if (skipped?.length) feedback.push("部分参数请人工补充。");
    if (material_match?.reason) feedback.push(material_match.reason);
    actionMessage(feedback.join("\n"), unmatched_operations.length || skipped?.length ? "warning" : "success");
  });
}

function clearProcessBinding(operation: RecordData) {
  clearArchiveBinding(operation);
  if (!operation.quote_rule_no) return;
  operation.quote_rule_no = null;
  operation.hourly_rate = null;
  operation.external_rate = null;
  operation.parameter_sources = {};
}

async function chooseMaterialReference(value: string) {
  await fillFromRules(false, value);
}

async function selectMaterialWithAi() {
  if (busy.value || running.value || externalChange.value || !part.value)
    return;
  selectingMaterial.value = true;
  await act(async () => {
    if (!(await syncPart(part.value!.id, true))) return;
    if (dirty.value) await save();
    const result = await request(
      "/parts/" + part.value!.id + "/select-material",
      jsonOptions({ version_no: part.value!.version_no, cloud_allowed: true })
    );
    store.current = result.part;
    applyForm();
    await store.refreshList();
    if (result.selection.status === "selected") {
      ElMessage.success(
        `AI 已选择 ${result.selection.rule_name}，补齐 ${result.summary.filled.length} 项参数，已有数值保留`
      );
    } else {
      ElMessage.warning(result.selection.reason);
    }
  }).finally(() => {
    selectingMaterial.value = false;
  });
}

function sourceText(target: RecordData, kind: string) {
  if (
    kind === "specs" &&
    form.value?.specs.material !== part.value?.specs.material
  )
    return "";
  if (kind === "operation") {
    const previous = part.value?.operations.find(
      (row: RecordData) => row.id === target.id
    );
    if (
      !previous ||
      previous.name !== target.name ||
      previous.machine !== target.machine ||
      previous.process_type_code !== target.process_type_code ||
      previous.pricing_mode_code !== target.pricing_mode_code ||
      previous.quote_rule_no !== target.quote_rule_no
    )
      return "";
  }
  const names = Object.entries(target.parameter_sources || {})
    .filter(([key, source]) =>
      numericSpecs.includes(key) || numericOperations.includes(key)
        ? target[key] != null &&
          Number(target[key]) === Number((source as RecordData).value)
        : String(target[key]) === String((source as RecordData).value)
    )
    .map(([, value]) => {
      const source = value as RecordData;
      return source.kind === "ai_estimate"
        ? `${source.rule_name}（按 ${source.quantity} 件预估）`
        : `${source.rule_name}（版本 ${source.version_no}）`;
    });
  return [...new Set(names)].join("、");
}

function businessMessage(value: string = "") {
  // 保留能指导新环境排查的失败类别，不向页面透传服务响应和凭据。
  if (/HTTP\s*(401|403)\b/i.test(value))
    return "图纸分析服务认证或访问权限校验失败，请管理员检查服务配置。";
  if (/HTTP\s*404\b/i.test(value))
    return "图纸分析服务地址或模型不可用，请管理员检查服务配置。";
  if (/HTTP\s*429\b/i.test(value))
    return "图纸分析服务请求受限，请管理员检查可用额度及调用限制。";
  if (/HTTP\s*(400|422)\b/i.test(value))
    return "图纸分析服务未接受请求，请管理员核对模型和图纸分析配置。";
  if (/HTTP\s*5\d\d\b/i.test(value))
    return "图纸分析服务暂不可用，请稍后重新生成。";
  if (
    /OCR|Paddle|DeepSeek|HTTP|云服务|云端|云文档|Markdown|Worker|API|Key|Token|Redis|PostgreSQL|JSON|traceback|PMI|schema/i.test(
      value
    )
  )
    return "部分内容暂未识别完成，可核对原图手工补充，或稍后重新解析。";
  if (/几何摘要|视觉模型|模型提取/.test(value)) return "正在识别制造要求与工艺";
  return value;
}

function focusOperation(operation: RecordData) {
  const references: string[] = operation.evidence_refs || [];
  const localDetail = pages.value
    .flatMap((p: RecordData) =>
      (p.detail_views || []).map((detail: RecordData) => ({
        ...detail,
        image: p.image,
        value: detail.label,
        source: "原图局部放大框"
      }))
    )
    .find((detail: RecordData) => references.includes(detail.id));
  if (localDetail) {
    focusFact(localDetail);
    return;
  }
  const faces = (geometry.value?.features || []).filter((feature: RecordData) =>
    references.includes(feature.id)
  );
  if (faces.length || (!pages.value.length && geometry.value)) {
    highlightedFaces.value = faces.flatMap(
      (feature: RecordData) => feature.face_ids
    );
    view.value = "model";
    return;
  }
  const evidence = pages.value
    .flatMap((p: RecordData) =>
      (p.ocr_blocks || []).map((block: RecordData) => ({
        ...block,
        image: p.image
      }))
    )
    .find((block: RecordData) => references.includes(block.id));
  if (evidence) {
    focusFact(evidence);
    return;
  }
  const index = pages.value.findIndex(
    (p: RecordData, i: number) =>
      references.includes(`pdf:p${i + 1}`) ||
      references.some(ref => ref.startsWith(`ocr-${p.fileId}-p${p.number}-`))
  );
  if (index >= 0) {
    pageIndex.value = index;
    view.value = "drawing";
    selectedEvidence.value = null;
  } else if (geometry.value) {
    view.value = "model";
    highlightedFaces.value = [];
  }
}

function focusFact(fact: RecordData) {
  const index = pages.value.findIndex(
    (p: RecordData) => p.image === fact.image
  );
  if (index >= 0) pageIndex.value = index;
  selectedEvidence.value = fact;
  view.value = "drawing";
}

function adoptFact(fact: RecordData) {
  if (["material", "treatment", "hardness", "tolerance"].includes(fact.key))
    form.value!.specs[fact.key] = fact.value;
  else form.value!.specs.notes += "\n" + fact.value;
  form.value!.specs.is_requirements_confirmed = false;
  focusFact(fact);
}

async function evaluate() {
  await act(async () => {
    if (dirty.value) await save();
    try {
      await request("/parts/" + part.value!.id + "/quote", jsonOptions({}));
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 422 &&
        Array.isArray(error.detail?.missing)
      ) {
        pricingMissing.value = error.detail.missing;
        ElMessage.warning("请先补充材料、毛坯及工序计价参数");
        return;
      }
      throw error;
    }
    await store.load(part.value!.id);
    applyForm();
    ElMessage.success("报价已更新");
  });
}

async function approve() {
  try {
    await ElMessageBox.confirm(
      "以当前登录身份审核本次报价，审核后保留核价依据。",
      "审核报价",
      {
        confirmButtonText: "确认审核",
        cancelButtonText: "取消"
      }
    );
    await act(async () => {
      await request("/quotes/" + quote.value.id + "/approve", jsonOptions({}));
      await store.load(part.value!.id);
      applyForm();
      ElMessage.success("报价已审核");
    });
  } catch {
    /* 用户取消审核，保留当前编辑状态。 */
  }
}

onMounted(async () => {
  await act(async () => {
    await refreshAnalysisServices();
    await store.refreshList();
  });
  const id = String(route.query.part_id || store.parts[0]?.id || "");
  if (id) await selectPart(id);
});
onBeforeUnmount(() => {
  disposed = true;
  stopPolling();
  clearTimeout(searchTimer);
  releaseAssets();
  store.$reset();
});
</script>

<template>
  <div class="cnc-workbench app-shell" @click.capture="downloadLink">
    <header class="app-header">
      <div class="brand">
        <span class="brand-mark">工</span>
        <div>
          <strong>加工工艺与评估报价</strong
          ><small>图纸解析 · 工艺复核 · 成本核算</small>
        </div>
      </div>
      <div class="header-status">
        <el-button
          :aria-expanded="tasksExpanded"
          aria-controls="quoting-task-list"
          @click="tasksExpanded = !tasksExpanded"
          >{{ tasksExpanded ? "收起任务" : "任务列表" }}</el-button
        >
        <el-button
          v-if="hasPerms('mes:quote:rules')"
          @click="rulesEditor?.show()"
          >报价规则</el-button
        >
        <el-button
          v-if="hasPerms('mes:quote:manage')"
          type="primary"
          @click="createOpen = true"
          >上传图纸</el-button
        >
      </div>
    </header>

    <div class="workbench" :class="{ 'tasks-collapsed': !tasksExpanded }">
      <aside
        v-show="tasksExpanded"
        id="quoting-task-list"
        class="project-sidebar"
      >
        <div class="sidebar-heading">
          <strong>询价零件</strong><span>{{ store.parts.length }}</span>
          <el-button link size="small" :disabled="busy" @click="showDeleted"
            >已删除</el-button
          >
        </div>
        <el-input v-model="search" placeholder="搜索名称或图号" clearable />
        <div class="part-list">
          <div
            v-for="item in parts"
            :key="item.id"
            class="part-item"
            :class="{ active: part?.id === item.id }"
          >
            <button
              class="part-select"
              :disabled="busy"
              @click="selectPart(item.id)"
            >
              <strong>{{ item.name }}</strong
              ><span
                >{{ item.quantity }} 件
                <i>{{
                  item.job?.status_code === "running"
                    ? "解析中"
                    : item.job?.status_code === "completed"
                      ? "已解析"
                      : item.job?.status_code === "failed"
                        ? "解析失败"
                        : item.job?.status_code === "queued"
                          ? "排队中"
                          : "待解析"
                }}</i></span
              >
              <time
                class="part-created-at"
                :datetime="item.created_at"
                :title="'创建时间：' + formatTaskTime(item.created_at)"
                >{{ formatTaskTime(item.created_at) }}</time
              >
            </button>
            <button
              v-if="hasPerms('mes:quote:manage')"
              class="part-remove"
              :aria-label="'删除零件：' + item.name"
              :disabled="
                busy || ['queued', 'running'].includes(item.job?.status_code)
              "
              :title="
                ['queued', 'running'].includes(item.job?.status_code)
                  ? '解析结束后可删除'
                  : '删除零件'
              "
              @click="removePart(item)"
            >
              删除
            </button>
          </div>
        </div>
        <div class="sidebar-footer">
          单零件 PDF / STEP<br />尺寸与工艺需审核后用于报价
        </div>
      </aside>

      <template v-if="part && form">
        <main class="preview-panel">
          <div class="part-title">
            <div>
              <small>零件 / 修订 {{ part.version_no }}</small>
              <h1>{{ part.name }}</h1>
            </div>
            <span>{{ part.quantity }} 件</span>
          </div>
          <div class="task-bar">
            <div>
              <span
                class="task-state"
                :class="{ failed: part.job?.status_code === 'failed' }"
                >{{ taskStage }}</span
              ><small v-if="part.job?.error" class="error-text">{{
                "本次解析未完成，请稍后重试或手工补充要求。"
              }}</small>
            </div>
            <el-button
              v-if="hasPerms(['mes:quote:manage', 'mes:quote:analyze'])"
              type="primary"
              :loading="running || busy"
              :disabled="!cloudReady || running || busy"
              @click="analyze"
              >{{
                analysis.artifact_job ? "重新生成报价" : "生成报价"
              }}</el-button
            >
          </div>
          <p class="analysis-flow field-help">
            {{
              hasPdf
                ? "识别图纸要求，结合三维模型生成可编辑的工艺初稿。"
                : "根据三维模型生成工艺建议；材料、公差和处理要求请结合图纸补充。"
            }}报价生成后可继续修改完善。
          </p>
          <p v-if="checkingServices" class="field-help">正在准备报价服务…</p>
          <el-alert
            v-else-if="!cloudReady"
            class="analysis-service-notice"
            :title="servicesError ? '报价服务暂不可用' : '暂不能自动生成报价'"
            :type="servicesError ? 'error' : 'warning'"
            :closable="false"
            show-icon
          >
            <p v-if="servicesError">请稍后重试，或联系管理员检查报价服务。</p>
            <template v-else>
              <p>{{ missingAnalysisConfig.join("、") }}尚未就绪。</p>
              <p>请联系管理员处理，已有报价仍可修改和完善。</p>
            </template>
            <el-button
              size="small"
              :loading="checkingServices"
              @click="refreshAnalysisServices"
            >
              重新检查
            </el-button>
          </el-alert>
          <el-alert
            v-if="externalChange"
            title="后台结果已更新，未保存的输入仍保留，暂不能提交。请重新加载最新结果后再修改。"
            type="warning"
            :closable="false"
            ><el-button :disabled="busy" @click="reloadLatestPart"
              >重新加载最新结果</el-button
            ></el-alert
          >
          <div class="file-links">
            <a
              v-for="file in part.files"
              :key="file.id"
              :href="'/api/mes/cnc/files/' + file.id"
              :data-filename="file.name"
              target="_blank"
              >{{ file.name }}</a
            >
          </div>
          <div class="preview-tabs">
            <button
              :class="{ active: view === 'drawing' }"
              @click="view = 'drawing'"
            >
              二维图纸</button
            ><button
              :class="{ active: view === 'model' }"
              @click="view = 'model'"
            >
              三维模型</button
            ><el-select
              v-if="view === 'drawing' && pages.length"
              v-model="pageIndex"
              size="small"
              style="width: 130px; margin-left: auto"
              ><el-option
                v-for="(p, index) in pages"
                :key="index"
                :value="Number(index)"
                :label="'第 ' + p.number + ' 页'"
            /></el-select>
          </div>
          <DrawingView
            v-if="view === 'drawing' && page"
            :key="part.id + ':' + analysis.artifact_job"
            :image-url="`/api/mes/cnc/parts/${part.id}/assets/${encodeURIComponent(page.image)}`"
            :page="page"
            :selected="selectedEvidence"
            @select="value => (selectedEvidence = value)"
          />
          <ModelView
            v-else-if="view === 'model' && geometry"
            :key="part.id + ':' + analysis.artifact_job"
            :url="`/api/mes/cnc/parts/${part.id}/assets/${encodeURIComponent(geometry.mesh)}`"
            :highlighted-faces="highlightedFaces"
          />
          <div v-else class="empty-preview">
            <strong>{{
              running
                ? "正在处理图纸"
                : view === "model"
                  ? "暂无可用三维模型"
                  : "暂无图纸预览"
            }}</strong>
            <p>
              {{
                running
                  ? "后台完成后会自动显示解析结果。"
                  : "上传对应文件并开始解析；已有结果可在右侧补充和修正。"
              }}
            </p>
          </div>
          <div v-if="selectedEvidence" class="evidence-strip">
            <span>选中依据</span
            ><strong>{{
              selectedEvidence.text || selectedEvidence.value
            }}</strong
            ><small>{{
              selectedEvidence.evidence_status === "visual_estimate"
                ? "视觉估计位置，待复核"
                : "图纸标注，待复核"
            }}</small
            ><button @click="selectedEvidence = null">关闭</button>
          </div>
          <div v-if="geometry" class="geometry-summary">
            <span
              >包围盒
              <b
                >{{
                  geometry.bounds.map((v: number) => v.toFixed(2)).join(" × ")
                }}
                mm</b
              ></span
            ><span
              >净体积
              <b>{{ (geometry.volume_mm3 / 1000).toFixed(3) }} cm³</b></span
            ><span
              >表面积
              <b>{{ (geometry.area_mm2 / 100).toFixed(2) }} cm²</b></span
            >
          </div>
          <el-alert
            v-if="analysis.ai?.uncovered_requirements?.length"
            title="部分加工要求待补充，已匹配工序继续处理"
            type="warning"
            :closable="false"
            show-icon
          >
            <p v-for="item in analysis.ai.uncovered_requirements" :key="item">
              {{ item }}
            </p>
          </el-alert>
          <div v-if="analysis.warnings?.length" class="analysis-notes">
            <strong>需要核对</strong>
            <p
              v-for="warning in [
                ...new Set(
                  (analysis.warnings || []).map((item: string) =>
                    businessMessage(item)
                  )
                )
              ]"
              :key="String(warning)"
            >
              {{ warning }}
            </p>
          </div>
          <el-button
            v-if="
              part.job &&
              ['queued', 'running', 'failed'].includes(part.job.status_code)
            "
            link
            class="reconcile-button"
            @click="
              act(async () => {
                await request(
                  '/jobs/' + part!.job.id + '/reconcile',
                  jsonOptions({})
                );
                await store.load(part!.id);
                applyForm();
              })
            "
            >异常任务状态核对</el-button
          >
        </main>

        <aside class="editor-panel" :class="{ 'has-quote': !!quote }">
          <section class="quote-panel">
            <div class="section-title">
              <h2>报价结果</h2>
              <el-tag
                v-if="quote?.result.is_reference"
                type="warning"
                size="small"
                >参考报价</el-tag
              >
              <el-tag v-if="dirty" type="warning" size="small"
                >修改待更新</el-tag
              >
              <el-tag
                v-else-if="quote"
                :type="quote.approved_by ? 'success' : 'info'"
                size="small"
                >{{ quote.approved_by ? "已审核" : "待复核" }}</el-tag
              >
            </div>
            <el-alert
              v-if="analysisIssue && !quote"
              :title="analysisIssue"
              type="warning"
              :closable="false"
              show-icon
            >
              <el-button link type="primary" @click="openAnalysisDetails"
                >查看解析结果</el-button
              >
            </el-alert>
            <template v-if="quote">
              <div class="quote-headline">
                <span>{{ dirty ? "上次不含税单价" : "不含税单价" }}</span>
                <strong>¥ {{ displayMoney(quote.result.unit_price) }}</strong>
              </div>
              <div class="quote-batch-total">
                <span>{{ quote.result.quantity }} 件合计</span>
                <b>¥ {{ displayMoney(quote.result.total_price) }}</b>
              </div>
              <div
                v-if="quote.result.weight_estimate?.estimated_weight_kg != null"
                class="quote-batch-total"
              >
                <span>{{
                  quote.result.weight_estimate.method_key === "cad_volume"
                    ? "预计净重 / 件"
                    : "外形估重 / 件（未扣孔槽）"
                }}</span>
                <b
                  >{{
                    displayWeight(
                      quote.result.weight_estimate.estimated_weight_kg
                    )
                  }}
                  kg</b
                >
              </div>
              <div
                v-if="quote.result.weight_estimate?.stock_weight_kg != null"
                class="quote-batch-total"
              >
                <span>毛坯重量 / 件</span>
                <b
                  >{{
                    displayWeight(quote.result.weight_estimate.stock_weight_kg)
                  }}
                  kg</b
                >
              </div>
              <div
                v-if="quote.result.warnings?.length"
                class="quote-update-notice"
              >
                <p v-for="warning in quote.result.warnings" :key="warning">
                  {{ warning }}
                </p>
              </div>
              <details class="cost-breakdown">
                <summary>查看费用构成</summary>
                <div class="quote-details">
                  <div>
                    <span>材料 / 件</span
                    ><b>¥ {{ displayMoney(quote.result.material_unit) }}</b>
                  </div>
                  <div>
                    <span>加工 / 件</span
                    ><b>¥ {{ displayMoney(quote.result.machining_unit) }}</b>
                  </div>
                  <div>
                    <span>外协 / 件</span
                    ><b>¥ {{ displayMoney(quote.result.external_unit) }}</b>
                  </div>
                  <div v-if="Number(quote.result.other_batch)">
                    <span>其他费用 / 批</span
                    ><b>¥ {{ displayMoney(quote.result.other_batch) }}</b>
                  </div>
                  <small
                    >报价修订 {{ quote.version_no
                    }}{{
                      quote.approved_by ? " · 已审核" : " · 内部评估"
                    }}</small
                  >
                </div>
              </details>
            </template>
            <div v-else class="quote-placeholder">
              {{
                running
                  ? "正在生成报价…"
                  : analysisIssue
                    ? "本次解析尚未生成完整报价数据"
                    : pricingMissing.length
                      ? "补充以下信息后即可核价"
                      : "点击更新报价完成核算"
              }}
            </div>
            <p v-if="dirty" class="quote-update-notice">
              修改尚未计入报价，完成编辑后点击“更新报价”。
            </p>
            <p v-if="materialNeedsAttention" class="quote-update-notice">
              材料参考价尚未匹配，请重新匹配或手动选择材料后更新报价。
            </p>
            <details v-if="pricingMissing.length" class="quote-missing" open>
              <summary>待补充 {{ pricingMissing.length }} 项信息</summary>
              <ul>
                <li v-for="missing in pricingMissing" :key="missing">
                  {{ missing }}
                </li>
              </ul>
            </details>
            <div class="quote-actions">
              <el-button
                v-if="hasPerms('mes:quote:manage')"
                type="primary"
                :loading="busy"
                :disabled="running || externalChange"
                @click="evaluate"
                >更新报价</el-button
              >
              <el-button
                v-if="pricingMissing.length || materialNeedsAttention"
                @click="openQuoteDetails"
                >完善缺失信息</el-button
              >
              <el-button
                v-if="
                  quote && !quote.approved_by && hasPerms('mes:quote:approve')
                "
                :disabled="
                  dirty || !form.specs.is_requirements_confirmed || running
                "
                @click="approve"
                >审核报价</el-button
              >
              <template v-if="quote && !dirty">
                <a :href="'/api/mes/cnc/quotes/' + quote.id + '/export/xlsx'"
                  >导出 Excel</a
                >
                <a :href="'/api/mes/cnc/quotes/' + quote.id + '/export/pdf'"
                  >导出 PDF</a
                >
              </template>
            </div>
            <el-checkbox
              v-if="quote"
              v-model="form.specs.is_requirements_confirmed"
              class="review-checkbox"
              >已核对制造要求、工艺和费用</el-checkbox
            >
            <details v-if="part.quote_history.length">
              <summary>历史报价 {{ part.quote_history.length }} 条</summary>
              <div
                v-for="old in part.quote_history"
                :key="old.id"
                class="history-row"
              >
                <span
                  >修订 {{ old.version_no }} · ¥{{ old.result.unit_price }} ·
                  {{ old.approved_by ? "已审核" : "评估" }}</span
                >
                <a :href="'/api/mes/cnc/quotes/' + old.id + '/export/xlsx'"
                  >导出</a
                >
              </div>
            </details>
          </section>
          <el-collapse v-model="detailPanels" class="quote-edit-details">
            <el-collapse-item name="details" title="查看和修改报价明细">
              <el-tabs v-model="editorTab" class="editor-tabs">
                <el-tab-pane label="制造要求" name="requirements">
                  <section class="editor-section">
                    <h2>基础信息</h2>
                    <div class="field">
                      <label>零件名称</label><el-input v-model="form.name" />
                    </div>
                    <div class="field">
                      <label>询价数量</label
                      ><el-input-number
                        v-model="form.quantity"
                        :min="1"
                        :max="1000000"
                        :precision="0"
                      />
                    </div>
                    <div class="field">
                      <label>表面处理</label
                      ><el-input
                        v-model="form.specs.treatment"
                        placeholder="处理方式、厚度、适用范围"
                      />
                    </div>
                    <div class="field">
                      <label>硬度 / 热处理</label
                      ><el-input v-model="form.specs.hardness" />
                    </div>
                    <div class="field">
                      <label>公差 / 粗糙度</label
                      ><el-input v-model="form.specs.tolerance" />
                    </div>
                    <div class="field vertical">
                      <label>技术备注与核价假设</label
                      ><el-input
                        v-model="form.specs.notes"
                        type="textarea"
                        :rows="4"
                      />
                    </div>
                  </section>
                </el-tab-pane>
                <el-tab-pane label="材料与费用" name="material">
                  <section class="editor-section">
                    <div class="section-title">
                      <h2>材料与计价条件</h2>
                      <el-button
                        v-if="
                          hasPerms(['mes:quote:manage', 'mes:quote:analyze'])
                        "
                        size="small"
                        :disabled="
                          busy ||
                          running ||
                          externalChange ||
                          !health?.ai_configured ||
                          !!form.specs.material_rule_no
                        "
                        :loading="selectingMaterial"
                        @click="selectMaterialWithAi"
                        >AI 选材</el-button
                      >
                    </div>
                    <div class="field">
                      <label>材料牌号</label
                      ><el-input
                        v-model="form.specs.material"
                        placeholder="保留客户原始牌号"
                      />
                    </div>
                    <p v-if="running" class="field-help">
                      正在解析并匹配材料，完成后会自动显示最新选材及报价结果。
                    </p>
                    <p v-else-if="!health?.ai_configured" class="field-help">
                      自动选材暂不可用，请联系管理员，或手动选择材料参考价。
                    </p>
                    <p
                      v-else-if="form.specs.material_rule_no"
                      class="field-help"
                    >
                      当前使用手选规则；清除下方选择后可使用 AI 选材。
                    </p>
                    <p v-else class="field-help">
                      图纸分析后会自动匹配材料价格；也可单独重新匹配，只补空白数值。
                    </p>
                    <p v-if="materialSelectionFeedback" class="field-help">
                      {{ materialSelectionFeedback }}
                    </p>
                    <details
                      v-if="analysis.material_selection?.reason"
                      class="material-selection-reason"
                    >
                      <summary>查看选材说明</summary>
                      <p class="field-help">
                        {{
                          businessMessage(analysis.material_selection.reason)
                        }}
                      </p>
                    </details>
                    <div class="field">
                      <label>材料参考价（可手动指定）</label>
                      <el-select
                        :key="`${form.id}:${form.version_no}:${quoteRules?.version_no || 0}:${materialRuleSelection}`"
                        :model-value="materialRuleSelection"
                        :disabled="busy || running || externalChange"
                        filterable
                        :clearable="!!form.specs.material_rule_no"
                        :placeholder="materialReferencePlaceholder"
                        @change="chooseMaterialReference"
                      >
                        <el-option
                          v-for="item in (
                            quoteRules?.config.materials || []
                          ).filter((row: RecordData) => row.is_active)"
                          :key="item.id"
                          :value="item.id"
                          :label="`${item.name} ${item.condition || ''} · ${item.material_price ?? '缺价'}元/${item.price_unit_code || 'kg'}`"
                        />
                      </el-select>
                    </div>
                    <p
                      v-if="sourceText(form.specs, 'specs')"
                      class="field-help"
                    >
                      参数来源：{{ sourceText(form.specs, "specs") }}
                    </p>
                    <div class="field">
                      <label>材料密度 g/cm³</label
                      ><el-input-number
                        v-model="form.specs.density"
                        :min="0.001"
                        :precision="3"
                        :controls="false"
                      />
                    </div>
                    <div class="field">
                      <label
                        >材料单价
                        {{
                          form.specs.material_price_unit_code === "mm"
                            ? "元/mm"
                            : "元/kg"
                        }}</label
                      ><el-input-number
                        v-model="form.specs.material_price"
                        :min="0.0001"
                        :precision="4"
                        :controls="false"
                      />
                    </div>
                    <div class="field">
                      <label>材料计价单位</label
                      ><el-select v-model="form.specs.material_price_unit_code"
                        ><el-option label="元/kg" value="kg" /><el-option
                          label="元/mm"
                          value="mm"
                      /></el-select>
                    </div>
                    <div
                      v-if="form.specs.material_price_unit_code === 'mm'"
                      class="field"
                    >
                      <label>材料计费长度 mm/件</label
                      ><el-input-number
                        v-model="form.specs.material_billing_length"
                        :min="0.001"
                        :controls="false"
                      />
                    </div>
                    <div class="field">
                      <label>其他外协费用 元/件</label
                      ><el-input-number
                        v-model="form.specs.external_unit_cost"
                        :min="0"
                        :precision="2"
                        :controls="false"
                      />
                    </div>
                    <div class="field">
                      <label>其他费用 元/批</label
                      ><el-input-number
                        v-model="form.specs.other_batch_cost"
                        :min="0"
                        :precision="2"
                        :controls="false"
                      />
                    </div>
                    <p class="field-help">
                      按材料、工序、外协及其他费用直接计价，不额外加价。工序暂只填小时/件，不单列准备时间。
                    </p>
                  </section>
                  <section class="editor-section">
                    <h2>模型净尺寸</h2>
                    <div
                      v-if="part.model_dimensions"
                      class="stock-grid model-dimensions"
                    >
                      <div
                        v-for="(label, key) in {
                          length: '长（X）mm',
                          width: '宽（Y）mm',
                          height: '高（Z）mm'
                        }"
                        :key="key"
                      >
                        <label>{{ label }}</label
                        ><strong>{{
                          Number(part.model_dimensions[key]).toFixed(3)
                        }}</strong>
                      </div>
                    </div>
                    <p class="field-help">
                      {{
                        part.model_dimensions
                          ? "已从三维模型自动带入，按模型坐标方向测量，未包含加工余量。"
                          : "上传并解析三维模型后自动显示净尺寸；仅有图纸时请核对尺寸后填写毛坯。"
                      }}
                    </p>
                  </section>
                  <section class="editor-section">
                    <div class="section-title">
                      <h2>长方体毛坯</h2>
                      <el-button
                        v-if="geometry"
                        size="small"
                        link
                        type="primary"
                        :disabled="busy || running"
                        @click="fillFromRules(true)"
                        >按规则补齐毛坯</el-button
                      >
                    </div>
                    <div class="stock-grid">
                      <div
                        v-for="(label, key) in {
                          stock_length: '长 mm',
                          stock_width: '宽 mm',
                          stock_height: '高 mm'
                        }"
                        :key="key"
                      >
                        <label>{{ label }}</label
                        ><el-input-number
                          v-model="form.specs[key]"
                          :min="0.001"
                          :precision="3"
                          :controls="false"
                        />
                      </div>
                    </div>
                    <p class="field-help">
                      解析后自动补齐：每个净尺寸加 5 mm，再向上取到 5 mm
                      的整数倍（24 → 30 mm）。
                      已有尺寸保留；棒料等仍需换算采购分摊。
                    </p>
                  </section>
                  <section v-if="weightEstimate" class="editor-section">
                    <h2>重量预估</h2>
                    <div class="stock-grid weight-grid">
                      <div>
                        <label>{{
                          weightEstimate.method_key === "model_bounds"
                            ? "单件外形估重（未扣孔槽）kg"
                            : "单件预计净重 kg"
                        }}</label>
                        <strong>{{
                          weightInputsChanged
                            ? "待更新"
                            : displayWeight(weightEstimate.estimated_weight_kg)
                        }}</strong>
                      </div>
                      <div>
                        <label>{{
                          weightEstimate.method_key === "model_bounds"
                            ? "整批外形估重 kg"
                            : "整批预计净重 kg"
                        }}</label>
                        <strong>{{
                          weightInputsChanged
                            ? "待更新"
                            : displayWeight(
                                weightEstimate.estimated_total_weight_kg
                              )
                        }}</strong>
                      </div>
                      <div>
                        <label>单件毛坯重量 kg</label>
                        <strong>{{
                          weightInputsChanged
                            ? "待更新"
                            : displayWeight(weightEstimate.stock_weight_kg)
                        }}</strong>
                      </div>
                      <div>
                        <label>整批毛坯重量 kg</label>
                        <strong>{{
                          weightInputsChanged
                            ? "待更新"
                            : displayWeight(
                                weightEstimate.stock_total_weight_kg
                              )
                        }}</strong>
                      </div>
                    </div>
                    <p class="field-help">{{ weightEstimate.basis }}</p>
                    <p class="field-help">
                      体积 mm³ × 密度 g/cm³ ÷ 1,000,000 = 重量 kg；按已保存数量
                      {{ weightEstimate.quantity }} 件计算。
                    </p>
                    <p v-if="weightInputsChanged" class="field-help">
                      密度、毛坯尺寸或数量已修改，点击“更新报价”刷新重量。
                    </p>
                  </section>
                </el-tab-pane>
                <el-tab-pane label="加工与外协" name="cost">
                  <section
                    v-if="analysis.draft"
                    class="editor-section draft-summary"
                  >
                    <h2>工艺初稿 · 待人工审核</h2>
                    <p class="field-help">
                      {{
                        analysis.draft.added_operations
                          ? `已自动填入 ${analysis.draft.added_operations} 道工序，可直接修改或删除。`
                          : analysis.draft.preserved_operations
                            ? "已保留现有工序及计价参数；本次新建议可在识别依据中查看并采用。"
                            : "暂未生成可用工序，请查看解析结果中的提示。"
                      }}
                    </p>
                    <p v-if="form.operations.length" class="field-help">
                      请逐项核对工时与费率，缺失参数需补充后再核价。
                    </p>
                    <p class="field-help">
                      材料：{{ form.specs.material || "待确认" }} ·
                      制造要求见“制造要求”页。
                    </p>
                  </section>
                  <section class="editor-section">
                    <div class="section-title">
                      <h2>加工工序</h2>
                    </div>
                    <div v-if="!form.operations.length" class="inline-empty">
                      图纸分析完成后自动生成加工工序，可在此修改和完善。
                    </div>
                    <details
                      v-for="(operation, index) in form.operations"
                      :key="operation.id"
                      class="operation-row"
                    >
                      <summary class="operation-summary">
                        <span class="operation-index">{{
                          Number(index) + 1
                        }}</span>
                        <span class="operation-overview">
                          <strong>{{ operation.name || "未命名工序" }}</strong>
                          <small>{{ operationSummary(operation) }}</small>
                        </span>
                        <b>{{ operationAmount(Number(index)) }}</b>
                        <span class="operation-expand">编辑</span>
                      </summary>
                      <div class="operation-editor">
                        <div class="operation-name">
                          <span>{{ Number(index) + 1 }}</span
                          ><el-input
                            v-model="operation.name"
                            placeholder="工序名称"
                            @input="clearArchiveBinding(operation)"
                          /><el-button
                            link
                            type="danger"
                            @click="form.operations.splice(Number(index), 1)"
                            >删除</el-button
                          >
                        </div>
                        <div class="field vertical">
                          <label
                            >正式生产工艺
                            <el-tag
                              :type="
                                operation.process_id ? 'success' : 'warning'
                              "
                              >{{
                                operation.process_no_snapshot || "待工程匹配"
                              }}</el-tag
                            ></label
                          >
                          <el-select
                            :model-value="operation.process_id || ''"
                            filterable
                            clearable
                            :loading="processOptionsLoading"
                            placeholder="选择当前组织的工艺档案"
                            @change="
                              selectManufacturingProcess(operation, $event)
                            "
                          >
                            <el-option
                              v-if="
                                operation.process_id &&
                                !processOptions(operation).some(
                                  p => p.id === operation.process_id
                                )
                              "
                              :value="operation.process_id"
                              :label="`${operation.process_no_snapshot || ''} · ${operation.name}（当前不可选）`"
                              disabled
                            />
                            <el-option
                              v-for="p in processOptions(operation)"
                              :key="p.id"
                              :value="p.id"
                              :label="`${p.process_no} · ${p.process_name}`"
                            />
                          </el-select>
                          <small v-if="processOptionsError" class="field-help"
                            >{{ processOptionsError }}
                            <el-button
                              link
                              type="primary"
                              @click="refreshManufacturingProcesses"
                              >刷新</el-button
                            ></small
                          >
                        </div>
                        <div class="operation-source">
                          <small>{{
                            operation.origin_code === "ai"
                              ? "自动初稿 · 可编辑，待工程确认"
                              : "人工工序"
                          }}</small
                          ><el-button
                            v-if="operation.evidence_refs?.length"
                            link
                            size="small"
                            @click="focusOperation(operation)"
                            >查看依据</el-button
                          >
                        </div>
                        <div class="field vertical">
                          <label>{{
                            operation.pricing_mode_code === "external"
                              ? "外协说明"
                              : "加工设备"
                          }}</label>
                          <el-input
                            v-model="operation.machine"
                            :placeholder="
                              operation.pricing_mode_code === 'external'
                                ? '选填，例如外协处理要求'
                                : '选填，例如三轴加工中心'
                            "
                          />
                        </div>
                        <div
                          v-if="operation.pricing_mode_code !== 'external'"
                          class="field vertical"
                        >
                          <label>加工类别</label>
                          <el-select
                            v-model="operation.process_type_code"
                            clearable
                            placeholder="选择工序类别以匹配费率"
                            @change="clearProcessBinding(operation)"
                          >
                            <el-option
                              v-for="item in quoteRules?.process_catalog || []"
                              :key="item.process_type_code"
                              :label="item.name"
                              :value="item.process_type_code"
                            />
                          </el-select>
                        </div>
                        <div class="field vertical">
                          <label>计价方式</label>
                          <el-select
                            v-model="operation.pricing_mode_code"
                            placeholder="计价方式"
                            @change="clearProcessBinding(operation)"
                          >
                            <el-option
                              label="按工时计价"
                              value="hourly"
                            /><el-option label="外协加工" value="external" />
                          </el-select>
                        </div>
                        <div
                          v-if="operation.pricing_mode_code === 'external'"
                          class="operation-values"
                        >
                          <div>
                            <label
                              >外协单价
                              {{
                                operation.external_price_unit_code === "m2"
                                  ? "元/m²"
                                  : "元/kg"
                              }}</label
                            ><el-input-number
                              v-model="operation.external_rate"
                              :min="0"
                              :precision="2"
                              :controls="false"
                            />
                          </div>
                          <div>
                            <label>单件最低收费（元/件）</label
                            ><el-input-number
                              v-model="operation.external_minimum_unit"
                              :min="0"
                              :precision="2"
                              :controls="false"
                            />
                          </div>
                          <div>
                            <label>计费单位</label>
                            <el-select
                              v-model="operation.external_price_unit_code"
                            >
                              <el-option label="按重量（元/kg）" value="kg" />
                              <el-option label="按面积（元/m²）" value="m2" />
                            </el-select>
                          </div>
                          <div
                            v-if="operation.external_price_unit_code === 'm2'"
                          >
                            <label>计费面积（mm²/件）</label>
                            <el-input-number
                              v-model="operation.external_area_mm2"
                              :min="0.001"
                              :controls="false"
                              placeholder="留空使用模型表面积"
                            />
                          </div>
                          <div v-else>
                            <label>计费重量</label>
                            <el-select
                              v-model="operation.external_weight_method_key"
                            >
                              <el-option label="按毛坯重量" value="stock" />
                              <el-option label="按零件净重" value="net" />
                            </el-select>
                          </div>
                        </div>
                        <div v-else class="operation-values">
                          <div>
                            <label>预估工时 h/件</label
                            ><el-input-number
                              v-model="operation.unit_hours"
                              placeholder="待填写"
                              :min="0"
                              :precision="4"
                              :controls="false"
                            />
                          </div>
                          <div>
                            <label>小时费率 元/h</label
                            ><el-input-number
                              v-model="operation.hourly_rate"
                              placeholder="待填写"
                              :min="0.01"
                              :precision="2"
                              :controls="false"
                            />
                          </div>
                        </div>
                        <p
                          v-if="operationResult(Number(index))"
                          class="field-help"
                        >
                          本次核价：{{ operationAmount(Number(index)) }}
                          <template
                            v-if="operation.pricing_mode_code === 'external'"
                          >
                            （计费{{
                              operation.external_price_unit_code === "m2"
                                ? "面积"
                                : "重量"
                            }}：
                            {{
                              operationResult(Number(index)).charged_area_m2 ??
                              operationResult(Number(index)).charged_weight_kg
                            }}
                            {{
                              operation.external_price_unit_code === "m2"
                                ? "m²"
                                : "kg"
                            }}；单件最低收费 ¥{{
                              operation.external_minimum_unit || 0
                            }}）
                          </template>
                        </p>
                        <p v-if="operation.estimate_basis" class="field-help">
                          {{
                            operation.pricing_mode_code === "external"
                              ? "计价依据"
                              : "工时依据"
                          }}：{{ operation.estimate_basis }}
                        </p>
                        <p
                          v-if="operation.assumptions?.length"
                          class="field-help"
                        >
                          估算假设：{{ operation.assumptions.join("；") }}
                        </p>
                        <p
                          v-if="
                            operation.estimate_quantity &&
                            operation.estimate_quantity !== form.quantity
                          "
                          class="warning-text"
                        >
                          该工时按
                          {{ operation.estimate_quantity }}
                          件预估，数量已变化，请复核。
                        </p>
                        <p
                          v-if="sourceText(operation, 'operation')"
                          class="field-help"
                        >
                          参数来源：{{ sourceText(operation, "operation") }}
                        </p>
                        <el-input
                          v-model="operation.note"
                          type="textarea"
                          :autosize="{ minRows: 2, maxRows: 4 }"
                          placeholder="补充加工要求或待确认事项"
                        />
                      </div>
                    </details>
                  </section>
                </el-tab-pane>
                <el-tab-pane label="识别依据" name="evidence" lazy>
                  <section v-if="analysis.ocr" class="editor-section">
                    <h2>图纸识别</h2>
                    <p class="field-help">
                      已解析 {{ analysis.ocr.processed_pages }} 页 ·
                      {{
                        analysis.ocr.status === "completed"
                          ? "文档解析完成"
                          : "解析未完整，请检查提示"
                      }}
                    </p>
                    <a
                      v-if="analysis.ocr.raw_files?.length"
                      :href="'/api/mes/cnc/parts/' + part.id + '/ocr-export'"
                      >下载识别文档与关联图片</a
                    >
                  </section>
                  <OcrDocument
                    v-if="page?.ocr_markdown_file"
                    :page="page"
                    :asset-url="assetUrl"
                    :bundle-url="
                      '/api/mes/cnc/parts/' + part.id + '/ocr-export'
                    "
                    @select="focusFact"
                  />
                  <section class="editor-section">
                    <h2>制造要求识别结果</h2>
                    <p v-if="!analysis.ai" class="field-help">
                      解析完成后显示。当前可通过图纸和模型人工录入。
                    </p>
                    <template v-if="analysis.ai"
                      ><p class="field-help">
                        制造要求识别：{{
                          analysisStateLabels[analysis.ai.status] || "未完成"
                        }}
                        · 工艺生成：{{
                          analysisStateLabels[analysis.ai.planning_status] ||
                          "未完成"
                        }}
                      </p>
                      <p v-if="analysis.ai.error" class="warning-text">
                        {{ businessMessage(analysis.ai.error) }}
                      </p>
                      <p class="field-help">
                        请对照图纸确认识别内容，确认后可采纳到制造要求。
                      </p>
                      <div
                        v-for="(fact, index) in analysis.ai.facts"
                        :key="index"
                        class="fact-row"
                      >
                        <button @click="focusFact(fact)">
                          {{ fact.value }}</button
                        ><el-button
                          size="small"
                          link
                          type="primary"
                          @click="adoptFact(fact)"
                          >采纳</el-button
                        >
                        <small
                          v-if="fact.evidence_warning"
                          class="warning-text"
                          >{{ fact.evidence_warning }}</small
                        >
                      </div>
                      <p
                        v-for="warning in analysis.ai.warnings"
                        :key="warning"
                        class="warning-text"
                      >
                        {{ businessMessage(warning) }}
                      </p>
                      <h2>建议工序（待确认）</h2>
                      <el-table
                        v-if="analysis.ai.process_assessments?.length"
                        :data="analysis.ai.process_assessments"
                        size="small"
                      >
                        <el-table-column
                          prop="name"
                          label="计价规则"
                          min-width="130"
                        />
                        <el-table-column label="正式工艺档案" min-width="180"
                          ><template #default="{ row }"
                            ><span v-if="row.used && row.process_no"
                              >{{ row.process_no }} ·
                              {{ row.process_name || "已选工艺" }}</span
                            ><el-tag v-else-if="row.used" type="warning"
                              >旧结果需重新分析</el-tag
                            ><span v-else>—</span></template
                          ></el-table-column
                        >
                        <el-table-column label="使用" width="65">
                          <template #default="{ row }">{{
                            row.used ? "是" : "否"
                          }}</template>
                        </el-table-column>
                        <el-table-column label="小时/件" width="95">
                          <template #default="{ row }">{{
                            !row.used
                              ? "—"
                              : row.pricing_mode_code === "external"
                                ? "按外协规则"
                                : (row.unit_hours ?? "待补充")
                          }}</template>
                        </el-table-column>
                        <el-table-column
                          prop="reason"
                          label="选择与估时依据"
                          min-width="220"
                        />
                      </el-table>
                      <p
                        v-if="analysis.ai.operations?.length"
                        class="field-help"
                      >
                        首次结果已自动填入工艺表；重新生成会保留现有工序，可选择采用本次新建议。
                      </p>
                      <el-button
                        v-if="
                          ['completed', 'partial'].includes(
                            analysis.ai.planning_status
                          )
                        "
                        :disabled="running"
                        type="primary"
                        plain
                        @click="adoptLatestDraft"
                        >{{
                          analysis.ai.planning_status === "partial"
                            ? "采用已匹配工艺与估时"
                            : "采用本次工艺与估时并核价"
                        }}</el-button
                      >
                    </template>
                  </section>
                  <section
                    v-if="analysis.process_archive_matches?.items?.length"
                    class="editor-section"
                  >
                    <h2>正式生产工艺</h2>
                    <p
                      v-if="analysis.process_archive_matches.pending_count"
                      class="warning-text"
                    >
                      此结果未全部选择正式工艺，请重新分析并采用本次工艺后再核价。
                    </p>
                    <p v-else class="field-help">
                      已选择
                      {{ analysis.process_archive_matches.matched_count }}
                      道正式工艺。生成工单时重新核对启用档案，工时保持报价结果。
                    </p>
                    <el-table
                      :data="analysis.process_archive_matches.items"
                      border
                    >
                      <el-table-column
                        prop="operation_name"
                        label="报价工序"
                        min-width="140"
                      />
                      <el-table-column label="生产工艺" min-width="160">
                        <template #default="{ row }">
                          <span v-if="row.process_no"
                            >{{ row.process_no }} · {{ row.process_name }}</span
                          >
                          <span v-else>未选择正式工艺</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="状态" width="100">
                        <template #default="{ row }">
                          <el-tag
                            :type="
                              row.status_code === 'matched'
                                ? 'success'
                                : 'warning'
                            "
                          >
                            {{
                              row.status_code === "matched"
                                ? "已匹配"
                                : "需重新分析"
                            }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        prop="reason"
                        label="说明"
                        min-width="220"
                      />
                    </el-table>
                  </section>
                  <section v-if="geometry" class="editor-section">
                    <h2>几何特征候选</h2>
                    <p class="field-help">
                      圆柱面不等于孔，可能来自外圆、圆角或分裂曲面。点击可高亮模型面。
                    </p>
                    <div class="feature-list">
                      <button
                        v-for="feature in geometry.features"
                        :key="feature.id"
                        @click="
                          view = 'model';
                          highlightedFaces = feature.face_ids;
                        "
                      >
                        {{ feature.label }}
                      </button>
                    </div>
                  </section>
                  <section
                    v-if="page?.detail_views?.length"
                    class="editor-section"
                  >
                    <h2>局部放大依据</h2>
                    <p class="field-help">
                      分区和旋转图只供阅读，定位框仍对应原始整页。
                    </p>
                    <details
                      v-for="detail in page.detail_views"
                      :key="detail.id"
                    >
                      <summary>{{ detail.label }}</summary>
                      <img
                        :src="assetUrl(detail.image) || undefined"
                        :alt="detail.label"
                        style="max-width: 100%"
                      />
                    </details>
                  </section>
                  <section v-if="page" class="editor-section">
                    <h2>当前页提取文字</h2>
                    <pre class="extracted-text">{{
                      page.ocr_text || page.text || "没有文字结果"
                    }}</pre>
                  </section>
                </el-tab-pane>
              </el-tabs>
            </el-collapse-item>
          </el-collapse>
        </aside>
      </template>
      <main v-else class="welcome">
        <h1>从一份零件图纸开始</h1>
        <p>上传图纸，自动生成报价，再按需修改和完善。</p>
        <el-button
          v-if="hasPerms('mes:quote:manage')"
          type="primary"
          size="large"
          @click="createOpen = true"
          >上传图纸</el-button
        >
      </main>
    </div>

    <QuoteRules
      ref="rulesEditor"
      :org-id="part?.org_id"
      @saved="act(refreshRules)"
    />
    <el-dialog
      v-model="deletedOpen"
      title="已删除的询价零件"
      width="min(640px, 95vw)"
    >
      <p class="field-help">
        图纸、工艺和历史报价保留，恢复后可继续编辑并重新核价。
      </p>
      <div v-if="!deletedParts.length" class="inline-empty">暂无已删除零件</div>
      <div v-for="item in deletedParts" :key="item.id" class="deleted-part-row">
        <div>
          <strong>{{ item.name }}</strong
          ><small
            >{{ item.quantity }} 件 ·
            {{ new Date(item.deleted_at).toLocaleString("zh-CN") }}</small
          >
        </div>
        <el-button
          v-if="hasPerms('mes:quote:manage')"
          :disabled="busy"
          @click="restorePart(item)"
          >恢复</el-button
        >
      </div>
      <template #footer
        ><el-button @click="deletedOpen = false">关闭</el-button></template
      >
    </el-dialog>
    <el-dialog
      v-model="createOpen"
      title="上传图纸并生成报价"
      width="540px"
      :close-on-click-modal="false"
      ><el-form label-position="top"
        ><el-form-item label="零件名称 / 图号"
          ><el-input
            v-model="newName"
            placeholder="留空时使用文件名称" /></el-form-item
        ><el-form-item label="询价数量"
          ><el-input-number
            v-model="newQuantity"
            :min="1"
            :max="1000000"
            :precision="0" /></el-form-item
        ><el-form-item label="图纸文件"
          ><label class="upload-zone"
            ><strong>选择 PDF 和 / 或 STEP 文件</strong
            ><span
              >每个零件最多一份 PDF 和一份 STP/STEP，单文件不超过 80 MB</span
            ><input
              type="file"
              accept=".pdf,.stp,.step"
              multiple
              @change="
                event =>
                  (uploadFiles = Array.from(
                    (event.target as HTMLInputElement).files || []
                  ))
              "
          /></label>
          <div class="pending-files">
            <span v-for="file in uploadFiles" :key="file.name"
              >{{ file.name }} ·
              {{ (file.size / 1024 / 1024).toFixed(2) }} MB</span
            >
          </div></el-form-item
        ></el-form
      ><template #footer
        ><el-button @click="createOpen = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="createPart"
          >上传并生成报价</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>

<style lang="scss" src="./workbench.scss"></style>
