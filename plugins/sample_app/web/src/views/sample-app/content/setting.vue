<script setup lang="ts">
import { useBusinessContext } from "@plugins/sample_app/web/src/api/sample_appContext";
import OrganizationField from "../components/OrganizationField.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, reactive, ref, computed, unref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  useSampleApi,
  type SocialPlan,
  type TaxBracket,
} from "@plugins/sample_app/web/src/api/sample_app";
const { getPaySetting, savePaySetting, saveSocialPlan } = useSampleApi();

const context = useBusinessContext()!;
const setting = reactive({
  org_id: "",
  daily_wage_mode_code: "fixed_days",
  standard_days: 21.75,
  overtime_multiplier: 2,
  tax_threshold: 5000,
});
const plans = ref<SocialPlan[]>([]);
const brackets = ref<TaxBracket[]>([]);
const visible = ref(false);
const plan = reactive<SocialPlan>({
  org_id: "",
  id: "",
  plan_name: "",
  pension_employer_rate: 16,
  pension_employee_rate: 8,
  unemployment_employer_rate: 0.7,
  unemployment_employee_rate: 0.3,
  injury_employer_rate: 0.16,
  medical_employer_rate: 8,
  medical_employee_rate: 2,
  housing_employer_rate: 5,
  housing_employee_rate: 5,
});
const rateFields = [
  ["pension_employer_rate", "养老企业"],
  ["pension_employee_rate", "养老个人"],
  ["unemployment_employer_rate", "失业企业"],
  ["unemployment_employee_rate", "失业个人"],
  ["injury_employer_rate", "工伤企业"],
  ["medical_employer_rate", "医疗企业"],
  ["medical_employee_rate", "医疗个人"],
  ["housing_employer_rate", "公积金企业"],
  ["housing_employee_rate", "公积金个人"],
] as const;

let settingRequest = 0;
async function load() {
  const request = ++settingRequest;
  if (!context.operationOrg.value) {
    plans.value = [];
    brackets.value = [];
    return;
  }
  loading.value = true;
  try {
    const response = await getPaySetting();
    if (request !== settingRequest) return;
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    Object.assign(setting, response.data.setting);
    plans.value = response.data.plans;
    brackets.value = response.data.brackets;
  } finally {
    if (request === settingRequest) loading.value = false;
  }
}

async function saveSetting() {
  if (!context.operationOrg.value || loading.value) return;
  const response = await savePaySetting({
    org_id: context.operationOrg.value,
    daily_wage_mode_code: setting.daily_wage_mode_code,
    standard_days: setting.standard_days,
    overtime_multiplier: setting.overtime_multiplier,
    tax_threshold: setting.tax_threshold,
  });
  ElMessage[response.code === 0 ? "success" : "error"](
    response.code === 0 ? "计薪参数已保存" : response.message,
  );
}

function edit(row?: SocialPlan) {
  Object.assign(
    plan,
    row || {
      id: "",
      plan_name: "新方案",
      pension_employer_rate: 0,
      pension_employee_rate: 0,
      unemployment_employer_rate: 0,
      unemployment_employee_rate: 0,
      injury_employer_rate: 0,
      medical_employer_rate: 0,
      medical_employee_rate: 0,
      housing_employer_rate: 0,
      housing_employee_rate: 0,
    },
  );
  visible.value = true;
}

async function savePlan() {
  const response = await saveSocialPlan(
    plan.id ? plan : { ...plan, id: undefined },
  );
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  visible.value = false;
  await load();
}

watch(() => context.operationOrg.value, load);
onMounted(load);
const loading = ref(false);
const tableColumns0 = computed<TableColumnList>(() => [
  { prop: "plan_name", label: "方案" },
  ...unref(rateFields).map(([key, label]) => ({ prop: key, label: label })),
  { label: "操作", width: "90", slot: "cell0_2" },
]);
const tableColumns1 = computed<TableColumnList>(() => [
  { prop: "min_amount", label: "超过", align: "right" },
  { prop: "max_amount", label: "至", align: "right" },
  { prop: "rate", label: "税率%" },
  { prop: "quick_deduction", label: "速算扣除" },
]);
</script>

<template>
  <section class="sample-page">
    <el-card shadow="never" header="计薪参数" class="parameter-card"
      ><el-form inline
        ><OrganizationField v-model="context.operationOrg.value" /></el-form
      ><el-form inline :disabled="loading || !context.operationOrg.value">
        <el-form-item label="日薪口径">
          <el-select v-model="setting.daily_wage_mode_code" style="width: 160px"
            ><el-option label="固定天数" value="fixed_days" /><el-option
              label="当月应出勤"
              value="attendance_days"
          /></el-select>
        </el-form-item>
        <el-form-item label="固定天数"
          ><el-input-number
            v-model="setting.standard_days"
            :min="1"
            :precision="2"
        /></el-form-item>
        <el-form-item label="加班倍率"
          ><el-input-number
            v-model="setting.overtime_multiplier"
            :min="0"
            :precision="2"
        /></el-form-item>
        <el-form-item label="月减除费用"
          ><el-input-number
            v-model="setting.tax_threshold"
            :min="0"
            :precision="2"
        /></el-form-item>
        <el-button type="primary" @click="saveSetting">保存参数</el-button>
      </el-form></el-card
    >

    <BusinessTable
      :organization-filter-visible="false"
      :data="plans"
      :loading="loading"
      :columns="tableColumns0"
      delete-resource="social-plans"
      title="社保公积金方案"
      @refresh="load"
      :searchable="false"
    >
      <template #buttons
        ><el-button @click="edit()" :icon="useRenderIcon('ri/add-line')"
          >新增社保方案</el-button
        ></template
      >
      <template #cell0_2="{ row }"
        ><el-button link type="primary" @click="edit(row as SocialPlan)"
          >修改</el-button
        ></template
      >
    </BusinessTable>

    <BusinessTable
      :organization-filter-visible="false"
      :data="brackets"
      :loading="loading"
      :columns="tableColumns1"
      title="个税税率档"
      @refresh="load"
      :searchable="false"
    >
    </BusinessTable>
    <el-dialog v-model="visible" title="社保公积金方案" width="640px">
      <el-form label-width="110px"
        ><OrganizationField v-model="plan.org_id" />
        <el-form-item label="名称"
          ><el-input v-model="plan.plan_name"
        /></el-form-item>
        <el-form-item
          v-for="[key, label] in rateFields"
          :key="key"
          :label="label"
          ><el-input-number v-model="plan[key]" :min="0" :precision="4"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" @click="savePlan">保存</el-button></template
      >
    </el-dialog>
  </section>
</template>
