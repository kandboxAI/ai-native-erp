<script setup lang="ts">
import BusinessTable from "../components/BusinessTable.vue";
import { computed, onMounted, ref, unref } from "vue";
import { ElMessage } from "element-plus";

import {
  useSampleApi,
  type ImportSourceRow,
} from "@plugins/sample_app/web/src/api/sample_app";
const { listImportHistory } = useSampleApi();

const rows = ref<ImportSourceRow[]>([]);
const selectedSheet = ref("");
const loading = ref(false);
const onlyPending = ref(false);
const labels: Record<string, string> = {
  imported: "已转业务",
  partial: "部分转入",
  reference: "历史参考",
  note: "说明 / 合计",
};
const sheets = computed(() => [
  ...new Set(rows.value.map((row) => row.sheet_name)),
]);
const visibleRows = computed(() =>
  rows.value.filter(
    (row) =>
      row.sheet_name === selectedSheet.value &&
      (!onlyPending.value ||
        ["partial", "reference"].includes(row.handling_key)),
  ),
);
const columns = computed(() =>
  Object.keys(
    rows.value.find((row) => row.sheet_name === selectedSheet.value)
      ?.source_cells || {},
  ),
);
async function load() {
  loading.value = true;
  try {
    const response = await listImportHistory();
    if (response.code !== 0) throw new Error(response.message);
    rows.value = response.data;
    selectedSheet.value = sheets.value.includes(selectedSheet.value)
      ? selectedSheet.value
      : sheets.value[0] || "";
  } catch {
    ElMessage.error("历史来源台账加载失败，请检查组织权限或稍后重试");
  } finally {
    loading.value = false;
  }
}
onMounted(load);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "row_no", label: "原表行号", width: "95", fixed: true },
  { label: "处理结果", width: "115", slot: "cell0_1" },
  ...unref(columns).map((column) => ({
    label: column,
    minWidth: "155",
    slot: `cell0_2_${column}`,
  })),
  { prop: "handling_note", label: "导入说明 / 待确认事项", minWidth: "360" },
]);
</script>

<template>
  <section class="sample-page">
    <p class="source-description">
      保留 Excel
      原表的行号、金额和说明。历史汇总、待确认资料与合计行不会重复计入正式工资、应收或资金流水。银行卡号仅显示尾四位。
    </p>

    <BusinessTable
      :loading="loading"
      :data="visibleRows"
      empty-text="当前授权范围暂无来源记录"
      row-key="id"
      :columns="tableColumns0"
      title="历史来源台账"
      @refresh="load"
    >
      <template #filters
        ><el-form-item label="工作表："
          ><el-select
            v-model="selectedSheet"
            placeholder="选择工作表"
            style="width: 220px"
            ><el-option
              v-for="sheet in sheets"
              :key="sheet"
              :label="sheet"
              :value="sheet" /></el-select
        ></el-form-item>
        <el-form-item
          ><el-checkbox v-model="onlyPending"
            >仅看待补充 / 待确认</el-checkbox
          ></el-form-item
        ></template
      >
      <template #cell0_1="{ row }"
        ><el-tag
          :type="
            row.handling_key === 'imported'
              ? 'success'
              : row.handling_key === 'note'
                ? 'info'
                : 'warning'
          "
          >{{ labels[row.handling_key] }}</el-tag
        ></template
      >
      <template
        v-for="column in columns"
        :key="column"
        #[`cell0_2_${column}`]="{ row }"
        >{{ row.source_cells[column] ?? "未提供" }}</template
      >
    </BusinessTable>
  </section>
</template>

<style scoped>
.source-description {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
  font-size: 14px;
}
</style>
