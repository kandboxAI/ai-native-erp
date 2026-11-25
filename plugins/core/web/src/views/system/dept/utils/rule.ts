import { reactive } from "vue";
import type { FormRules } from "element-plus";

export const formRules = reactive(<FormRules>{
  org_id: [{ required: true, message: "请选择所属组织", trigger: "change" }],
  department_no: [
    { required: true, message: "部门编号为必填项", trigger: "blur" }
  ],
  department_name: [
    { required: true, message: "部门名称为必填项", trigger: "blur" }
  ]
});

export const orgFormRules = reactive(<FormRules>{
  org_no: [{ required: true, message: "组织编号为必填项", trigger: "blur" }],
  org_name: [{ required: true, message: "组织名称为必填项", trigger: "blur" }]
});
