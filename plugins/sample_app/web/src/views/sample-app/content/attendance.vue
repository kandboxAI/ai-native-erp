<script setup lang="ts">
import { useBusinessContext } from "@plugins/sample_app/web/src/api/sample_appContext";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, ref, computed, unref } from "vue";
import { useOrganizationLifetime } from "@plugins/sample_app/web/src/api/sample_appContext";
import { ElMessage } from "element-plus";
import {
  useSampleApi,
  type AttendanceRow,
} from "@plugins/sample_app/web/src/api/sample_app";
const { listAttendance, saveAttendance } = useSampleApi();

const context = useBusinessContext()!;
const month = ref(new Date().toISOString().slice(0, 7));
const rows = ref<AttendanceRow[]>([]);
const loading = ref(false);
const isCurrentOrganization = useOrganizationLifetime();

async function load() {
  loading.value = true;
  try {
    const response = await listAttendance(month.value);
    if (response.code !== 0) throw new Error(response.message);
    rows.value = response.data;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "考勤加载失败");
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!context.operationOrg.value) {
    ElMessage.warning("请先在筛选栏选择所属组织");
    return;
  }
  const response = await saveAttendance(
    month.value,
    rows.value.filter((row) => row.org_id === context.operationOrg.value),
  );
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  const warnings = response.data.warnings.length
    ? `，实出勤大于应出勤：${response.data.warnings.join("、")}`
    : "";
  ElMessage.success(`已保存 ${response.data.saved} 人${warnings}`);
  await load();
}

function downloadTemplate() {
  const content = "\ufeff员工编号,应出勤,实出勤,加班天数\n";
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob([content], { type: "text/csv;charset=utf-8" }),
  );
  link.download = "考勤导入模板.csv";
  link.click();
}

function importFile(event: Event) {
  const importedOrg = context.operationOrg.value;
  if (!importedOrg) {
    ElMessage.warning("请先在筛选栏选择导入组织");
    return;
  }
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    if (!isCurrentOrganization() || context.operationOrg.value !== importedOrg)
      return;
    const lines = String(reader.result || "")
      .replace(/^\uFEFF/, "")
      .split(/\r?\n/)
      .slice(1)
      .filter(Boolean);
    const imported = new Map(
      lines.map((line) => {
        const [employee_no, expected_days, actual_days, overtime_days] =
          line.split(",");
        return [
          employee_no.trim(),
          {
            expected_days: Number(expected_days),
            actual_days: Number(actual_days),
            overtime_days: Number(overtime_days),
          },
        ] as const;
      }),
    );
    rows.value = rows.value.map((row) =>
      row.org_id === importedOrg && imported.has(row.employee_no)
        ? { ...row, ...imported.get(row.employee_no) }
        : row,
    );
    ElMessage.success("已填入表格，确认后点保存");
  };
  reader.readAsText(file, "utf-8");
}

onMounted(load);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "employee_no", label: "员工编号", width: "140" },
  { prop: "full_name", label: "姓名", width: "120" },
  { label: "应出勤", slot: "cell0_2", minWidth: 180 },
  { label: "实出勤", slot: "cell0_3", minWidth: 180 },
  { label: "加班天数", slot: "cell0_4", minWidth: 180 },
  { label: "提示", width: "160", slot: "cell0_5" },
]);
</script>

<template>
  <section class="sample-page">
    <BusinessTable
      v-model:organization="context.operationOrg.value"
      :loading="loading"
      :data="rows"
      :columns="tableColumns0"
      delete-resource="attendance"
      title="月度考勤"
      @refresh="load"
      row-key="employee_id"
    >
      <template #filters
        ><el-form-item label="核算月份："
          ><el-date-picker
            v-model="month"
            type="month"
            value-format="YYYY-MM"
            @change="load" /></el-form-item
      ></template>
      <template #buttons
        ><el-button
          type="primary"
          :disabled="!context.operationOrg.value"
          @click="save"
          >保存</el-button
        >
        <el-button @click="downloadTemplate">下载模板</el-button>
        <label class="cursor-pointer text-sm"
          >导入表格<input
            class="hidden"
            type="file"
            accept=".csv,text/csv"
            @change="importFile" /></label
      ></template>
      <template #cell0_2="{ row }"
        ><el-input-number
          v-model="row.expected_days"
          :min="0"
          :step="0.5"
          :precision="2"
      /></template>
      <template #cell0_3="{ row }"
        ><el-input-number
          v-model="row.actual_days"
          :min="0"
          :step="0.5"
          :precision="2"
      /></template>
      <template #cell0_4="{ row }"
        ><el-input-number
          v-model="row.overtime_days"
          :min="0"
          :step="0.5"
          :precision="2"
      /></template>
      <template #cell0_5="{ row }"
        ><span
          v-if="row.actual_days > row.expected_days && row.expected_days > 0"
          >实出勤大于应出勤</span
        ></template
      >
    </BusinessTable>
  </section>
</template>
