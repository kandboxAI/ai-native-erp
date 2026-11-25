<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, type TableInstance } from "element-plus";
import ListPagination from "@/components/ListPagination/index.vue";
import {
  request,
  normalize,
  type Quote,
  type QuoteLine,
  type ExchangeRateReference,
} from "./api";
import {
  matchesDrawing,
  pageItems,
  canSelectAdoption,
  reviewAdoptions,
  type AdoptionPreview,
  type AdoptionReview,
  type AdoptionResult,
} from "./lines";

const props = defineProps<{
  quote: Quote;
  editable: boolean;
  disabled: boolean;
  progressMessage: string;
  persist: () => Promise<Quote>;
}>();
const emit = defineEmits<{
  open: [partId: string];
  update: [quote: Quote];
  busy: [value: boolean];
}>();
const keyword = ref(""),
  filter = ref("all"),
  page = ref(1),
  size = ref(20);
const table = ref<TableInstance>(),
  selectedIds = ref<string[]>([]);
const working = ref(false),
  dialog = ref(false),
  confirmed = ref(false),
  submitted = ref(false);
const reviewRows = ref<AdoptionReview[]>([]),
  reviewPage = ref(1),
  reviewSize = ref(20);
const targetIds = ref<string[]>([]),
  exchangeRate = ref<number | null>(null),
  checkedRate = ref<number | null>(null);
const rateReference = ref<ExchangeRateReference | null>(null);
const needsRate = computed(() =>
  reviewRows.value.some(
    (row) => row.cnc_currency && row.cnc_currency !== props.quote.currency,
  ),
);
const sourceCurrency = computed(
  () =>
    reviewRows.value.find(
      (row) => row.cnc_currency && row.cnc_currency !== props.quote.currency,
    )?.cnc_currency || "CNY",
);
const rateChanged = computed(
  () => needsRate.value && (exchangeRate.value ?? null) !== checkedRate.value,
);
let disposed = false;
const allRows = computed(() =>
  props.quote.lines.filter((line) => line.cnc_records?.length),
);
const filtered = computed(() =>
  allRows.value.filter((line) => {
    const status = line.cnc_records![0].status_code;
    return (
      matchesDrawing(line, keyword.value) &&
      (filter.value === "all" ||
        (filter.value === "active" && ["queued", "running"].includes(status)) ||
        (filter.value === "completed" && status === "completed") ||
        (filter.value === "failed" && status === "failed") ||
        (filter.value === "unadopted" && !line.adopted_cnc_quote_id) ||
        (filter.value === "adopted" && !!line.adopted_cnc_quote_id))
    );
  }),
);
const visible = computed(() =>
  pageItems(filtered.value, page.value, size.value),
);
const selectable = computed(() => filtered.value.filter(canSelectAdoption));
const ready = computed(() =>
  rateChanged.value
    ? []
    : reviewRows.value.filter((row) => row.state === "ready"),
);
const successCount = computed(
  () => reviewRows.value.filter((row) => row.state === "success").length,
);
const stateLabels = {
  ready: "可采用",
  blocked: "暂不可采用",
  success: "采用成功",
  failed: "采用失败",
};
const statusLabels: Record<string, string> = {
  queued: "等待解析",
  running: "分析中",
  completed: "解析完成",
  failed: "解析失败",
  idle: "尚未解析",
};
const statusType = (status: string) =>
  (({ completed: "success", failed: "danger", running: "primary" }) as const)[
    status
  ] || "info";
const reset = () => {
  keyword.value = "";
  filter.value = "all";
  page.value = 1;
};
watch([keyword, filter, size], () => {
  page.value = 1;
});
watch(
  () => filtered.value.length,
  (count) => {
    page.value = Math.min(
      page.value,
      Math.max(1, Math.ceil(count / size.value)),
    );
  },
);
watch([() => props.quote.id, () => props.quote.currency], () => {
  selectedIds.value = [];
  reset();
  dialog.value = false;
  exchangeRate.value = checkedRate.value = null;
  rateReference.value = null;
  targetIds.value = [];
  reviewRows.value = [];
});
onBeforeUnmount(() => {
  disposed = true;
  emit("busy", false);
});

async function selectIds(ids: string[]) {
  const wanted = new Set(ids);
  table.value?.clearSelection();
  await nextTick();
  for (const line of allRows.value)
    if (line.id && wanted.has(line.id))
      table.value?.toggleRowSelection(line, true);
  selectedIds.value = [...wanted];
}
function selectAll() {
  void selectIds(selectable.value.map((line) => line.id!));
}
async function execute(action: () => Promise<void>) {
  if (working.value || props.disabled) return;
  working.value = true;
  emit("busy", true);
  try {
    await action();
  } catch (error) {
    if (!disposed) {
      actionMessage((error as Error).message || "操作失败，请重试");
    }
  } finally {
    if (!disposed) {
      working.value = false;
      emit("busy", false);
    }
  }
}
async function preview(ids = selectedIds.value, refreshRate = false) {
  if (!props.quote.id || !ids.length || working.value || props.disabled) return;
  targetIds.value = [...ids];
  const id = props.quote.id;
  const currency = props.quote.currency;
  dialog.value = true;
  confirmed.value = false;
  submitted.value = false;
  reviewRows.value = [];
  reviewPage.value = 1;
  await execute(async () => {
    const current = () =>
      !disposed && props.quote.id === id && props.quote.currency === currency;
    const load = async () => {
      const rate = exchangeRate.value ?? null;
      const data = await request<{ items: AdoptionPreview[] }>(
        `/${id}/adoption-preview`,
        "post",
        {
          version_no: props.quote.version_no,
          line_ids: ids,
          exchange_rate: rate,
        },
      );
      if (!current()) return;
      reviewRows.value = reviewAdoptions(props.quote.lines, data.items);
      checkedRate.value = rate;
    };
    await load();
    if (
      !current() ||
      !needsRate.value ||
      (!refreshRate && exchangeRate.value != null)
    )
      return;
    try {
      const reference = await request<ExchangeRateReference>(
        `/${id}/exchange-rate?quote_currency=${encodeURIComponent(sourceCurrency.value)}`,
      );
      if (!current()) return;
      const rate = Number(reference.rate);
      if (
        reference.base !== currency ||
        reference.quote !== sourceCurrency.value ||
        !Number.isFinite(rate) ||
        rate <= 0 ||
        rate > 1000000
      ) {
        throw new Error("参考汇率无效，请重试或人工填写");
      }
      rateReference.value = reference;
      exchangeRate.value = rate;
    } catch (error) {
      if (current())
        actionMessage((error as Error).message || "参考汇率获取失败，请重试或人工填写", "warning");
      return;
    }
    await load();
  });
}
async function submit() {
  if (!confirmed.value || !ready.value.length || submitted.value) return;
  const items = ready.value.map((row) => ({
    line_id: row.line_id,
    cnc_quote_id: row.cnc_quote_id,
  }));
  const id = props.quote.id;
  const rate = exchangeRate.value ?? null;
  const reference = needsRate.value ? rateReference.value?.reference : null;
  await execute(async () => {
    const saved = await props.persist();
    if (disposed || props.quote.id !== id || saved.id !== id) return;
    const result = await request<{ quotation: Quote; items: AdoptionResult[] }>(
      `/${id}/adopt-batch`,
      "post",
      {
        version_no: saved.version_no,
        lines: items,
        is_confirmed: true,
        exchange_rate: rate,
        exchange_rate_reference: reference ?? null,
      },
    );
    if (disposed || props.quote.id !== id) return;
    const results = new Map(result.items.map((item) => [item.line_id, item]));
    reviewRows.value = reviewRows.value.map((row) => {
      const item = results.get(row.line_id);
      return item
        ? {
            ...row,
            state: item.is_success ? "success" : "failed",
            message: item.message,
          }
        : row;
    });
    submitted.value = true;
    emit("update", normalize(result.quotation));
    const successes = new Set(
      result.items
        .filter((item) => item.is_success)
        .map((item) => item.line_id),
    );
    await selectIds(
      selectedIds.value.filter((identifier) => !successes.has(identifier)),
    );
    if (successes.size) {
      ElMessage.success(`已采用 ${successes.size} 项核价`);
      if (reviewRows.value.every((row) => row.state === "success"))
        dialog.value = false;
    }
  });
}
</script>

<template>
  <section
    class="cnc-adoption-panel erp-list-panel"
    aria-label="加工核价记录与人工采用"
  >
    <header class="cnc-header">
      <div>
        <h3>加工核价记录与人工采用</h3>
        <p>工程认可 AI 核价后可单项或批量采用，最终报价提交老板审核。</p>
      </div>
      <el-button
        v-if="editable"
        type="primary"
        :disabled="disabled || working || !selectedIds.length"
        @click="preview()"
        >批量确认采用（{{ selectedIds.length }}）</el-button
      >
    </header>
    <el-alert
      v-if="progressMessage"
      :title="progressMessage"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-form inline class="cnc-search" @submit.prevent="page = 1">
      <el-form-item label="图号"
        ><el-input
          v-model="keyword"
          placeholder="按图号搜索"
          clearable
          aria-label="核价记录图号"
      /></el-form-item>
      <el-form-item label="状态"
        ><el-select v-model="filter" aria-label="核价记录状态">
          <el-option label="全部状态" value="all" /><el-option
            label="排队 / 分析中"
            value="active"
          />
          <el-option label="解析完成" value="completed" /><el-option
            label="解析失败"
            value="failed"
          />
          <el-option label="尚未采用" value="unadopted" /><el-option
            label="已采用"
            value="adopted"
          /> </el-select
      ></el-form-item>
      <el-form-item
        ><el-button type="primary" native-type="submit">查询</el-button
        ><el-button @click="reset">重置</el-button></el-form-item
      >
    </el-form>
    <div v-if="editable" class="cnc-selection">
      <span
        >已选 {{ selectedIds.length }} 项<span class="cnc-muted"
          >（跨页保留）</span
        ></span
      >
      <el-button
        link
        type="primary"
        :disabled="disabled || working || !selectable.length"
        @click="selectAll"
        >选择全部匹配项（{{ selectable.length }}）</el-button
      >
      <el-button
        link
        :disabled="disabled || working || !selectedIds.length"
        @click="selectIds([])"
        >清空选择</el-button
      >
    </div>
    <el-table
      ref="table"
      :data="visible"
      row-key="id"
      border
      max-height="520"
      :empty-text="allRows.length ? '没有匹配的图号' : '暂无加工核价记录'"
      @selection-change="
        (value: QuoteLine[]) => (selectedIds = value.map((line) => line.id!))
      "
    >
      <el-table-column
        v-if="editable"
        type="selection"
        width="48"
        reserve-selection
        :selectable="
          (line: QuoteLine) => !disabled && !working && canSelectAdoption(line)
        "
      />
      <el-table-column
        prop="drawing_no"
        label="图号"
        min-width="190"
        fixed
        show-overflow-tooltip
      />
      <el-table-column label="分析进度" min-width="235"
        ><template #default="{ row }">
          <el-tag :type="statusType(row.cnc_records[0].status_code)">{{
            statusLabels[row.cnc_records[0].status_code] ||
            row.cnc_records[0].status_code
          }}</el-tag>
          <el-tooltip :content="row.cnc_records[0].stage"
            ><span class="cnc-stage">{{
              row.cnc_records[0].stage
            }}</span></el-tooltip
          >
        </template></el-table-column
      >
      <el-table-column
        prop="quoted_material"
        label="报价采用材料"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column
        :label="`对客单价（${quote.currency}）`"
        min-width="155"
        align="right"
        ><template #default="{ row }">{{
          row.unit_price == null ? "未填写" : Number(row.unit_price).toFixed(2)
        }}</template></el-table-column
      >
      <el-table-column label="采用状态" width="120"
        ><template #default="{ row }">
          <el-tag v-if="row.cnc_records[0].is_stale" type="warning"
            >来源已变化</el-tag
          >
          <el-tag v-else-if="row.adopted_cnc_quote_id" type="success"
            >已采用核价</el-tag
          ><span v-else class="cnc-muted">尚未采用</span>
        </template></el-table-column
      >
      <el-table-column label="发起时间" width="170"
        ><template #default="{ row }">{{
          new Date(row.cnc_records[0].created_at).toLocaleString()
        }}</template></el-table-column
      >
      <el-table-column label="操作" min-width="240" fixed="right"
        ><template #default="{ row }">
          <el-button
            link
            type="primary"
            :disabled="disabled || working"
            @click="emit('open', row.cnc_records[0].part_id)"
            >查看详情 / 核算</el-button
          >
          <el-button
            v-if="editable"
            link
            type="success"
            :disabled="
              disabled || working || !canSelectAdoption(row as QuoteLine)
            "
            @click="preview([row.id])"
            >{{ row.adopted_cnc_quote_id ? "重新采用" : "采用" }}</el-button
          >
          <el-popover
            v-if="row.cnc_records.length > 1"
            trigger="click"
            :width="580"
          >
            <template #reference><el-button link>历史记录</el-button></template>
            <el-table
              :data="row.cnc_records.slice(1)"
              size="small"
              max-height="280"
            >
              <el-table-column label="发起时间" width="170"
                ><template #default="{ row: record }">{{
                  new Date(record.created_at).toLocaleString()
                }}</template></el-table-column
              >
              <el-table-column prop="stage" label="处理进度" />
              <el-table-column width="90"
                ><template #default="{ row: record }"
                  ><el-button
                    link
                    type="primary"
                    @click="emit('open', record.part_id)"
                    >查看详情</el-button
                  ></template
                ></el-table-column
              >
            </el-table>
          </el-popover>
        </template></el-table-column
      >
    </el-table>
    <ListPagination
      v-model:current-page="page"
      v-model:page-size="size"
      :total="filtered.length"
      :disabled="disabled || working"
    />
    <el-dialog
      v-model="dialog"
      :title="submitted ? '采用结果' : '确认采用核价'"
      width="min(1100px, 94vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!working"
      :show-close="!working"
    >
      <el-form
        v-if="needsRate && !submitted"
        inline
        class="cnc-rate"
        @submit.prevent="preview(targetIds)"
      >
        <el-form-item
          :label="`汇率（1 ${quote.currency} 对应 ${sourceCurrency}）`"
        >
          <el-input-number
            v-model="exchangeRate"
            aria-label="采用换算汇率"
            :min="0.00000001"
            :max="1000000"
            :precision="8"
            :disabled="working"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item
          ><el-button :disabled="working" @click="preview(targetIds, true)"
            >获取参考汇率</el-button
          ></el-form-item
        >
        <el-form-item
          ><el-button
            :disabled="working || exchangeRate == null"
            @click="preview(targetIds)"
            >更新换算</el-button
          ></el-form-item
        >
      </el-form>
      <p v-if="needsRate && rateReference" class="cnc-muted">
        {{ rateReference.provider }} · {{ rateReference.rate_date }} 日参考价：
        1 {{ rateReference.base }} = {{ rateReference.rate }}
        {{ rateReference.quote }}。
        {{
          exchangeRate !== Number(rateReference.rate)
            ? "已人工调整，以确认值为准。"
            : "以本次确认值为准。"
        }}
      </p>
      <p v-if="needsRate && !submitted" class="cnc-muted">
        AI 报价按以上汇率换算后写入对客单价。{{
          rateChanged ? "汇率已变更，请更新换算。" : ""
        }}
      </p>
      <p class="cnc-review-summary">
        {{
          submitted
            ? `已采用 ${successCount} 项，未采用 ${reviewRows.length - successCount} 项`
            : `可采用 ${ready.length} 项，暂不可采用 ${reviewRows.length - ready.length} 项`
        }}。对客单价按当前 {{ quote.currency }} 币种确认。
        <span class="cnc-muted"
          >确认采用会带入对客单价及可用的单件预计净重，可在工程报价明细中调整。</span
        >
      </p>
      <el-table
        v-loading="working"
        :data="pageItems(reviewRows, reviewPage, reviewSize)"
        border
        max-height="420"
      >
        <el-table-column
          prop="drawing_no"
          label="图号"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="quoted_material"
          label="核价材料"
          min-width="130"
        />
        <el-table-column label="单件预计净重（kg）" min-width="135" align="right">
          <template #default="{ row }">{{ row.net_weight_kg ?? "—" }}</template>
        </el-table-column>
        <el-table-column label="AI 报价" min-width="145" align="right"
          ><template #default="{ row }">{{
            row.cnc_unit_price == null
              ? "—"
              : `${Number(row.cnc_unit_price).toFixed(2)} ${row.cnc_currency}`
          }}</template></el-table-column
        >
        <el-table-column
          :label="`原单价（${quote.currency}）`"
          width="145"
          align="right"
          ><template #default="{ row }">{{
            row.original_unit_price == null
              ? "未填写"
              : row.original_unit_price.toFixed(2)
          }}</template></el-table-column
        >
        <el-table-column
          :label="`采用后单价（${quote.currency}）`"
          width="170"
          align="right"
          ><template #default="{ row }">{{
            row.unit_price == null ? "未填写" : row.unit_price.toFixed(2)
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="120"
          ><template #default="{ row }"
            ><el-tag
              :type="
                row.state === 'success' || row.state === 'ready'
                  ? 'success'
                  : 'warning'
              "
              >{{ stateLabels[row.state] }}</el-tag
            ></template
          ></el-table-column
        >
        <el-table-column prop="message" label="说明" min-width="260" />
      </el-table>
      <ListPagination
        v-model:current-page="reviewPage"
        v-model:page-size="reviewSize"
        :total="reviewRows.length"
        :disabled="working"
        @size-change="reviewPage = 1"
      />
      <el-checkbox
        v-if="!submitted && reviewRows.length"
        v-model="confirmed"
        :disabled="working"
        >我已核对材料、工艺、核价依据及以上对客单价</el-checkbox
      >
      <template #footer
        ><el-button :disabled="working" @click="dialog = false">{{
          submitted ? "关闭" : "取消"
        }}</el-button
        ><el-button
          v-if="!submitted"
          type="primary"
          :loading="working"
          :disabled="!confirmed || !ready.length"
          @click="submit"
          >确认采用 {{ ready.length }} 项</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>

<style scoped>
.cnc-adoption-panel {
  padding: 20px;
  margin: 16px 0;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.cnc-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.cnc-header h3 {
  margin: 0;
  font-size: 18px;
}

.cnc-header p,
.cnc-muted {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.cnc-search {
  margin: 16px 0;
}

.cnc-search .el-input {
  width: 230px;
}

.cnc-search .el-select {
  width: 165px;
}

.cnc-selection {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 13px;
}

.cnc-stage {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.cnc-review-summary {
  margin: 8px 0 16px;
}

.cnc-rate {
  margin: 8px 0 12px;
}

@media (width <= 900px) {
  .cnc-header {
    flex-wrap: wrap;
  }
}
</style>
