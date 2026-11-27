<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import BusinessTable from "../components/BusinessTable.vue";
import OrganizationField from "../components/OrganizationField.vue";
import {
  useSampleApi,
  type SocialBasis,
  type EmployeeOption,
  type SocialPlan,
} from "@plugins/sample_app/web/src/api/sample_app";
const api = useSampleApi();
const rows = ref<SocialBasis[]>([]),
  people = ref<EmployeeOption[]>([]),
  plans = ref<SocialPlan[]>([]);
const visible = ref(false),
  loading = ref(false),
  saving = ref(false);
const form = reactive({
  org_id: "",
  employee_id: "",
  social_plan_id: "",
  social_base: 0,
  housing_base: 0,
  valid_from: new Date().toISOString().slice(0, 7),
});
const columns: TableColumnList = [
  { prop: "full_name", label: "员工" },
  { prop: "social_base", label: "社保基数" },
  { prop: "housing_base", label: "公积金基数" },
  { prop: "plan_name", label: "缴费方案" },
  { prop: "valid_from", label: "生效月份" },
  {
    prop: "valid_to",
    label: "失效月份",
    formatter: (row) => row.valid_to?.slice(0, 7) || "持续有效",
  },
  { label: "操作", slot: "actions", width: 130 },
];
const displayRows = computed(() =>
  rows.value.map((row) => ({
    ...row,
    plan_name:
      plans.value.find((p) => p.id === row.social_plan_id)?.plan_name || "—",
  })),
);
watch(
  () => form.org_id,
  () => {
    form.employee_id = "";
    form.social_plan_id = "";
  },
  { flush: "sync" },
);
function open(row?: SocialBasis) {
  Object.assign(form, {
    org_id: row?.org_id || "",
    employee_id: "",
    social_plan_id: "",
    social_base: 0,
    housing_base: 0,
    valid_from: new Date().toISOString().slice(0, 7),
  });
  if (row)
    Object.assign(form, {
      employee_id: row.employee_id,
      social_plan_id: row.social_plan_id,
      social_base: Number(row.social_base),
      housing_base: Number(row.housing_base),
    });
  visible.value = true;
}
async function load() {
  loading.value = true;
  try {
    const [a, b, c] = await Promise.all([
      api.listSocialBases(),
      api.listEmployees(),
      api.listSocialPlans(),
    ]);
    for (const response of [a, b, c])
      if (response.code !== 0) throw Error(response.message);
    rows.value = a.data;
    people.value = b.data;
    plans.value = c.data;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}
async function save() {
  if (saving.value) return;
  if (
    !form.org_id ||
    !form.employee_id ||
    !form.social_plan_id ||
    !form.valid_from
  ) {
    ElMessage.warning("请完整选择公司、员工、方案和生效月份");
    return;
  }
  saving.value = true;
  try {
    const r = await api.saveSocialBasis({ ...form });
    if (r.code !== 0) throw Error(r.message);
    visible.value = false;
    ElMessage.success("已保存独立缴费基数，历史缴费单不变");
    await load();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="sample-page">
    <BusinessTable
      delete-resource="social-bases"
      title="缴费基数"
      :data="displayRows"
      :columns="columns"
      :loading="loading"
      @refresh="load"
    >
      <template #buttons
        ><el-button type="primary" @click="open()"
          >新增基数版本</el-button
        ></template
      >
      <template #actions="{ row }"
        ><el-button link type="primary" @click="open(row)"
          >调整基数</el-button
        ></template
      >
    </BusinessTable>
    <el-dialog
      v-model="visible"
      title="新增缴费基数版本"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form label-width="110px">
        <OrganizationField v-model="form.org_id" />
        <el-form-item label="员工"
          ><el-select v-model="form.employee_id" filterable
            ><el-option
              v-for="p in people.filter((p) => p.org_id === form.org_id)"
              :key="p.id"
              :label="`${p.full_name} ${p.employee_no}`"
              :value="p.id" /></el-select
        ></el-form-item>
        <el-form-item label="缴费方案"
          ><el-select v-model="form.social_plan_id"
            ><el-option
              v-for="p in plans.filter((p) => p.org_id === form.org_id)"
              :key="p.id"
              :label="p.plan_name"
              :value="p.id" /></el-select
        ></el-form-item>
        <el-form-item label="社保缴费基数"
          ><el-input-number v-model="form.social_base" :min="0" :precision="2"
        /></el-form-item>
        <el-form-item label="公积金基数"
          ><el-input-number v-model="form.housing_base" :min="0" :precision="2"
        /></el-form-item>
        <el-form-item label="生效月份"
          ><el-date-picker
            v-model="form.valid_from"
            type="month"
            value-format="YYYY-MM"
        /></el-form-item>
        <el-alert
          title="基数独立于工资，可按年度调整；新版本生效后延续使用，直到下次调整。已确认缴费单保留原快照。"
          type="info"
          :closable="false"
        />
      </el-form>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>
