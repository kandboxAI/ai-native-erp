<template>
  <div class="mes-page">
    <el-card shadow="never">
      <template #header
        ><div class="page-header">
          <div>
            <div class="page-title">现场报工台账</div>
            <div class="page-subtitle">
              汇总手机小程序、Web 和设备终端提交的生产报工事实。
            </div>
          </div>
          <el-button @click="load">刷新</el-button>
        </div></template
      >
      <el-form :inline="true" @submit.prevent
        ><el-form-item label="关键字"
          ><el-input
            v-model="filters.keyword"
            clearable
            placeholder="报工单 / 工单 / 工序"
            @keyup.enter="load" /></el-form-item
        ><el-form-item label="处理状态"
          ><el-select v-model="filters.status_code" clearable placeholder="全部"
            ><el-option label="已入账" value="posted" /><el-option
              label="待库存处理"
              value="pending_inventory" /><el-option
              label="已冲销"
              value="reversed" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="load">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        ></el-form
      >
      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        class="data-table"
      >
        <el-table-column prop="report_no" label="报工单号" min-width="180" />
        <el-table-column label="工单 / 工序" min-width="170"
          ><template #default="{ row }"
            >{{ row.work_order_no }} / {{ row.operation_no }}</template
          ></el-table-column
        >
        <el-table-column
          label="产品 / 工序名称"
          min-width="180"
          show-overflow-tooltip
          ><template #default="{ row }"
            >{{ row.product_item_name }} / {{ row.operation_name }}</template
          ></el-table-column
        >
        <el-table-column label="合格" width="80" align="right"
          ><template #default="{ row }">{{
            row.good_quantity
          }}</template></el-table-column
        >
        <el-table-column label="报废" width="80" align="right"
          ><template #default="{ row }">{{
            row.scrap_quantity
          }}</template></el-table-column
        >
        <el-table-column label="返工" width="80" align="right"
          ><template #default="{ row }">{{
            row.rework_quantity
          }}</template></el-table-column
        >
        <el-table-column label="工时 / 机时" width="115"
          ><template #default="{ row }"
            >{{ row.labor_minutes ?? "—" }} /
            {{ row.machine_minutes ?? "—" }}</template
          ></el-table-column
        >
        <el-table-column label="来源" width="100"
          ><template #default="{ row }">{{
            mesStatusLabel(row.source_code)
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><el-tag size="small" :type="mesStatusType(row.status_code)">{{
              mesStatusLabel(row.status_code)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="报工时间" width="170"
          ><template #default="{ row }">{{
            formatMesDate(row.reported_at)
          }}</template></el-table-column
        >
        <el-table-column label="操作" min-width="165" fixed="right"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="
                reportId = row.id;
                detailVisible = true;
              "
              >详情</el-button
            ><el-button
              v-if="
                hasPerms('mes:production_report:change') &&
                row.status_code === 'posted'
              "
              link
              type="primary"
              @click="
                reportId = row.id;
                changeVisible = true;
              "
              >更正 / 冲销</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        class="pagination"
        layout="total, sizes, prev, pager, next"
        :total="total"
        @current-change="load"
        @size-change="load"
      />
    </el-card>
    <ReportChangeForm
      v-model="changeVisible"
      :report-id="reportId"
      @submitted="load"
    />
    <ReportDetail v-model="detailVisible" :report-id="reportId" />
  </div>
</template>

<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, reactive, ref } from "vue";
import { getMesReports, type MesReport } from "@plugins/mes/web/src/api/mes";
import { message } from "@/utils/message";
import { hasPerms } from "@/utils/auth";
import ReportChangeForm from "../components/ReportChangeForm.vue";
import ReportDetail from "../components/ReportDetail.vue";
import {
  formatMesDate,
  mesStatusLabel,
  mesStatusType,
} from "@plugins/mes/web/src/views/mes/shared";

defineOptions({ name: "MesProductionReports" });
const loading = ref(false);
const reportId = ref(""),
  changeVisible = ref(false),
  detailVisible = ref(false);
const rows = ref<MesReport[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const filters = reactive({ keyword: "", status_code: "" });
async function load() {
  loading.value = true;
  try {
    const res = await getMesReports({
      ...filters,
      page: page.value,
      page_size: pageSize.value,
    });
    rows.value = res.data?.items || [];
    total.value = res.data?.total || 0;
  } catch (error: any) {
    message(error?.message || "报工台账加载失败", { type: "warning" });
  } finally {
    loading.value = false;
  }
}
function reset() {
  Object.assign(filters, { keyword: "", status_code: "" });
  page.value = 1;
  load();
}
onMounted(load);
</script>

<style scoped>
.mes-page {
  padding: 16px;
}

.page-header {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.page-title {
  font-size: 20px;
  font-weight: 650;
}

.page-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.data-table {
  margin-top: 12px;
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
