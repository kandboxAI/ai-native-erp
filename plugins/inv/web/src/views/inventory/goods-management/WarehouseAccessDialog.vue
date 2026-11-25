<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getHttpErrorMessage } from "@/utils/http";
import {
  getWarehouseManagementAccess,
  saveWarehouseManagementAccess,
  type WarehouseManagementAccess,
} from "@plugins/inv/web/src/api/inventoryManagement";

const props = defineProps<{ modelValue: boolean; warehouseId: string }>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const access = ref<WarehouseManagementAccess | null>(null);
const selected = ref<string[]>([]);
let sequence = 0;

async function load() {
  const current = ++sequence;
  access.value = null;
  selected.value = [];
  error.value = "";
  loading.value = false;
  if (!props.modelValue || !props.warehouseId) return;
  loading.value = true;
  try {
    const result = await getWarehouseManagementAccess(props.warehouseId);
    if (current !== sequence || !props.modelValue) return;
    if (result.code !== 0) throw new Error(result.message);
    access.value = result.data;
    selected.value = [...result.data.user_ids];
  } catch (reason) {
    if (current === sequence)
      error.value = getHttpErrorMessage(reason, "管理账号加载失败");
  } finally {
    if (current === sequence) loading.value = false;
  }
}
watch(() => [props.modelValue, props.warehouseId], load, { immediate: true });

async function save() {
  if (!access.value || loading.value || saving.value) return;
  const current = sequence;
  const warehouseId = props.warehouseId;
  saving.value = true;
  try {
    const result = await saveWarehouseManagementAccess(warehouseId, {
      expected_updated_at: access.value.expected_updated_at,
      user_ids: [...selected.value],
    });
    if (current !== sequence) return;
    if (result.code !== 0) throw new Error(result.message);
    access.value = result.data;
    ElMessage.success("仓库管理账号已保存");
    emit("update:modelValue", false);
  } catch (reason) {
    if (current === sequence)
      ElMessage.error(
        getHttpErrorMessage(reason, "保存失败，请重新加载后核对"),
      );
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="仓库管理账号"
    width="min(640px, 94vw)"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading">
      <el-alert
        v-if="error"
        type="error"
        :title="error"
        :closable="false"
        show-icon
      />
      <template v-if="access">
        <p>{{ access.warehouse_name }}</p>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="账号的仓储功能权限设为“关联数据范围”时，只能管理明确授权的仓库；仍需分配相应功能权限，且仓库须在账号的组织范围内。"
        />
        <el-form class="erp-query-form access-form" label-position="top">
          <el-form-item label="管理账号">
            <el-select
              v-model="selected"
              multiple
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              :disabled="saving"
              placeholder="选择教务或其他仓库管理账号"
              style="width: 100%"
            >
              <el-option
                v-for="user in access.users"
                :key="user.id"
                :value="user.id"
                :label="
                  user.display_name +
                  (user.is_recommended ? '（责任部门或默认保管人推荐）' : '') +
                  (user.is_available ? '' : '（已失效，请移除）')
                "
                :disabled="!user.is_available"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <p>
          推荐账号须勾选并保存后才获得仓库授权，不会自动授权部门全员。撤销保留历史，教师可申领的组织仍通过“申领范围”配置。
        </p>
        <p>
          全量、组织等其他数据范围沿用原规则；如需账号仅查看指定仓库，请将相关权限统一设为关联数据范围。
        </p>
      </template>
    </div>
    <template #footer>
      <div class="erp-form-actions">
        <div class="erp-form-actions__primary">
          <el-button :disabled="loading || saving" @click="load"
            >重新加载</el-button
          >
          <el-button
            :disabled="saving"
            @click="emit('update:modelValue', false)"
            >取消</el-button
          >
          <el-button
            type="primary"
            :loading="saving"
            :disabled="loading || !access"
            @click="save"
            >保存管理账号</el-button
          >
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.access-form {
  margin-top: 20px;
}
p {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
</style>
