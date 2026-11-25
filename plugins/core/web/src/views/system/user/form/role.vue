<script setup lang="ts">
import { ref } from "vue";
import ReCol from "@/components/ReCol";
import type { RoleFormProps } from "../utils/types";

const props = withDefaults(defineProps<RoleFormProps>(), {
  formInline: () => ({
    display_name: "",
    roleOptions: [],
    ids: []
  })
});

const newFormInline = ref(props.formInline);
</script>

<template>
  <el-form :model="newFormInline">
    <el-row :gutter="30">
      <re-col>
        <el-form-item label="用户" prop="display_name">
          <el-input v-model="newFormInline.display_name" disabled />
        </el-form-item>
      </re-col>
      <re-col>
        <el-form-item label="角色列表" prop="ids">
          <el-select
            v-model="newFormInline.ids"
            placeholder="请选择"
            class="w-full"
            clearable
            multiple
            filterable
          >
            <el-option
              v-for="item in newFormInline.roleOptions"
              :key="item.id"
              :value="item.id"
              :label="item.role_name"
            >
              {{ item.role_name }}（{{ item.role_no }}）
            </el-option>
          </el-select>
        </el-form-item>
      </re-col>
    </el-row>
  </el-form>
</template>
