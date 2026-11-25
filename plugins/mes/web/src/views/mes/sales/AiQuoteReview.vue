<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  aiCostKey,
  aiQuoteLabels,
  aiTaskStale,
  latestAiTask,
  type AiQuoteTask,
} from "./aiQuoteModel";
import type { Quote } from "./model";
import { useMesSalesStoreHook } from "./store";

const props = defineProps<{
  task: AiQuoteTask;
  quote: Quote;
  canEdit: boolean;
}>();
const emit = defineEmits<{ back: []; open: [id: string] }>();
const session = useMesSalesStoreHook();
const acknowledged = ref(false);
const review = computed(() => props.task.review);
const stale = computed(() => aiTaskStale(props.task, props.quote));
const latest = computed(
  () =>
    latestAiTask(session.state, props.quote.id, props.task.line_id)?.id ===
    props.task.id,
);
const editable = computed(
  () =>
    props.canEdit &&
    props.task.status === "review" &&
    latest.value &&
    !stale.value,
);
const dirty = computed(
  () => review.value && props.task.cost_key !== aiCostKey(review.value),
);
const line = computed(() =>
  props.quote.lines.find((row) => row.id === props.task.line_id),
);
watch(
  () => JSON.stringify(props.task.review),
  () => {
    acknowledged.value = false;
  },
  { flush: "sync" },
);
function act(action: () => void) {
  try {
    action();
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function updateCost() {
  act(() => {
    session.updateAiCost(props.task.id);
    ElMessage.success("演示核价已更新，需重新确认最终报价");
  });
}
function suggest() {
  act(() => {
    session.suggestPrice(props.task.id);
  });
}
function adopt() {
  act(() => {
    session.adoptAi(props.task.id, acknowledged.value);
    ElMessage.success("已人工确认并采用到本次报价");
    emit("back");
  });
}
function retry() {
  act(() => {
    const next = session.retryAiQuote(props.task.id);
    emit("open", next.id);
  });
}
async function reject() {
  if (!editable.value) return;
  try {
    const { value } = await ElMessageBox.prompt(
      "不采用会保留本次记录和原有报价，请填写原因。",
      "不采用本次建议",
      { inputValidator: (value) => !!value?.trim() || "请填写原因" },
    );
    session.rejectAi(props.task.id, value);
    ElMessage.success("已记录不采用原因，可继续人工报价");
    emit("back");
  } catch (cause) {
    if (cause instanceof Error) actionMessage(cause.message);
  }
}
function viewFile(id: string) {
  act(() => {
    const file = props.task.input.files.find((row) => row.id === id);
    if (!file) throw Error("文件记录不存在");
    const url = session.files.url(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
  });
}
</script>
<template>
  <section
    class="sales-editor-page sales-prototype ai-quote-review"
    aria-label="AI 核价复核详情"
  >
    <header class="prototype-heading">
      <div>
        <h2>核价详情 · {{ task.input.drawing_no }}</h2>
        <p>
          {{ task.quote_no }} · R{{ task.quote_revision }} ·
          {{ task.input.quantity }} {{ task.input.unit }}
        </p>
      </div>
      <el-tag>{{ stale ? "需重新分析" : aiQuoteLabels[task.status] }}</el-tag>
      <el-button @click="emit('back')">返回工程报价</el-button>
    </header>
    <el-alert
      type="warning"
      :closable="false"
      title="仅前端流程演示：未读取图纸内容，未调用真实 AI。工艺、工时、费率和成本采用固定示例参数，不能作为真实生产或对客报价依据。"
    />
    <el-alert
      v-if="stale || !latest"
      type="warning"
      :closable="false"
      :title="
        stale
          ? '图纸、数量或客户要求已变化，本次结果不可采用，请重新分析。'
          : '已有新一轮分析，本页作为历史记录保留，不可再次采用。'
      "
    />
    <el-descriptions :column="3" border>
      <el-descriptions-item label="客户材料">{{
        task.input.customer_material || "未填写"
      }}</el-descriptions-item>
      <el-descriptions-item label="本次数量"
        >{{ task.input.quantity }} {{ task.input.unit }}</el-descriptions-item
      >
      <el-descriptions-item label="图纸版本">{{
        task.input.drawing_revision
      }}</el-descriptions-item>
      <el-descriptions-item label="零件描述">{{
        task.input.description
      }}</el-descriptions-item>
      <el-descriptions-item label="表面处理要求" :span="2">{{
        task.input.surface_treatment || "未填写"
      }}</el-descriptions-item>
    </el-descriptions>
    <div class="prototype-file-list">
      <strong>本次采用的图纸 / 模型</strong
      ><el-button
        v-for="file in task.input.files"
        :key="file.id"
        link
        type="primary"
        @click="viewFile(file.id)"
        >{{ file.name }}{{ file.is_demo ? "（仅示例文件名）" : "" }}</el-button
      ><span v-if="!task.input.files.length"
        >缺少图纸或模型，请退回业务补充后重新分析。</span
      >
    </div>
    <template v-if="!review">
      <el-alert
        :type="
          task.status === 'needs_input' || task.status === 'failed'
            ? 'warning'
            : 'info'
        "
        :closable="false"
        :title="
          task.error ||
          (task.missing.length
            ? `待补充：${task.missing.join('、')}`
            : task.stage)
        "
      />
      <p class="prototype-muted">
        任务会在本次登录中继续推进，可返回列表处理其他货品；刷新或退出登录后清空。
      </p>
    </template>
    <template v-else>
      <div class="prototype-stats ai-cost-summary">
        <div>
          <span>单件核算成本 · CNY</span
          ><strong>{{
            dirty ? "待更新" : `¥ ${task.cost?.unit_cost_cny.toFixed(2)}`
          }}</strong>
        </div>
        <div>
          <span>整批核算成本 · {{ task.input.quantity }} 件</span
          ><strong>{{
            dirty ? "待更新" : `¥ ${task.cost?.total_cost_cny.toFixed(2)}`
          }}</strong>
        </div>
        <div>
          <span>单件预计工时</span
          ><strong
            >{{ dirty ? "待更新" : task.cost?.unit_minutes }} 分钟</strong
          >
        </div>
        <div>
          <span>最终报价 · {{ task.currency }}</span
          ><strong>{{
            review.final_unit_price == null
              ? "待确认"
              : review.final_unit_price.toFixed(2)
          }}</strong>
        </div>
      </div>
      <p class="prototype-muted">
        示例毛坯重量按净重约 1.3 倍或固定 0.1 kg 展示，材料参考价固定为 30
        元/kg；没有解析真实几何或查实际材料库。以下费用仅用于体验复核与回填。
      </p>
      <el-form label-position="top" :disabled="!editable">
        <h3>材料与费用</h3>
        <div class="ai-review-fields">
          <el-form-item label="报价采用材料" required
            ><el-input
              v-model="review.material"
              maxlength="128"
              aria-label="复核采用材料"
          /></el-form-item>
          <el-form-item label="单件毛坯重量（kg）"
            ><el-input-number
              v-model="review.stock_weight_kg"
              :min="0.001"
              :precision="3"
              controls-position="right"
          /></el-form-item>
          <el-form-item label="材料单价（人民币 / kg）"
            ><el-input-number
              v-model="review.material_price_cny"
              :min="0"
              :precision="2"
              controls-position="right"
          /></el-form-item>
          <el-form-item label="单件外协 / 表面处理费（人民币）"
            ><el-input-number
              v-model="review.external_unit_cny"
              :min="0"
              :precision="2"
              controls-position="right"
          /></el-form-item>
          <el-form-item label="整批其他费用（人民币）"
            ><el-input-number
              v-model="review.other_batch_cny"
              :min="0"
              :precision="2"
              controls-position="right"
          /></el-form-item>
        </div>
        <h3>工艺与单件工时</h3>
        <el-table
          :data="review.operations"
          row-key="id"
          border
          class="prototype-table"
        >
          <el-table-column type="index" label="顺序" width="70" />
          <el-table-column label="工序" min-width="180"
            ><template #default="{ row }"
              ><el-input
                v-model="row.name"
                maxlength="100"
                :disabled="!editable" /></template
          ></el-table-column>
          <el-table-column label="单件工时（分钟）" min-width="180"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.minutes_per_unit"
                :min="0.001"
                :precision="3"
                :disabled="!editable"
                controls-position="right"
                :aria-label="`单件工时 ${row.id}`" /></template
          ></el-table-column>
          <el-table-column label="费率（人民币 / 小时）" min-width="190"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.hourly_rate_cny"
                :min="0"
                :precision="2"
                :disabled="!editable"
                controls-position="right" /></template
          ></el-table-column>
          <el-table-column label="操作" width="90"
            ><template #default="{ $index }"
              ><el-button
                v-if="editable && review.operations.length > 1"
                link
                type="danger"
                @click="review.operations.splice($index, 1)"
                >移除</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <div class="prototype-toolbar">
          <el-button
            v-if="editable"
            @click="
              review.operations.push({
                id: `manual-${Date.now()}`,
                name: '',
                minutes_per_unit: 1,
                hourly_rate_cny: 0,
              })
            "
            >添加工序</el-button
          ><el-button v-if="editable" type="primary" plain @click="updateCost"
            >更新核价</el-button
          ><span v-if="dirty" class="prototype-muted"
            >输入已修改，核算成本待更新；不能采用旧金额。</span
          >
        </div>
        <el-descriptions v-if="task.cost && !dirty" :column="4" border
          ><el-descriptions-item label="材料 / 件"
            >¥
            {{ task.cost.material_unit_cny.toFixed(2) }}</el-descriptions-item
          ><el-descriptions-item label="加工 / 件"
            >¥
            {{ task.cost.machining_unit_cny.toFixed(2) }}</el-descriptions-item
          ><el-descriptions-item label="外协 / 件"
            >¥
            {{ task.cost.external_unit_cny.toFixed(2) }}</el-descriptions-item
          ><el-descriptions-item label="其他 / 件"
            >¥ {{ task.cost.other_unit_cny.toFixed(2) }}</el-descriptions-item
          ></el-descriptions
        >
        <h3>确认对客报价 · {{ task.currency }} · 不含税</h3>
        <p class="prototype-muted">
          核算成本不等于对客单价。可输入成本加价比例、汇率后生成建议价，也可直接人工填写最终单价；加工工时不自动换算成交期。
        </p>
        <div class="ai-review-fields">
          <el-form-item label="成本加价（%，不是毛利率）"
            ><el-input-number
              v-model="review.markup_percent"
              :min="0"
              :max="1000"
              :precision="2"
              controls-position="right"
          /></el-form-item>
          <el-form-item
            v-if="task.currency !== 'CNY'"
            :label="`汇率（1 ${task.currency} = 多少人民币）`"
            ><el-input-number
              v-model="review.fx_rate"
              :min="0.0001"
              :precision="4"
              controls-position="right"
              placeholder="人工确认，无实时汇率"
              aria-label="报价汇率"
          /></el-form-item>
          <el-form-item label="最终对客单价" required
            ><el-input-number
              v-model="review.final_unit_price"
              :min="0"
              :max="1000000"
              :precision="2"
              controls-position="right"
              aria-label="复核最终单价"
          /></el-form-item>
          <el-form-item label="交期（自然日，人工确认）" required
            ><el-input-number
              v-model="review.lead_days"
              :min="1"
              :max="3650"
              :precision="0"
              controls-position="right"
              aria-label="复核交期天数"
          /></el-form-item>
        </div>
        <el-button v-if="editable" :disabled="!!dirty" @click="suggest"
          >按当前成本生成建议价</el-button
        >
        <el-form-item label="工程复核说明（内部）"
          ><el-input
            v-model="review.note"
            type="textarea"
            :rows="2"
            maxlength="1000"
            placeholder="记录工艺、工时、用料或定价的调整依据"
        /></el-form-item>
      </el-form>
      <el-alert
        v-if="task.adoption"
        type="success"
        :closable="false"
        :title="`本次已采用：${task.adoption.final_unit_price.toFixed(2)} ${task.adoption.currency} / 件，交期 ${task.adoption.lead_days} 天。`"
      />
      <el-alert
        v-if="task.adoption && line?.ai_review?.task_id !== task.id"
        type="info"
        :closable="false"
        title="本页保留历史采用记录，当前货品的价格或采用依据已有后续调整。"
      />
      <el-alert
        v-if="task.rejection_reason"
        type="info"
        :closable="false"
        :title="`不采用原因：${task.rejection_reason}`"
      />
      <el-checkbox v-if="editable" v-model="acknowledged"
        >我已复核材料、工艺、工时、币种与最终报价，确认采用到本次报价单</el-checkbox
      >
    </template>
    <footer class="prototype-footer sales-page-footer">
      <el-button @click="emit('back')">返回工程报价</el-button>
      <el-button
        v-if="canEdit && !['queued', 'running'].includes(task.status)"
        @click="retry"
        >重新分析</el-button
      >
      <el-button v-if="editable" type="danger" plain @click="reject"
        >不采用</el-button
      >
      <el-button v-if="editable" @click="emit('back')">保存待复核</el-button>
      <el-button
        v-if="editable"
        type="primary"
        :disabled="!acknowledged || !!dirty"
        @click="adopt"
        >确认并采用</el-button
      >
    </footer>
  </section>
</template>
<style scoped>
.ai-review-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 20px;
}

.ai-review-fields .el-input-number {
  width: 100%;
}

.ai-cost-summary {
  margin-top: 20px;
}

@media (width <= 1000px) {
  .ai-review-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
