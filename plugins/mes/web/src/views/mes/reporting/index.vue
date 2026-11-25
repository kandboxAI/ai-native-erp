<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, reactive, ref } from "vue";
import {
  getMesReportingTasks,
  type MesTask,
} from "@plugins/mes/web/src/api/mes";
import ReportExecution from "../components/ReportExecution.vue";
import { mesStatusType } from "../shared";
defineOptions({ name: "MesManualReporting" });
const filters = reactive({ keyword: "", status_code: "" });
const rows = ref<MesTask[]>([]),
  page = ref(1),
  size = ref(10),
  total = ref(0),
  loading = ref(false),
  error = ref("");
const visible = ref(false),
  taskId = ref("");
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getMesReportingTasks({
      ...filters,
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
      error.value = cause?.message || "可报工任务读取失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function open(id: string) {
  taskId.value = id;
  visible.value = true;
}
onMounted(load);
</script>
<template>
  <div class="mes-page">
    <h2>手动报工</h2>
    <p>
      应用排程方案后，系统按方案安排报工任务。也可选择手动派给本人或开放的任务。具备生产执行管理权限的人员可为无可用账号的人员代录。
    </p>
    <el-card shadow="never"
      ><el-form inline @submit.prevent="search"
        ><el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            clearable
            maxlength="128"
            placeholder="工单 / 产品 / 工序"
            @keyup.enter="search" /></el-form-item
        ><el-form-item label="状态"
          ><el-select
            v-model="filters.status_code"
            clearable
            style="width: 145px"
            ><el-option label="待执行" value="pending" /><el-option
              label="已派工"
              value="dispatched" /><el-option
              label="执行中"
              value="in_progress" /><el-option
              label="已暂停"
              value="paused" /><el-option
              label="待检验"
              value="waiting_quality" /><el-option
              label="已完成"
              value="completed" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              Object.assign(filters, { keyword: '', status_code: '' });
              search();
            "
            >重置</el-button
          ></el-form-item
        ></el-form
      ><el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id"
        ><el-table-column
          prop="work_order_no"
          label="工单号"
          min-width="185"
        /><el-table-column
          prop="product_item_name"
          label="产品"
          min-width="165"
        /><el-table-column label="工序" min-width="165"
          ><template #default="{ row }"
            >{{ row.operation_no }} · {{ row.operation_name }}</template
          ></el-table-column
        ><el-table-column label="计划 / 合格 / 报废 / 返工" min-width="230"
          ><template #default="{ row }"
            >{{ row.planned_quantity }} / {{ row.good_quantity }} /
            {{ row.scrap_quantity }} / {{ row.rework_quantity }}
            {{ row.unit_name }}</template
          ></el-table-column
        ><el-table-column label="状态" width="120"
          ><template #default="{ row }"
            ><el-tag :type="mesStatusType(row.status_code)">{{
              row.status_label
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="操作" width="130" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="open(row.id)"
              >查看 / 报工</el-button
            ></template
          ></el-table-column
        ></el-table
      ><ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="search" /></el-card
    ><ReportExecution v-model="visible" :task-id="taskId" @changed="load" />
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
