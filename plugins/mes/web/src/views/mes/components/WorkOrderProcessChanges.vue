<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { actionMessage } from "@/utils/message";
import { notifyTodosChanged } from "@/utils/todoRefresh";
import {
  actMesProcessChange,
  getMesProcessChanges,
  submitMesProcessChange,
  type MesProcessChangeOverview,
  type MesProcessDisposition,
} from "../../../api/mes";
import { archiveOptions } from "../../../api/mesArchives";
import RemoteSelect from "./RemoteSelect.vue";

const props = defineProps<{ orderId: string }>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ changed: []; repair: [id: string] }>();
const overview = ref<MesProcessChangeOverview>();
const busy = ref(false);
const creating = ref(false);
const operationId = ref("");
const processId = ref("");
const equipmentId = ref("");
const disposition = ref<MesProcessDisposition>("keep");
const reason = ref("");
const selected = computed(() => overview.value?.operations.find(row => row.id === operationId.value));
const canManage = computed(() => hasPerms("mes:work_order:manage"));
const canInspect = computed(() => hasPerms("mes:quality:inspect"));
const canSubmit = computed(() => canManage.value && overview.value &&
  !overview.value.is_pending && ["released", "in_progress", "paused"].includes(overview.value.status_code));
const showForm = computed(() => canSubmit.value &&
  (creating.value || overview.value?.changes.length === 0));
const statuses: Record<string, string> = {
  submitted: "审批中", rejected: "已驳回", cancelled: "已撤回", applied: "已生效",
};
const approvedStatuses: Record<MesProcessDisposition, string> = {
  keep: "已通过 · 待生效", reinspect: "已通过 · 待复检", rework: "已通过 · 待返工完成",
};
const dispositions = { keep: "沿用", reinspect: "复检", rework: "返工" };

async function run(work: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  try {
    await work();
  } catch (cause: any) {
    if (cause !== "cancel" && cause !== "close") actionMessage(cause?.message || "工艺变更操作失败");
  } finally {
    busy.value = false;
  }
}

async function load() {
  overview.value = (await getMesProcessChanges(props.orderId)).data;
}

function resetDraft() {
  creating.value = false;
  operationId.value = processId.value = equipmentId.value = reason.value = "";
  disposition.value = "keep";
}

async function open() {
  overview.value = undefined;
  resetDraft();
  await run(load);
}

async function refresh(message: string) {
  resetDraft();
  actionMessage(message, "success");
  notifyTodosChanged();
  emit("changed");
  await load();
}

async function submit() {
  if (!overview.value || !operationId.value || !processId.value || !reason.value.trim()) {
    throw Error("请选择工序和新工艺，并填写变更原因");
  }
  await ElMessageBox.confirm("提交后原工单暂停生产，审批和处置完成后恢复。确认提交？", "工艺变更", { type: "warning" });
  await submitMesProcessChange(props.orderId, {
    version_no: overview.value.version_no, operation_id: operationId.value,
    new_process_id: processId.value, new_equipment_id: equipmentId.value || undefined,
    disposition_code: disposition.value, reason: reason.value.trim(),
  });
  await refresh("工艺变更已提交审批");
}

async function act(changeId: string, action: Parameters<typeof actMesProcessChange>[2]) {
  let note = "";
  if (["pass", "rework", "cancel"].includes(action)) {
    const result = await ElMessageBox.prompt(action === "cancel" ? "填写取消原因" : "填写复检记录或检测依据",
      action === "cancel" ? "取消工艺变更" : "确认复检结果", {
        inputValidator: value => !!value?.trim() && value.trim().length <= 1000 || "请填写 1～1000 字",
      });
    note = result.value.trim();
  } else {
    await ElMessageBox.confirm(action === "arrange" ? "创建返修工单安排已加工件返工？" : "确认处置完成并使本次变更生效？",
      "确认工艺变更", { type: "warning" });
  }
  await actMesProcessChange(props.orderId, changeId, action, note);
  await refresh(action === "arrange" ? "已生成返修工单" : action === "rework" ? "复检已转返工" :
    action === "cancel" ? "工艺变更已取消" : "工艺变更已生效");
}
</script>

<template>
  <el-dialog v-model="visible" title="工艺变更" width="min(980px, 95vw)" @open="open">
    <div v-loading="busy">
      <el-table v-if="overview?.changes.length" :data="overview.changes" border>
        <el-table-column label="工艺变更" min-width="170">
          <template #default="{ row }">{{ row.previous_name_snapshot }} → {{ row.new_name_snapshot }}</template>
        </el-table-column>
        <el-table-column prop="remaining_quantity_snapshot" label="剩余数量" width="100" />
        <el-table-column label="已加工件处置" min-width="120">
          <template #default="{ row }">{{ dispositions[row.disposition_code as MesProcessDisposition] }} {{ row.disposition_quantity_snapshot }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="145">
          <template #default="{ row }">
            {{
              row.status_code === "approved"
                ? approvedStatuses[row.disposition_code as MesProcessDisposition]
                : statuses[row.status_code] || row.status_code
            }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="变更原因" min-width="115" />
        <el-table-column prop="disposition_note" label="处置记录" min-width="115" />
        <el-table-column label="操作" min-width="160">
          <template #default="{ row }">
            <div class="list-row-actions process-change-actions">
              <el-button v-if="row.repair_order_id" link type="primary" @click="emit('repair', row.repair_order_id)">查看返修</el-button>
              <template v-if="row.status_code === 'approved'">
                <el-button v-if="canManage && row.disposition_code === 'rework'" link type="primary"
                  @click="run(() => act(row.id, 'arrange'))">安排返工</el-button>
                <el-button v-if="canManage && row.disposition_code !== 'reinspect'" link type="primary"
                  @click="run(() => act(row.id, 'apply'))">确认生效</el-button>
                <template v-if="canInspect && row.disposition_code === 'reinspect'">
                  <el-button link type="success" @click="run(() => act(row.id, 'pass'))">复检通过</el-button>
                  <el-button link type="warning" @click="run(() => act(row.id, 'rework'))">转返工</el-button>
                </template>
                <el-button v-if="canManage" link type="danger" @click="run(() => act(row.id, 'cancel'))">取消变更</el-button>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-form v-if="showForm && overview" label-width="110px" class="process-change-form" @submit.prevent="run(submit)">
        <el-form-item label="目标工序" required>
          <el-select v-model="operationId" placeholder="选择要变更的工序" @change="disposition = 'keep'">
            <el-option v-for="op in overview.operations" :key="op.id" :value="op.id" :label="`${op.operation_no} · ${op.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="selected" label="变更数量">
          剩余 {{ selected.remaining }}，已报合格 {{ selected.good }}
        </el-form-item>
        <el-form-item label="新工艺" required>
          <RemoteSelect v-model="processId" :load-options="query => archiveOptions('processes', overview!.org_id, query)"
            placeholder="从工艺档案选择" @select="equipmentId = ''" />
        </el-form-item>
        <el-form-item v-if="processId && Number(selected?.remaining) > 0" label="生产设备">
          <RemoteSelect v-model="equipmentId" :context-key="processId"
            :load-options="query => archiveOptions('equipment', overview!.org_id, query, { applicable_process_id: processId })"
            placeholder="需要机器的工艺须选设备" />
        </el-form-item>
        <el-form-item v-if="Number(selected?.good) > 0" label="已加工件处置" required>
          <el-radio-group v-model="disposition">
            <el-radio v-for="(label, key) in dispositions" :key="key" :value="key">{{ label }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="变更原因" required>
          <el-input v-model="reason" type="textarea" maxlength="1000" />
        </el-form-item>
        <div class="erp-form-actions">
          <el-button v-if="overview.changes.length" :disabled="busy" @click="resetDraft">取消</el-button>
          <el-button native-type="submit" type="primary" :loading="busy">提交工艺变更</el-button>
        </div>
      </el-form>
      <div v-else-if="canSubmit" class="erp-form-actions">
        <el-button type="primary" :disabled="busy" @click="creating = true">发起工艺变更</el-button>
      </div>
      <el-empty v-else-if="overview && !overview.changes.length" description="暂无工艺变更记录" />
    </div>
  </el-dialog>
</template>

<style scoped>
.process-change-actions {
  width: 100%;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.process-change-form {
  margin-top: 20px;
}
</style>
