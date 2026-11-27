<script setup lang="ts">
import { watch as watchFormOrganization } from "vue";

import OrganizationField from "../components/OrganizationField.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, reactive, ref, computed, unref } from "vue";
import { ElMessage } from "element-plus";
import {
  useSampleApi,
  type EmployeeOption,
  type SalaryRow,
  type SocialPlan,
} from "@plugins/sample_app/web/src/api/sample_app";
const { createSalary, listSocialPlans, listEmployees, listSalaries } =
  useSampleApi();

const rows = ref<SalaryRow[]>([]);
const employees = ref<EmployeeOption[]>([]);
const plans = ref<SocialPlan[]>([]);
const visible = ref(false);
const form = reactive({
  org_id: "",
  employee_id: "",
  social_plan_id: "",
  social_base: 0,
  base_amount: 0,
  performance_amount: 0,
  valid_from: new Date().toISOString().slice(0, 10),
});

async function load() {
  loading.value = true;
  try {
    const [salary, people, setting] = await Promise.all([
      listSalaries(),
      listEmployees(),
      listSocialPlans(),
    ]);
    if (salary.code !== 0 || people.code !== 0 || setting.code !== 0) {
      ElMessage.error(salary.message || people.message || setting.message);
      return;
    }
    rows.value = salary.data;
    employees.value = people.data;
    plans.value = setting.data;
  } finally {
    loading.value = false;
  }
}

async function submit() {
  const response = await createSalary({
    ...form,
    social_plan_id: form.social_plan_id || null,
    valid_to: null,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  visible.value = false;
  ElMessage.success("已增加薪资版本");
  await load();
}

onMounted(load);
const loading = ref(false);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "employee_no", label: "员工编号", width: "140" },
  { prop: "full_name", label: "姓名", width: "120" },
  { prop: "base_amount", label: "基本工资", align: "right" },
  { prop: "performance_amount", label: "绩效工资", align: "right" },
  { prop: "valid_from", label: "生效日期" },
  { prop: "valid_to", label: "失效日期" },
]);

watchFormOrganization(
  () => form.org_id,
  () => {
    form.employee_id = "";
    form.social_plan_id = "";
  },
  { flush: "sync" },
);
</script>

<template>
  <section class="sample-page">
    <BusinessTable
      delete-resource="salaries"
      :data="rows"
      :loading="loading"
      :columns="tableColumns0"
      title="员工定薪"
      @refresh="load"
    >
      <template #buttons
        ><el-button
          type="primary"
          @click="visible = true"
          :icon="useRenderIcon('ri/add-line')"
          >新增定薪</el-button
        ></template
      >
    </BusinessTable>
    <el-dialog v-model="visible" title="新增定薪" width="520px">
      <el-form label-width="110px"
        ><OrganizationField v-model="form.org_id" />
        <el-form-item label="员工"
          ><el-select v-model="form.employee_id" filterable
            ><el-option
              v-for="item in employees.filter(
                (item) => !form.org_id || item.org_id === form.org_id,
              )"
              :key="item.id"
              :label="`${item.full_name} ${item.employee_no}`"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-alert
          title="调薪不改变缴费基数；请在“缴费基数”页面维护社保和公积金基数。"
          type="info"
          :closable="false"
          style="margin-bottom: 16px"
        />
        <el-form-item label="基本工资"
          ><el-input-number v-model="form.base_amount" :min="0" :precision="2"
        /></el-form-item>
        <el-form-item label="绩效工资"
          ><el-input-number
            v-model="form.performance_amount"
            :min="0"
            :precision="2"
        /></el-form-item>
        <el-form-item label="生效日期"
          ><el-date-picker
            v-model="form.valid_from"
            type="date"
            value-format="YYYY-MM-DD"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" @click="submit">保存</el-button></template
      >
    </el-dialog>
  </section>
</template>
