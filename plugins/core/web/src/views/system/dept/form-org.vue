<script setup lang="ts">
import { ref } from "vue";
import ReCol from "@/components/ReCol";
import { orgFormRules } from "./utils/rule";
import type { OrgFormProps } from "./utils/types";
import { usePublicHooks } from "../hooks";

const TYPE_LABEL: Record<string, string> = {
  group: "集团",
  school: "学校",
  organization: "组织"
};

const props = withDefaults(defineProps<OrgFormProps>(), {
  formInline: () => ({
    org_no: "",
    org_name: "",
    org_type_code: "school",
    parent_label: "",
    contact_name: "",
    contact_phone: "",
    province: "",
    city: "",
    district: "",
    address: "",
    sort_no: 0,
    is_active: true,
    remark: ""
  })
});

const ruleFormRef = ref();
const { switchStyle } = usePublicHooks();
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
    :rules="orgFormRules"
    label-width="90px"
  >
    <el-row :gutter="30">
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="组织类型">
          <el-input
            :model-value="TYPE_LABEL[newFormInline.org_type_code] || '组织'"
            disabled
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="上级组织">
          <el-input
            :model-value="newFormInline.parent_label || '无（根组织）'"
            disabled
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="组织编号" prop="org_no">
          <el-input
            v-model="newFormInline.org_no"
            clearable
            placeholder="请输入组织编号"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="组织名称" prop="org_name">
          <el-input
            v-model="newFormInline.org_name"
            clearable
            placeholder="请输入组织名称"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="联系人">
          <el-input
            v-model="newFormInline.contact_name"
            clearable
            placeholder="选填"
          />
        </el-form-item>
      </re-col>
      <re-col :value="12" :xs="24" :sm="24">
        <el-form-item label="联系电话">
          <el-input
            v-model="newFormInline.contact_phone"
            clearable
            placeholder="选填"
          />
        </el-form-item>
      </re-col>
      <re-col :value="8" :xs="24" :sm="8">
        <el-form-item label="省">
          <el-input v-model="newFormInline.province" clearable />
        </el-form-item>
      </re-col>
      <re-col :value="8" :xs="24" :sm="8">
        <el-form-item label="市">
          <el-input v-model="newFormInline.city" clearable />
        </el-form-item>
      </re-col>
      <re-col :value="8" :xs="24" :sm="8">
        <el-form-item label="区县">
          <el-input v-model="newFormInline.district" clearable />
        </el-form-item>
      </re-col>
      <re-col>
        <el-form-item label="详细地址">
          <el-input v-model="newFormInline.address" clearable />
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
        <el-form-item label="状态">
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
          <el-input v-model="newFormInline.remark" type="textarea" />
        </el-form-item>
      </re-col>
    </el-row>
  </el-form>
</template>
