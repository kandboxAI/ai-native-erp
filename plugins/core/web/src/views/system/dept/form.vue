<script setup lang="ts">
import { computed, ref } from "vue";
import ReCol from "@/components/ReCol";
import { formRules } from "./utils/rule";
import type { DeptOption, FormProps } from "./utils/types";
import { usePublicHooks } from "../hooks";

const props = withDefaults(defineProps<FormProps>(), {
  formInline: () => ({
    org_id: "",
    placement_label: "",
    department_no: "",
    department_name: "",
    parent_id: null,
    manager_user_id: null,
    sort_no: 0,
    is_active: true,
    remark: "",
    higherDeptOptions: [],
    managerOptions: []
  })
});

const ruleFormRef = ref();
const { switchStyle } = usePublicHooks();
const newFormInline = ref(props.formInline);

/** 上级部门只能选同一组织的部门，且不能选自己 */
const parentOptions = computed(() => {
  const strip = (nodes: DeptOption[]): DeptOption[] =>
    nodes
      .filter(node => node.id !== newFormInline.value.id)
      .map(node => ({ ...node, children: strip(node.children ?? []) }));
  return strip(newFormInline.value.higherDeptOptions);
});

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
    <el-row :gutter="30">
      <re-col>
        <el-form-item label="所属组织" prop="org_id">
          <el-input :model-value="newFormInline.placement_label" disabled />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="上级部门">
          <el-cascader
            v-model="newFormInline.parent_id"
            class="w-full"
            :options="parentOptions as any[]"
            :props="{
              value: 'id',
              label: 'department_name',
              emitPath: false,
              checkStrictly: true
            }"
            clearable
            filterable
            placeholder="不选表示顶级部门"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="部门编号" prop="department_no">
          <el-input
            v-model="newFormInline.department_no"
            clearable
            placeholder="同一组织内唯一"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="部门名称" prop="department_name">
          <el-input
            v-model="newFormInline.department_name"
            clearable
            placeholder="请输入部门名称"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="负责人">
          <el-select
            v-model="newFormInline.manager_user_id"
            class="w-full"
            clearable
            filterable
            placeholder="请选择负责人"
          >
            <el-option
              v-for="user in newFormInline.managerOptions"
              :key="user.id"
              :label="user.label"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="排序">
          <el-input-number
            v-model="newFormInline.sort_no"
            class="w-full!"
            :min="0"
            :max="9999"
            controls-position="right"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="部门状态">
          <el-switch
            v-model="newFormInline.is_active"
            inline-prompt
            active-text="启用"
            inactive-text="停用"
            :style="switchStyle"
          />
        </el-form-item>
      </re-col>
      <re-col>
        <el-form-item label="备注">
          <el-input
            v-model="newFormInline.remark"
            placeholder="请输入备注信息"
            type="textarea"
          />
        </el-form-item>
      </re-col>
    </el-row>
  </el-form>
</template>
