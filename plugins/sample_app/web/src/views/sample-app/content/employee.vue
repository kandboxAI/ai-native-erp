<script setup lang="ts">
import { watch as watchFormOrganization } from "vue";

import FlexFields from "../components/FlexFields.vue";
import OrganizationField from "../components/OrganizationField.vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import BusinessTable from "../components/BusinessTable.vue";
import { onMounted, reactive, ref, computed, unref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useUserStoreHook } from "@/store/modules/user";
import {
  useSampleApi,
  type ProjectRow,
  type SocialPlan,
  transferSampleEmployee,
  type EmployeeOption,
  type EmployeeAccountBinding,
  type EmployeeAccountOption,
  type FlexField,
  flexDisplay,
} from "@plugins/sample_app/web/src/api/sample_app";
const {
  listEmployees,
  listOrganizations,
  listSocialPlans,
  saveEmployee,
  listProjects,
  listFlexFields,
  listEmployeeAccountBindings,
  listEmployeeAccountOptions,
  bindEmployeeAccount,
  unbindEmployeeAccount,
} = useSampleApi();
const transferEmployee = ref<EmployeeOption | null>(null);
const transferVisible = ref(false);
const transferBusy = ref(false);
const transferOrganizations = ref<Array<{ id: string; org_name: string }>>([]);
const transferPlans = ref<SocialPlan[]>([]);
const transferForm = reactive({
  target_org_id: "",
  effective_on: "",
  social_plan_id: "",
});

async function openTransfer(row: EmployeeOption) {
  try {
    const [organizations, plans] = await Promise.all([
      listOrganizations(),
      listSocialPlans(),
    ]);
    if (organizations.code !== 0 || plans.code !== 0) {
      ElMessage.error("无法加载组织或缴费方案");
      return;
    }
    transferOrganizations.value = organizations.data.filter(
      (item) => item.id !== row.org_id,
    );
    transferPlans.value = plans.data;
    transferEmployee.value = row;
    Object.assign(transferForm, {
      target_org_id: "",
      effective_on: "",
      social_plan_id: "",
    });
    transferVisible.value = true;
  } catch {
    ElMessage.error("无法加载组织或缴费方案");
  }
}

async function submitTransfer() {
  const employee = transferEmployee.value;
  if (
    !employee ||
    transferBusy.value ||
    Object.values(transferForm).some((value) => !value)
  )
    return;
  const payload = { ...transferForm };
  transferBusy.value = true;
  try {
    const result = await transferSampleEmployee(employee.id, {
      ...payload,
      preview: true,
    });
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    const target = transferOrganizations.value.find(
      (item) => item.id === payload.target_org_id,
    );
    const data = result.data;
    try {
      await ElMessageBox.confirm(
        `${employee.full_name}自 ${data.effective_on} 起调入${target?.org_name}。基本工资 ${data.base_amount} 元，绩效 ${data.performance_amount} 元，社保基数 ${data.social_base} 元，公积金基数 ${data.housing_base} 元，缴费方案为${data.plan_name}。`,
        "确认组织调动",
        { type: "warning" },
      );
    } catch {
      return;
    }
    const saved = await transferSampleEmployee(employee.id, {
      ...payload,
      preview: false,
      preview_key: data.preview_key,
    });
    if (saved.code !== 0) {
      ElMessage.error(saved.message);
      return;
    }
    transferVisible.value = false;
    ElMessage.success("组织调动已登记");
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "组织调动失败");
  } finally {
    transferBusy.value = false;
  }
}
const userStore = useUserStoreHook();
const canReadBindings = computed(() =>
  ["sample_app:access", "user_profile:detail"].every((key) =>
    userStore.permissions.includes(key),
  ),
);
const canBindAccounts = computed(
  () =>
    canReadBindings.value &&
    userStore.permissions.includes("user_profile:list"),
);
const accountBindings = ref<EmployeeAccountBinding[]>([]);
const accountOptions = ref<EmployeeAccountOption[]>([]);
const bindingVisible = ref(false);
const bindingEmployee = ref<EmployeeOption | null>(null);
const bindingUserId = ref("");
const originalUserId = ref("");
const bindingSaving = ref(false);
const accountSearching = ref(false);
let accountSearchRevision = 0;
const bindingFor = (employeeId: string) =>
  accountBindings.value.find((item) => item.employee_id === employeeId);
const selectedAccountBinding = computed(() =>
  accountBindings.value.find((item) => item.user_id === bindingUserId.value),
);

async function loadBindings() {
  if (!canReadBindings.value || isOutsourced.value) return;
  const result = await listEmployeeAccountBindings();
  if (result.code === 0) accountBindings.value = result.data;
  else ElMessage.error(result.message);
}

async function searchAccounts(keyword = "") {
  const revision = ++accountSearchRevision;
  accountSearching.value = true;
  try {
    const result = await listEmployeeAccountOptions(keyword);
    if (revision !== accountSearchRevision) return;
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    const current =
      bindingEmployee.value && bindingFor(bindingEmployee.value.id);
    accountOptions.value = result.data;
    if (
      current &&
      !accountOptions.value.some((item) => item.id === current.user_id)
    ) {
      accountOptions.value.unshift({
        id: current.user_id,
        name: current.account_name,
        org_name: "",
      });
    }
  } finally {
    if (revision === accountSearchRevision) accountSearching.value = false;
  }
}

async function openBinding(row: EmployeeOption) {
  bindingEmployee.value = row;
  const current = bindingFor(row.id);
  bindingUserId.value = current?.user_id || "";
  originalUserId.value = current?.user_id || "";
  accountOptions.value = [];
  bindingVisible.value = true;
  await searchAccounts();
}

async function saveBinding() {
  if (!bindingEmployee.value || !bindingUserId.value || bindingSaving.value)
    return;
  bindingSaving.value = true;
  try {
    const result = await bindEmployeeAccount({
      user_id: bindingUserId.value,
      employee_id: bindingEmployee.value.id,
      ...(originalUserId.value
        ? { previous_user_id: originalUserId.value }
        : {}),
    });
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    bindingVisible.value = false;
    await loadBindings();
    ElMessage.success("账号关联已保存");
  } finally {
    bindingSaving.value = false;
  }
}

async function removeBinding(row: EmployeeOption) {
  const current = bindingFor(row.id);
  if (!current || bindingSaving.value) return;
  try {
    await ElMessageBox.confirm(
      `解除“${row.full_name}”与账号“${current.account_name}”的关联？解除后该账号不能继续提交此员工的报销，历史记录保留。`,
      "解除账号关联",
      { type: "warning" },
    );
  } catch {
    return;
  }
  bindingSaving.value = true;
  try {
    const result = await unbindEmployeeAccount(current.user_id, row.id);
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    await loadBindings();
    ElMessage.success("账号关联已解除");
  } finally {
    bindingSaving.value = false;
  }
}

const props = withDefaults(
  defineProps<{ personnelType?: "internal" | "outsourced" }>(),
  { personnelType: "internal" },
);
const isOutsourced = computed(() => props.personnelType === "outsourced");
const projects = ref<ProjectRow[]>([]);
const rows = ref<EmployeeOption[]>([]);
const visible = ref(false);
const form = reactive({
  org_id: "",
  project_id: "",
  id: "",
  employee_no: "",
  full_name: "",
  employment_status_code: "active",
  hire_date: new Date().toISOString().slice(0, 10),
  bank_name: "",
  account_no_masked: "",
  flex_form: {} as Record<string, string | number | boolean | null>,
});
const flexFields = ref<FlexField[]>([]);

async function load() {
  loading.value = true;
  try {
    const response = await listEmployees(props.personnelType);
    if (isOutsourced.value) {
      const projectRows = await listProjects();
      if (projectRows.code === 0) projects.value = projectRows.data;
    }
    if (response.code !== 0) {
      ElMessage.error(response.message);
      return;
    }
    rows.value = response.data;
    const fieldRows = await listFlexFields(
      isOutsourced.value ? "employee_outsourced" : "employee_internal",
    );
    if (fieldRows.code === 0) flexFields.value = fieldRows.data;
    await loadBindings();
  } finally {
    loading.value = false;
  }
}

function open(row?: EmployeeOption) {
  Object.assign(
    form,
    row
      ? {
          ...row,
          project_id: row.project_id || "",
          bank_name: row.bank_name || "",
          account_no_masked: row.account_no_masked || "",
          flex_form: { ...(row.flex_form || {}) },
        }
      : {
          org_id: "",
          project_id: "",
          id: "",
          employee_no: "",
          full_name: "",
          employment_status_code: "active",
          hire_date: new Date().toISOString().slice(0, 10),
          bank_name: "",
          account_no_masked: "",
          flex_form: {},
        },
  );
  visible.value = true;
}

async function submit() {
  const response = await saveEmployee({
    ...form,
    personnel_type_code: props.personnelType,
    project_id: isOutsourced.value ? form.project_id || null : null,
    hire_date: form.hire_date || null,
    id: form.id || undefined,
    bank_name: form.bank_name || null,
    account_no_masked: form.account_no_masked || null,
    flex_form: form.flex_form,
  });
  if (response.code !== 0) {
    ElMessage.error(response.message);
    return;
  }
  visible.value = false;
  await load();
}

onMounted(load);
const loading = ref(false);
const tableColumns0 = computed<TableColumnList>(() => [
  {
    prop: "employee_no",
    label: isOutsourced.value ? "人员编号" : "员工编号",
    width: "140",
  },
  ...(isOutsourced.value
    ? [{ label: "所属项目", slot: "projectName", minWidth: 140 }]
    : []),
  { prop: "full_name", label: "姓名", width: "120" },
  { label: "状态", width: "90", slot: "cell0_2" },
  { label: "入职日期", width: "120", slot: "cell0_3" },
  { prop: "bank_name", label: "开户行" },
  { prop: "account_no_masked", label: "银行卡（脱敏）" },
  ...flexFields.value
    .filter((field) => field.is_active)
    .map((field) => ({
      label: field.field_name,
      minWidth: 120,
      formatter: (row: EmployeeOption) =>
        flexDisplay(row.flex_form?.[field.field_key], field.value_type_code),
    })),
  ...(!isOutsourced.value && canReadBindings.value
    ? [{ label: "登录账号", slot: "loginAccount", minWidth: 150 }]
    : []),
  {
    label: "操作",
    width: !isOutsourced.value && canBindAccounts.value ? "260" : "90",
    slot: "cell0_6",
  },
]);

watchFormOrganization(
  () => form.org_id,
  () => {
    form.project_id = "";
  },
  { flush: "sync" },
);
</script>

<template>
  <section class="sample-page">
    <BusinessTable
      :data="rows"
      :loading="loading"
      :columns="tableColumns0"
      delete-resource="employees"
      :title="isOutsourced ? '外包项目人员' : '内部员工'"
      @refresh="load"
    >
      <template #buttons
        ><el-button
          type="primary"
          @click="open()"
          :icon="useRenderIcon('ri/add-line')"
          >{{ isOutsourced ? "新增项目人员" : "新增员工" }}</el-button
        ></template
      >
      <template #projectName="{ row }">{{
        projects.find((item) => item.id === row.project_id)?.project_name || "—"
      }}</template>
      <template #cell0_2="{ row }"
        ><el-tag
          :type="row.employment_status_code === 'resigned' ? 'info' : 'success'"
          effect="plain"
          >{{
            row.employment_end_on
              ? `${row.employment_end_on} 调出`
              : row.employment_status_code === "resigned"
                ? "离职"
                : "在职"
          }}</el-tag
        ></template
      >
      <template #cell0_3="{ row }">{{ row.hire_date || "待补充" }}</template>
      <template #loginAccount="{ row }">
        <span v-if="bindingFor(row.id)"
          >{{ bindingFor(row.id)?.account_name
          }}{{ bindingFor(row.id)?.is_active ? "" : "（不可用）" }}</span
        >
        <span v-else class="text-gray-400">未关联</span>
      </template>
      <template #cell0_6="{ row }"
        ><el-button
          v-if="
            !isOutsourced &&
            row.employment_status_code === 'active' &&
            !row.employment_end_on
          "
          link
          type="primary"
          @click="openTransfer(row)"
          >组织调动</el-button
        ><el-button link type="primary" @click="open(row as EmployeeOption)"
          >编辑</el-button
        ><template v-if="!isOutsourced && canBindAccounts">
          <el-button
            link
            type="primary"
            :disabled="bindingSaving"
            @click="openBinding(row)"
            >{{ bindingFor(row.id) ? "更换账号" : "关联账号" }}</el-button
          >
          <el-button
            v-if="bindingFor(row.id)"
            link
            type="danger"
            :disabled="bindingSaving"
            @click="removeBinding(row)"
            >解除关联</el-button
          >
        </template></template
      >
    </BusinessTable>
    <p class="mt-3 text-sm text-gray-500">
      {{
        isOutsourced
          ? "项目人员仅由所属组织代招聘、管理，不代表与所属组织存在劳动关系，不进入内部员工工资核算。"
          : "此处仅登记与所属组织存在内部劳动关系的员工。"
      }}银行卡只保存脱敏显示，不保存完整卡号。
    </p>
    <p
      v-if="!isOutsourced && canBindAccounts"
      class="mt-2 text-sm text-gray-500"
    >
      员工使用独立报销入口前，需要在此关联登录账号，并在角色权限中授予“员工提交本人报销”；不需要授予“访问快盒”管理权限。
    </p>
    <el-dialog
      v-model="transferVisible"
      title="组织调动"
      width="520px"
      :close-on-click-modal="!transferBusy"
    >
      <el-form label-width="110px" :disabled="transferBusy">
        <el-form-item label="员工"
          >{{ transferEmployee?.full_name }} ·
          {{ transferEmployee?.org_name }}</el-form-item
        >
        <el-form-item label="目标组织" required>
          <el-select
            v-model="transferForm.target_org_id"
            filterable
            @change="transferForm.social_plan_id = ''"
          >
            <el-option
              v-for="org in transferOrganizations"
              :key="org.id"
              :label="org.org_name"
              :value="org.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="生效月份" required>
          <el-date-picker
            v-model="transferForm.effective_on"
            type="month"
            value-format="YYYY-MM-01"
          />
        </el-form-item>
        <el-form-item label="缴费方案" required>
          <el-select v-model="transferForm.social_plan_id" filterable>
            <el-option
              v-for="plan in transferPlans.filter(
                (item) => item.org_id === transferForm.target_org_id,
              )"
              :key="plan.id"
              :label="plan.plan_name"
              :value="plan.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer
        ><el-button
          type="primary"
          :loading="transferBusy"
          :disabled="Object.values(transferForm).some((value) => !value)"
          @click="submitTransfer"
          >预览调动</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="bindingVisible"
      title="关联员工登录账号"
      width="560px"
      :close-on-click-modal="false"
      :show-close="!bindingSaving"
    >
      <el-form label-width="90px" :disabled="bindingSaving">
        <el-form-item label="员工"
          >{{ bindingEmployee?.full_name }} ·
          {{ bindingEmployee?.org_name }}</el-form-item
        >
        <el-form-item label="登录账号" required>
          <el-select
            v-model="bindingUserId"
            filterable
            remote
            :remote-method="searchAccounts"
            :loading="accountSearching"
            placeholder="输入账号姓名搜索"
            class="w-full"
          >
            <el-option
              v-for="item in accountOptions"
              :key="item.id"
              :value="item.id"
              :label="item.name + (item.org_name ? ' · ' + item.org_name : '')"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="
          selectedAccountBinding &&
          selectedAccountBinding.employee_id !== bindingEmployee?.id
        "
        :title="`该账号当前关联${selectedAccountBinding.employee_name}，保存后将改为关联${bindingEmployee?.full_name}，历史关联保留。`"
        type="warning"
        :closable="false"
      />
      <p class="mt-3 text-sm text-gray-500">
        一个账号同时只关联一名员工，一个员工同时只关联一个账号。这里不新建账号；请先在系统用户管理中创建员工账号。
      </p>
      <template #footer
        ><el-button :disabled="bindingSaving" @click="bindingVisible = false"
          >取消</el-button
        ><el-button
          type="primary"
          :disabled="!bindingUserId || accountSearching"
          :loading="bindingSaving"
          @click="saveBinding"
          >保存关联</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="visible"
      :title="isOutsourced ? '外包项目人员' : '内部员工'"
      width="520px"
    >
      <el-form label-width="90px"
        ><OrganizationField v-model="form.org_id" :disabled="!!form.id" />
        <el-form-item v-if="isOutsourced" label="所属项目" required
          ><el-select v-model="form.project_id" filterable
            ><el-option
              v-for="item in projects.filter(
                (item) => !form.org_id || item.org_id === form.org_id,
              )"
              :key="item.id"
              :label="item.project_name"
              :value="item.id" /></el-select
        ></el-form-item>
        <el-form-item label="编号"
          ><el-input v-model="form.employee_no"
        /></el-form-item>
        <el-form-item label="姓名"
          ><el-input v-model="form.full_name"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-select v-model="form.employment_status_code"
            ><el-option label="在职" value="active" /><el-option
              label="离职"
              value="resigned" /></el-select
        ></el-form-item>
        <el-form-item label="入职日期"
          ><el-date-picker
            v-model="form.hire_date"
            type="date"
            value-format="YYYY-MM-DD"
        /></el-form-item>
        <el-form-item label="开户行"
          ><el-input v-model="form.bank_name"
        /></el-form-item>
        <el-form-item label="脱敏账号"
          ><el-input
            v-model="form.account_no_masked"
            placeholder="例如 ****1234"
        /></el-form-item>
        <FlexFields
          v-model="form.flex_form"
          :form-key="isOutsourced ? 'employee_outsourced' : 'employee_internal'"
          @fields="flexFields = $event"
        />
      </el-form>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" @click="submit">保存</el-button></template
      >
    </el-dialog>
  </section>
</template>
