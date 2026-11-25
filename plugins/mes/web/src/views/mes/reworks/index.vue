<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, reactive, ref } from "vue";
import {
  getMesReworks,
  getMesOrderDefinition,
  type MesRework,
  type MesOrderDefinition,
} from "@plugins/mes/web/src/api/mes";
import { hasPerms } from "@/utils/auth";
import { message } from "@/utils/message";
import { formatMesDate, mesWorkOrderStatusLabel } from "../shared";
import WorkOrderCreate from "../components/WorkOrderCreate.vue";
import WorkOrderDetail from "../components/WorkOrderDetail.vue";
defineOptions({ name: "MesReworkDetails" });
const filters = reactive({ keyword: "", allocation: "" });
const page = ref(1),
  size = ref(10),
  total = ref(0),
  loading = ref(false),
  error = ref("");
const rows = ref<MesRework[]>([]),
  selected = ref<MesRework>();
const definition = ref<MesOrderDefinition>();
const createVisible = ref(false),
  detailVisible = ref(false),
  detailId = ref(""),
  busy = ref(false);
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getMesReworks({
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
      error.value = cause?.message || "返工明细加载失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function inspect(id: string) {
  detailId.value = id;
  detailVisible.value = true;
}
async function arrange(value: Record<string, any>) {
  const row = value as MesRework;
  if (busy.value || row.pending_quantity <= 0) return;
  busy.value = true;
  try {
    definition.value = (await getMesOrderDefinition(row.work_order_id)).data;
    selected.value = row;
    createVisible.value = true;
  } catch (cause: any) {
    message(cause?.message || "来源工单读取失败", { type: "warning" });
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="mes-page">
    <h2>返工明细</h2>
    <p class="muted">
      按原始报工查看返工数量，可拆分安排独立返修工单。返工数量是工序事实，不能跨工序相加作为成品数量。
    </p>
    <el-card shadow="never">
      <el-form inline @submit.prevent="search">
        <el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            clearable
            placeholder="报工单 / 工单 / 产品 / 工序"
            maxlength="128"
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="安排状态"
          ><el-select
            v-model="filters.allocation"
            clearable
            placeholder="全部"
            style="width: 150px"
            ><el-option label="待安排" value="pending" /><el-option
              label="部分安排"
              value="partial" /><el-option
              label="已全部安排"
              value="allocated" /></el-select
        ></el-form-item>
        <el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              Object.assign(filters, { keyword: '', allocation: '' });
              search();
            "
            >重置</el-button
          ></el-form-item
        >
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id">
        <el-table-column prop="report_no" label="报工单号" min-width="180" />
        <el-table-column label="来源 / 产品" min-width="200"
          ><template #default="{ row }"
            ><el-button
              v-if="hasPerms('mes:work_order:list')"
              link
              type="primary"
              @click="inspect(row.work_order_id)"
              >{{ row.work_order_no }}</el-button
            ><span v-else>{{ row.work_order_no }}</span>
            <div>{{ row.product_item_name }}</div></template
          ></el-table-column
        >
        <el-table-column
          prop="operation_name"
          label="产生返工的工序"
          min-width="145"
        />
        <el-table-column label="返工 / 已安排 / 待安排" min-width="190"
          ><template #default="{ row }"
            >{{ row.rework_quantity }} / {{ row.allocated_quantity }} /
            {{ row.pending_quantity }} {{ row.unit_name }}</template
          ></el-table-column
        >
        <el-table-column label="关联返修工单" min-width="245"
          ><template #default="{ row }"
            ><div v-for="repair in row.repairs" :key="repair.id">
              <el-button link type="primary" @click="inspect(repair.id)">{{
                repair.work_order_no
              }}</el-button
              ><small>
                · {{ mesWorkOrderStatusLabel(repair) }} · 计划
                {{ repair.planned_quantity }} / 合格
                {{ repair.good_quantity }}</small
              >
            </div>
            <span v-if="!row.repairs.length">—</span></template
          ></el-table-column
        >
        <el-table-column label="报工时间" min-width="175"
          ><template #default="{ row }">{{
            formatMesDate(row.reported_at)
          }}</template></el-table-column
        >
        <el-table-column
          v-if="
            hasPerms('mes:work_order:create') && hasPerms('mes:work_order:list')
          "
          label="操作"
          width="125"
          fixed="right"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="busy || row.pending_quantity <= 0"
              @click="arrange(row)"
              >安排返修</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        layout="total, sizes, prev, pager, next"
        :total="total"
        @current-change="load"
        @size-change="search"
      />
    </el-card>
    <WorkOrderCreate
      v-model="createVisible"
      purpose="repair"
      :initial-order="definition"
      :rework-report-id="selected?.id"
      :max-quantity="selected?.pending_quantity"
      @created="load"
    />
    <WorkOrderDetail v-model="detailVisible" :work-order-id="detailId" />
  </div>
</template>
<style scoped>
.mes-page {
  padding: 20px;
}

h2 {
  margin: 0 0 8px;
}

.muted {
  margin-bottom: 20px;
  color: var(--el-text-color-secondary);
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
