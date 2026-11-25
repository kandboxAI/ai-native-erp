<script setup lang="ts">
import { aiQuoteLabels, aiTaskStale, type AiQuoteTask } from "./aiQuoteModel";
import type { Quote } from "./model";
const props = defineProps<{
  tasks: AiQuoteTask[];
  quote: Quote;
  canEdit: boolean;
  onOpen: (id: string) => void;
  onRetry: (id: string) => void;
}>();
function attempt(task: AiQuoteTask) {
  const records = props.tasks.filter((row) => row.line_id === task.line_id);
  return records.length - records.findIndex((row) => row.id === task.id);
}
</script>
<template>
  <el-table :data="tasks" row-key="id" stripe max-height="520">
    <el-table-column label="图号 / 修订" min-width="200"
      ><template #default="{ row }"
        ><strong>{{ row.input.drawing_no }}</strong
        ><small
          >图纸 {{ row.input.drawing_revision }} · {{ row.input.quantity }}
          {{ row.input.unit }}</small
        ></template
      ></el-table-column
    >
    <el-table-column label="分析记录" width="150"
      ><template #default="{ row }"
        >第 {{ attempt(row as AiQuoteTask) }} 次分析<small>{{
          new Date(row.created_at).toLocaleTimeString()
        }}</small></template
      ></el-table-column
    >
    <el-table-column label="状态" width="130"
      ><template #default="{ row }"
        ><el-tag
          :type="
            row.status === 'adopted'
              ? 'success'
              : ['failed', 'needs_input', 'stale'].includes(row.status)
                ? 'warning'
                : 'info'
          "
          >{{
            aiTaskStale(row as AiQuoteTask, quote)
              ? "需重新分析"
              : aiQuoteLabels[row.status as AiQuoteTask["status"]]
          }}</el-tag
        ></template
      ></el-table-column
    >
    <el-table-column label="进度 / 待处理事项" min-width="250"
      ><template #default="{ row }">{{
        aiTaskStale(row as AiQuoteTask, quote)
          ? "来源图纸、数量或要求已变化"
          : row.error || row.missing.join("、") || row.stage
      }}</template></el-table-column
    >
    <el-table-column label="演示核算成本" width="160"
      ><template #default="{ row }"
        >{{ row.cost ? `¥ ${row.cost.unit_cost_cny.toFixed(2)} / 件` : "—"
        }}<small>人民币 · 不含税</small></template
      ></el-table-column
    >
    <el-table-column label="操作" width="210" fixed="right"
      ><template #default="{ row }"
        ><el-button link type="primary" @click="onOpen(row.id)">{{
          canEdit && row.status === "review" ? "复核报价" : "查看详情"
        }}</el-button
        ><el-button
          v-if="canEdit && !['queued', 'running'].includes(row.status)"
          link
          @click="onRetry(row.id)"
          >重新分析</el-button
        ></template
      ></el-table-column
    >
    <template #empty
      ><el-empty
        description="暂无 AI 核价记录，请先在货品报价中选择货品发起 AI 报价"
    /></template>
  </el-table>
</template>
