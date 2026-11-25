<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, reactive, ref } from "vue";
import {
  getMesTask,
  getMesTasks,
  dispatchMesTask,
  getMesDispatchPeople,
  type MesTask,
  type MesTaskDetail,
} from "@plugins/mes/web/src/api/mes";
import { message, actionMessage } from "@/utils/message";
import { hasPerms } from "@/utils/auth";
import {
  formatMesDate,
  mesStatusType,
  mesStatusLabel,
  mesPercent,
  mesReportedQuantity,
  mesDispatchPersonLabel,
} from "../shared";
import TaskDetail from "../components/TaskDetail.vue";
import RemoteSelect from "../components/RemoteSelect.vue";

defineOptions({ name: "MesExecution" });
const loading = ref(false);
const saving = ref(false);
const preparing = ref(false);
const rows = ref<MesTask[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const error = ref("");
const detailVisible = ref(false);
const taskId = ref("");
const dispatchVisible = ref(false);
const dispatchTarget = ref<MesTaskDetail>();
const dispatchError = ref("");
const filters = reactive({ keyword: "", status_code: "" });
const dispatchForm = reactive({ production_person_id: "", note: "" });
const statuses = [
  "draft",
  "pending",
  "dispatched",
  "in_progress",
  "paused",
  "waiting_quality",
  "completed",
  "cancelled",
];
let request = 0;
let dispatchRequest = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const res = await getMesTasks({
      ...filters,
      page: page.value,
      page_size: pageSize.value,
    });
    if (current === request) {
      rows.value = res.data.items;
      total.value = res.data.total;
    }
  } catch (cause: any) {
    if (current === request) {
      rows.value = [];
      total.value = 0;
      error.value = cause?.message || "任务加载失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function reset() {
  Object.assign(filters, { keyword: "", status_code: "" });
  search();
}
function inspect(id: string) {
  taskId.value = id;
  detailVisible.value = true;
}
async function openDispatch(row: { id?: string }) {
  if (!row.id) return;
  const current = ++dispatchRequest;
  taskId.value = row.id;
  dispatchTarget.value = undefined;
  dispatchError.value = "";
  Object.assign(dispatchForm, { production_person_id: "", note: "" });
  dispatchVisible.value = true;
  preparing.value = true;
  try {
    const res = await getMesTask(row.id);
    if (current === dispatchRequest && dispatchVisible.value)
      dispatchTarget.value = res.data;
  } catch (cause: any) {
    if (current === dispatchRequest)
      dispatchError.value = cause?.message || "任务版本读取失败，请关闭后重试";
  } finally {
    if (current === dispatchRequest) preparing.value = false;
  }
}
async function submitDispatch() {
  if (saving.value || !dispatchTarget.value || !dispatchForm.production_person_id)
    return;
  saving.value = true;
  try {
    await dispatchMesTask(dispatchTarget.value.id, {
      version_no: dispatchTarget.value.version_no,
      production_person_id: dispatchForm.production_person_id,
      note: dispatchForm.note.trim() || undefined,
    });
    message("生产任务已派工", { type: "success" });
    dispatchVisible.value = false;
    await load();
  } catch (cause: any) {
    actionMessage(cause?.message || "派工失败，请关闭窗口刷新后重试");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div class="mes-page">
    <div class="page-heading">
      <h2>执行控制与派工</h2>
      <p>查看执行进度。已应用排程方案的工序按方案执行；未排程的工序下单后可手动派工。</p>
    </div>
    <el-card shadow="never">
      <el-form inline @submit.prevent="search"
        ><el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            clearable
            maxlength="128"
            placeholder="工单号 / 工序 / 产品"
            @keyup.enter="search" /></el-form-item
        ><el-form-item label="状态"
          ><el-select
            v-model="filters.status_code"
            clearable
            placeholder="全部"
            style="width: 150px"
            ><el-option
              v-for="status in statuses"
              :key="status"
              :value="status"
              :label="status === 'draft' ? '待下单' : mesStatusLabel(status)" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        ></el-form
      >
      <el-alert v-if="error" :title="error" type="error" :closable="false"
        ><el-button link type="primary" @click="load"
          >重新加载</el-button
        ></el-alert
      >
      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        empty-text="暂无符合条件的工序任务"
      >
        <el-table-column label="工单 / 工序" min-width="200"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="inspect(row.id)">{{
              row.work_order_no
            }}</el-button>
            <div>
              {{ row.operation_no }} · {{ row.operation_name }}
            </div></template
          ></el-table-column
        >
        <el-table-column
          prop="product_item_name"
          label="产品"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column label="安排人员" min-width="150">
          <template #default="{ row }">
            <div>{{ mesDispatchPersonLabel(row) }}</div>
            <el-tag v-if="row.schedule_plan_id" type="success" size="small">方案已安排</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="work_center_name"
          label="工作中心"
          min-width="120"
        />
        <el-table-column label="报工 / 计划" min-width="160"
          ><template #default="{ row }"
            ><el-progress
              :percentage="
                mesPercent(mesReportedQuantity(row), row.planned_quantity)
              "
              :show-text="false"
              :stroke-width="7"
            /><small
              >{{ mesReportedQuantity(row) }} / {{ row.planned_quantity }}
              {{ row.unit_name }}</small
            ></template
          ></el-table-column
        >
        <el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="mesStatusType(row.status_code)">{{
              row.status_label
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="交付时间" min-width="165"
          ><template #default="{ row }">{{
            formatMesDate(row.due_at)
          }}</template></el-table-column
        >
        <el-table-column label="操作" width="145" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="inspect(row.id)"
              >详情</el-button
            ><el-button
              v-if="
                hasPerms('mes:operation_task:manage') &&
                ['pending', 'dispatched'].includes(row.status_code)
              "
              link
              type="primary"
              @click="openDispatch(row)"
              >{{ row.schedule_plan_id ? "改派" : "派工" }}</el-button
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
        @size-change="search"
      />
    </el-card>
    <TaskDetail v-model="detailVisible" :task-id="taskId" />
    <el-dialog
      v-model="dispatchVisible"
      title="生产任务派工"
      width="520px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      destroy-on-close
    >
      <div v-loading="preparing" class="dispatch-body">
        <el-alert
          v-if="dispatchError"
          :title="dispatchError"
          type="error"
          :closable="false"
        />
        <el-form
          v-if="dispatchTarget"
          :model="dispatchForm"
          label-width="90px"
          :disabled="saving"
        >
          <el-form-item label="工序任务"
            >{{ dispatchTarget.work_order_no }} /
            {{ dispatchTarget.operation_name }}</el-form-item
          >
          <el-form-item label="当前人员">{{
            mesDispatchPersonLabel(dispatchTarget)
          }}</el-form-item>
          <el-form-item label="生产人员" required
            ><RemoteSelect
              v-model="dispatchForm.production_person_id"
              :context-key="dispatchTarget.id"
              :load-options="(keyword) => getMesDispatchPeople(dispatchTarget.id, keyword)"
              placeholder="按姓名或工号查找生产人员"
          /></el-form-item>
          <p>
            仅显示本组织具备本工艺资格的生产人员。无可用账号的人员由有权限的班组长代报工；更换已排程人员后请重新排程。
          </p>
          <el-form-item label="备注"
            ><el-input
              v-model="dispatchForm.note"
              type="textarea"
              maxlength="1000"
              :rows="3"
          /></el-form-item>
        </el-form>
      </div>
      <template #footer
        ><el-button :disabled="saving" @click="dispatchVisible = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="
            !dispatchTarget ||
            !dispatchForm.production_person_id ||
            !['pending', 'dispatched'].includes(dispatchTarget.status_code)
          "
          @click="submitDispatch"
          >确认派工</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<style scoped>
.mes-page {
  padding: 20px;
}

.page-heading {
  margin-bottom: 22px;
}

h2 {
  margin: 0 0 8px;
  font-size: 24px;
}

p,
small {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.pagination {
  justify-content: flex-end;
  margin-top: 20px;
}

.dispatch-body {
  min-height: 140px;
}

.el-alert {
  margin-bottom: 16px;
}
</style>
