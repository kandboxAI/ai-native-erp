<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getUserPositionOptions,
  type UserPositionOption
} from "@/api/systemUserProfile";
import { getHttpErrorMessage } from "@/utils/http";
import ReCol from "@/components/ReCol";
import { formRules } from "../utils/rule";
import type { FormProps, OrgDeptNode } from "../utils/types";
import { usePublicHooks } from "../../hooks";

const props = withDefaults(defineProps<FormProps>(), {
  formInline: () => ({
    title: "新增",
    email: "",
    mobile: "",
    password: "",
    full_name: "",
    display_name: "",
    org_id: "",
    org_access_mode_code: "primary_only",
    org_ids: [],
    department_id: null,
    role_ids: [],
    position_ids: [],
    is_active: true,
    orgOptions: [],
    deptTree: [],
    roleOptions: []
  })
});

const accessModeOptions = [
  { value: "primary_only", label: "仅所属组织" },
  { value: "assigned", label: "授权的组织" },
  { value: "all", label: "全部组织" }
];

const ruleFormRef = ref();
const { switchStyle } = usePublicHooks();
const newFormInline = ref(props.formInline);
const isCreate = computed(() => newFormInline.value.title === "新增");

/** 所属组织下的部门树 */
const deptOptions = computed(() => {
  const find = (nodes: OrgDeptNode[]): OrgDeptNode | undefined => {
    for (const node of nodes) {
      if (node.node_type === "org" && node.id === newFormInline.value.org_id) {
        return node;
      }
      const hit = find(node.children ?? []);
      if (hit) return hit;
    }
    return undefined;
  };
  const org = find(newFormInline.value.deptTree);
  return (org?.children ?? []).filter(node => node.node_type === "dept");
});

function onOrgChange() {
  newFormInline.value.department_id = null;
  newFormInline.value.position_ids = [];
}

const positionOptions = ref<UserPositionOption[]>([]);
const positionsLoading = ref(false);
watch(
  () => newFormInline.value.org_id,
  async (orgId, _oldId, onCleanup) => {
    let current = true;
    onCleanup(() => {
      current = false;
    });
    positionOptions.value = [];
    positionsLoading.value = !!orgId;
    if (!orgId) return;
    try {
      const result = await getUserPositionOptions(orgId);
      if (result.code !== 0) throw new Error(result.message);
      if (current) positionOptions.value = result.data;
    } catch (error) {
      if (current)
        ElMessage.error(getHttpErrorMessage(error, "岗位选项加载失败"));
    } finally {
      if (current) positionsLoading.value = false;
    }
  },
  { immediate: true }
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
    label-width="96px"
  >
    <el-row :gutter="30">
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="姓名" prop="full_name">
          <el-input
            v-model="newFormInline.full_name"
            clearable
            placeholder="请输入姓名"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="显示名称" prop="display_name">
          <el-input
            v-model="newFormInline.display_name"
            clearable
            placeholder="不填则与姓名相同"
          />
        </el-form-item>
      </re-col>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="登录邮箱" prop="email">
          <el-input
            v-model="newFormInline.email"
            clearable
            :disabled="!isCreate"
            placeholder="邮箱、手机号至少填一个"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="手机号" prop="mobile">
          <el-input
            v-model="newFormInline.mobile"
            clearable
            :disabled="!isCreate"
            :placeholder="isCreate ? '请输入手机号' : '手机号暂不允许修改'"
          />
        </el-form-item>
      </re-col>

      <re-col v-if="isCreate" :value="12" :xs="24" :sm="24">
        <el-form-item label="初始密码" prop="password">
          <el-input
            v-model="newFormInline.password"
            clearable
            show-password
            placeholder="请输入初始密码"
          />
        </el-form-item>
      </re-col>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="所属组织" prop="org_id">
          <el-select
            v-model="newFormInline.org_id"
            class="w-full"
            filterable
            placeholder="请选择组织"
            @change="onOrgChange"
          >
            <el-option
              v-for="org in newFormInline.orgOptions"
              :key="org.id"
              :label="org.org_name"
              :value="org.id"
            />
          </el-select>
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="所属部门">
          <el-cascader
            v-model="newFormInline.department_id"
            class="w-full"
            :options="deptOptions as any[]"
            :props="{
              value: 'id',
              label: 'name',
              emitPath: false,
              checkStrictly: true
            }"
            clearable
            filterable
            placeholder="请选择部门"
          />
        </el-form-item>
      </re-col>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="组织访问">
          <el-select
            v-model="newFormInline.org_access_mode_code"
            class="w-full"
          >
            <el-option
              v-for="item in accessModeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </re-col>
      <re-col
        v-if="newFormInline.org_access_mode_code === 'assigned'"
        :value="12"
        :xs="24"
        :sm="24"
      >
        <el-form-item label="授权组织">
          <el-select
            v-model="newFormInline.org_ids"
            class="w-full"
            multiple
            filterable
            placeholder="可访问的其他组织"
          >
            <el-option
              v-for="org in newFormInline.orgOptions"
              :key="org.id"
              :label="org.org_name"
              :value="org.id"
            />
          </el-select>
        </el-form-item>
      </re-col>

      <re-col>
        <el-form-item label="岗位">
          <el-select
            v-model="newFormInline.position_ids"
            class="w-full"
            multiple
            filterable
            clearable
            :loading="positionsLoading"
            :disabled="!newFormInline.org_id"
            placeholder="请选择岗位"
          >
            <el-option
              v-for="position in positionOptions"
              :key="position.id"
              :value="position.id"
              :label="`${position.department_name} / ${position.name}${position.is_active ? '' : '（已停用）'}`"
              :disabled="!position.is_active"
            />
          </el-select>
        </el-form-item>
      </re-col>

      <re-col>
        <el-form-item label="角色">
          <el-select
            v-model="newFormInline.role_ids"
            class="w-full"
            multiple
            filterable
            clearable
            placeholder="请选择角色"
          >
            <el-option
              v-for="role in newFormInline.roleOptions"
              :key="role.id"
              :label="role.role_name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
      </re-col>

      <re-col v-if="isCreate" :value="12" :xs="24" :sm="24">
        <el-form-item label="用户状态">
          <el-switch
            v-model="newFormInline.is_active"
            inline-prompt
            active-text="启用"
            inactive-text="停用"
            :style="switchStyle"
          />
        </el-form-item>
      </re-col>
    </el-row>
  </el-form>
</template>
