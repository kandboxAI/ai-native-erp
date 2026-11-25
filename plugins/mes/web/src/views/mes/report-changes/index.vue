<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, ref } from "vue";
import { ElMessageBox } from "element-plus";
import {
  getMesReportChanges,
  withdrawMesReportChange,
  type MesReportChange,
} from "@plugins/mes/web/src/api/mes";
import { getPendingTaskForBusiness } from "@/api/workflowTask";
import { hasPerms, getToken } from "@/utils/auth";
import { message } from "@/utils/message";
import WorkflowTaskDialog from "@/layout/components/lay-notice/components/WorkflowTaskDialog.vue";
import WorkflowApprovalProgress from "@/components/workflow/WorkflowApprovalProgress.vue";
import { formatMesDate } from "../shared";
import ReportDetail from "../components/ReportDetail.vue";
defineOptions({ name: "MesReportChanges" });
const rows = ref<MesReportChange[]>([]),
  keyword = ref(""),
  status = ref(""),
  page = ref(1),
  size = ref(10),
  total = ref(0),
  loading = ref(false),
  error = ref("");
const taskId = ref(""),
  taskVisible = ref(false),
  progressId = ref(""),
  progressVisible = ref(false),
  busy = ref(false);
const reportId = ref(""),
  reportVisible = ref(false);
const labels = {
  draft: "待提交",
  submitted: "审批中",
  approved: "已通过",
  rejected: "已驳回",
  cancelled: "已撤回",
};
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getMesReportChanges({
      keyword: keyword.value,
      status_code: status.value,
      page: page.value,
      page_size: size.value,
    });
    if (current === request) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause: any) {
    if (current === request) {
      rows.value = [];
      total.value = 0;
      error.value = cause?.message || "变更申请读取失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
async function approve(id: string) {
  if (busy.value) return;
  busy.value = true;
  try {
    const result = await getPendingTaskForBusiness("mes_report_change", id);
    if (result.data) {
      taskId.value = result.data.id;
      taskVisible.value = true;
    } else message("当前没有待你办理的审批任务", { type: "warning" });
  } catch (cause: any) {
    message(cause?.message || "审批任务读取失败", { type: "warning" });
  } finally {
    busy.value = false;
  }
}
async function withdraw(id: string) {
  if (busy.value) return;
  busy.value = true;
  try {
    await ElMessageBox.confirm(
      "撤回后原报工保持不变，工单解除审批冻结。",
      "撤回报工变更",
      { confirmButtonText: "确认撤回", cancelButtonText: "取消" },
    );
    await withdrawMesReportChange(id);
    await load();
  } catch (cause: any) {
    if (!["cancel", "close"].includes(cause))
      message(cause?.message || "撤回失败", { type: "warning" });
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="mes-page">
    <h2>报工变更 / 审批</h2>
    <p>
      从“现场报工台账”发起更正或冲销，复用底座审批任务办理。已驳回或撤回的申请需从原报工重新提交。
    </p>
    <el-card shadow="never"
      ><el-form inline @submit.prevent="search"
        ><el-form-item label="报工单号"
          ><el-input
            v-model="keyword"
            clearable
            maxlength="128"
            @keyup.enter="search" /></el-form-item
        ><el-form-item label="状态"
          ><el-select v-model="status" clearable style="width: 145px"
            ><el-option
              v-for="(label, value) in labels"
              :key="value"
              :value="value"
              :label="label" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              keyword = '';
              status = '';
              search();
            "
            >重置</el-button
          ></el-form-item
        ></el-form
      ><el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id"
        ><el-table-column
          prop="report_no"
          label="原报工单号"
          min-width="185"
        /><el-table-column label="申请类型" width="100"
          ><template #default="{ row }">{{
            row.change_type_code === "reverse" ? "冲销" : "更正"
          }}</template></el-table-column
        ><el-table-column label="申请合格 / 报废 / 返工" min-width="190"
          ><template #default="{ row }"
            >{{ row.good_quantity }} / {{ row.scrap_quantity }} /
            {{ row.rework_quantity }}</template
          ></el-table-column
        ><el-table-column
          prop="reason"
          label="申请理由"
          min-width="220"
          show-overflow-tooltip
        /><el-table-column label="状态" width="100"
          ><template #default="{ row }">{{
            labels[row.status_code] || row.status_code
          }}</template></el-table-column
        ><el-table-column label="申请时间" min-width="175"
          ><template #default="{ row }">{{
            formatMesDate(row.created_at)
          }}</template></el-table-column
        ><el-table-column label="操作" min-width="190" fixed="right"
          ><template #default="{ row }"
            ><el-button
              v-if="hasPerms('mes:production_report:list')"
              link
              type="primary"
              @click="
                reportId = row.report_id;
                reportVisible = true;
              "
              >原报工</el-button
            ><el-button
              v-if="
                row.replacement_report_id &&
                hasPerms('mes:production_report:list')
              "
              link
              type="primary"
              @click="
                reportId = row.replacement_report_id;
                reportVisible = true;
              "
              >更正报工</el-button
            ><el-button
              v-if="
                row.created_by === getToken()?.userId ||
                hasPerms('workflow_task:supervise')
              "
              link
              type="primary"
              @click="
                progressId = row.id;
                progressVisible = true;
              "
              >审批进度</el-button
            ><el-button
              v-if="
                row.status_code === 'submitted' &&
                hasPerms('mes:production_report:approve') &&
                hasPerms('workflow_task:list')
              "
              link
              type="primary"
              :disabled="busy"
              @click="approve(row.id)"
              >办理审批</el-button
            ><el-button
              v-if="
                row.status_code === 'submitted' &&
                row.created_by === getToken()?.userId &&
                hasPerms('mes:production_report:change')
              "
              link
              type="warning"
              :disabled="busy"
              @click="withdraw(row.id)"
              >撤回</el-button
            ></template
          ></el-table-column
        ></el-table
      ><ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="search"
    /></el-card>
    <ReportDetail
      v-model="reportVisible"
      :report-id="reportId"
    /><WorkflowTaskDialog
      v-model="taskVisible"
      :task-id="taskId"
      @success="load"
    />
    <el-dialog
      v-model="progressVisible"
      title="报工变更审批进度"
      width="min(800px, 95vw)"
      destroy-on-close
      append-to-body
      ><WorkflowApprovalProgress
        business-type="mes_report_change"
        :business-id="progressId"
    /></el-dialog>
  </div>
</template>
<style scoped>
.mes-page {
  padding: 20px;
}

h2 {
  margin: 0;
}

p {
  color: var(--el-text-color-secondary);
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
