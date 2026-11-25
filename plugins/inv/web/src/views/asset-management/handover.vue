<script setup lang="ts">
import { assetLocationOptions } from "../../utils/assetLocationAliases";
import { formatQuantity } from "@/utils/quantity";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  createAssetHandover,
  getAssetHandover,
  listAssetHandovers,
  listMyAssetHandovers,
  receiveAssetHandoverLine,
  rejectAssetHandoverLine,
  resubmitAssetHandoverLine,
  submitAssetHandover,
  updateAssetHandover,
  withdrawAssetHandover,
  voidAssetHandover,
  type AssetHandover,
} from "@plugins/inv/web/src/api/invAssetHandover";
import {
  getAssetOptions,
  listAssetLedger,
  type AssetLedger,
  type AssetOptions,
} from "@plugins/inv/web/src/api/invAssetManagement";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const voiding = ref(false);
const rows = ref<AssetHandover[]>([]);
const total = ref(0);
const detailVisible = ref(false);
const createVisible = ref(false);
const current = ref<AssetHandover | null>(null);
const options = ref<AssetOptions | null>(null);
const availableAssets = ref<AssetLedger[]>([]);
const createForm = reactive({
  transferor_user_id: "",
  asset_key: "",
  disposition_code: "return_logistics" as
    "transfer_teacher" | "return_logistics",
  to_location_id: "",
  to_department_id: "",
  to_custodian_user_id: "",
  quantity: 1,
  remark: "",
});
const query = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  status_code: "",
});
const canList = computed(() => hasPerms("asset_handover:list"));
const canMine = computed(() => hasPerms("asset_handover:mine"));
const canCreate = computed(() => hasPerms("asset_handover:create"));
const canManage = computed(() => hasPerms("asset_handover:manage"));
const canVoid = computed(
  () =>
    canManage.value &&
    current.value &&
    current.value.source_type_code === "manual" &&
    !current.value.source_id &&
    ["draft", "awaiting_receipt"].includes(current.value.status_code) &&
    current.value.received_count === 0,
);
const transferorOptions = computed(() => {
  const result = new Map<
    string,
    { id: string; display_name: string; count: number }
  >();
  for (const asset of availableAssets.value) {
    if (!asset.custodian_user_id || !asset.custodian_name) continue;
    const current = result.get(asset.custodian_user_id);
    if (current) current.count += 1;
    else
      result.set(asset.custodian_user_id, {
        id: asset.custodian_user_id,
        display_name: asset.custodian_name,
        count: 1,
      });
  }
  return [...result.values()].sort((left, right) =>
    left.display_name.localeCompare(right.display_name, "zh-CN"),
  );
});
const selectedAsset = computed(() =>
  availableAssets.value.find((item) => assetKey(item) === createForm.asset_key),
);
const transferorAssets = computed(() =>
  availableAssets.value.filter(
    (item) => item.custodian_user_id === createForm.transferor_user_id,
  ),
);

const statusLabels: Record<string, string> = {
  draft: "草稿",
  awaiting_receipt: "待接收",
  completed: "已完成",
  voided: "已作废",
};
const lineStatusLabels: Record<string, string> = {
  pending: "待接收",
  rejected: "已拒收",
  received: "已接收",
};

function lineStatusLabel(line: AssetHandover["lines"][number]) {
  if (current.value?.status_code === "voided") return "已作废";
  if (line.status_code === "pending" && line.rejection_reason)
    return "待重新确认";
  return lineStatusLabels[line.status_code] || line.status_code;
}
const sourceLabels: Record<string, string> = {
  manual: "人工发起",
  teacher_offboarding: "教师离职",
};
const unitLabels: Record<string, string> = {
  bottle: "瓶",
  box: "箱",
  pack: "包",
  piece: "件",
  set: "套",
  sheet: "张",
  unit: "件",
};

function rejectedCount(value: unknown) {
  const item = value as AssetHandover;
  return (
    item.rejected_count ??
    item.lines.filter((line) => line.status_code === "rejected").length
  );
}

function pendingCount(value: unknown) {
  const item = value as AssetHandover;
  return (
    item.pending_count ??
    item.lines.filter((line) => line.status_code === "pending").length
  );
}

function displayStatusLabel(value: unknown) {
  const item = value as AssetHandover;
  if (item.status_code === "awaiting_receipt" && rejectedCount(item) > 0)
    return "存在拒收";
  if (
    item.status_code === "awaiting_receipt" &&
    item.lines.some(
      (line) => line.status_code === "pending" && line.rejection_reason,
    )
  )
    return "待重新确认";
  return statusLabels[item.status_code] || item.status_code;
}

function unitLabel(code: string) {
  return unitLabels[code] || code;
}

function departmentOptionLabel(item: AssetOptions["departments"][number]) {
  return `${item.org_name} / ${item.department_name}`;
}

function assetKey(asset: AssetLedger) {
  return `${asset.management_mode}:${asset.id}`;
}

function resetCreateForm() {
  Object.assign(createForm, {
    transferor_user_id: "",
    asset_key: "",
    disposition_code: "return_logistics",
    to_location_id: "",
    to_department_id: "",
    to_custodian_user_id: "",
    quantity: 1,
    remark: "【测试】人工资产交接",
  });
}

async function openCreate() {
  resetCreateForm();
  options.value = null;
  const response = await listAssetLedger({
    page: 1,
    page_size: 100,
    registration_status_code: "confirmed",
  });
  availableAssets.value = response.data.items.filter((item) =>
    ["in_use", "idle"].includes(item.status_code),
  );
  createVisible.value = true;
}

function changeTransferor() {
  createForm.asset_key = "";
  createForm.to_location_id = "";
  createForm.to_department_id = "";
  createForm.to_custodian_user_id = "";
  createForm.quantity = 1;
  options.value = null;
}

async function changeAsset() {
  const asset = selectedAsset.value;
  if (!asset) return;
  options.value = (await getAssetOptions(asset.org_id)).data;
  createForm.to_location_id = asset.location_id;
  createForm.to_department_id = asset.department_id || "";
  createForm.quantity = asset.management_mode === "individual" ? 1 : 1;
}

async function createDraft() {
  const asset = selectedAsset.value;
  const transferor = transferorOptions.value.find(
    (item) => item.id === createForm.transferor_user_id,
  );
  if (!transferor || !asset) {
    ElMessage.warning("请选择交出人和交接资产");
    return;
  }
  if (!createForm.to_location_id || !createForm.to_department_id) {
    ElMessage.warning("请选择接收地点和责任部门");
    return;
  }
  if (
    createForm.disposition_code === "transfer_teacher" &&
    !createForm.to_custodian_user_id
  ) {
    ElMessage.warning("移交接任教师时必须选择接收人");
    return;
  }
  saving.value = true;
  try {
    const response = await createAssetHandover({
      org_id: asset.org_id,
      source_type_code: "manual",
      transferor_user_id: transferor.id,
      transferor_name_snapshot: transferor.display_name,
      remark: createForm.remark.trim() || null,
      lines: [
        {
          asset_register_id:
            asset.management_mode === "individual" ? asset.id : null,
          location_item_id: asset.management_mode === "batch" ? asset.id : null,
          quantity:
            asset.management_mode === "individual" ? 1 : createForm.quantity,
          disposition_code: createForm.disposition_code,
          to_location_id: createForm.to_location_id,
          to_department_id: createForm.to_department_id,
          to_custodian_user_id:
            createForm.disposition_code === "transfer_teacher"
              ? createForm.to_custodian_user_id
              : null,
        },
      ],
    });
    ElMessage.success("资产交接草稿已创建");
    createVisible.value = false;
    await load();
    await openDetail(response.data.id);
  } finally {
    saving.value = false;
  }
}

async function load() {
  loading.value = true;
  try {
    const response = await (
      canList.value ? listAssetHandovers : listMyAssetHandovers
    )({
      ...query,
      keyword: query.keyword || undefined,
      status_code: query.status_code || undefined,
    });
    rows.value = response.data.items;
    total.value = response.data.total;
  } finally {
    loading.value = false;
  }
}

async function openDetail(id: string) {
  const detail = (await getAssetHandover(id)).data;
  current.value = detail;
  if (canManage.value || canCreate.value) {
    options.value = (await getAssetOptions(detail.org_id)).data;
    if (detail.status_code === "draft") {
      const departmentIds = new Set(
        options.value.departments.map((item) => item.id),
      );
      const hasInvalidDepartment = detail.lines.some((line) => {
        if (departmentIds.has(line.to_department_id)) return false;
        line.to_department_id = "";
        return true;
      });
      if (hasInvalidDepartment)
        ElMessage.warning("原责任部门已失效，请重新选择有效部门后保存");
    }
  }
  detailVisible.value = true;
}

function linePayload(line: AssetHandover["lines"][number]) {
  return {
    asset_register_id: line.asset_register_id,
    location_item_id: line.location_item_id,
    quantity: line.quantity,
    disposition_code: line.disposition_code,
    to_location_id: line.to_location_id,
    to_department_id: line.to_department_id,
    to_custodian_user_id:
      line.disposition_code === "transfer_teacher"
        ? line.to_custodian_user_id
        : null,
  };
}

async function saveDraft() {
  if (!current.value) return false;
  const invalid = current.value.lines.some(
    (line) =>
      !line.to_location_id ||
      !line.to_department_id ||
      (line.disposition_code === "transfer_teacher" &&
        !line.to_custodian_user_id),
  );
  if (invalid) {
    ElMessage.warning("请完整填写每项资产的接收地点、责任部门和接收人");
    return false;
  }
  saving.value = true;
  try {
    current.value = (
      await updateAssetHandover(current.value.id, {
        expected_version: current.value.version_no,
        remark: current.value.remark,
        lines: current.value.lines.map(linePayload),
      })
    ).data;
    ElMessage.success("资产交接单已保存");
    await load();
    return true;
  } finally {
    saving.value = false;
  }
}

async function submit() {
  if (!current.value) return;
  if (!(await saveDraft())) return;
  if (!current.value) return;
  current.value = (
    await submitAssetHandover(current.value.id, current.value.version_no)
  ).data;
  ElMessage.success("交接单已提交，等待接收人确认");
  await load();
}

async function withdraw() {
  if (!current.value) return;
  try {
    await ElMessageBox.confirm(
      "确认撤回该资产交接单？撤回后交接单将恢复为草稿，可重新编辑并提交。",
      "撤回交接单",
      {
        confirmButtonClass: "app-button-warning",
        confirmButtonText: "确认撤回",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  current.value = (
    await withdrawAssetHandover(current.value.id, current.value.version_no)
  ).data;
  ElMessage.success("交接单已撤回");
  await load();
}

async function voidHandover() {
  if (!current.value || !canVoid.value || voiding.value) return;
  const target = current.value;
  voiding.value = true;
  try {
    const { value } = await ElMessageBox.prompt(
      `确认作废交接单 ${target.handover_no}？作废后停止接收并释放资产占用，原单据和明细保留。请填写作废原因。`,
      "作废资产交接单",
      {
        confirmButtonClass: "app-button-danger",
        type: "warning",
        confirmButtonText: "确认作废",
        cancelButtonText: "取消",
        inputValidator: (value) =>
          (Boolean(value?.trim()) && value.trim().length <= 1000) ||
          "请填写作废原因，最多 1000 字",
      },
    );
    const result = (
      await voidAssetHandover(target.id, target.version_no, value.trim())
    ).data;
    if (current.value?.id === target.id) current.value = result;
    ElMessage.success("交接单已作废，资产占用已释放");
    await load();
  } catch (error) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(getHttpErrorMessage(error, "作废交接单失败"));
    if (current.value?.id === target.id) {
      try {
        current.value = (await getAssetHandover(target.id)).data;
      } catch {
        /* 保留原详情，错误已提示 */
      }
    }
  } finally {
    voiding.value = false;
  }
}

async function receive(lineId: string) {
  if (!current.value) return;
  await ElMessageBox.confirm(
    "确认资产已经实际接收？确认后将更新资产责任关系。",
    "接收资产",
    { confirmButtonClass: "app-button-success" },
  );
  current.value = (
    await receiveAssetHandoverLine(current.value.id, lineId)
  ).data;
  ElMessage.success("资产已接收");
  await load();
}

async function reject(lineId: string) {
  if (!current.value) return;
  const { value } = await ElMessageBox.prompt("请填写拒收原因", "拒收资产", {
    confirmButtonClass: "app-button-warning",
    inputValidator: (value) => Boolean(value?.trim()) || "拒收原因不能为空",
  });
  current.value = (
    await rejectAssetHandoverLine(current.value.id, lineId, value)
  ).data;
  ElMessage.success("已记录拒收原因");
  await load();
}

async function resubmit(line: AssetHandover["lines"][number]) {
  if (!current.value) return;
  if (
    !line.to_location_id ||
    !line.to_department_id ||
    (line.disposition_code === "transfer_teacher" && !line.to_custodian_user_id)
  ) {
    ElMessage.warning("请完整填写接收地点、责任部门和接收人");
    return;
  }
  try {
    await ElMessageBox.confirm(
      "确认已处理拒收问题并重新发起接收？系统将通知新的接收人再次确认。",
      "重新发起接收",
      {
        confirmButtonClass: "app-button-warning",
        confirmButtonText: "确认重新发起",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  saving.value = true;
  try {
    current.value = (
      await resubmitAssetHandoverLine(current.value.id, line.id, {
        expected_version: current.value.version_no,
        quantity: line.quantity,
        disposition_code: line.disposition_code,
        to_location_id: line.to_location_id,
        to_department_id: line.to_department_id,
        to_custodian_user_id:
          line.disposition_code === "transfer_teacher"
            ? line.to_custodian_user_id
            : null,
      })
    ).data;
    ElMessage.success("已重新发起接收并通知接收人");
    await load();
  } catch (error) {
    await ElMessageBox.alert(
      getHttpErrorMessage(error, "重新发起接收失败，请稍后重试"),
      "重新发起失败",
      {
        confirmButtonText: "我知道了",
        type: "error",
      },
    );
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  if (canList.value || canMine.value) await load();
});

watch(
  () => route.query.id,
  async (id) => {
    if (typeof id !== "string") return;
    try {
      await openDetail(id);
    } catch (error) {
      ElMessage.error(getHttpErrorMessage(error, "资产交接详情加载失败"));
    }
  },
  { immediate: true },
);
function searchList() {
  query.page = 1;
  return load();
}

function resetList() {
  Object.assign(query, { keyword: "", status_code: "" });
  return searchList();
}
</script>

<template>
  <ReListPresentation>
    <main class="page list-page list-presentation-container">
      <section class="list-section" v-if="canList || canMine">
        <ReListHeading data-list-key="handover-0" />
        <section class="list-query-panel">
          <el-form :inline="true" class="list-filters" @submit.prevent>
            <el-form-item label="关键词">
              <el-input
                v-model="query.keyword"
                clearable
                placeholder="请输入单号、交出人或资产"
                @keyup.enter="searchList"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-select
                v-model="query.status_code"
                clearable
                placeholder="请选择状态"
              >
                <el-option
                  v-for="(label, value) in statusLabels"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <div class="list-query-actions">
                <el-button
                  data-list-query="search"
                  type="primary"
                  @click="searchList"
                  >查询</el-button
                >
                <el-button data-list-query="reset" @click="resetList"
                  >重置</el-button
                >
              </div>
            </el-form-item>
          </el-form>
          <ReListTable
            :list-heading="false"
            list-key="handover-0"
            :list-refresh="load"
            v-loading="loading"
            :data="rows"
            row-key="id"
          >
            <el-table-column
              prop="handover_no"
              label="交接单号"
              min-width="190"
            />
            <el-table-column
              prop="transferor_name_snapshot"
              label="交出人"
              min-width="120"
            />
            <el-table-column prop="source_type_code" label="来源" width="130">
              <template #default="{ row }">{{
                row.source_type_code === "teacher_offboarding"
                  ? "教师离职"
                  : "人工发起"
              }}</template>
            </el-table-column>
            <el-table-column label="办理进度" min-width="230">
              <template #default="{ row }">
                <el-space :size="6" wrap>
                  <el-tag size="small" type="success" effect="plain">
                    已接收 {{ row.received_count }}
                  </el-tag>
                  <el-tag
                    v-if="pendingCount(row)"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    待接收 {{ pendingCount(row) }}
                  </el-tag>
                  <el-tag
                    v-if="rejectedCount(row)"
                    size="small"
                    type="danger"
                    effect="plain"
                  >
                    已拒收 {{ rejectedCount(row) }}
                  </el-tag>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag
                  :type="
                    rejectedCount(row)
                      ? 'danger'
                      : row.status_code === 'completed'
                        ? 'success'
                        : row.status_code === 'awaiting_receipt'
                          ? 'warning'
                          : 'info'
                  "
                >
                  {{ displayStatusLabel(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }"
                ><el-button
                  data-action="primary"
                  link
                  type="primary"
                  @click="openDetail(row.id)"
                  >办理</el-button
                ></template
              >
            </el-table-column>

            <template #list-actions>
              <el-button
                data-list-action="create"
                v-if="canCreate"
                type="primary"
                @click="openCreate"
                >新建交接</el-button
              >
            </template>

            <template #list-pagination
              ><ReListPagination
                v-model:current-page="query.page"
                v-model:page-size="query.page_size"
                :total="total"
                @current-change="load"
            /></template>
          </ReListTable>
        </section>
      </section>

      <el-dialog v-model="createVisible" title="新建资产交接" width="680px">
        <el-form label-width="100px">
          <el-form-item label="交出人" required>
            <el-select
              v-model="createForm.transferor_user_id"
              filterable
              placeholder="选择当前资产保管人"
              style="width: 100%"
              @change="changeTransferor"
            >
              <el-option
                v-for="item in transferorOptions"
                :key="item.id"
                :label="`${item.display_name}（${item.count} 项可交接资产）`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="交接资产" required>
            <el-select
              v-model="createForm.asset_key"
              filterable
              placeholder="选择交出人当前保管的在用或闲置资产"
              style="width: 100%"
              @change="changeAsset"
            >
              <el-option
                v-for="item in transferorAssets"
                :key="assetKey(item)"
                :label="`${item.asset_no || '批量资产'} · ${item.item_name} · ${item.location_name}`"
                :value="assetKey(item)"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="selectedAsset?.management_mode === 'batch'"
            label="交接数量"
            required
          >
            <el-input-number
              v-model="createForm.quantity"
              :min="1"
              :max="Number(selectedAsset.quantity)"
              :precision="3"
            />
            <span class="quantity-tip"
              >当前 {{ selectedAsset.quantity }}
              {{ selectedAsset.unit_code }}</span
            >
          </el-form-item>
          <el-form-item label="交接去向" required>
            <el-radio-group v-model="createForm.disposition_code">
              <el-radio value="return_logistics">退回后勤</el-radio>
              <el-radio value="transfer_teacher">移交接任教师</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="接收地点" required>
            <el-select
              v-model="createForm.to_location_id"
              :disabled="!selectedAsset"
              filterable
              :placeholder="selectedAsset ? '请选择' : '请先选择交接资产'"
              style="width: 100%"
            >
              <el-option
                v-for="item in assetLocationOptions(
                  options?.locations || [],
                  createForm.to_location_id,
                )"
                :key="item.id"
                :label="item.location_name"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="责任部门" required>
            <el-select
              v-model="createForm.to_department_id"
              :disabled="!selectedAsset"
              filterable
              :placeholder="selectedAsset ? '请选择' : '请先选择交接资产'"
              style="width: 100%"
            >
              <el-option
                v-for="item in options?.departments || []"
                :key="item.id"
                :label="departmentOptionLabel(item)"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="createForm.disposition_code === 'transfer_teacher'"
            label="接收人"
            required
          >
            <el-select
              v-model="createForm.to_custodian_user_id"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="item in options?.users || []"
                :key="item.id"
                :label="item.display_name"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="备注">
            <el-input
              v-model="createForm.remark"
              type="textarea"
              maxlength="1000"
              show-word-limit
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button data-action="neutral" @click="createVisible = false"
            >取消</el-button
          >
          <el-button
            data-action="primary"
            type="primary"
            :loading="saving"
            @click="createDraft"
            >创建草稿</el-button
          >
        </template>
      </el-dialog>

      <el-drawer
        v-model="detailVisible"
        title="资产交接详情"
        size="min(920px, 92%)"
        class="handover-drawer"
      >
        <template v-if="current">
          <div class="detail-heading">
            <div>
              <h2>{{ current.handover_no }}</h2>
              <p>{{ sourceLabels[current.source_type_code] }}</p>
            </div>
            <el-tag
              :type="
                rejectedCount(current)
                  ? 'danger'
                  : current.status_code === 'completed'
                    ? 'success'
                    : current.status_code === 'awaiting_receipt'
                      ? 'warning'
                      : current.status_code === 'voided'
                        ? 'info'
                        : 'primary'
              "
              effect="light"
              size="large"
            >
              {{ displayStatusLabel(current) }}
            </el-tag>
          </div>
          <el-alert
            v-if="current.status_code === 'voided'"
            type="info"
            :closable="false"
            :title="'作废原因：' + (current.void_reason || '未记录')"
            :description="`作废时间：${current.voided_at ? new Date(current.voided_at).toLocaleString('zh-CN') : '未记录'}。资产占用已释放，原交接明细保留供查询。`"
          />
          <el-alert
            v-if="current.source_id"
            type="info"
            :closable="false"
            :title="
              current.status_code === 'completed'
                ? '全部资产已接收，交接记录仅供查看。'
                : current.status_code === 'voided'
                  ? '该资产交接单已作废，记录仅供查看。'
                  : current.status_code === 'awaiting_receipt'
                    ? '已提交，等待指定接收人或后勤确认；如有拒收，请处理后重新发起。'
                    : '该资产单由来源业务统一提交和撤回。请在本页设置交接去向并保存，再返回来源业务提交。'
            "
          />
          <el-button
            data-action="neutral"
            v-if="current.source_context"
            link
            type="primary"
            @click="router.push(current.source_context.path)"
          >
            返回{{ current.source_context.label }} ·
            {{ current.source_context.document_no }}
          </el-button>
          <el-descriptions :column="4" border class="summary-grid">
            <el-descriptions-item label="交出人">{{
              current.transferor_name_snapshot
            }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{
              sourceLabels[current.source_type_code]
            }}</el-descriptions-item>
            <el-descriptions-item label="已接收">
              {{ current.received_count }} 项
            </el-descriptions-item>
            <el-descriptions-item label="待接收/已拒收">
              {{ pendingCount(current) }}/{{ rejectedCount(current) }} 项
            </el-descriptions-item>
          </el-descriptions>
          <el-alert
            v-if="rejectedCount(current)"
            :title="
              '该交接单有 ' +
              rejectedCount(current) +
              ' 项资产被拒收，请核对原因并处理后重新发起接收。'
            "
            type="error"
            show-icon
            :closable="false"
            class="handover-exception"
          />
          <h3 class="section-title">交接备注</h3>
          <el-input
            v-model="current.remark"
            :disabled="!canManage || current.status_code !== 'draft'"
            type="textarea"
            placeholder="交接备注"
            class="remark"
          />
          <h3 class="section-title">交接资产</h3>
          <el-card
            v-for="line in current.lines"
            :key="line.id"
            shadow="never"
            class="asset-card"
          >
            <template #header>
              <div class="asset-card__header">
                <div>
                  <strong>{{ line.asset_name_snapshot }}</strong>
                  <span>{{ line.asset_no_snapshot || "批量资产" }}</span>
                </div>
                <el-space>
                  <el-tag type="info" effect="plain">
                    {{ formatQuantity(line.quantity) }}
                    {{ unitLabel(line.unit_code_snapshot) }}
                  </el-tag>
                  <el-tag
                    :type="
                      line.status_code === 'received'
                        ? 'success'
                        : line.status_code === 'rejected'
                          ? 'danger'
                          : 'warning'
                    "
                  >
                    {{ lineStatusLabel(line) }}
                  </el-tag>
                </el-space>
              </div>
            </template>

            <el-descriptions :column="2" border class="asset-origin">
              <el-descriptions-item label="规格型号">
                {{ line.specification_snapshot || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="原保管人">
                {{ line.from_custodian_name || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="原存放地点">
                {{ line.from_location_name }}
              </el-descriptions-item>
              <el-descriptions-item label="原责任部门">
                {{ line.from_department_name || "-" }}
              </el-descriptions-item>
            </el-descriptions>

            <el-form
              v-if="
                canManage &&
                (current.status_code === 'draft' ||
                  (current.status_code === 'awaiting_receipt' &&
                    line.status_code === 'rejected'))
              "
              label-position="top"
              class="target-form"
            >
              <el-form-item
                v-if="line.location_item_id"
                label="交接数量"
                required
              >
                <el-input-number
                  :model-value="Number(line.quantity)"
                  :min="0.001"
                  :precision="3"
                  style="width: 100%"
                  @update:model-value="
                    (value) => (line.quantity = String(value))
                  "
                />
              </el-form-item>
              <el-form-item label="交接去向" required>
                <el-select v-model="line.disposition_code" style="width: 100%">
                  <el-option label="移交接任教师" value="transfer_teacher" />
                  <el-option label="退回后勤" value="return_logistics" />
                </el-select>
              </el-form-item>
              <el-form-item label="接收地点" required>
                <el-select
                  v-model="line.to_location_id"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in assetLocationOptions(
                      options?.locations || [],
                      line.to_location_id,
                    )"
                    :key="item.id"
                    :label="item.location_name"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="责任部门" required>
                <el-select
                  v-model="line.to_department_id"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in options?.departments || []"
                    :key="item.id"
                    :label="departmentOptionLabel(item)"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item
                v-if="line.disposition_code === 'transfer_teacher'"
                label="接收人"
                required
              >
                <el-select
                  v-model="line.to_custodian_user_id"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in options?.users || []"
                    :key="item.id"
                    :label="item.display_name"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
            </el-form>

            <el-descriptions v-else :column="2" border class="asset-target">
              <el-descriptions-item label="交接去向">
                {{
                  line.disposition_code === "transfer_teacher"
                    ? "移交接任教师"
                    : "退回后勤"
                }}
              </el-descriptions-item>
              <el-descriptions-item label="接收人">
                {{ line.to_custodian_name || "后勤科确认" }}
              </el-descriptions-item>
              <el-descriptions-item label="接收地点">
                {{ line.to_location_name }}
              </el-descriptions-item>
              <el-descriptions-item label="责任部门">
                {{ line.to_department_name }}
              </el-descriptions-item>
            </el-descriptions>

            <div
              v-if="
                canManage &&
                current.status_code === 'awaiting_receipt' &&
                line.status_code === 'rejected'
              "
              class="reject-processing"
            >
              <el-alert
                :title="'拒收原因：' + (line.rejection_reason || '未填写')"
                description="请核实资产、数量及接收信息；修正后重新发起，由接收人再次确认。"
                type="error"
                show-icon
                :closable="false"
              />
              <el-button
                data-action="edit"
                type="primary"
                :loading="saving"
                @click="resubmit(line)"
              >
                修正并重新发起
              </el-button>
            </div>
            <div
              v-else-if="
                current.status_code === 'awaiting_receipt' && line.can_receive
              "
              class="receive-actions"
            >
              <el-button
                data-action="success"
                type="success"
                @click="receive(line.id)"
              >
                {{ line.rejection_reason ? "确认重新接收" : "确认接收" }}
              </el-button>
              <el-button
                data-action="warning"
                v-if="line.status_code === 'pending'"
                type="danger"
                plain
                @click="reject(line.id)"
              >
                拒收
              </el-button>
            </div>
            <el-alert
              v-else-if="
                line.rejection_reason && line.status_code === 'rejected'
              "
              :title="'拒收原因：' + line.rejection_reason"
              :description="
                line.status_code === 'rejected' &&
                current.status_code !== 'voided'
                  ? '等待后勤处理后重新发起接收。'
                  : undefined
              "
              type="error"
              show-icon
              :closable="false"
              class="line-result"
            />
            <details
              v-if="line.rejection_reason && line.status_code !== 'rejected'"
              :key="`${line.id}-${line.status_code}`"
              class="line-result rejection-history"
            >
              <summary>查看拒收记录</summary>
              <p>历史拒收原因：{{ line.rejection_reason }}</p>
            </details>
            <p v-if="line.confirmed_by_name" class="line-result">
              接收确认人：{{ line.confirmed_by_name }}
            </p>
          </el-card>
        </template>
        <template #footer>
          <el-space v-if="current" class="drawer-footer">
            <el-button
              data-action="danger"
              v-if="canVoid"
              type="danger"
              plain
              :loading="voiding"
              :disabled="saving"
              @click="voidHandover"
              >作废交接单</el-button
            >
            <el-button
              data-action="warning"
              v-if="
                canManage &&
                !current.source_id &&
                current.status_code === 'awaiting_receipt' &&
                current.received_count === 0
              "
              @click="withdraw"
              >{{ rejectedCount(current) ? "撤回整单" : "撤回" }}</el-button
            >
            <el-button
              data-action="primary"
              v-if="canManage && current.status_code === 'draft'"
              :loading="saving"
              @click="saveDraft"
              >保存</el-button
            >
            <el-button
              data-action="primary"
              v-if="
                canManage &&
                !current.source_id &&
                current.status_code === 'draft'
              "
              :loading="saving"
              type="primary"
              @click="submit"
              >提交交接</el-button
            >
          </el-space>
        </template>
      </el-drawer>
    </main>
  </ReListPresentation>
</template>

<style scoped>
.page {
  padding: 16px;
}

.header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.header h2 {
  margin: 0;
}

.header p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
}

.remark {
  margin-bottom: 20px;
}

.handover-exception {
  margin-top: 16px;
}

.detail-heading,
.asset-card__header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.detail-heading {
  margin-bottom: 16px;
}

.detail-heading h2 {
  margin: 0;
  font-size: 22px;
}

.detail-heading p,
.asset-card__header span {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
}

.asset-card__header > div:first-child {
  display: flex;
  flex-direction: column;
}

.section-title {
  margin: 20px 0 10px;
  font-size: 16px;
}

.asset-card + .asset-card {
  margin-top: 16px;
}

.asset-origin,
.asset-target {
  margin-bottom: 16px;
}

.target-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.receive-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.reject-processing {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.reject-processing .el-alert {
  flex: 1;
}

.line-result {
  margin: 12px 0 0;
  color: var(--el-text-color-secondary);
}
.rejection-history summary {
  cursor: pointer;
}
.rejection-history p {
  margin: 8px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  width: 100%;
  padding-right: 76px;
}

.quantity-tip {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

@media (width <= 720px) {
  .summary-grid,
  .asset-origin,
  .asset-target {
    --el-descriptions-table-border: 1px solid var(--el-border-color-lighter);
  }

  .target-form {
    grid-template-columns: 1fr;
  }

  .drawer-footer {
    padding-right: 0;
  }
}
</style>
