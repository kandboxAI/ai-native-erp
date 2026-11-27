<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import BusinessTable from "../components/BusinessTable.vue";
import OrganizationField from "../components/OrganizationField.vue";
import {
  useSampleApi,
  socialAmountLabels,
  type SocialAmountKey,
  type SocialBill,
  type SocialDetail,
  type CashAccount,
  type CashEntry,
} from "@plugins/sample_app/web/src/api/sample_app";
const api = useSampleApi();
const rows = ref<SocialBill[]>([]),
  loading = ref(false),
  busy = ref(false),
  month = ref<string | null>(null);
const filtered = computed(() =>
  rows.value.filter(
    (r) => !month.value || r.period_month.slice(0, 7) === month.value,
  ),
);
const generating = ref(false),
  detailVisible = ref(false),
  paying = ref(false);
const generation = reactive({
  org_id: "",
  period_month: new Date().toISOString().slice(0, 7),
});
const detail = ref<SocialDetail | null>(null);
const target = ref<SocialBill | null>(null),
  paymentKind = ref<"social" | "payroll">("social");
const accounts = ref<CashAccount[]>([]),
  entries = ref<CashEntry[]>([]);
const payment = reactive({
  account_id: "",
  paid_on: new Date().toISOString().slice(0, 10),
  cash_entry_id: "",
  mode: "new",
});
const amountKeys = Object.keys(socialAmountLabels) as SocialAmountKey[];
const money = (value: unknown) =>
  Number(value || 0).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const expected = computed(() =>
  Number(
    paymentKind.value === "social"
      ? target.value?.total_amount
      : target.value?.payroll_net_amount,
  ),
);
const candidates = computed(() =>
  entries.value.filter(
    (e) =>
      e.org_id === target.value?.org_id &&
      e.direction_code === "expense" &&
      !e.source_type_code &&
      !e.source_id &&
      Number(e.amount).toFixed(2) === expected.value.toFixed(2),
  ),
);
watch(
  () => payment.cash_entry_id,
  (id) => {
    const e = candidates.value.find((e) => e.id === id);
    if (e) {
      payment.account_id = e.account_id;
      payment.paid_on = e.occurred_on;
    }
  },
);
watch(
  () => payment.mode,
  () => {
    payment.cash_entry_id = "";
    payment.account_id = "";
  },
);
const columns: TableColumnList = [
  {
    prop: "period_month",
    label: "费用所属月份",
    width: 130,
    formatter: (r) => r.period_month.slice(0, 7),
  },
  {
    prop: "status_code",
    label: "缴费状态",
    width: 115,
    formatter: (r) =>
      r.is_paid
        ? "已缴费"
        : r.status_code === "confirmed"
          ? "已确认待缴"
          : r.status_code === "draft"
            ? "待核对"
            : "未建缴费单",
  },
  { prop: "employer_amount", label: "单位承担" },
  { prop: "employee_amount", label: "个人承担" },
  { prop: "paid_amount", label: "实际已缴" },
  { prop: "pending_recovery_amount", label: "个人待扣回" },
  { prop: "labor_cost_amount", label: "当月人工成本", minWidth: 145 },
  {
    prop: "payroll_paid",
    label: "工资支付",
    formatter: (r) =>
      r.payroll_paid
        ? "已实付"
        : r.payroll_status_code === "closed"
          ? "待实付"
          : r.has_payroll
            ? "未封账"
            : "未核算",
  },
  { label: "操作", slot: "actions", width: 230 },
];
const lineColumns: TableColumnList = [
  { prop: "full_name", label: "员工", fixed: "left", width: 110 },
  { prop: "social_base_snapshot", label: "社保基数快照", width: 135 },
  { prop: "housing_base_snapshot", label: "公积金基数快照", width: 150 },
  ...amountKeys.map((key) => ({
    prop: key,
    label: socialAmountLabels[key],
    slot: key,
    width: 160,
  })),
];
function summary(data: SocialBill[]) {
  const sum = (key: keyof SocialBill) =>
    data.reduce((v, row) => v + Number(row[key] || 0), 0);
  return `单位承担 ${money(sum("employer_amount"))} 元，个人承担 ${money(sum("employee_amount"))} 元，已缴 ${money(sum("paid_amount"))} 元，个人待扣回 ${money(sum("pending_recovery_amount"))} 元`;
}
async function load() {
  loading.value = true;
  try {
    const r = await api.listSocialBills();
    if (r.code !== 0) throw Error(r.message);
    rows.value = r.data;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}
async function generate() {
  if (busy.value) return;
  if (!generation.org_id || !generation.period_month) {
    ElMessage.warning("请选择公司和费用所属月份");
    return;
  }
  busy.value = true;
  try {
    const r = await api.generateSocialBill({ ...generation });
    if (r.code !== 0) throw Error(r.message);
    generating.value = false;
    if (r.data.warnings?.length) ElMessage.warning(r.data.warnings.join("；"));
    await load();
    await openDetail(r.data.id);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "生成失败");
  } finally {
    busy.value = false;
  }
}
async function openDetail(id: string) {
  try {
    const r = await api.getSocialBill(id);
    if (r.code !== 0) throw Error(r.message);
    for (const line of r.data.lines)
      for (const key of amountKeys) line[key] = Number(line[key]);
    detail.value = r.data;
    detailVisible.value = true;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  }
}
async function saveDetail(confirm = false) {
  if (busy.value || !detail.value) return;
  const current = detail.value;
  if (confirm) {
    try {
      await ElMessageBox.confirm(
        "确认后金额将用于当月工资和成本核算，不能再修改。",
        "确认缴费单",
      );
    } catch {
      return;
    }
  }
  busy.value = true;
  try {
    const saved = await api.updateSocialBill(current.id, current.lines);
    if (saved.code !== 0) throw Error(saved.message);
    if (confirm) {
      const r = await api.confirmSocialBill(current.id);
      if (r.code !== 0) throw Error(r.message);
      detailVisible.value = false;
      ElMessage.success("已确认；若当月已有草稿工资，请重新核算");
    } else ElMessage.success("已保存核对金额");
    await load();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    busy.value = false;
  }
}
async function openPayment(row: SocialBill, kind: "social" | "payroll") {
  if (busy.value) return;
  busy.value = true;
  try {
    const r = await api.getCashLedger();
    if (r.code !== 0) throw Error(r.message);
    accounts.value = r.data.accounts;
    entries.value = r.data.entries;
    target.value = { ...row };
    paymentKind.value = kind;
    Object.assign(payment, {
      mode: "new",
      cash_entry_id: "",
      account_id: "",
      paid_on: new Date().toISOString().slice(0, 10),
    });
    paying.value = true;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载账户失败");
  } finally {
    busy.value = false;
  }
}
async function pay() {
  if (busy.value || !target.value) return;
  if (
    !payment.account_id ||
    !payment.paid_on ||
    (payment.mode === "existing" && !payment.cash_entry_id)
  ) {
    ElMessage.warning("请完整填写付款信息");
    return;
  }
  busy.value = true;
  try {
    const data = {
      org_id: target.value.org_id,
      account_id: payment.account_id,
      paid_on: payment.paid_on,
      cash_entry_id: payment.mode === "existing" ? payment.cash_entry_id : null,
    };
    const r =
      paymentKind.value === "social"
        ? await api.paySocialBill(target.value.bill_id!, data)
        : await api.payPayroll({
            ...data,
            period_month: target.value.period_month.slice(0, 7),
          });
    if (r.code !== 0) throw Error(r.message);
    paying.value = false;
    ElMessage.success("已登记实际付款");
    await load();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "付款登记失败");
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="sample-page">
    <BusinessTable
      delete-resource="social-bills"
      title="社保与工资支付"
      :data="filtered"
      :columns="columns"
      :loading="loading"
      @refresh="load"
      @reset="month = null"
    >
      <template #filters
        ><el-form-item label="费用账期："
          ><el-date-picker
            v-model="month"
            type="month"
            value-format="YYYY-MM"
            placeholder="全部月份"
            clearable /></el-form-item
      ></template>
      <template #summary="{ rows: matched }">{{ summary(matched) }}</template>
      <template #buttons
        ><el-button type="primary" @click="generating = true"
          >生成月度缴费单</el-button
        ></template
      >
      <template #actions="{ row }">
        <el-button
          v-if="row.bill_id"
          link
          type="primary"
          :disabled="busy"
          @click="openDetail(row.bill_id)"
          >{{
            row.status_code === "draft" ? "核对缴费单" : "查看明细"
          }}</el-button
        >
        <el-button
          v-if="row.status_code === 'confirmed' && !row.is_paid"
          link
          type="primary"
          :disabled="busy"
          @click="openPayment(row, 'social')"
          >登记缴费</el-button
        >
        <el-button
          v-if="row.payroll_status_code === 'closed' && !row.payroll_paid"
          link
          type="primary"
          :disabled="busy"
          @click="openPayment(row, 'payroll')"
          >工资实付</el-button
        >
      </template>
    </BusinessTable>
    <el-alert
      title="人工成本按费用所属月份统计：应发工资＋单位缴费，个人部分不重复计成本。未确认缴费单时沿用工资预估；工资未核算时仅显示已确认单位缴费成本。工资实付登记采用整批一次支付，个人扣回据此确认。"
      type="info"
      :closable="false"
      class="mt-4"
    />
    <el-dialog
      v-model="generating"
      title="生成月度缴费单"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form label-width="115px"
        ><OrganizationField v-model="generation.org_id" /><el-form-item
          label="费用所属月份"
          ><el-date-picker
            v-model="generation.period_month"
            type="month"
            value-format="YYYY-MM" /></el-form-item
      ></el-form>
      <template #footer
        ><el-button @click="generating = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="generate"
          >生成</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="detailVisible"
      :title="`${detail?.period_month.slice(0, 7)} 缴费明细`"
      width="92%"
      :close-on-click-modal="false"
    >
      <template v-if="detail">
        <el-alert
          title="按缴费明细核对单位及个人金额；基数和比例保存生成时快照。金额为零的人员可将各项缴费设为零。"
          type="info"
          :closable="false"
          class="mb-4"
        />
        <BusinessTable
          :organization-filter-visible="false"
          title="参保人员"
          :data="detail.lines"
          :columns="lineColumns"
          :searchable="false"
          @refresh="openDetail(detail!.id)"
        >
          <template v-for="key in amountKeys" :key="key" #[key]="{ row }"
            ><el-input-number
              v-if="detail.status_code === 'draft'"
              v-model="row[key]"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 130px"
            /><span v-else>{{ money(row[key]) }}</span></template
          >
        </BusinessTable>
      </template>
      <template #footer
        ><el-button @click="detailVisible = false">关闭</el-button
        ><template v-if="detail?.status_code === 'draft'"
          ><el-button :loading="busy" @click="saveDetail()"
            >保存核对金额</el-button
          ><el-button type="primary" :loading="busy" @click="saveDetail(true)"
            >保存并确认</el-button
          ></template
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="paying"
      :title="
        paymentKind === 'social' ? '登记社保公积金缴费' : '登记工资整批实付'
      "
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form label-width="110px">
        <el-form-item label="所属组织">{{ target?.org_name }}</el-form-item
        ><el-form-item label="费用月份">{{
          target?.period_month.slice(0, 7)
        }}</el-form-item>
        <el-form-item label="实际付款金额"
          >{{ money(expected) }} 元</el-form-item
        >
        <el-form-item label="流水方式"
          ><el-radio-group v-model="payment.mode"
            ><el-radio value="new">新增实际流水</el-radio
            ><el-radio value="existing">关联已有流水</el-radio></el-radio-group
          ></el-form-item
        >
        <el-form-item v-if="payment.mode === 'existing'" label="已有支出流水"
          ><el-select
            v-model="payment.cash_entry_id"
            filterable
            placeholder="同公司、同金额、未关联业务的支出"
            style="width: 100%"
            ><el-option
              v-for="e in candidates"
              :key="e.id"
              :value="e.id"
              :label="`${e.occurred_on} ${e.account_name} ${e.summary || ''} ${money(e.amount)}`" /></el-select
        ></el-form-item>
        <el-form-item label="付款账户"
          ><el-select
            v-model="payment.account_id"
            :disabled="payment.mode === 'existing'"
            ><el-option
              v-for="a in accounts.filter((a) => a.org_id === target?.org_id)"
              :key="a.id"
              :label="a.account_name"
              :value="a.id" /></el-select
        ></el-form-item>
        <el-form-item label="实际付款日期"
          ><el-date-picker
            v-model="payment.paid_on"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="payment.mode === 'existing'"
        /></el-form-item>
        <el-alert
          title="按实际日期记录完整支出，成本仍归费用所属月份；已导入银行流水时请选择关联，避免重复记账。"
          type="info"
          :closable="false"
        />
      </el-form>
      <template #footer
        ><el-button @click="paying = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="pay"
          >确认登记</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>
