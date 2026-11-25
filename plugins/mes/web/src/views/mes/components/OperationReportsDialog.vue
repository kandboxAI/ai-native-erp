<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { ref, watch } from "vue";
import {
  getMesReports,
  type MesReport,
  type MesOperationProgress,
} from "@plugins/mes/web/src/api/mes";
import { getHttpErrorMessage } from "@/utils/http";
import {
  formatMesDate,
  mesReportedQuantity,
  mesStatusLabel,
  mesStatusType,
} from "../shared";
import OperationTimeSummary from "./OperationTimeSummary.vue";
const props = defineProps<{
  context?: {
    work_order_id: string;
    work_order_no: string;
    operation: MesOperationProgress;
  };
}>();
const visible = defineModel<boolean>({ default: false });
const rows = ref<MesReport[]>([]),
  page = ref(1),
  size = ref(20),
  total = ref(0),
  loading = ref(false),
  error = ref("");
let request = 0;
async function load() {
  const source = props.context,
    current = ++request;
  rows.value = [];
  total.value = 0;
  error.value = "";
  if (!visible.value || !source) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const response = await getMesReports({
      operation_id: source.operation.id,
      work_order_id: source.work_order_id,
      page: page.value,
      page_size: size.value,
    });
    if (current === request) {
      rows.value = response.data.items;
      total.value = response.data.total;
    }
  } catch (cause) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "工序报工记录加载失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
watch([visible, () => props.context], () => {
  page.value = 1;
  load();
});
</script>
<template>
  <el-dialog
    v-model="visible"
    title="工序报工记录"
    width="min(1120px, 96vw)"
    append-to-body
  >
    <template v-if="context">
      <div class="report-heading">
        <span>{{ context.work_order_no }}</span
        ><el-button :loading="loading" @click="load">刷新记录</el-button>
      </div>
      <OperationTimeSummary :operation="context.operation" />
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
      <p class="report-note">已冲销记录保留历史，不计入当前工序累计数量。</p>
      <el-table
        v-loading="loading"
        :data="rows"
        empty-text="当前工序暂无可查看的报工记录"
        max-height="420"
      >
        <el-table-column
          type="index"
          label="#"
          width="55"
          :index="(index) => (page - 1) * size + index + 1"
        />
        <el-table-column label="报工人" min-width="100"
          ><template #default="{ row }">{{
            row.reporter_name || "—"
          }}</template></el-table-column
        >
        <el-table-column label="报工时间" min-width="165"
          ><template #default="{ row }">{{
            formatMesDate(row.reported_at)
          }}</template></el-table-column
        >
        <el-table-column label="报工数" width="95"
          ><template #default="{ row }">{{
            mesReportedQuantity(row)
          }}</template></el-table-column
        >
        <el-table-column
          prop="good_quantity"
          label="合格"
          width="80"
        /><el-table-column
          prop="scrap_quantity"
          label="报废"
          width="80"
        /><el-table-column prop="rework_quantity" label="返工" width="80" />
        <el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="mesStatusType(row.status_code)">{{
              mesStatusLabel(row.status_code)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="异常 / 说明" min-width="185"
          ><template #default="{ row }">{{
            row.note || "—"
          }}</template></el-table-column
        >
      </el-table>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        class="report-pagination"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="
          page = 1;
          load();
        "
      />
    </template>
  </el-dialog>
</template>
<style scoped>
.report-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  color: var(--el-text-color-secondary);
}

.report-note {
  margin: 20px 0 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.report-pagination {
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
