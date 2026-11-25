<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import {
  getWarehouseRequisitionScope,
  saveWarehouseRequisitionScope,
  type WarehouseRequisitionScope,
} from "@plugins/inv/web/src/api/inventoryManagement";

const props = defineProps<{ modelValue: boolean; warehouseId: string }>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const scope = ref<WarehouseRequisitionScope | null>(null);
const selected = ref<string[]>([]);
let sequence = 0;
const choices = computed(() => {
  const rows = scope.value?.organizations || [];
  const byId = new Map(rows.map((row) => [row.id, row]));
  return rows.map((row) => {
    const labels = [row.org_name];
    const seen = new Set([row.id]);
    let parent = row.parent_id ? byId.get(row.parent_id) : undefined;
    while (parent && !seen.has(parent.id)) {
      labels.unshift(parent.org_name);
      seen.add(parent.id);
      parent = parent.parent_id ? byId.get(parent.parent_id) : undefined;
    }
    return {
      ...row,
      label:
        labels.join(" / ") + (row.is_available ? "" : "（已失效，请移除）"),
    };
  });
});
async function load() {
  const current = ++sequence;
  scope.value = null;
  selected.value = [];
  error.value = "";
  loading.value = false;
  if (!props.modelValue || !props.warehouseId) return;
  loading.value = true;
  try {
    const result = await getWarehouseRequisitionScope(props.warehouseId);
    if (current !== sequence || !props.modelValue) return;
    if (result.code !== 0) throw new Error(result.message);
    scope.value = result.data;
    selected.value = [...result.data.recipient_org_ids];
  } catch (reason) {
    if (current === sequence)
      error.value = getHttpErrorMessage(reason, "申领范围加载失败");
  } finally {
    if (current === sequence) loading.value = false;
  }
}
watch(() => [props.modelValue, props.warehouseId], load, { immediate: true });
async function save() {
  if (!scope.value || loading.value || saving.value) return;
  saving.value = true;
  try {
    const result = await saveWarehouseRequisitionScope(props.warehouseId, {
      expected_updated_at: scope.value.expected_updated_at,
      recipient_org_ids: [...selected.value],
    });
    if (result.code !== 0) throw new Error(result.message);
    scope.value = result.data;
    ElMessage.success("仓库申领范围已保存");
    emit("update:modelValue", false);
  } catch (reason) {
    ElMessage.error(getHttpErrorMessage(reason, "保存失败，请重新加载后核对"));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="仓库申领范围"
    width="min(640px, 94vw)"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="scope-content">
      <el-alert
        v-if="error"
        type="error"
        :title="error"
        :closable="false"
        show-icon
      />
      <template v-if="scope">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="仓库">{{
            scope.warehouse_name
          }}</el-descriptions-item>
          <el-descriptions-item label="所属组织">{{
            scope.owner_org_name
          }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="scope-hint"
          title="所选组织中具有物资申领权限的成员，可查看该仓库的可领物资及可用数量并提交申请。组织按成员当前主组织精确匹配，不自动包含下级组织。"
        />
        <el-form label-position="top" class="scope-form">
          <el-form-item label="额外开放申领的组织">
            <el-select
              v-model="selected"
              multiple
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="4"
              :disabled="saving"
              placeholder="选择校区或组织，可搜索并多选"
              style="width: 100%"
            >
              <el-option
                v-for="org in choices"
                :key="org.id"
                :value="org.id"
                :label="org.label"
                :disabled="!org.is_available"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <p class="scope-note">
          仅列出仓库所属组织下的有效组织。同组织成员沿用现有规则；留空表示不额外向其他组织开放。
        </p>
        <p class="scope-note">
          共享申领不增加审批、发放、库存流水或成本查看权限。移除组织后，其成员不能再发起新申请；已提交申请继续按原流程办理。
        </p>
      </template>
    </div>
    <template #footer>
      <el-button :disabled="loading || saving" @click="load"
        >重新加载</el-button
      >
      <el-button :disabled="saving" @click="emit('update:modelValue', false)"
        >取消</el-button
      >
      <el-button
        type="primary"
        :disabled="loading || !scope"
        :loading="saving"
        @click="save"
        >保存申领范围</el-button
      >
    </template>
  </el-dialog>
</template>
<style scoped>
.scope-content {
  min-height: 120px;
}
.scope-hint,
.scope-form {
  margin-top: 20px;
}
.scope-note {
  margin: 12px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}
</style>
