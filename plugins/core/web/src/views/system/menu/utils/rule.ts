import { reactive } from "vue";
import type { FormRules } from "element-plus";

/** 菜单表单校验 */
export const formRules = reactive(<FormRules>{
  menu_key: [{ required: true, message: "菜单标识为必填项", trigger: "blur" }],
  menu_name: [{ required: true, message: "菜单名称为必填项", trigger: "blur" }]
});
