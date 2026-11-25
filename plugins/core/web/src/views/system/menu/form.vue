<script setup lang="ts">
import { ref } from "vue";
import ReCol from "@/components/ReCol";
import { formRules } from "./utils/rule";
import type { FormProps } from "./utils/types";
import { IconSelect } from "@/components/ReIcon";
import Segmented from "@/components/ReSegmented";
import {
  activeOptions,
  menuTypeOptions,
  openTargetOptions,
  visibleOptions
} from "./utils/enums";

const props = withDefaults(defineProps<FormProps>(), {
  formInline: () => ({
    menu_key: "",
    menu_name: "",
    menu_type_code: "menu",
    parent_id: null,
    path: "",
    component: "",
    route_redirect: "",
    route_meta: "{}",
    flex_form: {},
    icon: "",
    permission_key: "",
    is_external: false,
    external_url: "",
    open_target_code: "self",
    sort_no: 0,
    is_visible: true,
    is_active: true,
    remark: "",
    higherMenuOptions: [],
    permissionOptions: []
  })
});

const ruleFormRef = ref();
const newFormInline = ref(props.formInline);

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
        <el-form-item label="菜单类型">
          <Segmented
            v-model="newFormInline.menu_type_code"
            :options="menuTypeOptions"
          />
        </el-form-item>
      </re-col>

      <re-col>
        <el-form-item label="上级菜单">
          <el-cascader
            v-model="newFormInline.parent_id"
            class="w-full"
            :options="newFormInline.higherMenuOptions"
            :props="{
              value: 'id',
              label: 'menu_name',
              emitPath: false,
              checkStrictly: true
            }"
            clearable
            filterable
            placeholder="不选表示顶级菜单"
          />
        </el-form-item>
      </re-col>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="菜单名称" prop="menu_name">
          <el-input
            v-model="newFormInline.menu_name"
            clearable
            placeholder="请输入菜单名称"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="菜单标识" prop="menu_key">
          <el-input
            v-model="newFormInline.menu_key"
            clearable
            :disabled="Boolean(newFormInline.id)"
            placeholder="对应前端路由名称，创建后不可修改"
          />
        </el-form-item>
      </re-col>

      <template v-if="newFormInline.menu_type_code !== 'button'">
        <re-col :value="12" :xs="24" :sm="24">
          <el-form-item label="路由路径">
            <el-input
              v-model="newFormInline.path"
              clearable
              placeholder="如 /system/user/index"
            />
          </el-form-item>
        </re-col>
        <re-col
          v-if="newFormInline.menu_type_code === 'menu'"
          :value="12"
          :xs="24"
          :sm="24"
        >
          <el-form-item label="组件路径">
            <el-input
              v-model="newFormInline.component"
              clearable
              placeholder="如 system/user/index"
            />
          </el-form-item>
        </re-col>
        <re-col :value="12" :xs="24" :sm="24">
          <el-form-item label="重定向">
            <el-input
              v-model="newFormInline.route_redirect"
              clearable
              placeholder="如 /education/academic-terms"
            />
          </el-form-item>
        </re-col>
        <re-col :value="12" :xs="24" :sm="24">
          <el-form-item label="菜单图标">
            <IconSelect v-model="newFormInline.icon" class="w-full" />
          </el-form-item>
        </re-col>
      </template>

      <re-col v-if="newFormInline.menu_type_code !== 'button'">
        <el-form-item label="页面参数">
          <el-input
            v-model="newFormInline.route_meta"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            placeholder='JSON，如 {"activePath":"/applications"}'
          />
        </el-form-item>
      </re-col>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="所需权限">
          <el-select
            v-model="newFormInline.permission_key"
            class="w-full"
            clearable
            filterable
            placeholder="拥有该权限才可访问（可不选）"
          >
            <el-option
              v-for="item in newFormInline.permissionOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
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

      <template v-if="newFormInline.menu_type_code === 'menu'">
        <re-col :value="12" :xs="24" :sm="24">
          <el-form-item label="是否外链">
            <el-switch
              v-model="newFormInline.is_external"
              inline-prompt
              active-text="是"
              inactive-text="否"
            />
          </el-form-item>
        </re-col>
        <re-col v-if="newFormInline.is_external" :value="12" :xs="24" :sm="24">
          <el-form-item label="打开方式">
            <Segmented
              v-model="newFormInline.open_target_code"
              :options="openTargetOptions"
            />
          </el-form-item>
        </re-col>
        <re-col v-if="newFormInline.is_external">
          <el-form-item label="外链地址">
            <el-input
              v-model="newFormInline.external_url"
              clearable
              placeholder="https://"
            />
          </el-form-item>
        </re-col>
      </template>

      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="菜单显示">
          <Segmented
            v-model="newFormInline.is_visible"
            :options="visibleOptions"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="菜单状态">
          <Segmented
            v-model="newFormInline.is_active"
            :options="activeOptions"
          />
        </el-form-item>
      </re-col>
      <re-col>
        <el-form-item label="备注">
          <el-input v-model="newFormInline.remark" type="textarea" />
        </el-form-item>
      </re-col>
    </el-row>
  </el-form>
</template>
