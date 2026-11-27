<script setup lang="ts">
import { computed, ref, useSlots, watch } from "vue";
import { PureTable } from "@pureadmin/table";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteSampleRecord } from "@plugins/sample_app/web/src/api/sample_app";

import { useBusinessContext } from "@plugins/sample_app/web/src/api/sample_appContext";
const context = useBusinessContext();
const localOrganization = ref("");
const props = withDefaults(
  defineProps<{
    organization?: string;
    organizationFilterVisible?: boolean;
    title: string;
    data: any[];
    columns: TableColumnList;
    loading?: boolean;
    searchable?: boolean;
    rowKey?: string;
    emptyText?: string;
    deleteResource?: string;
    /** client：前端切片；server：data 已是当前页，total/page 由父组件驱动 */
    paginationMode?: "client" | "server";
    total?: number;
    page?: number;
    pageSize?: number;
  }>(),
  {
    loading: false,
    searchable: true,
    rowKey: "id",
    emptyText: "暂无数据",
    organizationFilterVisible: true,
    paginationMode: "client",
    total: 0,
    page: 1,
    pageSize: 20,
  },
);
const emit = defineEmits<{
  refresh: [];
  reset: [];
  "update:organization": [value: string];
  "update:page": [value: number];
  "update:pageSize": [value: number];
  search: [keyword: string];
}>();
// 组织级操作页共用外部选择；普通列表仍保留自己的组织筛选。
const organizationFilter = computed({
  get: () => props.organization ?? localOrganization.value,
  set: (value: string) => {
    localOrganization.value = value;
    emit("update:organization", value);
  },
});
const slots = useSlots();
const tableRef = ref();
const keyword = ref("");
const appliedKeyword = ref("");
const localPage = ref(1);
const localPageSize = ref(20);
const page = computed({
  get: () =>
    props.paginationMode === "server" ? props.page : localPage.value,
  set: (value: number) => {
    if (props.paginationMode === "server") emit("update:page", value);
    else localPage.value = value;
  },
});
const pageSize = computed({
  get: () =>
    props.paginationMode === "server" ? props.pageSize : localPageSize.value,
  set: (value: number) => {
    if (props.paginationMode === "server") emit("update:pageSize", value);
    else localPageSize.value = value;
  },
});
const fullscreen = ref(false);
const deleting = ref(false);
function canDelete(row: any) {
  if (props.deleteResource === "social-bills")
    return !!row.bill_id && row.status_code === "draft" && !row.cash_entry_id;
  return (
    !!row.id &&
    (props.deleteResource !== "reimbursements" ||
      ["draft", "rejected"].includes(row.status_code))
  );
}
async function deleteRow(row: any) {
  if (deleting.value || !props.deleteResource || !canDelete(row)) return;
  deleting.value = true;
  try {
    await ElMessageBox.confirm(
      "确认删除这条记录？已有业务关联或核算记录时，系统会拒绝删除。",
      "删除确认",
      { type: "warning" },
    );
  } catch {
    deleting.value = false;
    return;
  }
  try {
    const result = await deleteSampleRecord(props.deleteResource, row.id);
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    ElMessage.success("已删除");
    emit("refresh");
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : "删除失败，请刷新核对后重试",
    );
  } finally {
    deleting.value = false;
  }
}
const cellSlots = () =>
  Object.keys(slots).filter(
    (name) => !["buttons", "filters", "summary"].includes(name),
  );
const filtered = computed(() => {
  if (props.paginationMode === "server") return props.data;
  const value = appliedKeyword.value.trim().toLocaleLowerCase();
  const rows = organizationFilter.value
    ? props.data.filter((row) => row.org_id === organizationFilter.value)
    : props.data;
  return value
    ? rows.filter((row) =>
        JSON.stringify(row).toLocaleLowerCase().includes(value),
      )
    : rows;
});
const currentPage = computed(() => {
  if (props.paginationMode === "server") return page.value;
  return Math.min(
    page.value,
    Math.max(1, Math.ceil(filtered.value.length / pageSize.value)),
  );
});
const pageRows = computed(() => {
  if (props.paginationMode === "server") return filtered.value;
  return filtered.value.slice(
    (currentPage.value - 1) * pageSize.value,
    currentPage.value * pageSize.value,
  );
});
const paginationTotal = computed(() =>
  props.paginationMode === "server" ? props.total : filtered.value.length,
);
const tableColumns = computed<TableColumnList>(() =>
  [
    {
      minWidth: 240,
      ...props.columns.find((column) => column.prop === "org_name"),
      prop: "org_name",
      label: "所属组织",
      fixed: "left" as const,
      formatter: (row) =>
        row.org_name ||
        context?.organizations.value.find((item) => item.id === row.org_id)
          ?.org_name ||
        "—",
    },
    ...props.columns.filter((column) => column.prop !== "org_name"),
    ...(props.deleteResource
      ? [
          {
            label: "删除",
            width: 80,
            fixed: "right" as const,
            slot: "deleteAction",
          },
        ]
      : []),
  ].map((column) => ({
    minWidth: 120,
    ...column,
    ...(!column.slot &&
    !column.formatter &&
    /amount|cost|balance|income|expense|profit|social_base|month_net/.test(
      String(column.prop || ""),
    )
      ? {
          align: "right" as const,
          formatter: (_row, _column, value) =>
            value == null
              ? "—"
              : Number.isFinite(Number(value))
                ? Number(value).toLocaleString("zh-CN", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })
                : value,
        }
      : {}),
    ...(column.label === "操作"
      ? {
          fixed: "right" as const,
          align: "center" as const,
          className: ["business-actions-cell", column.className]
            .filter(Boolean)
            .join(" "),
        }
      : {}),
  })),
);
// PureTableBar的列配置随表结构重建，工作表切换时同步重置显隐配置。
const columnKey = computed(() =>
  JSON.stringify(
    tableColumns.value.map(({ label, prop, slot }) => [label, prop, slot]),
  ),
);
function search() {
  appliedKeyword.value = keyword.value;
  page.value = 1;
  if (props.paginationMode === "server") emit("search", keyword.value.trim());
}
function reset() {
  organizationFilter.value = "";
  emit("reset");
  keyword.value = "";
  appliedKeyword.value = "";
  page.value = 1;
  if (props.paginationMode === "server") emit("search", "");
}
watch(
  () => props.data,
  () => {
    if (props.paginationMode === "client") page.value = 1;
  },
);
watch(columnKey, () => {
  fullscreen.value = false;
});
</script>

<template>
  <div class="business-table">
    <el-form
      v-if="
        searchable || $slots.filters || (context && organizationFilterVisible)
      "
      :inline="true"
      :model="{ keyword }"
      class="search-form business-search"
      @submit.prevent="search"
    >
      <el-form-item
        v-if="context && organizationFilterVisible"
        label="所属组织："
        ><el-select
          v-model="organizationFilter"
          clearable
          filterable
          placeholder="全部授权组织"
          style="width: 180px"
          ><el-option
            v-for="item in context.organizations.value"
            :key="item.id"
            :label="item.org_name"
            :value="item.id" /></el-select
      ></el-form-item>
      <slot name="filters" />
      <el-form-item v-if="searchable" label="关键词：">
        <el-input
          v-model="keyword"
          placeholder="输入名称、编号或内容"
          clearable
          style="width: 220px"
          @keyup.enter="search"
          @clear="search"
        />
      </el-form-item>
      <el-form-item v-if="searchable">
        <el-button
          type="primary"
          :icon="useRenderIcon('ri/search-line')"
          :loading="loading"
          @click="search"
          >搜索</el-button
        >
        <el-button :icon="useRenderIcon('ri/refresh-line')" @click="reset"
          >重置</el-button
        >
      </el-form-item>
    </el-form>
    <PureTableBar
      :key="columnKey"
      :title="title"
      :columns="tableColumns"
      :table-ref="tableRef?.getTableRef()"
      @refresh="emit('refresh')"
      @fullscreen="fullscreen = !fullscreen"
    >
      <template #title>
        <div class="business-table-heading">
          <span class="business-table-title">{{ title }}</span
          ><span v-if="$slots.summary" class="business-table-summary"
            ><slot name="summary" :rows="filtered"
          /></span>
        </div>
      </template>
      <template #buttons
        ><div class="business-table-actions"><slot name="buttons" /></div
      ></template>
      <template #default="{ size, dynamicColumns }">
        <PureTable
          ref="tableRef"
          :max-height="fullscreen ? 'calc(100vh - 180px)' : 600"
          :row-key="rowKey"
          :empty-text="emptyText"
          :loading="loading"
          :size="size"
          :data="pageRows"
          :columns="dynamicColumns"
          align-whole="left"
          table-layout="fixed"
          show-overflow-tooltip
          :header-cell-style="{
            background: 'var(--el-fill-color-light)',
            color: 'var(--el-text-color-primary)',
          }"
          :pagination="{
            total: paginationTotal,
            currentPage,
            pageSize,
            pageSizes: [10, 20, 50, 100],
            background: true,
            size,
            layout: 'total, sizes, prev, pager, next, jumper',
          }"
          @page-size-change="
            (value) => {
              pageSize = value;
              page = 1;
            }
          "
          @page-current-change="
            (value) => {
              page = value;
            }
          "
        >
          <template v-if="deleteResource" #deleteAction="{ row }">
            <el-button
              v-if="canDelete(row)"
              link
              type="danger"
              :disabled="deleting"
              @click="deleteRow(row)"
              >删除</el-button
            >
          </template>
          <template v-for="name in cellSlots()" :key="name" #[name]="scope"
            ><slot :name="name" v-bind="scope"
          /></template>
        </PureTable>
      </template>
    </PureTableBar>
  </div>
</template>

<style scoped>
.business-table {
  min-width: 0;
  margin-bottom: 20px;
}
.business-search {
  padding: 18px 24px 0;
  margin-bottom: 16px;
  background: var(--el-bg-color);
}
.business-table-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.business-table :deep(.el-pagination) {
  flex-wrap: wrap;
  gap: 8px;
  padding: 16px 0;
}
.business-table :deep(.el-table .el-input-number) {
  width: 100%;
}
.business-table :deep(.el-table .el-select) {
  width: 100%;
}
.business-table :deep(td.business-actions-cell .cell),
.business-table :deep(td.business-actions-cell .cell.el-tooltip) {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 4px 8px;
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
  line-height: 1.4;
}
.business-table :deep(td.business-actions-cell .el-button) {
  margin-left: 0;
  white-space: nowrap;
}
.business-table :deep(.h-15) {
  height: auto;
  min-height: 60px;
  flex-wrap: wrap;
  gap: 12px;
}
.business-table-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>

<style scoped>
.business-table-heading {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 16px;
  min-width: 0;
  padding: 12px 0;
}
.business-table-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.business-table-summary {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
