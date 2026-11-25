<script setup lang="ts">
import { computed, ref } from "vue";
import { formRules } from "./utils/rule";
import type { FormProps } from "./utils/types";
import AiTemplates from "./aiTemplates.vue";
import { useUserStoreHook } from "@/store/modules/user";
import { DATA_SCOPE_LABELS } from "@/api/systemRole";

const props = withDefaults(defineProps<FormProps>(), {
  formInline: () => ({
    role_no: "",
    role_name: "",
    description: "",
    data_scope_code: "organization",
    is_active: true,
    is_builtin: false
  })
});

const canManageAiTemplates = computed(() =>
  useUserStoreHook().permissions.includes("system_setting:update")
);
const ruleFormRef = ref();
const newFormInline = ref(props.formInline);
/** 内置管理员（数据范围为全部）的数据范围不可修改 */
const scopeLocked = computed(
  () =>
    Boolean(newFormInline.value.id) &&
    newFormInline.value.is_builtin &&
    newFormInline.value.data_scope_code === "all"
);

function getRef() {
  return ruleFormRef.value;
}

defineExpose({ getRef });
</script>

<template>
  <el-form
    ref="ruleFormRef"
    :model="newFormInline"
    :rules="formRules"
    label-width="90px"
  >
    <el-form-item label="角色名称" prop="role_name">
      <el-input
        v-model="newFormInline.role_name"
        clearable
        placeholder="请输入角色名称"
      />
    </el-form-item>

    <el-form-item label="角色编号" prop="role_no">
      <el-input
        v-model="newFormInline.role_no"
        clearable
        :disabled="newFormInline.is_builtin"
        placeholder="如 reviewer"
      />
    </el-form-item>

    <el-form-item label="数据范围" prop="data_scope_code">
      <el-select
        v-model="newFormInline.data_scope_code"
        class="w-full"
        :disabled="scopeLocked"
      >
        <el-option
          v-for="(label, value) in DATA_SCOPE_LABELS"
          :key="value"
          :label="label"
          :value="value"
        />
      </el-select>
    </el-form-item>

    <el-form-item label="是否启用">
      <el-switch
        v-model="newFormInline.is_active"
        :disabled="newFormInline.is_builtin"
      />
    </el-form-item>

    <el-form-item label="说明">
      <el-input
        v-model="newFormInline.description"
        placeholder="请输入说明"
        type="textarea"
      />
    </el-form-item>
  </el-form>
  <AiTemplates
    v-if="newFormInline.id && canManageAiTemplates"
    :role-id="newFormInline.id"
  />
</template>
