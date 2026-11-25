<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { TableInstance } from "element-plus";
import { useRoute } from "vue-router";
import { useMesSalesStoreHook } from "./store";
import {
  aiMissing,
  aiQuoteLabels,
  aiTaskStale,
  latestAiTask,
  type AiQuoteTask,
} from "./aiQuoteModel";
import AiQuoteTaskList from "./AiQuoteTaskList.vue";
import {
  clone,
  customers,
  newLine,
  quoteLabels,
  type DemoState,
  type Drawing,
  type Quote,
  type Role,
} from "./model";
import type { LocalDrawings } from "./files";

const visible = defineModel<boolean>({ default: false });
const props = defineProps<{
  initial?: Quote;
  state: DemoState;
  files: LocalDrawings;
  role: Role;
  readOnly?: boolean;
  canPrice?: boolean;
  onCommit: (
    quote: Quote,
    action: "save" | "submit" | "finish" | "return",
  ) => void;
}>();
const emit = defineEmits<{ price: []; aiDetail: [id: string, tab: string] }>();
const session = useMesSalesStoreHook();
const route = useRoute();
const quoteTable = ref<TableInstance>();
const selectedAiLines = ref<string[]>([]);
const aiStartVisible = ref(false);
const pricingTab = ref(route.query.ai_tab === "history" ? "history" : "items");
const draft = ref<Quote>();
const tab = ref("requirements");
const fileInput = ref<HTMLInputElement>();
const fileTarget = ref<string>();
const pasteVisible = ref(false),
  pasteText = ref("");
const editorMode = computed(() =>
  props.readOnly
    ? "view"
    : props.role === "engineering"
      ? "pricing"
      : "requirements",
);
const shownTab = computed(() =>
  editorMode.value === "view" ? tab.value : editorMode.value,
);
const hasQuoteResult = computed(
  () => draft.value && ["pricing", "quoted"].includes(draft.value.status),
);
const salesEdit = computed(
  () =>
    !props.readOnly &&
    props.role === "sales" &&
    draft.value?.status === "draft",
);
const engineerEdit = computed(
  () =>
    !props.readOnly &&
    props.role === "engineering" &&
    ["pending", "pricing"].includes(draft.value?.status),
);
const canViewAi = computed(
  () => !!props.canPrice && shownTab.value === "pricing",
);
const aiTasks = computed(() =>
  props.state.ai_quote_tasks.filter(
    (task) => task.quote_id === draft.value?.id,
  ),
);
const latestTasks = computed(
  () =>
    (draft.value?.lines
      .map((line) => latestAiTask(props.state, draft.value.id, line.id))
      .filter(Boolean) as AiQuoteTask[]) || [],
);
const aiSummary = computed(() => ({
  running: latestTasks.value.filter((task) =>
    ["queued", "running"].includes(task.status),
  ).length,
  review: latestTasks.value.filter((task) => task.status === "review").length,
  adopted: latestTasks.value.filter((task) => task.status === "adopted").length,
  attention: latestTasks.value.filter(
    (task) =>
      ["needs_input", "failed", "stale"].includes(task.status) ||
      aiTaskStale(task, draft.value),
  ).length,
}));
const aiChoices = computed(
  () =>
    draft.value?.lines.filter((line) =>
      selectedAiLines.value.includes(line.id),
    ) || [],
);
function rowTask(lineId: string) {
  return draft.value
    ? latestAiTask(props.state, draft.value.id, lineId)
    : undefined;
}
function selectableAi(line: Quote["lines"][number]) {
  const task = rowTask(line.id);
  return (
    !task ||
    (!["queued", "running"].includes(task.status) &&
      (aiTaskStale(task, draft.value) ||
        !["adopted", "review"].includes(task.status)))
  );
}
function selectAllAi() {
  if (!engineerEdit.value || !draft.value) return;
  quoteTable.value?.clearSelection();
  draft.value.lines
    .filter(selectableAi)
    .forEach((line) => quoteTable.value?.toggleRowSelection(line, true));
}
function startAi() {
  if (!engineerEdit.value || !draft.value) return;
  try {
    const tasks = session.startAiQuotes(draft.value, selectedAiLines.value);
    draft.value = clone(
      props.state.quotes.find((row) => row.id === draft.value.id)!,
    );
    aiStartVisible.value = false;
    selectedAiLines.value = [];
    pricingTab.value = "history";
    ElMessage.success(`已提交 ${tasks.length} 项前端演示任务，不调用真实 AI`);
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function openAi(id: string) {
  try {
    if (engineerEdit.value && draft.value)
      session.saveEngineeringDraft(draft.value);
    emit("aiDetail", id, pricingTab.value);
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function retryAi(id: string) {
  if (!engineerEdit.value || !draft.value) return;
  try {
    const task = props.state.ai_quote_tasks.find((row) => row.id === id);
    if (!task) throw Error("分析记录不存在");
    session.startAiQuotes(draft.value, [task.line_id], true);
    draft.value = clone(
      props.state.quotes.find((row) => row.id === draft.value.id)!,
    );
    pricingTab.value = "history";
    ElMessage.success("新一轮演示分析已提交，原价格和历史结果保留");
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
watch(
  () => [visible.value, props.initial?.id, props.role, props.readOnly],
  () => {
    if (visible.value && props.initial) {
      draft.value = clone(props.initial);
      tab.value = hasQuoteResult.value ? "pricing" : "requirements";
    }
  },
  { immediate: true },
);
function pickFiles(lineId?: string) {
  fileTarget.value = lineId;
  fileInput.value?.click();
}
function addFiles(event: Event) {
  const input = event.target as HTMLInputElement,
    chosen = [...(input.files || [])];
  input.value = "";
  if (!draft.value || !salesEdit.value) return;
  try {
    draft.value.lines = props.files.attach(
      props.state,
      draft.value.lines,
      chosen,
      fileTarget.value,
    );
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function dropFiles(event: DragEvent) {
  if (!salesEdit.value || !draft.value || !event.dataTransfer) return;
  try {
    draft.value.lines = props.files.attach(props.state, draft.value.lines, [
      ...event.dataTransfer.files,
    ]);
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function viewFile(file: Drawing) {
  try {
    const url = props.files.url(file);
    if (file.kind === "pdf") window.open(url, "_blank", "noopener,noreferrer");
    else {
      const link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      link.click();
    }
  } catch (cause) {
    ElMessage.info((cause as Error).message);
  }
}
function commit(action: "save" | "submit" | "finish" | "return") {
  if (!draft.value || !visible.value) return;
  try {
    props.onCommit(draft.value, action);
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function pasteRows() {
  if (!draft.value || !salesEdit.value) return;
  try {
    const rows = pasteText.value
      .split(/\r?\n/)
      .filter((value) => value.trim())
      .map((value) => value.split("\t"))
      .filter((row) => row[0]?.trim() !== "图号");
    if (!rows.length || rows.length > 100)
      throw Error("请粘贴 1 至 100 行货品数据");
    const lines = rows.map((row, index) => {
      const quantity = Number(row[2]);
      if (
        !row[0]?.trim() ||
        !row[1]?.trim() ||
        !Number.isFinite(quantity) ||
        quantity <= 0
      )
        throw Error(`第 ${index + 1} 行请填写图号、描述和有效数量`);
      return {
        ...newLine(props.state),
        drawing_no: row[0].trim(),
        description: row[1].trim(),
        quantity,
        customer_material: row[3]?.trim() || "",
        surface_treatment: row[4]?.trim() || "",
      };
    });
    draft.value.lines.push(...lines);
    pasteVisible.value = false;
    pasteText.value = "";
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
</script>

<template>
  <section v-if="visible" class="sales-editor-page" aria-label="询价报价表单">
    <header class="prototype-heading">
      <div>
        <h2>
          {{
            editorMode === "requirements"
              ? "货品需求"
              : editorMode === "pricing"
                ? "工程报价"
                : "询价报价详情"
          }}
        </h2>
        <p v-if="draft">
          {{ draft.quote_no }} · R{{ draft.revision }} ·
          {{ quoteLabels[draft.status] }}
        </p>
      </div>
      <el-button @click="visible = false">返回询价报价</el-button>
    </header>
    <div v-if="draft" class="sales-prototype quote-editor">
      <el-steps
        :active="
          draft.status === 'draft' ? 0 : draft.status === 'quoted' ? 3 : 1
        "
        finish-status="success"
        simple
      >
        <el-step title="业务录入需求" /><el-step title="工程报价" /><el-step
          title="报价完成"
        />
      </el-steps>
      <el-alert
        v-if="salesEdit && draft.revision > 1"
        type="warning"
        :closable="false"
        title="正在新建报价修订：旧版及已成交订单保持不变，本版完成工程报价后才用于后续接单。"
      />
      <el-alert
        v-if="salesEdit"
        type="info"
        :closable="false"
        title="第一步：添加货品、图纸及客户要求，完成后提交工程报价。此步骤不填写本次价格。"
      />
      <el-alert
        v-else-if="engineerEdit"
        type="info"
        :closable="false"
        title="第二步：货品与客户要求作为只读依据；请填写本次单价、交期及报价材料。"
      />
      <el-alert
        v-if="draft.return_reason"
        type="warning"
        :closable="false"
        :title="`待补充：${draft.return_reason}`"
      />
      <el-alert
        v-if="!salesEdit && !engineerEdit"
        type="info"
        :closable="false"
        title="当前为查看模式。业务人员录入需求，工程人员填写报价；已完成报价需新建修订后修改。"
      />
      <el-form label-position="top" :disabled="!salesEdit">
        <el-row :gutter="16">
          <el-col :span="8"
            ><el-form-item label="询价名称" required
              ><el-input v-model="draft.title" maxlength="128" /></el-form-item
          ></el-col>
          <el-col :span="8"
            ><el-form-item label="客户" required
              ><el-select
                v-model="draft.customer_id"
                @change="
                  draft.currency =
                    customers.find((row) => row.id === draft.customer_id)
                      ?.currency || 'EUR'
                "
                ><el-option
                  v-for="customer in customers"
                  :key="customer.id"
                  :label="customer.name"
                  :value="customer.id" /></el-select></el-form-item
          ></el-col>
          <el-col :span="4"
            ><el-form-item label="币种"
              ><el-select v-model="draft.currency"
                ><el-option
                  v-for="currency in ['EUR', 'CNY', 'USD']"
                  :key="currency"
                  :label="currency"
                  :value="currency" /></el-select></el-form-item
          ></el-col>
          <el-col :span="4"
            ><el-form-item label="报价截止日期"
              ><el-date-picker
                v-model="draft.deadline"
                type="date"
                value-format="YYYY-MM-DD" /></el-form-item
          ></el-col>
          <el-col :span="6"
            ><el-form-item label="业务负责人"
              ><el-input v-model="draft.owner" maxlength="64" /></el-form-item
          ></el-col>
          <el-col :span="6"
            ><el-form-item label="报价工程师"
              ><el-input
                v-model="draft.engineer"
                maxlength="64" /></el-form-item
          ></el-col>
          <el-col :span="12"
            ><el-form-item label="询价说明"
              ><el-input v-model="draft.note" maxlength="1000" /></el-form-item
          ></el-col>
        </el-row>
      </el-form>
      <div
        v-if="salesEdit"
        class="prototype-upload"
        @dragover.prevent
        @drop.prevent="dropFiles"
      >
        <strong>一次选择全部 PDF 和 STP / STEP 文件，按同名图号自动配对</strong>
        <span
          >也可拖入文件；每行最多一份
          PDF、一份模型，同类文件再次选择会替换当前文件。未匹配的文件新建货品行。</span
        >
        <el-button type="primary" plain @click="pickFiles()"
          >批量选择图纸与模型</el-button
        >
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.stp,.step"
          multiple
          hidden
          @change="addFiles"
        />
      </div>
      <div class="prototype-toolbar">
        <el-radio-group
          v-if="editorMode === 'view' && hasQuoteResult"
          v-model="tab"
          ><el-radio-button value="requirements">客户需求</el-radio-button
          ><el-radio-button value="pricing"
            >报价结果（只读）</el-radio-button
          ></el-radio-group
        >
        <strong v-else>{{
          editorMode === "pricing" ? "工程报价明细" : "货品与客户要求"
        }}</strong>
        <span class="prototype-muted">共 {{ draft.lines.length }} 种货品</span>
        <template v-if="salesEdit"
          ><el-button @click="draft.lines.push(newLine(state))"
            >＋ 添加货品</el-button
          ><el-button @click="pasteVisible = true"
            >从 Excel 粘贴</el-button
          ></template
        >
      </div>
      <template v-if="canViewAi">
        <el-alert
          type="warning"
          :closable="false"
          title="AI 报价仅为前端流程演示：沿用已上传的文件记录，不读取图纸、不调用真实 AI；工艺、工时及费用是示例数据，必须人工复核后才能采用。刷新或退出登录后清空。"
        />
        <div class="prototype-toolbar">
          <el-radio-group v-model="pricingTab"
            ><el-radio-button value="items">货品报价</el-radio-button
            ><el-radio-button value="history"
              >AI 核价记录（{{ aiTasks.length }}）</el-radio-button
            ></el-radio-group
          >
          <template v-if="engineerEdit && pricingTab === 'items'"
            ><el-button @click="selectAllAi">全选可分析货品</el-button
            ><el-button
              type="primary"
              :disabled="!selectedAiLines.length"
              @click="aiStartVisible = true"
              >AI 报价（{{ selectedAiLines.length }}）</el-button
            ></template
          >
          <span class="prototype-muted"
            >处理中 {{ aiSummary.running }} · 待复核 {{ aiSummary.review }} ·
            已采用 {{ aiSummary.adopted }} · 待处理
            {{ aiSummary.attention }}</span
          >
        </div>
        <AiQuoteTaskList
          v-if="pricingTab === 'history'"
          :tasks="aiTasks"
          :quote="draft"
          :can-edit="engineerEdit"
          :on-open="openAi"
          :on-retry="retryAi"
        />
      </template>
      <el-table
        v-if="!canViewAi || pricingTab === 'items'"
        ref="quoteTable"
        :key="editorMode"
        :data="draft.lines"
        row-key="id"
        border
        max-height="480"
        class="prototype-table"
        @selection-change="
          (rows) => (selectedAiLines = rows.map((row) => row.id))
        "
      >
        <el-table-column
          v-if="engineerEdit"
          type="selection"
          width="46"
          :selectable="selectableAi"
          fixed
        />
        <el-table-column type="index" label="#" width="48" />
        <el-table-column label="图号 / 版本" width="210" fixed
          ><template #default="{ row }"
            ><el-input
              v-model="row.drawing_no"
              :disabled="!salesEdit"
              maxlength="64"
              placeholder="客户图号" /><el-input
              v-model="row.drawing_revision"
              :disabled="!salesEdit"
              maxlength="32"
              placeholder="图纸版本" /></template
        ></el-table-column>
        <template v-if="shownTab === 'pricing'">
          <el-table-column label="客户要求材料" width="175"
            ><template #default="{ row }"
              ><el-input
                v-model="row.customer_material"
                aria-label="客户要求材料"
                disabled
                maxlength="128" /></template
          ></el-table-column>
          <el-table-column label="报价采用材料" width="175"
            ><template #default="{ row }"
              ><el-input
                v-model="row.quoted_material"
                :disabled="!engineerEdit"
                maxlength="128"
                placeholder="工程确认材料" /></template
          ></el-table-column>
          <el-table-column :label="`本次单价（${draft.currency}）`" width="160"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.unit_price"
                aria-label="本次报价单价"
                :disabled="!engineerEdit"
                :min="0"
                :max="1000000"
                :precision="2"
                controls-position="right"
              /><small>{{
                row.ai_review
                  ? "来源：AI 建议经人工复核采用"
                  : "人工填写，AI 不自动回填"
              }}</small></template
            ></el-table-column
          >
          <el-table-column label="交期（自然日）" width="145"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.lead_days"
                aria-label="报价交期天数"
                :disabled="!engineerEdit"
                :min="1"
                :max="3650"
                :precision="0"
                controls-position="right" /></template
          ></el-table-column>
          <el-table-column
            v-if="canViewAi"
            label="AI 核价"
            width="190"
            fixed="right"
            ><template #default="{ row }">
              <template v-if="rowTask(row.id)"
                ><el-tag>{{
                  aiTaskStale(rowTask(row.id), draft)
                    ? "需重新分析"
                    : aiQuoteLabels[rowTask(row.id).status]
                }}</el-tag
                ><small v-if="rowTask(row.id).cost"
                  >演示成本 ¥
                  {{ rowTask(row.id).cost.unit_cost_cny.toFixed(2) }} /
                  件</small
                ><el-button
                  link
                  type="primary"
                  @click="openAi(rowTask(row.id).id)"
                  >查看核价详情</el-button
                ></template
              >
              <span v-else class="prototype-muted">未分析，可人工报价</span>
            </template></el-table-column
          >
        </template>
        <el-table-column label="图纸 / 模型" width="230"
          ><template #default="{ row }"
            ><el-button
              v-for="file in row.files"
              :key="file.id"
              link
              type="primary"
              @click="viewFile(file)"
              >{{ file.name }}{{ file.is_demo ? "（示例）" : "" }}</el-button
            ><span v-if="!row.files.length" class="prototype-muted">未添加</span
            ><el-button v-if="salesEdit" link @click="pickFiles(row.id)"
              >上传 / 替换</el-button
            ></template
          ></el-table-column
        >
        <el-table-column label="零件描述" width="220"
          ><template #default="{ row }"
            ><el-input
              v-model="row.description"
              :disabled="!salesEdit"
              maxlength="128"
              type="textarea"
              :rows="2" /></template
        ></el-table-column>
        <el-table-column label="询价数量 / 单位" width="155"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.quantity"
              :disabled="!salesEdit"
              :min="0.001"
              :max="1000000"
              :precision="3"
              controls-position="right" /><el-input
              v-model="row.unit"
              :disabled="!salesEdit"
              maxlength="16" /></template
        ></el-table-column>
        <el-table-column
          v-if="shownTab !== 'pricing'"
          label="客户要求材料"
          width="175"
          ><template #default="{ row }"
            ><el-input
              v-model="row.customer_material"
              :disabled="!salesEdit"
              maxlength="128" /></template
        ></el-table-column>
        <el-table-column label="净重量（kg）" width="145"
          ><template #default="{ row }"
            ><el-input-number
              v-if="salesEdit"
              v-model="row.weight_kg"
              aria-label="货品净重量（kg）"
              :min="0"
              :precision="3"
              controls-position="right"
            /><span v-else>{{ row.weight_kg ?? "未填写" }}</span></template
          ></el-table-column
        >
        <template v-if="shownTab === 'requirements'">
          <el-table-column label="表面处理要求" width="230"
            ><template #default="{ row }"
              ><el-input
                v-model="row.surface_treatment"
                :disabled="!salesEdit"
                maxlength="500"
                type="textarea"
                :rows="2" /></template
          ></el-table-column>
          <el-table-column label="上次订单数量" width="145"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.last_quantity"
                :disabled="!salesEdit"
                :min="0"
                :precision="3"
                controls-position="right" /></template
          ></el-table-column>
          <el-table-column :label="`上次单价（${draft.currency}）`" width="155"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.last_price"
                :disabled="!salesEdit"
                :min="0"
                :precision="2"
                controls-position="right" /></template
          ></el-table-column>
          <el-table-column label="客户备注" width="230"
            ><template #default="{ row }"
              ><el-input
                v-model="row.note"
                :disabled="!salesEdit"
                type="textarea"
                :rows="2"
                maxlength="1000" /></template
          ></el-table-column>
        </template>
        <template v-else>
          <el-table-column label="工程内部说明（不导出）" width="240"
            ><template #default="{ row }"
              ><el-input
                v-model="row.engineering_note"
                :disabled="!engineerEdit"
                type="textarea"
                :rows="2"
                maxlength="1000" /></template
          ></el-table-column>
        </template>
        <el-table-column v-if="salesEdit" label="操作" width="70" fixed="right"
          ><template #default="{ $index }"
            ><el-button
              link
              type="danger"
              @click="draft.lines.splice($index, 1)"
              >移除</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <p class="prototype-muted">
        本轮使用工程填写的单价作为对客报价，按未税价演示；上次数量、单价仅作参考。报价完成后，接单时仍可调整实际购买数量、成交价格及交期。
      </p>
      <el-form-item v-if="engineerEdit" label="需要业务补充的资料"
        ><el-input
          v-model="draft.return_reason"
          maxlength="1000"
          placeholder="退回时填写具体缺项"
      /></el-form-item>
    </div>
    <footer class="prototype-footer sales-page-footer">
      <el-button @click="visible = false">关闭</el-button
      ><el-button
        v-if="
          editorMode === 'view' &&
          canPrice &&
          ['pending', 'pricing'].includes(draft?.status)
        "
        type="primary"
        @click="emit('price')"
        >进入工程报价</el-button
      ><template v-if="salesEdit"
        ><el-button @click="commit('save')">保存录入</el-button
        ><el-button type="primary" @click="commit('submit')"
          >提交工程报价</el-button
        ></template
      ><template v-if="engineerEdit"
        ><el-button @click="commit('return')">退回补充</el-button
        ><el-button @click="commit('save')">保存报价进度</el-button
        ><el-button type="primary" @click="commit('finish')"
          >完成报价</el-button
        ></template
      >
    </footer>
  </section>
  <el-dialog
    v-model="aiStartVisible"
    title="批量 AI 报价"
    width="1000px"
    append-to-body
    :close-on-click-modal="false"
  >
    <el-alert
      type="info"
      :closable="false"
      title="复用业务录入的图纸和模型，不重复上传。提交时保存当前工程输入；模拟每项货品独立处理，最多两项同时推进，缺资料的货品单独标记待补充。"
    />
    <el-table :data="aiChoices" row-key="id" border
      ><el-table-column
        label="图号"
        prop="drawing_no"
        min-width="180"
      /><el-table-column
        label="数量"
        prop="quantity"
        width="100"
      /><el-table-column
        label="客户材料"
        prop="customer_material"
        min-width="150"
      /><el-table-column label="报价采用材料" min-width="150"
        ><template #default="{ row }">{{
          row.quoted_material || "待确认"
        }}</template></el-table-column
      ><el-table-column label="图纸 / 资料" min-width="240"
        ><template #default="{ row }"
          >{{ row.files.map((file) => file.name).join("、") || "未上传"
          }}<small>{{
            aiMissing(row as Quote["lines"][number]).length
              ? `待补充：${aiMissing(row as Quote["lines"][number]).join("、")}`
              : "可开始演示分析"
          }}</small></template
        ></el-table-column
      ></el-table
    >
    <template #footer
      ><el-button @click="aiStartVisible = false">取消</el-button
      ><el-button
        type="primary"
        :disabled="!engineerEdit || !aiChoices.length"
        @click="startAi"
        >开始演示分析</el-button
      ></template
    >
  </el-dialog>
  <el-dialog
    v-model="pasteVisible"
    title="从 Excel 粘贴货品"
    width="760px"
    append-to-body
    ><p>
      列顺序：图号、零件描述、数量、客户材料、表面处理要求。复制 Excel
      单元格后粘贴，图纸可随后按图号批量匹配。
    </p>
    <el-input
      v-model="pasteText"
      type="textarea"
      :rows="10"
      placeholder="图号&#9;零件描述&#9;数量&#9;客户材料&#9;表面处理要求"
    /><template #footer
      ><el-button @click="pasteVisible = false">取消</el-button
      ><el-button type="primary" @click="pasteRows"
        >加入货品明细</el-button
      ></template
    ></el-dialog
  >
</template>
